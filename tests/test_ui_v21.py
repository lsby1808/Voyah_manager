"""Behaviour checks for the 2.1 interface; no head unit is required."""
from pathlib import Path
import time

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QWidget, QScrollArea

from test_manager import window
import voyah_manager as v


def test_stable_sections_and_direct_workspace_containers(window, qtbot):
    expected = {'catalog', 'installer', 'keyboards', 'inspector', 'files', 'apps', 'tweaks', 'terminal'}
    assert set(window.section_indices) == set(window.pages) == expected
    assert window.stack.count() == 8
    for key in expected:
        window.select_section(key)
        qtbot.waitUntil(lambda: window.current_section() == key)
        container = window.stack.currentWidget()
        assert container.property('section') == key
        if key in ('files', 'apps', 'terminal'):
            assert container is window.pages[key]
            assert not isinstance(container, QScrollArea)
        else:
            assert isinstance(container, QScrollArea)
            assert container.widget() is window.pages[key]
    window.resize(1000, 760); qtbot.wait(20)
    assert window.sidebar_panel.width() == 72
    assert all(not item.icon().isNull() for item in window.section_items.values())
    window.resize(1300, 860); qtbot.wait(20)
    assert window.sidebar_panel.width() == 240


@pytest.mark.parametrize('width, columns', [(320, 1), (720, 2), (1100, 3)])
def test_responsive_cards_follow_content_width(qtbot, width, columns):
    grid = v.ResponsiveGrid(min_card_width=280, max_columns=3); qtbot.addWidget(grid)
    for _ in range(5): grid.addWidget(v.SurfaceCard())
    grid.resize(width, 720); grid.show(); qtbot.wait(20)
    assert grid.columns == columns
    positions = [grid.grid.getItemPosition(index)[:2] for index in range(grid.grid.count())]
    assert positions == [(index // columns, index % columns) for index in range(5)]
    assert all(grid.grid.itemAt(index).alignment() & Qt.AlignmentFlag.AlignTop for index in range(5))


def test_availability_combines_device_busy_selection_and_admin(window, qtbot):
    installer = window.pages['installer']; files = window.pages['files']; apps = window.pages['apps']
    assert not installer.install_button.isEnabled()
    installer.add_paths([Path(__file__).parent / 'fixtures' / 'upstream.apk'])
    assert installer.install_button.isEnabled()
    files.refresh(); qtbot.waitUntil(lambda: bool(files.entries), timeout=3000)
    assert not files.pull_button.isEnabled()
    files.file_table.selectRow(0); assert files.pull_button.isEnabled()
    apps.refresh(); qtbot.waitUntil(lambda: bool(apps.packages), timeout=3000)
    assert not apps.launch_button.isEnabled()
    apps.package_table.selectRow(0); assert apps.launch_button.isEnabled()
    window.catalog.profile['features']['apps.clear'] = False; window.apply_policy()
    assert not apps.more_actions['Очистить данные и кэш'].isEnabled()
    assert apps.launch_button.isEnabled()
    assert window.begin('UI state check')
    assert not installer.install_button.isEnabled()
    assert not files.push_button.isEnabled() and not files.more_actions['Удалить'].isEnabled()
    assert not apps.launch_button.isEnabled()
    window.end()
    assert installer.install_button.isEnabled() and files.pull_button.isEnabled() and apps.launch_button.isEnabled()
    assert not apps.more_actions['Очистить данные и кэш'].isEnabled()
    window.set_target(None); window.apply_policy()
    assert not installer.install_button.isEnabled() and not files.pull_button.isEnabled() and not apps.launch_button.isEnabled()


def test_app_selection_survives_refresh_and_language(window, qtbot):
    apps = window.pages['apps']; apps.refresh(); qtbot.waitUntil(lambda: bool(apps.packages), timeout=3000)
    apps.package_table.selectRow(1)
    package = apps.package_table.item(apps.package_table.currentRow(), 0).text()
    apps.filter_rows(); assert apps.package_table.item(apps.package_table.currentRow(), 0).text() == package
    window.language.setCurrentIndex(1)
    assert apps.package_table.item(apps.package_table.currentRow(), 0).text() == package
    assert apps.selection_title.text() == package
    assert apps.more_actions['Очистить данные и кэш'].text() == 'Clear data and cache'


@pytest.mark.parametrize('section, attribute', [('installer', 'install_button'), ('files', 'push_button'), ('apps', 'launch_button'), ('terminal', 'run_button')])
def test_button_help_survives_language_and_policy(window, section, attribute):
    button = getattr(window.pages[section], attribute)
    key = button.property('help_key'); assert key and window.t(key) in button.toolTip()
    window.apply_policy(); assert window.t(key) in button.toolTip()
    feature = button.property('feature')
    window.catalog.profile['features'][feature] = False; window.apply_policy()
    assert window.t('Отключено администратором') in button.toolTip()
    assert window.t(key) in button.toolTip()
    window.language.setCurrentIndex(1)
    assert v.EN[key] in button.toolTip() and 'Disabled by administrator' in button.toolTip()
    window.catalog.profile['features'][feature] = True; window.apply_policy()
    assert v.EN[key] in button.toolTip() and 'Disabled by administrator' not in button.toolTip()


def test_field_help_is_retained_after_policy_and_language(window):
    widgets = [window.pages['installer'].mode, *window.pages['installer'].flags,
               window.pages['apps'].filter, window.pages['apps'].display]
    for widget in widgets:
        assert widget.property('help_key') and widget.toolTip()
    window.apply_policy()
    for widget in widgets: assert window.t(widget.property('help_key')) in widget.toolTip()
    window.language.setCurrentIndex(1)
    for widget in widgets:
        assert v.EN[widget.property('help_key')] in widget.toolTip()


def test_popup_keeps_keyboard_selection_and_escape(qtbot):
    combo = v.QComboBox(); qtbot.addWidget(combo); combo.addItems(['First', 'Unavailable', 'Third'])
    item = combo.model().item(1); item.setEnabled(False)
    combo.show(); combo.setFocus(); combo.showPopup()
    qtbot.waitUntil(lambda: combo.view().window().isVisible())
    qtbot.keyClick(combo.view(), Qt.Key.Key_Down)
    qtbot.keyClick(combo.view(), Qt.Key.Key_Return)
    assert combo.currentText() == 'Third'
    combo.showPopup(); qtbot.waitUntil(lambda: combo.view().window().isVisible())
    qtbot.keyClick(combo.view(), Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not combo.view().window().isVisible())
    assert combo.currentText() == 'Third'


def test_editable_popup_preserves_typed_value(qtbot):
    combo = v.QComboBox(); qtbot.addWidget(combo); combo.setEditable(True); combo.addItems(['140', '150', '160'])
    combo.show(); combo.setCurrentText('175'); combo.showPopup()
    qtbot.waitUntil(lambda: combo.view().window().isVisible())
    qtbot.keyClick(combo.view(), Qt.Key.Key_Escape)
    assert combo.currentText() == '175' and combo.lineEdit().text() == '175'


@pytest.mark.parametrize('edge', ['top_left', 'bottom_right'])
def test_popup_stays_in_monitor_work_area(qtbot, edge):
    host = QWidget(); qtbot.addWidget(host); area = QApplication.primaryScreen().availableGeometry()
    x = area.left() if edge == 'top_left' else area.right() - 259
    y = area.top() if edge == 'top_left' else area.bottom() - 89
    host.setGeometry(x, y, 260, 90)
    combo = v.QComboBox(host); combo.setGeometry(90, 25, 150, 44); combo.addItems([f'Choice {index}' for index in range(20)])
    host.show(); combo.showPopup(); qtbot.waitUntil(lambda: combo.view().window().isVisible())
    popup = combo.view().window(); bounds = popup.geometry()
    assert area.contains(bounds.topLeft()) and area.contains(bounds.bottomRight())
    if edge == 'bottom_right': assert bounds.bottom() < combo.mapToGlobal(QPoint(0, 0)).y()
    combo.hidePopup()


def test_reduce_motion_and_disclosure_finish_in_correct_state(window, qtbot):
    window.reduce_motion.setChecked(True); assert window.motion.reduced and not window.motion.enabled
    disclosure = window.connection_disclosure
    disclosure.setExpanded(True); assert disclosure.expanded and disclosure.content.isVisible()
    disclosure.setExpanded(False); assert not disclosure.expanded and not disclosure.content.isVisible()
    window.motion.system_enabled = False; window.motion.set_reduced(False)
    assert not window.motion.enabled


def test_inspector_capture_waits_six_seconds_and_reports_records(window, qtbot, monkeypatch):
    page = window.pages['inspector']; calls = []; original = window.demo_backend.run
    def run(args, callback, **kwargs):
        calls.append(args); return original(args, callback, **kwargs)
    monkeypatch.setattr(window.demo_backend, 'run', run)
    page.capture(); qtbot.waitUntil(lambda: page.capture_state == 'recording', timeout=3000)
    page.capture_timer.stop()
    page.capture_started = time.monotonic() - 5.5; page.capture_tick()
    assert page.capture_state == 'recording'
    assert not any('logcat' in args and '-d' in args for args in calls)
    page.capture_started = time.monotonic() - 6.1; page.capture_tick()
    qtbot.waitUntil(lambda: page.capture_state == 'done', timeout=4000)
    assert any('logcat' in args and '-d' in args for args in calls)
    assert page.capture_counts[3] == len(page.full_capture.splitlines())
    assert page.capture_summary.text() == window.t('Обработано сообщений: {count}. Одно нажатие может создавать несколько сообщений.', count=page.capture_counts[3])
    assert page.capture_save_btn.isEnabled() and not page.capture_cancel_btn.isEnabled()


def test_inspector_live_streams_pause_view_without_losing_recording(window, qtbot):
    page = window.pages['inspector']; page.toggle_stream('logcat'); page.toggle_stream('getevent')
    assert set(page.streams) == {'logcat', 'getevent'}
    qtbot.waitUntil(lambda: bool(page.stream_buffers['logcat']) and bool(page.stream_buffers['getevent']), timeout=3000)
    page._flush_live(); page.toggle_pause('logcat'); visible = page.live_views['logcat'].toPlainText(); recorded = len(page.stream_buffers['logcat'])
    qtbot.waitUntil(lambda: len(page.stream_buffers['logcat']) > recorded, timeout=3000); page._flush_live()
    assert page.live_views['logcat'].toPlainText() == visible
    assert page.live_paused['logcat'] and not page.live_paused['getevent']
    page.toggle_stream('getevent'); assert set(page.streams) == {'logcat'}
    page.toggle_pause('logcat'); assert len(page.live_views['logcat'].toPlainText()) > len(visible)
    page.live_filter.setText('no-message-can-contain-this-word')
    assert not page.live_views['logcat'].toPlainText()
    assert page.stream_buffers['logcat'] and page.live_save_btn.isEnabled()
    page.stop_streams(); assert not page.streams


def test_inspector_cancel_returns_to_ready_state(window, qtbot):
    page = window.pages['inspector']; page.capture()
    qtbot.waitUntil(lambda: page.capture_state == 'recording', timeout=3000)
    window.cancel_operation(); page.capture_tick()
    assert page.capture_state == 'cancelled' and not page.capture_timer.isActive()
    assert not window.busy and page.capture_btn.isEnabled() and not page.capture_cancel_btn.isEnabled()
    assert page.capture_progress.value() == 0


def test_device_profile_updates_compatibility_without_reopening_page(window, qtbot):
    catalog=window.pages['catalog']; keyboards=window.pages['keyboards']
    profile=v.default_catalog(); profile['revision']=2
    profile['apps']=[{'id':'future-app','name':'Future app','source':'https://example.com/app.apk','enabled':True,'min_sdk':31}]
    profile['keyboards']=[{'id':'test-kit','name':'Test kit','central_url':'https://example.com/center.apk','passenger_url':'https://example.com/passenger.apk','enabled':True}]
    window.catalog.profile=v.validate_catalog(profile); catalog.refresh(); keyboards.refresh()
    target=window.target
    window.set_target(None); window.set_target(target)
    assert not catalog.install_btn.isEnabled() and not keyboards.install_btn.isEnabled()
    window.read_profile(); qtbot.waitUntil(lambda: window.profile.api==30,timeout=6000)
    assert not catalog.install_btn.isEnabled()
    assert keyboards.install_btn.isEnabled()
    assert window.t('Нужна более новая версия Android') in catalog.selection_status.text()


def test_animated_navigation_and_popups_remain_responsive(window,qtbot):
    window.smoke=False; window.motion.system_enabled=True; window.motion.set_reduced(False)
    window.select_section('files'); window.select_section('apps'); window.select_section('terminal')
    assert window.stack.fade.duration()==140
    qtbot.waitUntil(lambda: window.stack.currentWidget().graphicsEffect() is None,timeout=1500)
    assert window.current_section()=='terminal' and window.stack.currentWidget().graphicsEffect() is None
    window.connection_disclosure.setExpanded(True)
    assert window.connection_disclosure.animation.duration()==200
    qtbot.waitUntil(lambda: window.connection_details.maximumHeight()>1000,timeout=1500)
    assert window.connection_details.isVisible() and window.connection_details.maximumHeight()>1000
    window.language.showPopup(); qtbot.waitUntil(lambda: window.language.view().window().windowOpacity()==1,timeout=1500)
    assert window.language.view().window().windowOpacity()==1
    window.language.hidePopup(); window.connection_disclosure.setExpanded(False); qtbot.waitUntil(lambda: not window.connection_details.isVisible(),timeout=1500)
    assert not window.connection_details.isVisible()
    window.smoke=True
