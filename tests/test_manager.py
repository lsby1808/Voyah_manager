import json
import shlex
import stat
import sys
import threading
import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import voyah_manager as v


@pytest.mark.parametrize('raw, expected', [
    ('192.168.43.1', '192.168.43.1:5555'), ('192.168.43.1:5578', '192.168.43.1:5578'),
    ('[2001:db8::1]:5578', '[2001:db8::1]:5578'), ('2001:db8::1', '[2001:db8::1]:5555')])
def test_endpoints(raw, expected): assert v.normalize_endpoint(raw) == expected

@pytest.mark.parametrize('bad', ['1.2.3.999', 'localhost;reboot', '1.2.3.4:0', '1.2.3.4:65536', '', '[::1]:x'])
def test_bad_endpoints(bad):
    with pytest.raises(ValueError): v.normalize_endpoint(bad)


def test_device_routing():
    text = 'List of devices attached\nABC device usb:1-2 model:VOYAH_Free\nXYZ unauthorized usb:1-3\n192.168.43.1:5578 offline\nemulator-5554 device product:sdk\n'
    devices = v.parse_devices(text)
    assert [d['state'] for d in devices] == ['device', 'unauthorized', 'offline', 'device']
    assert devices[0]['usb'] and not devices[2]['usb'] and not devices[3]['usb']
    assert v.Target('ABC', use_d=True).args() == ['-d']
    assert v.Target('XYZ').args() == ['-s', 'XYZ']


@pytest.mark.parametrize('activity_marker', ['mResumedActivity:', 'mFocusedActivity:', 'topResumedActivity='])
def test_three_display_parser(activity_marker):
    activity = '\n'.join(f'Display #{i}\n {activity_marker} ActivityRecord{{a u0 com.example.app{i}/.MainActivity t{i}}}' for i in range(3))
    window = 'Display #1\n mCurrentFocus=Window{b u0 com.real.front/.Screen}\n'
    parsed = v.parse_screens(window, activity)
    assert set(parsed) == {0, 1, 2}
    assert parsed[1] == {'package':'com.real.front', 'activity':'.Screen', 'component':'com.real.front/.Screen'}
    assert v.parse_screens('mCurrentFocus=null', '') == {}


def test_log_categories_overlap():
    lines = 'START u0 cmp=a\nMCU KeyEvent assistant\nstartService voice\nam_broadcast x\nunrelated'
    launches, buttons, services = v.classify_capture(lines)
    assert len(launches) == 1 and len(buttons) == 2 and len(services) == 2


def test_toybox_listing_unicode_spaces_links():
    text = 'total 4\ndrwxr-xr-x 2 0 0 4096 2026-10-14 10:12 .\n-rw-rw---- 1 1023 1023 128 2026-10-14 12:30 Тест с пробелом.txt\ndrwxrwx--- 2 1023 1023 4096 2026-10-14 13:00 Download\nlrwxrwxrwx 1 0 0 12 2026-10-14 13:27 ссылка -> /sdcard/Download'
    rows = v.parse_listing(text)
    assert len(rows) == 3 and rows[0]['directory']
    assert next(e for e in rows if e['symlink'])['link'] == '/sdcard/Download'
    assert next(e for e in rows if e['size'] == 128)['name'] == 'Тест с пробелом.txt'


@pytest.mark.parametrize('name', ['папка с пробелом', "x'; reboot; echo '", 'quoted"file', '-rf'])
def test_remote_argument_injection_is_quoted(name):
    args = ['rm', '-rf', '--', '/sdcard/' + name]
    assert shlex.split(v.remote_command(args)) == args
    assert v.valid_name(name)


@pytest.mark.parametrize('name', ['.', '..', '', 'a/b', 'a\nb', 'a\x00b'])
def test_rejected_names(name): assert not v.valid_name(name)


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'C:/escape', 'a\\..\\escape'])
def test_zip_traversal_rejected(tmp_path, name):
    archive = tmp_path / 'bad.xapk'
    with zipfile.ZipFile(archive, 'w') as z: z.writestr(name, b'bad')
    with pytest.raises(ValueError, match='небезопасный'): v.safe_extract(archive, tmp_path / 'out')
    assert not (tmp_path / 'escape').exists()


def test_zip_symlink_and_cancel(tmp_path):
    archive = tmp_path / 'link.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        i = zipfile.ZipInfo('link'); i.external_attr = (stat.S_IFLNK | 0o777) << 16; z.writestr(i, '/etc/passwd')
    with pytest.raises(ValueError): v.safe_extract(archive, tmp_path / 'out')
    event = threading.Event(); event.set()
    with pytest.raises(InterruptedError): v.safe_extract(archive, tmp_path / 'out', event)


def test_zip_corruption(tmp_path):
    path = tmp_path / 'bad.zip'; path.write_bytes(b'bad')
    with pytest.raises(ValueError, match='повреждённый'): v.safe_extract(path, tmp_path / 'out')


def test_safe_xapk_extraction(tmp_path):
    archive = tmp_path / 'app.xapk'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('base.apk', b'apk'); z.writestr('Android/obb/com.example.app/main.1.com.example.app.obb', b'obb')
    extracted = v.safe_extract(archive, tmp_path / 'out')
    assert len(extracted) == 2 and all(p.exists() for p in extracted)


def test_apk_metadata_and_dependencies():
    base = v.parse_badging(Path('base.apk'), "package: name='com.example.app' versionCode='42'\nsdkVersion:'28'\nnative-code: 'arm64-v8a'\n")
    split = v.parse_badging(Path('split.apk'), "package: name='com.example.app' versionCode='42' split='config.ru'\nsdkVersion:'28'\n")
    v.validate_apks([base, split], 28)
    with pytest.raises(ValueError, match='новую'): v.validate_apks([base], 27)
    with pytest.raises(ValueError, match='base'): v.validate_apks([split], 30)
    split.requires = ['feature']
    with pytest.raises(ValueError, match='зависимости'): v.validate_apks([base, split], 30)
    split.version = '43'
    with pytest.raises(ValueError, match='versionCode'): v.validate_apks([base, split], 30)


@pytest.mark.parametrize('text', ['Failure [INSTALL_FAILED_OLDER_SDK]', 'Error: bad package', 'java.lang.SecurityException: denial', '/system/bin/sh: bad: not found', 'rm: /system/x: Permission denied'])
def test_semantic_failure(text): assert v.semantic_error(text)


def test_install_error_localized():
    assert 'minSdk' in v.explain_error('Failure [INSTALL_FAILED_OLDER_SDK]')
    assert v.tr(v.explain_error('Failure [INSTALL_FAILED_MISSING_SPLIT]'), 'en') == 'Required split components are missing.'


def test_process_is_async_and_keeps_ui_responsive(qtbot):
    runner = v.Runner(); results = []; ticks = []; timer = QTimer(); timer.timeout.connect(lambda: ticks.append(1)); timer.start(10)
    job = runner.run(sys.executable, ['-c', 'import time; print("begin",flush=True); time.sleep(.35); print("done")'], results.append, timeout=2000)
    qtbot.waitUntil(lambda: bool(results), timeout=5000); timer.stop()
    assert results[0].ok and b'done' in results[0].stdout and len(ticks) >= 15
    assert not runner.jobs


def test_process_timeout_cancel_and_zero_exit_failure(qtbot):
    runner = v.Runner(); results = []
    runner.run(sys.executable, ['-c', 'import time; time.sleep(10)'], results.append, timeout=80)
    qtbot.waitUntil(lambda: len(results) == 1, timeout=3000)
    assert results[0].timed_out and not results[0].ok
    job = runner.run(sys.executable, ['-c', 'import time; time.sleep(10)'], results.append, timeout=0)
    QTimer.singleShot(60, job.cancel); qtbot.waitUntil(lambda: len(results) == 2, timeout=3000)
    assert results[1].cancelled
    runner.run(sys.executable, ['-c', 'print("Failure [INSTALL_FAILED_OLDER_SDK]")'], results.append)
    qtbot.waitUntil(lambda: len(results) == 3, timeout=3000)
    assert results[2].code == 0 and not results[2].ok


def test_process_binary_and_failed_start(qtbot):
    runner = v.Runner(); results = []
    runner.run(sys.executable, ['-c', 'import sys; sys.stdout.buffer.write(bytes(range(256)))'], results.append, binary=True)
    qtbot.waitUntil(lambda: len(results) == 1, timeout=3000)
    assert results[0].stdout == bytes(range(256))
    runner.run('C:/no-such-voyah-executable.exe', [], results.append)
    qtbot.waitUntil(lambda: len(results) == 2, timeout=3000)
    assert not results[1].ok


@pytest.fixture
def window(qtbot,monkeypatch,tmp_path):
    monkeypatch.setattr(v,'DATA_DIR',tmp_path/'profile')
    monkeypatch.setattr(v,'BOOTSTRAP_REPOSITORY','')
    app = QApplication.instance(); app.setStyleSheet(v.STYLE)
    win = v.MainWindow(demo=True, smoke=True); qtbot.addWidget(win); win.show(); win.poll.stop()
    qtbot.waitUntil(lambda: win.profile.api == 30, timeout=7000)
    yield win
    win.close(); qtbot.wait(250)


def test_ui_all_tabs_and_live_language(window, qtbot):
    assert window.stack.count() == 8
    window.language.setCurrentIndex(1); assert window.section_items['inspector'].toolTip() == v.EN[v.SECTION_HELP['inspector']]
    assert window.pages['installer'].flags[0].text() == 'Keep app data'
    window.language.setCurrentIndex(0); assert window.section_items['tweaks'].toolTip() == v.SECTION_HELP['tweaks']
    window.resize(1080, 760); qtbot.wait(100)
    assert window.width() <= 1150


def test_inspector_scan_capture_stream_and_package(window, qtbot):
    page = window.pages['inspector']; page.scan(); qtbot.waitUntil(lambda: bool(page.fields[2, 'component'].text()), timeout=5000)
    assert page.fields[1, 'package'].text() == 'com.voyah.launcher'
    page.capture(); qtbot.waitUntil(lambda: page.capture_timer.isActive(), timeout=3000)
    page.capture_started -= 6; page.capture_tick(); qtbot.waitUntil(lambda: bool(page.full_capture), timeout=3000)
    qtbot.waitUntil(lambda: bool(page.capture_views[1].toPlainText()), timeout=3000)
    assert 'MCU' in page.capture_views[1].toPlainText()
    page.toggle_stream('logcat'); qtbot.wait(500); page.toggle_stream('logcat')
    assert page.stream_buffers['logcat']
    page.package_search.setText('music'); page.search_packages(); qtbot.waitUntil(lambda: page.package_combo.count() > 0, timeout=3000)
    assert page.package_combo.currentText() == 'com.voyah.music'
    page.dump_package(); qtbot.waitUntil(lambda: bool(page.full_dump), timeout=3000)
    assert 'Receiver Resolver Table' in page.full_dump


def test_files_apps_dpi_and_setting_restore(window, qtbot):
    files = window.pages['files']; files.refresh(); qtbot.waitUntil(lambda: files.file_table.rowCount() > 0, timeout=3000)
    assert any(e['name'] == 'Тестовый файл.txt' for e in files.entries)
    apps = window.pages['apps']; apps.refresh(); qtbot.waitUntil(lambda: apps.package_table.rowCount() > 0, timeout=3000)
    apps.search.setText('yandex'); assert apps.package_table.rowCount() == 1
    tweaks = window.pages['tweaks']; tweaks.dpi.setCurrentText('150'); tweaks.set_density(False)
    qtbot.waitUntil(lambda: not window.busy, timeout=6000)
    assert window.demo_backend.settings['density'] == '150'
    key = tweaks.saved_key('dns'); window.settings.remove(key)
    tweaks.setting_feature('dns', True); qtbot.waitUntil(lambda: not window.busy, timeout=6000)
    assert window.demo_backend.settings['private_dns_mode'] == 'hostname'
    tweaks.restore_feature('dns'); qtbot.waitUntil(lambda: not window.busy, timeout=6000)
    assert 'private_dns_mode' not in window.demo_backend.settings


def test_terminal_history_and_remote_pipeline(window, qtbot):
    terminal = window.pages['terminal']; terminal.input.setText('adb shell echo hello | cat'); terminal.run_command()
    qtbot.waitUntil(lambda: not window.busy, timeout=3000)
    assert terminal.history[-1] == 'adb shell echo hello | cat'
    terminal.move_history(-1); assert 'echo hello' in terminal.input.text()


def test_installer_real_aapt_demo_adb(window, qtbot):
    page = window.pages['installer']; page.add_paths([Path(__file__).parent / 'fixtures' / 'upstream.apk']); page.mode.setCurrentIndex(0)
    page.install(); qtbot.waitUntil(lambda: not window.busy, timeout=15000)
    assert page.file_table.item(0, 2).text() in ('Успешно', 'Success')
    assert 'com.test.app' in page.log.toPlainText()


def test_shell_quote_for_voyah_su(window, qtbot):
    captured = []; original = window.demo_backend.run
    def run(args, callback, **kwargs): captured.append(args); return original(args, callback, **kwargs)
    window.demo_backend.run = run; window.privilege = 'su'; results = []
    window.adb(['ls', '/sdcard/Путь с пробелом'], results.append, shell=True, privileged=True)
    qtbot.waitUntil(lambda: bool(results), timeout=2000)
    shell_args = shlex.split(captured[-1][-1]); assert shell_args[:3] == ['su', 'sh', '-c']
    assert shlex.split(shell_args[3]) == ['ls', '/sdcard/Путь с пробелом']


def test_apks_bundletool_and_xapk_obb_flow(window, qtbot, tmp_path):
    page = window.pages['installer']
    archive = Path(__file__).parent / 'fixtures' / 'sample.apks'
    if not archive.exists(): pytest.skip('Generated bundletool fixture not available')
    page.add_paths([archive]); page.install(); qtbot.waitUntil(lambda: not window.busy, timeout=30000)
    assert page.file_table.item(0, 2).text() in ('Успешно', 'Success'), page.log.toPlainText()
    page.clear_files()
    xapk = tmp_path / 'sample.xapk'
    with zipfile.ZipFile(xapk, 'w') as z:
        z.write(Path(__file__).parent / 'fixtures' / 'upstream.apk', 'base.apk')
        z.writestr('Android/obb/com.test.app/main.24.com.test.app.obb', b'obb-test')
    window.confirm = lambda text: True
    page.add_paths([xapk]); page.install(); qtbot.waitUntil(lambda: not window.busy, timeout=15000)
    assert page.file_table.item(0, 2).text() in ('Успешно', 'Success'), page.log.toPlainText()
    assert 'OBB:' in page.log.toPlainText()


def test_root_opt_in_and_unroot(window, qtbot):
    window.confirm = lambda text: True
    window.set_privilege('root'); qtbot.waitUntil(lambda: not window.busy, timeout=6000)
    assert window.privilege == 'root' and window.demo_backend.root
    window.set_privilege('unroot'); qtbot.waitUntil(lambda: not window.busy, timeout=6000)
    assert window.privilege == 'shell' and not window.demo_backend.root
    window.set_privilege('su'); qtbot.waitUntil(lambda: not window.busy, timeout=5000)
    assert window.privilege == 'su' and window.su_prefix == ['su', 'sh', '-c']


def test_terminal_global_command_without_device(window, qtbot):
    window.set_target(None); terminal = window.pages['terminal']; terminal.input.setText('adb devices -l'); terminal.run_command()
    qtbot.waitUntil(lambda: not window.busy, timeout=3000)
    assert 'VOYAH-DEMO' in terminal.output.toPlainText()


def test_batch_continues_after_app_error_and_stops_on_disconnect(window, qtbot, tmp_path):
    page = window.pages['installer']; original = window.demo_backend.response; count = [0]
    def response(args):
        if 'install' in args:
            count[0] += 1
            if count[0] == 1: return v.Result(False, b'Failure [INSTALL_FAILED_VERSION_DOWNGRADE]')
        return original(args)
    window.demo_backend.response = response
    fixture = Path(__file__).parent / 'fixtures' / 'upstream.apk'; second = tmp_path / 'second.apk'; second.write_bytes(fixture.read_bytes())
    page.add_paths([fixture, second]); page.mode.setCurrentIndex(1); page.install()
    qtbot.waitUntil(lambda: not window.busy, timeout=15000)
    assert count[0] == 2 and page.file_table.item(0, 2).text() in ('Ошибка', 'Error')
    assert page.file_table.item(1, 2).text() in ('Успешно', 'Success')
    page.clear_files(); count[0] = 0
    def disconnected(args):
        if 'install' in args:
            count[0] += 1
            return v.Result(False, stderr=b'adb: device offline', code=1)
        return original(args)
    window.demo_backend.response = disconnected
    page.add_paths([fixture, second]); page.mode.setCurrentIndex(1); page.install()
    qtbot.waitUntil(lambda: not window.busy, timeout=15000)
    assert count[0] == 1
    assert page.file_table.item(1, 2).text() in ('Пропущено', 'Skipped')


def test_global_window_focus_is_matched_to_activity_display():
    activity = 'Display #0\n mResumedActivity: a com.cluster.app/.Main\nDisplay #1\n mResumedActivity: a com.center.app/.Main'
    result = v.parse_screens('mCurrentFocus=Window{a com.center.app/.Main}', activity)
    assert result[0]['package'] == 'com.cluster.app' and result[1]['package'] == 'com.center.app'
