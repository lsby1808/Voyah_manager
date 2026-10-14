"""Reproducible Windows packaging. Run with .venv/Scripts/python.exe."""
import argparse
import hashlib
import json
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--onedir', action='store_true')
parser.add_argument('--distpath', default='dist')
args = parser.parse_args()

subprocess.run([sys.executable, str(ROOT / 'voyah_manager.py'), '--export-icon', str(ROOT / 'voyah.ico')], check=True)
legal = ROOT / 'tools' / 'licenses' / 'qt'
legal.mkdir(parents=True, exist_ok=True)
for name in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6'):
    dist = importlib.metadata.distribution(name)
    for entry in dist.files or []:
        if 'licenses/' in str(entry).lower() or Path(str(entry)).name.upper().startswith(('LICENSE', 'COPYING')):
            source = Path(dist.locate_file(entry))
            if source.is_file():
                dest = legal / name / str(entry).replace('..', '_')
                dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)

version = ROOT / 'version_info.txt'
manifest = {'version':'2.1.2','source_sha256':hashlib.sha256((ROOT/'voyah_manager.py').read_bytes()).hexdigest(),
            'python':sys.version.split()[0],'dependencies':{name:importlib.metadata.version(name) for name in ('PySide6','PyInstaller')}}
(ROOT/'build_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
version.write_text("""VSVersionInfo(ffi=FixedFileInfo(filevers=(2,1,2,0), prodvers=(2,1,2,0), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName','Voyah Manager'), StringStruct('FileDescription','Voyah Manager - Android Automotive Workbench'), StringStruct('FileVersion','2.1.2'), StringStruct('InternalName','Voyah Manager'), StringStruct('OriginalFilename','Voyah Manager.exe'), StringStruct('ProductName','Voyah Manager'), StringStruct('ProductVersion','2.1.2')])]), VarFileInfo([VarStruct('Translation',[1033,1200])])])""", encoding='utf-8')
command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
    '--distpath', args.distpath,
    '--onedir' if args.onedir else '--onefile', '--name', 'Voyah Manager',
    '--icon', str(ROOT / 'voyah.ico'), '--version-file', str(version),
    '--add-data', str(ROOT / 'tools') + ';tools',
    '--add-data', str(ROOT / 'THIRD_PARTY_NOTICES.txt') + ';.',
    '--add-data', str(ROOT / 'README_RU.md') + ';.',
    '--add-data', str(ROOT / 'build_manifest.json') + ';.',
    '--exclude-module', 'PySide6.QtWebEngineCore', '--exclude-module', 'PySide6.QtWebEngineWidgets',
    '--exclude-module', 'PySide6.QtQml', '--exclude-module', 'PySide6.QtQuick',
    '--exclude-module', 'pytest', str(ROOT / 'voyah_manager.py')]
# Qt 6.10 needs a newer MSVC runtime than Temurin's bundled copy. Explicit
# root binaries prevent PyInstaller resolving Qt against Java's older runtime.
qt_dir = Path(importlib.metadata.distribution('PySide6_Essentials').locate_file('PySide6'))
for dll in ('MSVCP140.dll', 'MSVCP140_1.dll', 'MSVCP140_2.dll', 'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll'):
    if (qt_dir / dll).exists(): command[3:3] = ['--add-binary', str(qt_dir / dll) + ';.']
environment = os.environ.copy()
# The Codex workspace PATH also contains Poppler's ICU DLLs. Qt on Windows
# imports the OS ICU forwarding library, so those unrelated DLLs must not be
# discovered and bundled instead of the Windows system component.
windows_dir = Path(os.environ.get('SystemRoot', 'C:/Windows'))
environment['PATH'] = os.pathsep.join([str(Path(sys.executable).parent), str(qt_dir), str(windows_dir / 'System32'), str(windows_dir)])
subprocess.run(command, cwd=ROOT, env=environment, check=True)
