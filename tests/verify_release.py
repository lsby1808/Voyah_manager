"""Validate the delivered onefile against its embedded build manifest and smoke runs."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
def digest(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
source=digest(root/'voyah_manager.py');executable=root/'dist'/'Voyah Manager.exe'
build=json.loads((root/'build_manifest.json').read_text())
assert build['source_sha256']==source
version=build['version']
series='v'+version.replace('.','')
smokes={}
for name,dpr,api in [('100',1.0,30),('125',1.25,30),('150',1.5,30),('offline',1.0,0)]:
    folder=root/('qa-'+series+'-release-'+name);report=json.loads((folder/'report.json').read_text())
    assert report['version']==version and report['frozen'] and report['tabs']==8
    assert report['build']['source_sha256']==source and report['dpr']==dpr and report['profile']==api
    assert report['catalog']['repository']=='lsby1808/Voyah_manager' and report['catalog']['revision']>=1
    assert all(report['tools'].values()) and all(check['ok'] for check in report['tool_checks'].values())
    assert len(list(folder.glob('tab-*.png')))==16
    assert len(list(folder.glob('admin-*.png')))==4
    smokes[name]=report
suite=ET.parse(root/('qa-'+series+'-tests.xml')).find('testsuite')
count=int(suite.get('tests'))
assert count>=124 and suite.get('failures')=='0' and suite.get('errors')=='0'
count=len({(case.get('classname'),case.get('name')) for case in suite.findall('testcase')})
publication_path=root/('qa-'+series+'-publication.json')
publication=json.loads(publication_path.read_text()) if publication_path.exists() else {}
manifest={'version':version,'file':executable.name,'size_bytes':executable.stat().st_size,
          'sha256':digest(executable),'source_sha256':source,'authenticode':'NotSigned',
          'unique_tests':count,'real_headunit_tested':False,
          'github_publication_tested':{'application_admin':'mock API','codex_connector':'actual repository commits','public_catalog':'actual frozen EXE HTTPS read'},
          'github_release':publication,
          'build':build,'smoke_checks':smokes}
(root/'dist'/'release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'dist'/'Voyah Manager.exe.sha256').write_text(manifest['sha256']+'  '+executable.name+'\n',encoding='ascii')
print(json.dumps({key:manifest[key] for key in ('version','size_bytes','sha256','source_sha256','unique_tests')},indent=2))
