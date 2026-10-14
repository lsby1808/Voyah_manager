"""Engineering date boundaries, local demo switching and automatic APK planning."""
from datetime import date, datetime, timezone
from pathlib import Path
import json,os

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtWidgets import QApplication
import voyah_manager as v
from test_manager import window


@pytest.mark.parametrize('day,expected',[(date(2026,10,14),'30310'),(date(2026,10,15),'30311'),(date(2026,12,31),'3257'),(date(2024,2,29),'22413'),(date(2026,1,1),'2127')])
def test_engineering_algorithm_preserves_two_digit_sums(day,expected):
    assert v.voyah_engineering_password(day)==expected

def test_beijing_midnight_and_year_boundary():
    before=v.engineering_passwords(datetime(2026,10,14,15,59,59,tzinfo=timezone.utc))
    after=v.engineering_passwords(datetime(2026,10,14,16,0,0,tzinfo=timezone.utc))
    assert before[0]==(date(2026,10,14),'30310')
    assert after[0]==(date(2026,10,15),'30311')
    boundary=v.engineering_passwords(datetime(2025,12,31,16,0,tzinfo=timezone.utc))
    assert boundary==[(date(2026,1,1),'2127'),(date(2025,12,31),'3256'),(date(2026,1,2),'2128')]
    with pytest.raises(ValueError): v.engineering_passwords(datetime(2026,1,1))

@pytest.mark.parametrize('width',[900,1400])
@pytest.mark.parametrize('language',[0,1])
def test_header_password_and_copy_remain_readable_offline(window,qtbot,monkeypatch,width,language):
    samples=v.engineering_passwords(datetime(2026,10,14,16,0,tzinfo=timezone.utc))
    monkeypatch.setattr(v,'engineering_passwords',lambda:samples)
    window.set_target(None); window.resize(width,760); window.language.setCurrentIndex(language); window.update_engineering_password(); qtbot.wait(30)
    button=window.engineering_button
    assert '30311' in button.text() and '15.10.2026' in button.toolTip()
    assert button.isEnabled() and window.header_frame.rect().contains(QRect(button.mapTo(window.header_frame,QPoint(0,0)),button.size()))
    assert button.geometry().right()<window.connect_btn.geometry().left()
    dialog=v.EngineeringPasswordDialog(window);qtbot.addWidget(dialog);dialog.show()
    assert [row[2].text() for row in dialog.rows]==[value for day,value in samples]
    dialog.copy(dialog.rows[0][2].property('password'));assert QApplication.clipboard().text()=='30311'
    dialog.close()

def isolated_demo_settings(monkeypatch,tmp_path):
    prefs=QSettings(str(tmp_path/'demo.ini'),QSettings.Format.IniFormat)
    monkeypatch.setattr(v,'QSettings',lambda *args,**kwargs:prefs)
    return prefs

def test_demo_choice_is_local_and_restarts_without_external_commands(window,qtbot,monkeypatch,tmp_path):
    qtbot.waitUntil(lambda:not window.workers and not window.probing)
    prefs=isolated_demo_settings(monkeypatch,tmp_path);calls=[];closed=[]
    monkeypatch.setattr(window,'launch_application',lambda args:calls.append(args) or True)
    original_close=window.close
    monkeypatch.setattr(window,'close',lambda:closed.append(True) or original_close())
    profile=dict(window.catalog.profile)
    assert window.demo and window.set_demo_mode(False)
    qtbot.waitUntil(lambda:bool(closed))
    assert calls==[[]] and prefs.value('runtime/demo_enabled') is False
    assert window.demo and window.catalog.profile==profile

@pytest.mark.parametrize('reason',['busy','streams','failed launch'])
def test_demo_restart_does_not_interrupt_operations_or_lose_setting(window,qtbot,monkeypatch,tmp_path,reason):
    qtbot.waitUntil(lambda:not window.workers and not window.probing)
    prefs=isolated_demo_settings(monkeypatch,tmp_path);prefs.setValue('runtime/demo_enabled',True)
    launched=[];monkeypatch.setattr(window,'launch_application',lambda args:launched.append(args) or False)
    if reason=='busy': window.busy=True
    if reason=='streams': window.pages['inspector'].streams['logcat']=object()
    try:
        if reason=='busy':
            admin=v.AdminDialog(window);qtbot.addWidget(admin);admin.demo_check.setChecked(False);admin.demo_apply.click()
            assert admin.status.text()==window.notice_label.text() and admin.status.text()
            admin.reject()
        else: assert not window.set_demo_mode(False)
        assert prefs.value('runtime/demo_enabled') is True
        assert bool(launched)==(reason=='failed launch')
    finally:
        window.busy=False;window.pages['inspector'].streams.clear()

def test_saved_demo_mode_never_routes_to_real_adb(qtbot,monkeypatch,tmp_path):
    prefs=isolated_demo_settings(monkeypatch,tmp_path);prefs.setValue('runtime/demo_enabled',True)
    monkeypatch.setattr(v,'DATA_DIR',tmp_path/'profile');monkeypatch.setattr(v,'BOOTSTRAP_REPOSITORY','')
    monkeypatch.setattr(v.Runner,'run',lambda *args,**kwargs:pytest.fail('Demo must not run real ADB'))
    win=v.MainWindow(demo=None,smoke=True);qtbot.addWidget(win);win.show();win.poll.stop()
    qtbot.waitUntil(lambda:win.profile.api==30,timeout=7000)
    assert win.demo and isinstance(win.demo_backend,v.DemoBackend)
    admin=v.AdminDialog(win);qtbot.addWidget(admin)
    assert admin.demo_check.isChecked() and 'runtime/demo_enabled' not in admin.collect()
    admin.reject();win.close();qtbot.wait(50)

def test_restart_uses_an_independent_detached_process_environment(qtbot,monkeypatch,tmp_path):
    marker=tmp_path/'restart-result.json';before=os.environ.get('PYINSTALLER_RESET_ENVIRONMENT')
    monkeypatch.setattr(v.sys,'frozen',True,raising=False);monkeypatch.setattr(v,'APP_DIR',tmp_path)
    code="import os,json,time;from pathlib import Path;time.sleep(.15);Path("+repr(str(marker))+").write_text(json.dumps({'reset':os.environ.get('PYINSTALLER_RESET_ENVIRONMENT'),'cwd':str(Path.cwd())}))"
    assert v.MainWindow.launch_application(None,['-c',code])
    qtbot.waitUntil(marker.exists,timeout=5000)
    data=json.loads(marker.read_text());assert data=={'reset':'1','cwd':str(tmp_path)}
    assert os.environ.get('PYINSTALLER_RESET_ENVIRONMENT')==before

def apk(path,pkg='com.test.one',version='1',split=''):
    return v.ApkInfo(Path(path),pkg,version,28,split)

def test_auto_planner_uses_manifest_identity_and_base_first():
    paths=list(map(Path,['part.apk','other.apk','base.apk','bundle.xapk','more.apk']))
    infos=[apk(paths[0],split='config.ru'),apk(paths[1],pkg='com.other.app'),apk(paths[2]),None,apk(paths[4],version='2')]
    groups=v.plan_apk_queue(paths,infos)
    assert groups==[([paths[2],paths[0]],[2,0]),([paths[1]],[1]),([paths[3]],[3]),([paths[4]],[4])]

@pytest.mark.parametrize('infos',[
    [apk('s.apk',split='ru')],
    [apk('s.apk',split='ru'),apk('a.apk'),apk('b.apk')],
    [apk('b.apk'),apk('s.apk',split='ru'),apk('s2.apk',split='ru')],
    [apk('s.apk',version='2',split='ru'),apk('b.apk')],
])
def test_auto_planner_rejects_missing_or_ambiguous_base(infos):
    with pytest.raises(ValueError): v.plan_apk_queue([i.path for i in infos],infos)

def test_multiple_full_apks_are_separate_even_if_package_matches():
    infos=[apk('first.apk'),apk('second.apk')]
    assert len(v.plan_apk_queue([i.path for i in infos],infos))==2

def test_automatic_queue_installs_a_real_extracted_split_set(window,qtbot,tmp_path):
    import zipfile
    with zipfile.ZipFile(Path(__file__).parent/'fixtures/sample.apks') as archive:
        names=['splits/base-master.apk','splits/base-mdpi.apk']
        # The fixture is a device-compatible base + language/density split set.
        paths=[]
        for number,name in enumerate(names):
            path=tmp_path/f'piece-{number}.apk';path.write_bytes(archive.read(name));paths.append(path)
    if len(paths)<2: pytest.skip('Fixture has no split APK set')
    calls=[];original=window.demo_backend.response
    def response(args):
        if 'install-multiple' in args or 'install' in args:calls.append(args)
        return original(args)
    window.demo_backend.response=response
    page=window.pages['installer'];page.add_paths(paths);assert not page.mode.isVisible();page.install()
    qtbot.waitUntil(lambda:not window.busy,timeout=30000)
    assert len(calls)==1 and 'install-multiple' in calls[0],page.log.toPlainText()
    assert all(page.file_table.item(i,2).text() in ('Успешно','Success') for i in range(len(paths)))

def test_capture_idle_has_no_large_empty_result_panel(window,qtbot):
    page=window.pages['inspector'];window.resize(1400,940);window.select_section('inspector');page.sections.setCurrentIndex(1);qtbot.wait(30)
    assert page.capture_controls_card.height()<300
    assert page.capture_results_card.height()<160
    assert not page.capture_tabs.isVisible() and page.capture_idle_hint.isVisible()
    assert page.capture_save_btn.text()==page.capture_open_btn.text()==''
    page.capture();qtbot.waitUntil(lambda:page.capture_state=='recording',timeout=3000)
    assert page.capture_progress.isVisible()
    page.capture_started-=6;page.capture_tick();qtbot.waitUntil(lambda:page.capture_state=='done',timeout=5000)
    assert page.capture_tabs.isVisible() and not page.capture_idle_hint.isVisible()
    assert not page.capture_progress.isVisible() and 180<=page.capture_tabs.height()<=280
