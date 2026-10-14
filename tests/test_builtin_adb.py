"""The app always prepares its bundled ADB off the GUI thread."""
import hashlib
import json
from pathlib import Path
import threading

import pytest
from PySide6.QtCore import QTimer

import voyah_manager as v


@pytest.fixture
def builtin_window(qtbot, monkeypatch, tmp_path):
    native_settings = v.QSettings
    settings = native_settings(str(tmp_path / 'settings.ini'), native_settings.Format.IniFormat)
    external = tmp_path / 'old-external-adb.exe'; external.write_bytes(b'not the bundled tool')
    settings.setValue('adb_path', str(external)); settings.setValue('language', 'ru')
    monkeypatch.setattr(v, 'DATA_DIR', tmp_path / 'profile')
    monkeypatch.setattr(v, 'BOOTSTRAP_REPOSITORY', '')
    monkeypatch.setattr(v, 'QSettings', lambda *args, **kwargs: settings)
    monkeypatch.setattr(v.Tools, 'find_adb', lambda *args: pytest.fail('External ADB discovery must never run'))
    windows = []
    def create():
        window = v.MainWindow(demo=True, smoke=True); windows.append(window); qtbot.addWidget(window)
        window.poll.stop(); window.show(); return window
    yield create, external
    for window in windows:
        window.close()
    qtbot.wait(50)


def test_cold_start_uses_verified_bundle_without_blocking_ui(builtin_window, qtbot, monkeypatch, tmp_path):
    create, external = builtin_window
    entered = threading.Event(); release = threading.Event(); calls = []; gui_thread = threading.get_ident()
    cache = tmp_path / 'verified-cache' / 'adb.exe'; cache.parent.mkdir(); cache.write_bytes(b'bundled test tool')
    def prepare(tools):
        calls.append(threading.get_ident()); entered.set()
        assert release.wait(5), 'Test did not release preparation worker'
        return str(cache)
    monkeypatch.setattr(v.Tools, 'bundled_adb', prepare)
    window = create()
    try:
        assert window.adb_path == '' and str(external) not in window.adb_label.text()
        qtbot.waitUntil(entered.is_set, timeout=2000)
        assert window.adb_preparing and window.busy and window.adb_path == ''
        ticks = []; timer = QTimer(window); timer.timeout.connect(lambda: ticks.append(True)); timer.start(10)
        qtbot.waitUntil(lambda: len(ticks) >= 3, timeout=1000)
        assert calls == [calls[0]] and calls[0] != gui_thread
        window.use_bundled(); assert len(calls) == 1
    finally:
        release.set()
    qtbot.waitUntil(lambda: window.adb_path == str(cache) and not window.busy, timeout=3000)
    qtbot.waitUntil(lambda: window.profile.api == 30, timeout=5000)
    assert not window.adb_preparing and not window.adb_error
    assert window.adb_label.text() == 'Встроенное средство связи'
    window.use_bundled(); qtbot.wait(30)
    assert len(calls) == 1 and window.adb_path != str(external)


def test_settings_have_no_adb_picker_or_header_navigation(builtin_window, qtbot, monkeypatch, tmp_path):
    create, external = builtin_window
    cache = tmp_path / 'adb.exe'; cache.write_bytes(b'test bundled tool')
    monkeypatch.setattr(v.Tools, 'bundled_adb', lambda tools: str(cache))
    monkeypatch.setattr(v.QFileDialog, 'getOpenFileName', lambda *args, **kwargs: pytest.fail('No ADB file dialog is allowed'))
    window = create(); qtbot.waitUntil(lambda: window.adb_path == str(cache), timeout=3000)
    forbidden = {'Выбрать ADB', 'Встроенный ADB', 'Назад', 'Домой', 'Недавние', 'Скриншот'}
    labels = {button.text() for button in window.findChildren(v.QPushButton)}
    names = {button.accessibleName() for button in window.findChildren(v.QPushButton)}
    assert not forbidden.intersection(labels | names)
    assert window.nav_buttons == []
    window.choose_adb(); assert window.adb_path == str(cache)
    window.language.setCurrentIndex(1)
    assert window.adb_label.text() == 'Built-in connection tool'
    assert str(cache) not in window.adb_label.text()
    for method in ('keyevent', 'screenshot', 'capture_screen'): assert callable(getattr(window, method))


def test_bundled_tool_failure_never_falls_back_to_saved_external_path(builtin_window, qtbot, monkeypatch):
    create, external = builtin_window
    def damaged(tools): raise ValueError('Bundled ADB integrity check failed')
    monkeypatch.setattr(v.Tools, 'bundled_adb', damaged)
    monkeypatch.setattr(v.QFileDialog, 'getOpenFileName', lambda *args, **kwargs: pytest.fail('Failure must not open a file picker'))
    window = create()
    qtbot.waitUntil(lambda: bool(window.adb_error) and not window.busy, timeout=3000)
    assert window.adb_path == '' and not window.adb_preparing
    assert window.adb_label.text() == 'Встроенное средство связи недоступно'
    assert 'Не удалось подготовить встроенное средство связи' in window.notice_label.text()
    assert window.target is None and window.profile.api == 0
    assert str(external) not in window.adb_label.text()


def test_bundle_cache_is_versioned_and_corrupt_files_are_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(v, 'DATA_DIR', tmp_path / 'profile')
    base = tmp_path / 'resources'; (base / 'adb').mkdir(parents=True)
    payloads = {'adb/adb.exe': b'correct-executable', 'adb/AdbWinApi.dll': b'correct-library'}
    manifest = {}
    for name, payload in payloads.items():
        (base / name).write_bytes(payload); manifest[name] = hashlib.sha256(payload).hexdigest()
    (base / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    tools = v.Tools(); tools.base = base
    executable = Path(tools.bundled_adb())
    assert executable.parent.name == manifest['adb/adb.exe'][:16]
    assert executable.read_bytes() == payloads['adb/adb.exe']
    executable.write_bytes(b'corrupted cache')
    assert tools.bundled_adb() == str(executable)
    assert executable.read_bytes() == payloads['adb/adb.exe']
    assert (executable.parent / 'AdbWinApi.dll').read_bytes() == payloads['adb/AdbWinApi.dll']
    executable.unlink(); (base / 'adb' / 'adb.exe').write_bytes(b'corrupted bundle')
    with pytest.raises(ValueError, match='integrity'): tools.bundled_adb()
