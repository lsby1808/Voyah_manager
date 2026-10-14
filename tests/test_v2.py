import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject,Signal,QTimer
from PySide6.QtNetwork import QNetworkRequest,QNetworkReply
from PySide6.QtWidgets import QDialog,QApplication,QInputDialog
from test_manager import window
import voyah_manager as v


class FakeReply(QObject):
    readyRead = Signal()
    finished = Signal()
    downloadProgress = Signal(int,int)
    def __init__(self,body,status=200,etag='"revision"',delay=0):
        super().__init__(); self.body=body; self.status=status; self.etag=etag; self.aborted=False; self.done=False
        QTimer.singleShot(delay,self.deliver)
    def deliver(self):
        if self.done:return
        self.readyRead.emit(); self.downloadProgress.emit(len(self.body),len(self.body)); self.done=True; self.finished.emit()
    def readAll(self):
        body=self.body;self.body=b'';return body
    def attribute(self,key):return self.status
    def error(self):return QNetworkReply.NetworkError.OperationCanceledError if self.aborted else QNetworkReply.NetworkError.ContentNotFoundError if self.status>=400 else QNetworkReply.NetworkError.NoError
    def errorString(self):return 'mock response'
    def rawHeader(self,key):
        assert isinstance(key,str)
        return self.etag.encode() if key=='ETag' else b''
    def abort(self):
        if self.done:return
        self.aborted=True;self.body=b'';self.done=True;self.finished.emit()


class FakeManager:
    def __init__(self,handler):self.handler=handler;self.requests=[];self.replies=[]
    def send(self,method,request,payload=None):
        self.requests.append((method,request.url().toString(),payload,request))
        body,status,*extra=self.handler(method,request,payload)
        if not isinstance(body,bytes):body=json.dumps(body).encode()
        reply=FakeReply(body,status,delay=extra[0] if extra else 0);self.replies.append(reply);return reply
    def get(self,request):return self.send('GET',request)
    def head(self,request):return self.send('HEAD',request)
    def put(self,request,payload):return self.send('PUT',request,json.loads(bytes(payload)))


def install_network(window,handler):
    fake=FakeManager(handler);window.web.manager=fake;return fake


def test_admin_hash_and_async_login(window,qtbot,monkeypatch):
    code='test-only-admin-code'
    monkeypatch.setattr(v,'ADMIN_HASH',hashlib.pbkdf2_hmac('sha256',code.encode(),v.ADMIN_SALT,310000))
    assert v.verify_admin_code(code) and not v.verify_admin_code('wrong')
    login=v.AdminLogin(window);qtbot.addWidget(login);login.show();login.code.setText('wrong');login.verify()
    qtbot.waitUntil(lambda:bool(login.status.text()),timeout=3000);assert login.result()!=QDialog.DialogCode.Accepted
    qtbot.waitUntil(lambda:login.submit.isEnabled(),timeout=3000);login.code.setText(code);login.verify()
    qtbot.waitUntil(lambda:login.result()==QDialog.DialogCode.Accepted,timeout=3000);assert login.code.text()==''
    admin=v.AdminDialog(window);qtbot.addWidget(admin);admin.show();assert admin.tabs.count()==4
    admin.checks['terminal'].setChecked(False);admin.save_draft();assert window.catalog.profile['features']['terminal']
    admin.reject();assert not admin.isVisible();assert 'token' not in admin.draft_path.read_text()


@pytest.mark.parametrize('feature,section,method,args',[
 ('apk.install','installer','install',()),('files.write','files','push_paths',(['/nonexistent'],)),
 ('apps.freeze','apps','disable',()),('apps.clear','apps','clear_data',()),('apps.uninstall','apps','uninstall',()),
 ('tweaks.dpi','tweaks','set_density',(False,)),('tweaks.network','tweaks','setting_feature',('dns',True)),
 ('tweaks.permissions','tweaks','grant',('android.permission.RECORD_AUDIO',)),
 ('terminal','terminal','run_command',()),('keyboard.install','keyboards','install',()),('keyboard.restore','keyboards','restore',())])
def test_policy_guards_all_entry_points(window,feature,section,method,args):
    called=[];window.adb=lambda *a,**kw:called.append((a,kw));window.catalog.profile['features'][feature]=False;window.apply_policy()
    if section=='terminal':window.pages[section].input.setText('adb shell reboot')
    getattr(window.pages[section],method)(*args);assert not called and not window.busy


def test_policy_applies_after_running_job(window):
    changed=copy.deepcopy(window.catalog.profile);changed['features']['apk.install']=False
    window.begin('test');window.catalog.apply(changed);assert window.catalog.profile['features']['apk.install']
    window.end();assert not window.catalog.profile['features']['apk.install']
    assert not window.pages['installer'].install_button.isEnabled()


@pytest.mark.parametrize('mutate',[
 lambda p:p.update(schema_version=2),lambda p:p['features'].update(terminal='false'),
 lambda p:p.update(shell='reboot'),lambda p:p['apps'].append({'id':'test','name':'Test','source':'https://example.com/test.apk','post_install':['rm -rf /']}),
 lambda p:p['keyboards'].append({'id':'k','name':'K','central_url':'file:///x','passenger_url':'https://example.com/p.apk'}),
])
def test_catalog_rejects_untrusted_fields(mutate):
    profile=v.default_catalog();mutate(profile)
    with pytest.raises(ValueError):v.validate_catalog(profile)


def catalog_response(profile,sha='sha1'):
    return {'content':base64.b64encode(json.dumps(profile).encode()).decode(),'sha':sha}


def test_catalog_refresh_cache_corruption_and_304(window,qtbot):
    profile=v.default_catalog();profile['revision']=12;profile['features']['terminal']=False
    store=window.catalog;store.config={'repository':'owner/repo','path':'catalog.json','branch':''}
    fake=install_network(window,lambda *a:(profile,200))
    store.refresh();qtbot.waitUntil(lambda:not store.loading,timeout=3000);assert store.profile['revision']==12
    assert json.loads(store.path.read_text())['profile']['features']['terminal'] is False
    fake.handler=lambda *a:(b'bad json',200);store.refresh();qtbot.waitUntil(lambda:not store.loading);assert store.profile['revision']==12
    fake.handler=lambda *a:(b'',304);store.refresh();qtbot.waitUntil(lambda:not store.loading);assert store.profile['revision']==12
    assert bytes(fake.requests[-1][3].rawHeader('If-None-Match'))==b'"revision"'


@pytest.mark.parametrize('branch,encoded',[('', 'HEAD'),('release/v2','release%2Fv2')])
def test_public_catalog_avoids_api_quota_and_preserves_exact_blob_sha(window,qtbot,branch,encoded):
    store=window.catalog;store.config={'repository':'owner/repo','path':'folder/catalog.json','branch':branch}
    profile=v.default_catalog();profile['revision']=5
    body=(json.dumps(profile,ensure_ascii=False,indent=2)+'\r\n').encode()
    fake=install_network(window,lambda *a:(body,200))
    store.refresh();qtbot.waitUntil(lambda:not store.loading,timeout=3000)
    assert store.remote_loaded and store.profile['revision']==5
    assert fake.requests[0][1]==f'https://raw.githubusercontent.com/owner/repo/{encoded}/folder/catalog.json'
    assert store.remote_sha==hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
    assert not bytes(fake.requests[0][3].rawHeader('Authorization'))


@pytest.mark.parametrize('status',[401,403,404,409])
def test_github_failures_preserve_draft(window,qtbot,monkeypatch,status):
    store=window.catalog;store.config={'repository':'owner/repo','path':'catalog.json','branch':'main'};store.remote_loaded=True;store.remote_sha='sha1'
    monkeypatch.setattr(v.CredentialStore,'read',lambda repo:'ephemeral-test-token')
    fake=install_network(window,lambda method,*a:(catalog_response(v.default_catalog()),200) if method=='GET' else ({'message':'mock failure'},status))
    draft=v.default_catalog();draft['revision']=2;v.atomic_json(v.DATA_DIR/'catalog-draft.json',draft);results=[];store.publish(draft,lambda *r:results.append(r))
    qtbot.waitUntil(lambda:bool(results));assert results[0][0] is False;assert json.loads((v.DATA_DIR/'catalog-draft.json').read_text())['revision']==2
    assert store.profile['revision']==0


def test_github_sha_conflict_and_publication(window,qtbot,monkeypatch):
    store=window.catalog;store.config={'repository':'owner/repo','path':'catalog.json','branch':''};store.remote_loaded=True;store.remote_sha='sha1';monkeypatch.setattr(v.CredentialStore,'read',lambda repo:'test-token')
    fake=install_network(window,lambda *a:(catalog_response(v.default_catalog(),'other'),200));results=[];store.publish(v.default_catalog(),lambda *r:results.append(r));qtbot.waitUntil(lambda:bool(results));assert not results.pop()[0] and len(fake.requests)==1
    fake.handler=lambda method,*a:(catalog_response(v.default_catalog(),'sha1'),200) if method=='GET' else ({'content':{'sha':'sha2'}},201)
    draft=v.default_catalog();draft['revision']=4;store.publish(draft,lambda *r:results.append(r));qtbot.waitUntil(lambda:bool(results));assert results[0][0] and store.remote_sha=='sha2' and store.profile['revision']==4
    payload=fake.requests[-1][2];assert payload['sha']=='sha1' and 'token' not in json.dumps(payload)


@pytest.mark.parametrize('url,expected',[
 ('https://github.com/o/r','https://api.github.com/repos/o/r/releases/latest'),
 ('https://github.com/o/r/releases/latest','https://api.github.com/repos/o/r/releases/latest'),
 ('https://github.com/o/r/releases/tag/v1.2','https://api.github.com/repos/o/r/releases/tags/v1.2'),
 ('https://github.com/o/r/releases/download/v1/test.apk',None),('https://example.com/test.xapk',None)])
def test_source_resolution(url,expected):assert v.release_endpoint(url)==expected


def test_download_atomic_sha_size_cancel_and_offline_cache(window,qtbot,tmp_path):
    data=b'apk-payload';fake=install_network(window,lambda *a:(data,200));results=[];path=tmp_path/'payload.apk'
    window.web.request('https://example.com/test.apk',results.append,destination=path,digest=hashlib.sha256(data).hexdigest(),expected_size=len(data))
    assert not path.exists();qtbot.waitUntil(lambda:bool(results));assert path.read_bytes()==data and not path.with_suffix('.apk.part').exists()
    results.clear();window.web.request('https://example.com/bad.apk',results.append,destination=tmp_path/'bad.apk',digest='0'*64);qtbot.waitUntil(lambda:bool(results));assert results[0]['error'] and not (tmp_path/'bad.apk').exists()
    results.clear();fake.handler=lambda *a:(data,200,500);job=window.web.request('https://example.com/cancel.apk',results.append,destination=tmp_path/'cancel.apk');job.cancel();qtbot.waitUntil(lambda:bool(results));assert not (tmp_path/'cancel.apk.part').exists()
    fake.handler=lambda *a:(data,200);downloader=v.DownloadService(window);results.clear();downloader.acquire('https://example.com/test.apk',lambda *r:results.append(r));qtbot.waitUntil(lambda:bool(results));cached=results[0][0];assert cached.is_file()
    fake.handler=lambda *a:(b'',503);results.clear();downloader.acquire('https://example.com/test.apk',lambda *r:results.append(r));qtbot.waitUntil(lambda:bool(results));assert results[0][0]==cached
    cached.write_bytes(b'corrupt');results.clear();downloader.acquire('https://example.com/test.apk',lambda *r:results.append(r));qtbot.waitUntil(lambda:bool(results));assert results[0][0] is None


def fake_apk_metadata(window,monkeypatch,packages=None):
    original=window.runner.run
    def run(program,args,callback,**kwargs):
        if 'badging' in args:
            path=Path(args[-1]);package=(packages or {}).get(path.name,'ru.vk.store')
            result=v.Result(True,f"package: name='{package}' versionCode='144'\nsdkVersion:'24'\n".encode())
            QTimer.singleShot(0,lambda:callback(result));return None
        return original(program,args,callback,**kwargs)
    monkeypatch.setattr(window.runner,'run',run)


def test_voyah_installer_prepare_no_streaming_rustore_and_version(window,qtbot,monkeypatch):
    fake_apk_metadata(window,monkeypatch);page=window.pages['installer'];fixture=Path(__file__).parent/'fixtures'/'upstream.apk';page.add_paths([fixture]);calls=[];original=window.demo_backend.response
    def response(args):calls.append(args);return original(args)
    window.demo_backend.response=response;page.install();qtbot.waitUntil(lambda:not window.busy,timeout=10000)
    assert window.demo_backend.install_disabled=='false';install=next(a for a in calls if 'install' in a);assert '--no-streaming' in install and install[:2]==['-s','VOYAH-DEMO']
    assert window.demo_backend.settings['appops:ru.vk.store:REQUEST_INSTALL_PACKAGES']=='allow'
    assert page.file_table.item(0,2).text() in ('Успешно','Success')


def make_keyboard_recipe(window,monkeypatch,tmp_path):
    paths=[tmp_path/'central.apk',tmp_path/'second.apk'];paths[0].write_bytes(b'new-central');paths[1].write_bytes(b'new-passenger')
    fake_apk_metadata(window,monkeypatch,{'central.apk':v.KEYBOARD_PATHS[0][0],'second.apk':v.KEYBOARD_PATHS[1][0]});window.confirm=lambda _:True
    recipe=v.SystemRecipe(window,'keyboard',paths);window.recipe=recipe;return recipe


def test_keyboard_pair_backup_existing_old_and_restore(window,qtbot,monkeypatch,tmp_path):
    recipe=make_keyboard_recipe(window,monkeypatch,tmp_path);backend=window.demo_backend
    stock=copy.deepcopy(backend.files);old0=str(Path(v.KEYBOARD_PATHS[0][1]).with_suffix('.old')).replace('\\','/');backend.files[old0]=b'original-factory-backup'
    recipe.start();qtbot.waitUntil(lambda:not window.busy,timeout=20000)
    assert recipe.journal['status']=='complete',recipe.journal
    assert backend.files[old0]==b'original-factory-backup';assert backend.selinux=='Enforcing'
    for index,(_,path) in enumerate(v.KEYBOARD_PATHS):assert (recipe.backup_dir/f'before-{index}.apk').read_bytes()==stock[path]
    restore=v.SystemRecipe(window,'keyboard_restore');window.recipe=restore;restore.start();qtbot.waitUntil(lambda:not window.busy,timeout=15000);assert restore.journal['status']=='complete'
    assert backend.files[v.KEYBOARD_PATHS[0][1]]==b'original-factory-backup'


def test_keyboard_second_failure_rolls_back_first(window,qtbot,monkeypatch,tmp_path):
    recipe=make_keyboard_recipe(window,monkeypatch,tmp_path);backend=window.demo_backend;stock=copy.deepcopy(backend.files);original=backend.response;failed=[False]
    def response(args):
        if 'push' in args and args[-1]==v.KEYBOARD_PATHS[1][1] and not failed[0]:failed[0]=True;return v.Result(False,stderr=b'read-only file system',code=1)
        return original(args)
    backend.response=response;recipe.start();qtbot.waitUntil(lambda:not window.busy,timeout=20000)
    assert recipe.journal['status']=='failed' and recipe.journal['cleanup_ok']
    for _,path in v.KEYBOARD_PATHS:assert backend.files[path]==stock[path]
    assert backend.selinux=='Enforcing'


@pytest.mark.parametrize('kind,stage',[('settings','backup'),('settings','cancel'),('verity','root'),('keyboard_restore','model')])
def test_system_safety_on_failures(window,qtbot,kind,stage):
    backend=window.demo_backend;original=backend.response;calls=[];window.confirm=lambda _:True
    if stage=='model':window.profile.model_code='unsupported'
    def response(args):
        calls.append(args)
        if stage=='backup' and 'pull' in args and args[-2].endswith('-wal'):return v.Result(False,stderr=b'copy failed',code=1)
        if stage=='root' and 'root' in args:return v.Result(False,stderr=b'adbd cannot run as root',code=1)
        return original(args)
    backend.response=response;recipe=v.SystemRecipe(window,kind);window.recipe=recipe;recipe.start()
    if stage=='cancel':
        qtbot.waitUntil(lambda:recipe.android_stopped,timeout=5000);window.cancel_operation()
    qtbot.waitUntil(lambda:not window.busy,timeout=15000)
    assert backend.android_running
    if stage in ('backup','cancel'):assert v.SETTINGS_DB in backend.files and not any('rm -f' in a[-1] for a in calls)
    if stage=='root':assert not any('disable-verity' in a for a in calls)


def test_settings_success_has_three_verified_backups_and_restart(window,qtbot):
    window.confirm=lambda _:True;backend=window.demo_backend;recipe=v.SystemRecipe(window,'settings');window.recipe=recipe;recipe.start();qtbot.waitUntil(lambda:not window.busy,timeout=15000)
    assert recipe.journal['status']=='complete' and backend.android_running
    for suffix in ('','-wal','-shm'):assert (recipe.backup_dir/('qinggan_settings.db'+suffix)).is_file()
    assert v.SETTINGS_DB not in backend.files


def test_credential_store_roundtrip_does_not_use_settings(window):
    repo='voyah-manager-tests/ephemeral';token='temporary-test-secret'
    try:v.CredentialStore.write(repo,token);assert v.CredentialStore.read(repo)==token
    finally:v.CredentialStore.delete(repo)
    assert not v.CredentialStore.read(repo)
    assert all(token not in str(window.settings.value(k)) for k in window.settings.allKeys())


def test_catalog_download_automatically_installs_on_pinned_device(window,qtbot):
    data=(Path(__file__).parent/'fixtures'/'upstream.apk').read_bytes()
    fake=install_network(window,lambda *a:(data,200));profile=v.default_catalog();profile['apps']=[{'id':'sample','name':'Sample','source':'https://example.com/sample.apk','package':'com.test.app'}]
    window.catalog.apply(profile);page=window.pages['catalog'];page.listing.selectRow(0);page.install()
    qtbot.waitUntil(lambda:not window.busy,timeout=12000)
    assert window.demo_backend.installed_versions['com.test.app']=='24'
    assert page.service.install_target.serial=='VOYAH-DEMO' and fake.requests


@pytest.mark.parametrize('failure',['root','remount'])
def test_keyboard_root_and_remount_denial_does_not_replace_files(window,qtbot,monkeypatch,tmp_path,failure):
    recipe=make_keyboard_recipe(window,monkeypatch,tmp_path);backend=window.demo_backend;stock=copy.deepcopy(backend.files);original=backend.response
    def response(args):
        if failure in args:return v.Result(False,stderr=b'operation denied',code=1)
        return original(args)
    backend.response=response;recipe.start();qtbot.waitUntil(lambda:not window.busy,timeout=12000)
    for _,path in v.KEYBOARD_PATHS:assert backend.files[path]==stock[path]
    assert recipe.journal['status']=='failed'


def test_release_asset_selection_and_supplied_digest(window,qtbot,monkeypatch):
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a:('second.apk  (4 B)',True))
    assets=[{'name':name,'size':4,'browser_download_url':'https://example.com/'+name,'digest':'sha256:'+'a'*64} for name in ('first.apk','second.apk')]
    install_network(window,lambda *a:({'tag_name':'v9','assets':assets},200));downloader=v.DownloadService(window);results=[]
    downloader.resolve('https://github.com/o/r','',lambda *r:results.append(r));qtbot.waitUntil(lambda:bool(results))
    assert results[0][0]['name']=='second.apk' and results[0][0]['digest']=='sha256:'+'a'*64


def test_bad_size_and_corrupt_cache_structure(window,qtbot,tmp_path):
    install_network(window,lambda *a:(b'data',200));results=[]
    window.web.request('https://example.com/bad.apk',results.append,destination=tmp_path/'size.apk',expected_size=999)
    qtbot.waitUntil(lambda:bool(results));assert results[0]['error'] and not (tmp_path/'size.apk').exists()
    cache=v.DATA_DIR/'downloads'/'index.json';cache.parent.mkdir(exist_ok=True,parents=True);cache.write_text('[]');assert v.DownloadService(window).index=={}
    profile=v.default_catalog();profile['apps']=[{'id':42,'name':'bad','source':'https://example.com/app.apk'}]
    with pytest.raises(ValueError):v.validate_catalog(profile)


def test_missing_device_state_does_not_start_install(window,qtbot):
    original=window.demo_backend.response;calls=[]
    def response(args):
        calls.append(args)
        if 'get-state' in args:return v.Result(False,stderr=b'device offline',code=1)
        return original(args)
    window.demo_backend.response=response;page=window.pages['installer'];page.add_paths([Path(__file__).parent/'fixtures'/'upstream.apk']);page.install();qtbot.waitUntil(lambda:not window.busy,timeout=4000)
    assert not any('install' in a for a in calls)


def test_close_during_stopped_android_runs_cleanup(window,qtbot):
    window.confirm=lambda _:True;recipe=v.SystemRecipe(window,'settings');window.recipe=recipe;recipe.start();qtbot.waitUntil(lambda:recipe.android_stopped,timeout=5000)
    window.close();qtbot.waitUntil(lambda:window.closing,timeout=6000);assert window.demo_backend.android_running and not recipe.running


@pytest.mark.parametrize('failure',['protocol','timeout'])
def test_uncertain_install_stops_batch_without_retry(window,qtbot,tmp_path,failure):
    original=window.demo_backend.response;calls=[]
    def response(args):
        if 'install' in args:
            calls.append(args)
            return v.Result(False,stderr=b'protocol fault: Connection reset by peer') if failure=='protocol' else v.Result(False,timed_out=True)
        return original(args)
    window.demo_backend.response=response;source=Path(__file__).parent/'fixtures'/'upstream.apk';second=tmp_path/'second.apk';second.write_bytes(source.read_bytes())
    page=window.pages['installer'];page.add_paths([source,second]);page.mode.setCurrentIndex(1);page.install();qtbot.waitUntil(lambda:not window.busy,timeout=10000)
    assert len(calls)==1 and page.file_table.item(1,2).text() in ('Пропущено','Skipped')
