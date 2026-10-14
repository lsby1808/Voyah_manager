"""Fetch and package upstream Android / Java tools, retaining notices and hashes."""
from pathlib import Path
import hashlib, json, shutil, urllib.request, zipfile, xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / '.downloads'
TOOLS = ROOT / 'tools'
CACHE.mkdir(exist_ok=True)
TOOLS.mkdir(exist_ok=True)
LOCK = json.loads((ROOT / 'tools.lock.json').read_text(encoding='utf-8')) if (ROOT / 'tools.lock.json').exists() else {}

def download(url, name):
    locked = next((item for item in LOCK.values() if isinstance(item, dict) and item.get('name') == name), None)
    if locked: url = locked['url']
    dest = CACHE / name
    if not dest.exists():
        print('Downloading', name, flush=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'VoyahManager-build/1.0'})
        with urllib.request.urlopen(req, timeout=90) as response, dest.with_suffix('.part').open('wb') as out:
            shutil.copyfileobj(response, out)
        dest.with_suffix('.part').replace(dest)
    if locked and hashlib.sha256(dest.read_bytes()).hexdigest() != locked['sha256']:
        raise RuntimeError('Pinned archive checksum mismatch: ' + name + '. Review tools.lock.json before updating tools.')
    return dest

platform = download('https://dl.google.com/android/repository/platform-tools-latest-windows.zip', 'platform-tools.zip')
with zipfile.ZipFile(platform) as z:
    for name in z.namelist():
        if name.rsplit('/', 1)[-1] in ('adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll', 'NOTICE.txt', 'source.properties'):
            dest = TOOLS / 'adb' / name.rsplit('/', 1)[-1]
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(z.read(name))

bundle = download('https://github.com/google/bundletool/releases/download/1.18.3/bundletool-all-1.18.3.jar', 'bundletool-1.18.3.jar')
shutil.copyfile(bundle, TOOLS / 'bundletool.jar')
with zipfile.ZipFile(bundle) as z:
    names = [n for n in z.namelist() if n.endswith('aapt2.exe')]
    if not names:
        raise RuntimeError('bundletool has no Windows AAPT2: inspect upstream archive')
    (TOOLS / 'aapt2.exe').write_bytes(z.read(names[0]))
    notices = [n for n in z.namelist() if ('license' in n.lower() or 'notice' in n.lower()) and not n.endswith('/')]
    legal = TOOLS / 'licenses' / 'bundletool'
    legal.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(notices):
        (legal / (str(i) + '-' + name.rsplit('/', 1)[-1])).write_bytes(z.read(name))
download('https://raw.githubusercontent.com/google/bundletool/1.18.3/LICENSE', 'bundletool-LICENSE.txt')
shutil.copyfile(CACHE / 'bundletool-LICENSE.txt', TOOLS / 'licenses' / 'bundletool-LICENSE.txt')

meta_url = 'https://api.adoptium.net/v3/assets/latest/17/hotspot?architecture=x64&image_type=jre&os=windows&vendor=eclipse'
try:
    if LOCK.get('java'):
        pin = LOCK['java']; meta = {'binary':{'package':{'name':pin['name'],'link':pin['url'],'checksum':pin['sha256']}},'version':{'semver':pin['version']}}
    else:
        with urllib.request.urlopen(urllib.request.Request(meta_url, headers={'User-Agent': 'VoyahManager-build/2.0'}), timeout=90) as r:
            meta = json.load(r)[0]
    package = meta['binary']['package']
    java_version = meta['version']['semver']
except Exception:
    req = urllib.request.Request('https://api.github.com/repos/adoptium/temurin17-binaries/releases/latest', headers={'User-Agent': 'VoyahManager-build/1.0'})
    with urllib.request.urlopen(req, timeout=90) as r:
        release = json.load(r)
    asset = next(a for a in release['assets'] if a['name'].startswith('OpenJDK17U-jre_x64_windows_hotspot_') and a['name'].endswith('.zip'))
    checksum_url = next(a['browser_download_url'] for a in release['assets'] if a['name'] == asset['name'] + '.sha256.txt')
    with urllib.request.urlopen(checksum_url, timeout=90) as r:
        checksum = r.read().decode().split()[0]
    package = {'name': asset['name'], 'link': asset['browser_download_url'], 'checksum': checksum}
    java_version = release['tag_name']
jre = download(package['link'], package['name'])
if hashlib.sha256(jre.read_bytes()).hexdigest() != package['checksum']:
    raise RuntimeError('Java archive checksum mismatch')
with zipfile.ZipFile(jre) as z:
    prefix = z.namelist()[0].split('/')[0] + '/'
    for entry in z.infolist():
        relative = entry.filename.removeprefix(prefix)
        if not relative or entry.is_dir():
            continue
        dest = TOOLS / 'jre' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(entry))

manifest = {p.relative_to(TOOLS).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in TOOLS.rglob('*') if p.is_file() and p.name != 'manifest.json'}
(TOOLS / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
(TOOLS / 'versions.json').write_text(json.dumps({'bundletool': '1.18.3', 'java': java_version,
    'sources': ['https://developer.android.com/tools/releases/platform-tools', package['link'],
    'https://github.com/google/bundletool/releases/tag/1.18.3']}, indent=2), encoding='utf-8')
print('Packaged', len(manifest), 'files;', sum(p.stat().st_size for p in TOOLS.rglob('*') if p.is_file()) // 1024**2, 'MiB', flush=True)
