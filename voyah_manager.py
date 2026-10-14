"""Voyah Manager 2.0 — single-file PySide6 Android Automotive workbench.

Run: python voyah_manager.py | --demo | --smoke-dir DIRECTORY
All device commands are asynchronous QProcess jobs. No host command shell is used.
"""
from __future__ import annotations

import argparse
import base64
import copy
import functools
import hmac
import secrets
from urllib.parse import urlparse, quote, unquote, urlencode
import codecs
import ctypes
import hashlib
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shlex
import shutil
import stat
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import (Qt, QObject, Signal, QProcess, QTimer, QThreadPool,
                            QRunnable, QSettings, QUrl, QSize, QRect, QPoint)
from PySide6.QtGui import (QFont, QIcon, QPainter, QColor, QPixmap, QDesktopServices,
                           QTextCursor, QKeySequence, QShortcut, QPen)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QPlainTextEdit, QTabWidget, QFrame, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QInputDialog,
    QProgressBar, QSplitter, QAbstractItemView, QSpinBox, QMenu, QDialog,
    QDialogButtonBox, QListWidget, QListWidgetItem, QStyle, QStackedWidget, QFormLayout, QToolButton, QLayout, QWidgetItem, QSizePolicy)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

VERSION = '2.0.1'
APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
DATA_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Voyah Manager'
PACKAGE_RE = re.compile(r'^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+$', re.ASCII)
COMPONENT_RE = re.compile(r'([\w.]+)/(\.?[\w.$]+)')
MAX_LOG_LINES = 6000

# English counterparts of user-facing strings. Dynamic text is translated before formatting.
EN = {
 'Подключение':'Connection', 'Отключено':'Disconnected', 'Готово':'Ready', 'Обновить':'Refresh',
 'Выбрать ADB':'Choose ADB', 'Встроенный ADB':'Bundled ADB', 'Подключить':'Connect',
 'Перезапуск ADB':'Restart ADB', 'Перезагрузка':'Reboot', 'Обычная перезагрузка':'Reboot device',
 'Перезагрузка в Recovery':'Reboot to recovery', 'Перезагрузка в Bootloader':'Reboot to bootloader',
 'Рестарт Android (stop/start)':'Restart Android (stop/start)', 'Назад':'Back', 'Домой':'Home',
 'Недавние':'Recents', 'Скриншот':'Screenshot', 'Отмена':'Cancel', 'Стоп':'Stop', 'Старт':'Start',
 'Инспектор':'Inspector', 'Установщик APK':'APK installer', 'Файлы':'Files',
 'Приложения':'Applications', 'Твики Voyah':'Voyah tweaks', 'Терминал ADB':'ADB terminal',
 'Нет подключённых устройств':'No connected devices', 'Подключено':'Connected',
 'Не авторизовано — подтвердите RSA на ГУ':'Unauthorized — accept the RSA prompt on the head unit',
 'Устройство не отвечает':'Device offline', 'Выполняется…':'Working…', 'Ошибка':'Error',
 'Подтверждение':'Confirmation', 'Копировать':'Copy', 'Сохранить':'Save', 'Очистить':'Clear',
 'Открыть журнал':'Open log', 'Отменить задание':'Cancel task',
 'Диагностика • управление • мультимедиа':'Diagnostics • control • multimedia',
 'ADB не найден. Выберите adb.exe.':'ADB not found. Choose adb.exe.',
 'Сначала подключите устройство.':'Connect a device first.',
 'Дождитесь завершения или отмените текущее задание.':'Wait for completion or cancel the current task.',
 'Подключите ГУ по USB или Wi-Fi, чтобы начать.':'Connect the head unit by USB or Wi-Fi to begin.',
 'Что сейчас на экранах?':'What is on the displays?', 'Сканировать экраны':'Scan displays',
 'Нет данных — выполните сканирование':'No data — scan the displays', 'Все события':'All events',
 'Перехват кнопки руля':'Steering wheel capture', 'Перехватить 6 секунд':'Capture for 6 seconds',
 'Запуски экранов':'Activity launches', 'Руль / MCU / ассистенты':'Wheel / MCU / assistants',
 'Сервисы / Broadcast':'Services / broadcasts', 'Полный лог':'Full log',
 'Сохранить и открыть в Блокноте':'Save and open in Notepad',
 'Live-мониторинг':'Live monitoring', 'Фильтр: слова через запятую':'Filter: comma-separated keywords',
 'Пакеты и интенты':'Packages and intents', 'Поиск пакета':'Search packages',
 'Найти':'Find', 'Дамп пакета':'Dump package', 'Нажмите кнопку на руле сейчас…':'Press the steering wheel button now…',
 'События не найдены. CAN/MCU может обходить Android input и публичные логи.':'No matching events. CAN/MCU may bypass Android input and public logs.',
 'Режим установки':'Install mode', 'Одиночный APK':'Single APK',
 'Пакетная установка':'Batch install', 'Split / APKS / XAPK / APKM':'Split / APKS / XAPK / APKM',
 'Добавить файлы':'Add files', 'Добавить папку':'Add folder', 'Установить':'Install',
 'Файл':'File', 'Размер':'Size', 'Статус':'Status', 'В очереди':'Queued',
 'Перетащите APK или архивы сюда':'Drop APK files or archives here',
 'Переустановка (-r)':'Reinstall (-r)', 'Понижение версии (-d)':'Downgrade (-d)',
 'Выдать разрешения (-g)':'Grant permissions (-g)', 'Успешно':'Success', 'Пропущено':'Skipped',
 'Подготовка APK…':'Preparing APKs…', 'Выберите файлы для установки.':'Choose files to install.',
 'Выбор компонентов':'Select components', 'Выберите один совместимый base и нужные splits.':'Select one compatible base and required splits.',
 'Перенести OBB в память ГУ?':'Copy OBB files to the head unit?',
 'Приложение установлено; перенос OBB завершён отдельно.':'App installed; OBB copy completed separately.',
 'Путь на ГУ':'Device path', 'Вверх':'Up', 'Имя':'Name', 'Тип':'Type', 'Дата':'Modified',
 'Папка':'Directory', 'Ссылка':'Symlink', 'Загрузить в ГУ':'Push to device', 'Скачать на ПК':'Pull to PC',
 'Создать папку':'New folder', 'Переименовать':'Rename', 'Удалить':'Delete', 'Установить APK':'Install APK',
 'Новая папка':'New folder', 'Новое имя':'New name', 'Выберите файл или папку.':'Select a file or directory.',
 'Недопустимое имя.':'Invalid name.', 'Удалить выбранные объекты безвозвратно?':'Permanently delete selected items?',
 'Все':'All', 'Сторонние':'Third-party', 'Системные':'System', 'Отключённые':'Disabled',
 'Пакет':'Package', 'Поиск по имени пакета':'Search package name', 'Запустить':'Launch',
 'Остановить':'Force stop', 'Очистить данные и кэш':'Clear data and cache', 'Заморозить':'Disable',
 'Разморозить':'Enable', 'Экспорт APK':'Export APK', 'Центральный':'Center', 'Пассажирский':'Passenger',
 'Выберите пакет.':'Select a package.', 'Данные приложения будут удалены. Продолжить?':'App data will be deleted. Continue?',
 'Отключить выбранный пакет?':'Disable selected package?', 'Удалить выбранное приложение?':'Uninstall selected application?',
 'Пакет содержит splits. Скачать полный комплект?':'Package contains splits. Download the complete set?',
 'Масштаб и дисплеи':'Density and displays', 'Все мультимедийные':'All multimedia',
 'Приборная панель':'Instrument cluster', 'Применить DPI':'Apply DPI', 'Заводской DPI':'Factory DPI',
 'Сопоставить экраны':'Map displays', 'Приложение для твиков':'Target application',
 'Аудиофокус и разрешения':'Audio focus and permissions',
 'Не глушить музыку':'Ignore audio focus', 'Вернуть аудиофокус':'Allow audio focus',
 'Микрофон':'Microphone', 'Поверх окон':'Overlay', 'Белый список питания':'Power whitelist',
 'Сеть и система':'Network and system', 'Включить':'Enable', 'Выключить':'Disable',
 'Восстановить':'Restore', 'Отключить Doze':'Disable Doze', 'Включить Doze':'Enable Doze',
 'Скрытые настройки Android':'Android settings',
 'Изменить DPI приборной панели?':'Change instrument cluster density?',
 'Прошивка не поддерживает DPI по дисплеям. Операция недоступна.':'Firmware does not support per-display density. Operation unavailable.',
 'Команда ADB или adb shell…':'ADB command or adb shell…', 'Выполнить':'Run',
 'Интерактивная shell':'Interactive shell', 'Отправить':'Send',
 'О приложении':'About', 'Закрыть':'Close',
 'Расширенный режим':'Advanced mode', 'Проверить su':'Test su', 'Обычный shell':'Standard shell',
 'Повысить права через adb root? adbd будет перезапущен.':'Elevate via adb root? adbd will restart.',
 'Проверить su на ГУ? Может потребоваться разрешение на экране.':'Test su on the head unit? On-screen authorization may be required.',
 'Вернуть adbd к обычным правам?':'Return adbd to standard privileges?',
 'Сеанс не имеет Root-прав.':'Session does not have root privileges.',
 'Root подтверждён':'Root verified', 'Журнал операций':'Operation log',
 'Демонстрационный режим • команды имитируются':'Demo mode • commands are simulated',
 'Сохранено: {path}':'Saved: {path}', 'Готово: {name}':'Completed: {name}',
 'Ошибка: {name}':'Failed: {name}', 'Отменено':'Cancelled', 'Истекло время ожидания':'Timed out',
 'Запрещено прошивкой или недостаточно прав.':'Firmware restriction or insufficient privileges.',
 'Приложение требует более новую версию Android (minSdk выше API ГУ).':'App requires a newer Android version (minSdk exceeds head unit API).',
 'APK предназначен для другой архитектуры процессора.':'APK is built for a different CPU architecture.',
 'Подпись APK отличается от установленного приложения.':'APK signature differs from the installed application.',
 'Понижение версии запрещено прошивкой или типом приложения.':'Downgrade is disallowed by firmware or application type.',
 'Не хватает обязательных split-компонентов.':'Required split components are missing.',
 'Нет свободного места на ГУ.':'Insufficient storage on device.',
 'Установка не подтверждена Package Manager.':'Installation was not confirmed by Package Manager.',
 'Пустой или повреждённый архив.':'Empty or damaged archive.',
 'Архив содержит небезопасный путь или ссылку.':'Archive contains an unsafe path or link.',
 'Архив превышает допустимый размер распаковки (8 ГБ).':'Archive exceeds the extraction limit (8 GB).',
 'В архиве нет APK.':'No APK files in archive.',
 'APK имеют разные package/versionCode.':'APKs have different package/versionCode values.',
 'Не найден единственный base APK.':'Exactly one base APK is required.',
 'Отсутствуют зависимости splits: {names}':'Missing split dependencies: {names}',
 'Команда завершилась с ошибкой.':'Command failed.',
 'Устройство отключилось; оставшиеся задания остановлены.':'Device disconnected; remaining jobs stopped.',
 'Только чтение: отсутствует разрешение доступа.':'Read access denied.',
 'Выберите один APK в одиночном режиме.':'Select one APK in single mode.',
 'Архивы устанавливаются в режиме Split.':'Install archives in Split mode.',
 'Для продолжения нужен один комплект приложения.':'One application set is required.',
 'Восстанавливать нечего.':'No saved state to restore.',
 'Состояние не подтверждено устройством.':'Device state could not be verified.',
 'Захват этого экрана недоступен на прошивке.':'Capturing this display is unavailable on the firmware.',
 'Основной экран SurfaceFlinger':'Default SurfaceFlinger display',
 'Перезапустить ГУ выбранным способом?':'Reboot the head unit using the selected method?',
 'Остановить текущие задания и закрыть программу?':'Stop running tasks and close the application?',
 'Повторить':'Retry', 'Нужны Android SDK инструменты в папке tools.':'Android SDK tools are required in the tools directory.',
 'Копирование OBB завершилось ошибкой; APK уже установлен.':'OBB copy failed; APK is already installed.',
 'Не удалось прочитать манифест APK.':'Cannot read APK manifest.',
 'Значение DPI должно быть от 72 до 1000.':'Density must be between 72 and 1000.',
 'Системные пакеты могут отвечать за функции автомобиля.':'System packages may control vehicle functions.',
 'Этот пакет не содержит launcher Activity.':'This package has no launcher activity.',
 'Требуется выбрать устройство USB.':'Select a USB device.',
 'Введите корректный IP-адрес и порт.':'Enter a valid IP address and port.',
    'Совместимость с реальным ГУ ещё не проверена.':'Compatibility with a real head unit has not been verified yet.',
    'Из отчёта установщика; применимость зависит от прошивки.':'From the installer analysis; applicability depends on firmware.',
    'Выбрать физический дисплей':'Choose a physical display',
    'Физические дисплеи не обнаружены. Используйте основной экран SurfaceFlinger.':'No physical displays found. Use the default SurfaceFlinger display.',
}

def tr(text: str, lang: str = 'ru', **values) -> str:
    value = EN.get(text, text) if lang == 'en' else text
    return value.format(**values) if values else value

def remote_command(args) -> str:
    return ' '.join(shlex.quote(str(arg)) for arg in args)

def normalize_endpoint(value: str) -> str:
    value = value.strip()
    if value.startswith('['):
        match = re.fullmatch(r'\[([^]]+)](?::(\d+))?', value)
        if not match:
            raise ValueError('Введите корректный IP-адрес и порт.')
        ip = ipaddress.IPv6Address(match[1]); port = int(match[2] or 5555)
        host = f'[{ip}]'
    else:
        if value.count(':') > 1:
            host = f'[{ipaddress.IPv6Address(value)}]'; port = 5555
        else:
            bits = value.split(':'); host = str(ipaddress.IPv4Address(bits[0])); port = int(bits[1]) if len(bits) == 2 else 5555
    if not 1 <= port <= 65535:
        raise ValueError('Введите корректный IP-адрес и порт.')
    return f'{host}:{port}'

def parse_devices(text: str) -> list[dict]:
    result = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in ('device', 'offline', 'unauthorized', 'recovery', 'sideload', 'no'):
            attrs = dict(p.split(':', 1) for p in parts[2:] if ':' in p)
            result.append(dict(serial=parts[0], state=parts[1], attrs=attrs,
                               usb='usb' in attrs or (':' not in parts[0] and not parts[0].startswith('emulator-'))))
    return result

def parse_screens(window: str, activity: str) -> dict[int, dict[str, str]]:
    screens = {}
    for source, text in (('activity', activity), ('window', window)):
        display = 0 if source == 'activity' else None
        for line in text.splitlines():
            m = re.search(r'(?:Display\s*#?\s*|displayId[=: ]+|mDisplayId=)(\d+)', line, re.I)
            if m:
                display = int(m[1]); screens.setdefault(display, {})
            if re.search(r'mCurrentFocus|mFocusedApp|mResumedActivity|topResumedActivity|ResumedActivity|mFocusedActivity', line):
                component = COMPONENT_RE.search(line)
                if component:
                    assigned = display
                    if assigned is None:
                        # Global mCurrentFocus is not necessarily on Display 0 in a car.
                        matching = [d for d, entries in screens.items() if component.group(0) in entries.values()]
                        focused = re.search(r'(?:mTopFocusedDisplayId|mFocusedDisplayId)=(\d+)', window)
                        assigned = matching[0] if len(matching) == 1 else int(focused[1]) if focused else 0 if not screens else None
                    if assigned is not None: screens.setdefault(assigned, {})[source] = component.group(0)
    result = {}
    for display, entries in screens.items():
        component = entries.get('window') or entries.get('activity')
        if component:
            package, cls = component.split('/', 1)
            result[display] = {'package': package, 'activity': cls, 'component': component}
    return result

def classify_capture(text: str) -> list[list[str]]:
    patterns = (r'START u\d|am_create_activity|am_focused_activity|am_resume_activity',
                r'KeyEvent|keyCode|mcu|hardkey|voice|assistant|CarService',
                r'startService|am_broadcast|BroadcastRecord|am_create_service')
    return [[line for line in text.splitlines() if re.search(pattern, line, re.I)] for pattern in patterns]

def parse_listing(text: str) -> list[dict]:
    """Parse toybox ls -lan output. -n avoids ambiguous owner/group names."""
    entries = []
    pattern = re.compile(r'^([bcdlps-][rwxStTs-]{9}[+@.]?)\s+\d+\s+\S+\s+\S+\s+(\d+)\s+(\d{4}-\d\d-\d\d\s+\d\d:\d\d(?::\d\d)?)\s+(.*)$')
    fallback = re.compile(r'^([bcdlps-][rwxStTs-]{9}[+@.]?)\s+\d+\s+\S+\s+\S+\s+(\d+)\s+(\w{3}\s+\d+\s+[\d:]+)\s+(.*)$')
    for line in text.splitlines():
        m = pattern.match(line) or fallback.match(line)
        if not m:
            continue
        mode, size, date, name = m.groups()
        link = ''
        if mode[0] == 'l' and ' -> ' in name:
            name, link = name.rsplit(' -> ', 1)
        if name in ('.', '..'):
            continue
        entries.append({'name': name, 'size': int(size), 'date': date, 'directory': mode[0] == 'd',
                        'link': link, 'mode': mode, 'symlink': mode[0] == 'l'})
    return sorted(entries, key=lambda e: (not e['directory'], e['name'].casefold()))

def valid_name(name: str) -> bool:
    return bool(name and name not in ('.', '..') and '/' not in name and '\x00' not in name and '\n' not in name and '\r' not in name)

def safe_extract(archive: Path, dest: Path, cancel: threading.Event | None = None) -> list[Path]:
    """Extract regular ZIP files only; reject Windows/POSIX traversal, links and bombs."""
    extracted = []
    try:
        with zipfile.ZipFile(archive) as z:
            total = 0
            if len(z.infolist()) > 20000:
                raise ValueError('Архив превышает допустимый размер распаковки (8 ГБ).')
            for info in z.infolist():
                if cancel and cancel.is_set():
                    raise InterruptedError('Отменено')
                name = info.filename
                path = PurePosixPath(name)
                if ('\\' in name or ':' in name or path.is_absolute() or '..' in path.parts
                        or stat.S_ISLNK(info.external_attr >> 16)):
                    raise ValueError('Архив содержит небезопасный путь или ссылку.')
                total += info.file_size
                if total > 8 * 1024**3:
                    raise ValueError('Архив превышает допустимый размер распаковки (8 ГБ).')
                target = dest.joinpath(*path.parts)
                if not target.resolve().is_relative_to(dest.resolve()):
                    raise ValueError('Архив содержит небезопасный путь или ссылку.')
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True); continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, target.open('wb') as out:
                    while chunk := src.read(1024 * 1024):
                        if cancel and cancel.is_set():
                            raise InterruptedError('Отменено')
                        out.write(chunk)
                extracted.append(target)
    except zipfile.BadZipFile as e:
        raise ValueError('Пустой или повреждённый архив.') from e
    return extracted

def explain_error(text: str) -> str:
    for token, message in (
        ('INSTALL_FAILED_OLDER_SDK', 'Приложение требует более новую версию Android (minSdk выше API ГУ).'),
        ('NO_MATCHING_ABIS', 'APK предназначен для другой архитектуры процессора.'),
        ('UPDATE_INCOMPATIBLE', 'Подпись APK отличается от установленного приложения.'),
        ('VERSION_DOWNGRADE', 'Понижение версии запрещено прошивкой или типом приложения.'),
        ('MISSING_SPLIT', 'Не хватает обязательных split-компонпонентов.'),
        ('INSUFFICIENT_STORAGE', 'Нет свободного места на ГУ.'),
        ('permission denied', 'Запрещено прошивкой или недостаточно прав.'),
        ('SecurityException', 'Запрещено прошивкой или недостаточно прав.'),
        ('unauthorized', 'Не авторизовано — подтвердите RSA на ГУ'),
        ('device offline', 'Устройство не отвечает'),
        ('device not found', 'Устройство отключилось; оставшиеся задания остановлены.'),
        ('no devices', 'Нет подключённых устройств')):
        if token.lower() in text.lower():
            return message.replace('компонпонентов', 'компонентов')
    return 'Команда завершилась с ошибкой.'

def semantic_error(text: str) -> bool:
    return bool(re.search(r'(?im)^\s*(?:Failure\s*\[|Failed\b|Error(?: type \d+)?[: ]|Unknown (?:command|operation|package):|(?:cmd: )?Can\x27t find service|adb:\s*(?:error|failed)|SecurityException|Exception occurred|java\.lang\.|/system/bin/sh:.*(?:not found|denied)|.*Permission denied|.*not allowed)', text))

@dataclass(frozen=True)
class Target:
    serial: str
    mode: str = 'usb'
    use_d: bool = False

    def args(self):
        return ['-d'] if self.use_d else ['-s', self.serial]

@dataclass
class Profile:
    api: int = 0
    release: str = '?'
    model: str = '?'
    model_code: str = ''
    vin: str = ''
    abis: list[str] = field(default_factory=lambda: ['arm64-v8a'])
    locales: list[str] = field(default_factory=lambda: ['ru', 'en'])
    density: int = 160
    displays: list[int] = field(default_factory=lambda: [0, 1, 2])
    per_display: bool = False
    input_display: bool = False
    uid: int = 2000
    raw: dict = field(default_factory=dict)

@dataclass
class Result:
    ok: bool
    stdout: bytes = b''
    stderr: bytes = b''
    code: int = 0
    cancelled: bool = False
    timed_out: bool = False

    @property
    def text(self):
        return (self.stdout + b'\n' + self.stderr).decode('utf-8', errors='replace').strip()

class ProcessJob(QObject):
    def __init__(self, runner, program, args, callback, stream=None, timeout=30000, check=True, binary=False):
        super().__init__(runner)
        self.runner, self.callback, self.stream = runner, callback, stream
        self.check, self.binary = check, binary
        self.out = bytearray(); self.err = bytearray(); self.cancelled = False; self.timed_out = False; self.ended = False
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.proc = QProcess(self)
        self.proc.setProgram(str(program)); self.proc.setArguments([str(a) for a in args])
        self.proc.readyReadStandardOutput.connect(self.read_out)
        self.proc.readyReadStandardError.connect(self.read_err)
        self.proc.finished.connect(self.finish)
        self.proc.errorOccurred.connect(self.process_error)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.expire)
        if timeout:
            self.timer.start(timeout)
        self.proc.start()

    def read_out(self):
        chunk = bytes(self.proc.readAllStandardOutput()); self.out.extend(chunk)
        if len(self.out) > (2 * 1024**2 if self.stream else 64 * 1024**2):
            del self.out[:len(self.out) // 2]
        if self.stream and not self.binary:
            self.stream(self.decoder.decode(chunk))

    def read_err(self):
        chunk = bytes(self.proc.readAllStandardError()); self.err.extend(chunk)
        if len(self.err) > 2 * 1024**2:
            del self.err[:len(self.err) // 2]
        if self.stream:
            self.stream(chunk.decode('utf-8', 'replace'))

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.err.extend(self.proc.errorString().encode('utf-8')); self.finish(-1)

    def expire(self):
        self.timed_out = True; self.proc.kill()

    def cancel(self):
        self.cancelled = True; self.proc.kill()

    def finish(self, code=0, status=None):
        if self.ended:
            return
        self.ended = True; self.timer.stop(); self.read_out(); self.read_err()
        result = Result(code == 0 and not self.cancelled and not self.timed_out, bytes(self.out), bytes(self.err), code, self.cancelled, self.timed_out)
        if self.check and semantic_error(result.text):
            result.ok = False
        self.runner.jobs.discard(self)
        if self.callback:
            self.callback(result)
        self.deleteLater()

class Runner(QObject):
    def __init__(self, parent=None):
        super().__init__(parent); self.jobs = set()

    def run(self, program, args, callback, **kwargs):
        job = ProcessJob(self, program, args, callback, **kwargs); self.jobs.add(job); return job

    def cancel_all(self):
        for job in list(self.jobs):
            job.cancel()

class WorkerSignals(QObject):
    done = Signal(object, object)

class Worker(QRunnable):
    def __init__(self, fn, callback):
        super().__init__(); self.fn = fn; self.signals = WorkerSignals(); self.signals.done.connect(callback)

    def run(self):
        try:
            result = self.fn(); self.signals.done.emit(result, None)
        except Exception as error:
            self.signals.done.emit(None, error)

class Tools:
    def __init__(self):
        self.base = RESOURCE_DIR / 'tools'

    def path(self, name):
        return self.base / name

    def bundled_adb(self):
        manifest = json.loads((self.base / 'manifest.json').read_text('utf-8'))
        digest = manifest['adb/adb.exe'][:16]
        dest = DATA_DIR / 'tools' / 'adb' / digest
        dest.mkdir(parents=True, exist_ok=True)
        for relative, expected in manifest.items():
            if not relative.startswith('adb/'):
                continue
            target = dest / Path(relative).name
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                source = self.base / relative
                if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                    raise ValueError('Bundled ADB integrity check failed')
                temporary = target.with_suffix('.new'); shutil.copyfile(source, temporary); temporary.replace(target)
        return str(dest / 'adb.exe')

    def find_adb(self, saved=''):
        choices = [saved, r'C:\adb\adb.exe', str(APP_DIR / 'adb.exe'), shutil.which('adb') or '']
        for choice in choices:
            if choice and Path(choice).is_file():
                return choice
        return ''

STYLE = """
QWidget { background: #121417; color: #E5EBF2; font-family: 'Segoe UI'; font-size: 11pt; }
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget { background: #121417; }
QFrame#card, QFrame#header { background: #1C1F26; border: 1px solid #2B303A; border-radius: 12px; }
QFrame#card QLabel, QFrame#header QLabel { background: transparent; }
QLabel#title { font-size: 22pt; font-weight: 700; letter-spacing: 1px; }
QLabel#subtitle { color: #B1BED0; font-size: 10pt; }
QLabel#section { font-size: 13pt; font-weight: 600; color: #F2F7FC; }
QLabel#eyebrow { color: #00B4D8; font-size: 8pt; font-weight: 700; letter-spacing: 2px; }
QPushButton { background: #262C36; border: 1px solid #343D4C; border-radius: 7px; padding: 7px 12px; min-height: 20px; }
QPushButton:hover { background: #323C4A; border-color: #00B4D8; }
QPushButton:pressed { background: #164754; }
QPushButton:disabled { color: #626C7A; border-color: #282D36; background: #20252D; }
QPushButton[accent='true'] { background: #00A2C2; color: #06151C; border-color: #00B4D8; font-weight: 700; }
QPushButton[accent='true']:disabled { color: #8995A6; border-color: #343D4C; background: #252C35; }
QPushButton[danger='true'] { color: #FFA4AA; border-color: #71414A; }
QLineEdit, QComboBox, QSpinBox { background: #14191F; border: 1px solid #343D4C; border-radius: 6px; padding: 7px; selection-background-color: #006D85; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #00B4D8; }
QComboBox QAbstractItemView { background: #20262F; selection-background-color: #165364; }
QTabWidget::pane { border: 0; padding-top: 12px; }
QTabBar::tab { background: #1A1E25; color: #92A0B3; padding: 11px 18px; border-bottom: 2px solid transparent; margin-right: 4px; }
QTabBar::tab:selected { color: #7BE6FB; background: #1D2C35; border-bottom: 2px solid #00B4D8; }
QPlainTextEdit { background: #0F1319; border: 1px solid #2B3441; border-radius: 7px; padding: 8px; font-family: Consolas; font-size: 9pt; selection-background-color: #105269; }
QTableWidget, QListWidget { background: #161B22; alternate-background-color: #1C222B; border: 1px solid #2B3441; border-radius: 7px; gridline-color: #272F3A; selection-background-color: #174453; }
QListWidget#sidebar::item { padding: 5px 4px; min-height: 18px; border-radius: 5px; }
QListWidget#sidebar::item:selected { background: #174453; color: #A5F0FF; }
QHeaderView::section { background: #232B35; border: 0; padding: 9px; color: #99AFC3; font-weight: 600; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #455267; border-radius: 4px; background: #151B22; }
QCheckBox::indicator:checked { background: #00A2C2; border-color: #71E5F5; }
QProgressBar { border: 0; border-radius: 5px; background: #26303B; text-align: center; min-height: 10px; color: #CBE7EF; }
QProgressBar::chunk { background: #00B4D8; border-radius: 4px; }
QScrollBar:vertical { background: #151A21; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #3A4657; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenu { background: #222A34; border: 1px solid #3B4655; padding: 5px; }
QMenu::item { padding: 8px 22px; }
QMenu::item:selected { background: #164B5C; }
QSplitter::handle { background: #252D38; height: 5px; }
QToolTip { background: #29333F; color: #E7F6FA; border: 1px solid #00B4D8; padding: 6px; }
"""

def make_icon() -> QIcon:
    pix = QPixmap(128, 128); pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor('#1C2633')); p.setPen(Qt.PenStyle.NoPen); p.drawRoundedRect(1, 1, 126, 126, 27, 27)
    p.setPen(QPen(QColor('#00B4D8'), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawLine(26, 39, 62, 92); p.drawLine(62, 92, 102, 34)
    p.setPen(QPen(QColor('#97E8F7'), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)); p.drawLine(44, 31, 63, 58); p.drawLine(63, 58, 79, 31)
    p.end(); return QIcon(pix)

def logbox():
    w = QPlainTextEdit(); w.setReadOnly(True); w.setMaximumBlockCount(MAX_LOG_LINES); return w

def append_log(widget, text):
    if not text:
        return
    cursor = widget.textCursor(); cursor.movePosition(QTextCursor.MoveOperation.End); cursor.insertText(text)
    widget.setTextCursor(cursor); widget.ensureCursorVisible()

def table(columns):
    w = QTableWidget(0, len(columns)); w.setHorizontalHeaderLabels(columns)
    w.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    w.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); w.setAlternatingRowColors(True)
    w.verticalHeader().hide(); w.verticalHeader().setDefaultSectionSize(34); w.horizontalHeader().setStretchLastSection(True)
    w.horizontalHeader().setMinimumSectionSize(130)
    return w

class FlowLayout(QLayout):
    """Wrap action rows on narrow windows without hiding individual actions."""
    def __init__(self):
        super().__init__(); self.items = []; self.setContentsMargins(0,0,0,0); self.setSpacing(8)
    def addItem(self,item): self.items.append(item)
    def addStretch(self,stretch=0): pass
    def count(self): return len(self.items)
    def itemAt(self,index): return self.items[index] if 0 <= index < len(self.items) else None
    def takeAt(self,index): return self.items.pop(index) if 0 <= index < len(self.items) else None
    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self,width): return self.arrange(QRect(0,0,width,0),True)
    def setGeometry(self,rect): super().setGeometry(rect); self.arrange(rect,False)
    def sizeHint(self): return self.minimumSize()
    def minimumSize(self):
        size = QSize()
        for item in self.items: size = size.expandedTo(item.minimumSize())
        return size
    def arrange(self,rect,test):
        x,y,line = rect.x(),rect.y(),0
        for item in self.items:
            if item.isEmpty(): continue
            size = item.sizeHint(); width = min(size.width(),max(1,rect.width()))
            widget = item.widget()
            if isinstance(widget,QLineEdit): width = min(max(210,width),max(1,rect.width()))
            if x > rect.x() and x+width > rect.right()+1: x = rect.x(); y += line+self.spacing(); line = 0
            if not test: item.setGeometry(QRect(QPoint(x,y),QSize(width,size.height())))
            x += width+self.spacing(); line = max(line,size.height())
        return y+line-rect.y()

class Page(QWidget):
    def __init__(self, main):
        super().__init__(); self.main = main; self.bindings = []; self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0); self.layout.setSpacing(14)

    def t(self, text, **values): return self.main.t(text, **values)

    def bind(self, obj, key, method='setText'):
        self.bindings.append((obj, key, method)); getattr(obj, method)(self.t(key)); return obj

    def button(self, key, callback, accent=False, danger=False):
        w = self.bind(QPushButton(), key); w.clicked.connect(callback)
        if getattr(callback, 'feature_id', None): w.setProperty('feature', callback.feature_id)
        if accent: w.setProperty('accent', True)
        if danger: w.setProperty('danger', True)
        return w

    def label(self, key, style=None):
        w = self.bind(QLabel(), key)
        if style: w.setObjectName(style)
        return w

    def edit(self, placeholder=''):
        w = QLineEdit()
        if placeholder: self.bind(w, placeholder, 'setPlaceholderText')
        return w

    def card(self, title):
        frame = QFrame(); frame.setObjectName('card'); layout = QVBoxLayout(frame)
        group = {'Масштаб и дисплеи':'tweaks.dpi','Аудиофокус и разрешения':'tweaks.permissions','Сеть и система':'tweaks.network'}.get(title)
        if group: frame.setProperty('feature',group)
        layout.setContentsMargins(18, 16, 18, 16); layout.setSpacing(12)
        if title: layout.addWidget(self.label(title, 'section'))
        self.layout.addWidget(frame); return layout

    def row(self, layout, *widgets):
        row = FlowLayout()
        for w in widgets:
            if isinstance(w, QWidget): row.addWidget(w)
        layout.addLayout(row); return row

    def retranslate(self):
        for obj, key, method in self.bindings:
            getattr(obj, method)(self.t(key))

    def save_text(self, text, name='voyah-log.txt', open_notepad=False):
        file, _ = QFileDialog.getSaveFileName(self, self.t('Сохранить'), str(Path.home() / 'Documents' / name), 'Text (*.txt);;All (*)')
        if file:
            try:
                Path(file).write_text(text, encoding='utf-8')
                if open_notepad:
                    QProcess.startDetached(str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32' / 'notepad.exe'), [file])
                self.main.notice(self.t('Сохранено: {path}', path=file))
            except OSError as error:
                self.main.error(str(error))

class DemoJob(QObject):
    def __init__(self, backend, args, callback, stream=None, **kwargs):
        super().__init__(backend); self.backend = backend; self.callback = callback; self.ended = False
        self.proc = None; self.timer = QTimer(self); self.count = 0; self.stream = stream
        if stream and any('logcat' in a or 'getevent' in a for a in args) and '-d' not in args[-7:]:
            self.timer.timeout.connect(self.tick); self.timer.start(190)
        else:
            QTimer.singleShot(160, lambda: self.finish(backend.response(args)) if not self.ended else None)

    def tick(self):
        self.count += 1
        lines = ['ActivityManager: START u0 {cmp=com.voyah.music/.MainActivity} displayId=1',
                 'CarService: MCU hardkey keyCode=79 action=DOWN', 'VoiceService: assistant startService request',
                 'InputReader: KeyEvent keyCode=85', '[  583.320] /dev/input/event2: EV_KEY KEY_PLAYPAUSE DOWN']
        if self.stream: self.stream(time.strftime('%m-%d %H:%M:%S') + '  ' + lines[self.count % len(lines)] + '\n')

    def finish(self, result):
        if self.ended: return
        self.ended = True; self.timer.stop(); self.backend.jobs.discard(self)
        if self.stream and result.stdout: self.stream(result.stdout.decode('utf-8', 'replace') + '\n')
        if self.callback: self.callback(result)
        self.deleteLater()

    def cancel(self): self.finish(Result(False, cancelled=True))

class DemoBackend(QObject):
    def __init__(self, parent):
        super().__init__(parent); self.jobs = set(); self.settings = {}; self.root = False; self.installed_versions = {}; self.pending_install = None; self.install_disabled = 'true'
        self.files = {path: ('stock-'+str(index)).encode() for index,(_,path) in enumerate(KEYBOARD_PATHS)}
        self.files.update({SETTINGS_DB:b'SQLite format 3\x00demo-settings',SETTINGS_DB+'-wal':b'demo-wal',SETTINGS_DB+'-shm':b'demo-shm'})
        self.selinux = 'Enforcing'; self.android_running = True

    def run(self, args, callback, **kwargs):
        job = DemoJob(self, args, callback, **kwargs); self.jobs.add(job); return job

    def response(self, args):
        raw = ' '.join(args); command = args[-1] if 'shell' in args else raw
        out = ''
        if 'pull' in args:
            source,dest = args[-2:]
            if source not in self.files: return Result(False,stderr=b'remote file does not exist',code=1)
            Path(dest).parent.mkdir(parents=True,exist_ok=True); Path(dest).write_bytes(self.files[source]); return Result(True,b'1 file pulled')
        if 'push' in args:
            source,dest = args[-2:]; self.files[dest] = Path(source).read_bytes()
            recipe = getattr(self.parent(),'recipe',None)
            if recipe and recipe.kind == 'keyboard':
                for index,(_,path) in enumerate(KEYBOARD_PATHS):
                    if dest == path and len(recipe.paths) > index and Path(source) == recipe.paths[index] and len(recipe.infos)>index: self.installed_versions[KEYBOARD_PATHS[index][0]] = recipe.infos[index].version
            return Result(True,b'1 file pushed')
        if command == 'getenforce': return Result(True,self.selinux.encode())
        if command.startswith('setenforce '): self.selinux = 'Enforcing' if command.endswith('1') else 'Permissive'; return Result(True)
        if command == 'stop': self.android_running = False; return Result(True)
        if command == 'start': self.android_running = True; return Result(True)
        if command.startswith('toybox stat -c '): return Result(True,b'0:0:644')
        if command.startswith('toybox sha256sum '):
            path = shlex.split(command)[-1]
            if path not in self.files: return Result(False,stderr=b'No such file',code=1)
            return Result(True,(hashlib.sha256(self.files[path]).hexdigest()+'  '+path).encode())
        if command.startswith('cp -p '):
            _,_,source,dest = shlex.split(command)
            if source not in self.files: return Result(False,stderr=b'No such file',code=1)
            self.files[dest] = self.files[source]; return Result(True)
        if command.startswith('test ! -L ') and '|| cp -p' in command:
            bits = shlex.split(command); n = bits.index('cp'); source,dest = bits[n+2:n+4]; dest = dest.rstrip(';')
            if dest not in self.files: self.files[dest] = self.files[source]
            return Result(True)
        if command.startswith('test -f ') or command.startswith('test -e '):
            path = shlex.split(command)[2]
            return Result(path in self.files,code=0 if path in self.files else 1)
        if command.startswith('rm -f -- '):
            for path in shlex.split(command)[3:]: self.files.pop(path,None)
            return Result(True)
        if 'devices' in args:
            out = 'List of devices attached\nVOYAH-DEMO device usb:1-1 product:8155 model:VOYAH_Free device:8155\n'
        elif 'get-state' in args: out = 'device'
        elif 'root' in args: self.root = True; out = 'restarting adbd as root'
        elif 'unroot' in args: self.root = False; out = 'restarting adbd as non root'
        elif 'getprop' == command:
            out = '[ro.build.version.sdk]: [30]\n[ro.build.version.release]: [11]\n[ro.product.model]: [VOYAH Free 8155]\n[ro.build.product_3rdparty]: [f0506h]\n[ro.product.cpu.abilist]: [arm64-v8a,armeabi-v7a]\n[persist.sys.locale]: [ru-RU]'
        elif command == 'getprop sys.config.app_install_disabled': out = self.install_disabled
        elif command == 'setprop sys.config.app_install_disabled false': self.install_disabled = 'false'
        elif command.startswith('appops set '):
            bits = shlex.split(command); self.settings['appops:' + bits[2] + ':' + bits[3]] = bits[4]
        elif command.startswith('appops get '):
            bits = shlex.split(command); out = bits[3] + ': ' + self.settings.get('appops:' + bits[2] + ':' + bits[3],'default')
        elif command.startswith('id') or command.startswith('su '): out = 'uid=0(root) gid=0(root)' if self.root or command.startswith('su ') else 'uid=2000(shell) gid=2000(shell)'
        elif command == 'getprop sys.boot_completed': out = '1'
        elif command == 'wm help': out = 'density [reset|DENSITY] [-d DISPLAY_ID]\nsize [reset|WxH] [-d DISPLAY_ID]'
        elif command.startswith('input --help'): out = 'input [-d DISPLAY_ID] keyevent KEYCODE'
        elif command == 'dumpsys display': out = 'Display 0: mDisplayId=0 1920 x 720 density 160\nDisplay 1: mDisplayId=1 1920 x 720 density 160\nDisplay 2: mDisplayId=2 1920 x 720 density 160'
        elif command.startswith('wm density'):
            m = re.search(r'wm density (\d+)', command)
            if m: self.settings['density'] = m[1]
            if 'reset' in command: self.settings['density'] = '160'
            out = 'Physical density: 160\nOverride density: ' + self.settings.get('density', '160')
        elif command.startswith('wm size'): out = 'Physical size: 1920x720'
        elif command == 'dumpsys window':
            out = 'Display #0\n mCurrentFocus=Window{1 u0 com.voyah.cluster/.ClusterActivity}\nDisplay #1\n mCurrentFocus=Window{2 u0 com.voyah.launcher/.MainActivity}\nDisplay #2\n mCurrentFocus=Window{3 u0 com.voyah.video/.PlayerActivity}'
        elif command == 'dumpsys activity activities':
            out = 'Display #0\n mResumedActivity: ActivityRecord{1 u0 com.voyah.cluster/.ClusterActivity t1}\nDisplay #1\n mResumedActivity: ActivityRecord{2 u0 com.voyah.launcher/.MainActivity t2}\nDisplay #2\n mResumedActivity: ActivityRecord{3 u0 com.voyah.video/.PlayerActivity t3}'
        elif command.startswith('ls '):
            out = 'total 128\ndrwxrwx--- 2 1023 1023 4096 2026-10-14 12:30 Download\ndrwxrwx--- 3 1023 1023 4096 2026-10-14 12:31 Music\n-rw-rw---- 1 1023 1023 68157440 2026-10-14 13:25 navigator.apk\n-rw-rw---- 1 1023 1023 1024 2026-10-14 13:26 Тестовый файл.txt\nlrwxrwxrwx 1 0 0 12 2026-10-14 13:27 downloads -> /sdcard/Download'
        elif command.startswith('pm list packages'):
            out = '\n'.join('package:' + p for p in ['com.voyah.launcher', 'com.voyah.music', 'com.voyah.voice', 'com.voyah.video', 'com.android.settings', 'org.videolan.vlc', 'ru.yandex.yandexmaps', 'com.example.mapper'])
        elif command.startswith('dumpsys package '):
            pkg = command.split()[-1]
            out = f'Activity Resolver Table:\n  android.intent.action.MAIN:\n    {pkg}/.MainActivity\nReceiver Resolver Table:\n  android.intent.action.BOOT_COMPLETED:\n    {pkg}/.BootReceiver\nService Resolver Table:\n  {pkg}/.MediaService\nPackages:\n  Package [{pkg}]\n    versionCode={self.installed_versions.get(pkg,"42")}\n    User 0: installed=true enabled=1'
        elif 'resolve-activity' in command: out = command.split()[-1] + '/.MainActivity'
        elif command.startswith('pm path '): out = 'package:/data/app/demo/base.apk\npackage:/data/app/demo/split_config.arm64_v8a.apk'
        elif command.startswith('settings get '):
            out = self.settings.get(command.split()[-1], 'null')
        elif command.startswith('settings put '):
            bits = shlex.split(command); self.settings[bits[3]] = bits[4]
        elif command.startswith('settings delete '): self.settings.pop(command.split()[-1], None)
        elif 'ip -4 addr show' in command: out = '2: wlan0\n    inet 192.168.1.100/24 brd 192.168.1.255 scope global wlan0'
        elif 'logcat' in args and '-d' in args:
            out = 'ActivityManager: START u0 {cmp=com.voyah.voice/.VoiceActivity}\nCarService MCU hardkey keyCode=79\nVoiceService startService assistant\nBroadcastRecord com.voyah.KEY'
        elif 'install' in raw:
            if self.pending_install:
                pkg,version = self.pending_install; self.installed_versions[pkg] = version; self.pending_install = None
            out = 'Success'
        elif 'connect' in args: out = 'connected to ' + args[-1]
        return Result(True, out.encode('utf-8'))

BOOTSTRAP_REPOSITORY = 'lsby1808/Voyah_manager'
EN.update({
 'Каталог приложений':'App catalog','APK с ПК':'Local APKs','Клавиатуры':'Keyboards','Установленные приложения':'Installed apps','Твики':'Tweaks','Терминал':'Terminal',
 'Отключено администратором':'Disabled by administrator','Настройки подключения и устройства':'Connection and device settings','Обновить каталог':'Refresh catalog',
 'Каталог ещё не настроен':'Catalog is not configured yet','Последний сохранённый каталог':'Last saved catalog','Каталог актуален':'Catalog is up to date','Каталог обновлён':'Catalog updated',
 'Поиск приложений':'Search applications','Приложение':'Application','Совместимость':'Compatibility','Версия':'Version','Скачать и установить':'Download and install',
 'Определяется перед загрузкой':'Resolved before download','Выберите приложение из каталога.':'Select an app from the catalog.','Скачивание':'Downloading',
 'Подключитесь к интернету для первой загрузки.':'Connect to the Internet for the first download.','Кэш повреждён. Нужна повторная загрузка.':'Cache is corrupt. Download the file again.',
 'Размер загрузки не совпадает с источником.':'Downloaded size differs from the source.','Контрольная сумма не совпадает.':'Checksum mismatch.','Пустая загрузка.':'Empty download.',
 'Превышен допустимый размер загрузки.':'Download size limit exceeded.','Ошибка записи скачанного файла.':'Cannot write the download.',
 'Выбор файла':'Choose a file','В релизе несколько файлов. Выберите совместимый комплект.':'This release has multiple assets. Choose a compatible package.',
 'В релизе нет подходящего APK/архива.':'The release has no matching APK or archive.','Ссылка должна вести к APK или Android-архиву.':'The link must point to an APK or Android archive.',
 'Нужна ссылка на репозиторий, релиз или APK/архив.':'Enter a repository, release or APK/archive link.','Нужна публичная HTTPS-ссылка без пароля.':'Enter a public HTTPS URL without credentials.',
 'Скачать и установить комплект':'Download and install keyboard pair','Восстановить штатные клавиатуры':'Restore stock keyboards',
 'Комплекты пока не добавлены администратором.':'No keyboard pairs have been added by the administrator.',
 'Комплект заменяет системные клавиатуры двух экранов. Перед изменениями создаются резервные копии на ГУ и ПК.':'A pair replaces the system keyboards on both displays. Backups are made on the head unit and PC before changes.',
 'Модель не поддерживает этот комплект клавиатур.':'This keyboard pair does not support the device model.',
 'Вход администратора':'Administrator sign-in','Введите секретный код':'Enter the secret code','Войти':'Sign in','Неверный код':'Incorrect code','Администратор':'Administrator',
 'Функции':'Features','Установка APK':'APK installation','Изменение файлов':'File changes','Заморозка и включение':'Freeze and enable apps',
 'Очистка данных приложений':'Clear app data','Удаление приложений':'Uninstall apps','Управление Root':'Root controls','Перезагрузки':'Reboots','Масштаб DPI':'Display DPI',
 'Сеть и система':'Network and system','Починить настройки машины':'Repair vehicle settings','Починить verity':'Repair verity','Установка клавиатур':'Install keyboards','Восстановление клавиатур':'Restore keyboards',
 'GitHub и публикация':'GitHub and publishing','Изменения общего профиля вступают в силу после успешной публикации.':'Shared profile changes take effect after successful publication.',
 'Запись каталога':'Catalog entry','Постоянный ID':'Permanent ID','Название':'Name','Описание':'Description','Ссылка GitHub / APK':'GitHub / APK URL',
 'Имя файла релиза':'Release asset filename','Android-пакет':'Android package','APK центрального экрана':'Center display APK','APK пассажирского экрана':'Passenger display APK',
 'Доступно пользователям':'Available to users','Разрешить установку приложений (REQUEST_INSTALL_PACKAGES)':'Allow package installation (REQUEST_INSTALL_PACKAGES)',
 'Проверить ссылки':'Check links','Добавить':'Add','Изменить':'Edit','Сохранить черновик':'Save draft','Черновик сохранён':'Draft saved','Закрыть':'Close',
 'Репозиторий':'Repository','Ветка':'Branch','Путь JSON':'JSON path','Токен Contents: write':'Contents: write token','Основная ветка репозитория':'Repository default branch',
 'Сохраняется только в Windows Credential Manager':'Stored only in Windows Credential Manager','Сохранить подключение и токен':'Save connection and token',
 'Удалить сохранённый токен':'Delete saved token','Загрузить актуальный профиль':'Load current profile','Опубликовать':'Publish','Опубликовано':'Published',
 'Настройки сохранены':'Settings saved','Токен удалён':'Token deleted','Удалить запись каталога?':'Delete this catalog entry?',
 'Заменить черновик актуальным профилем GitHub?':'Replace the draft with the current GitHub profile?',
 'Файл ещё не создан. Можно опубликовать первый каталог.':'The file does not exist yet. You can publish the first catalog.',
 'Конфликт: загрузите актуальный каталог. Черновик сохранён.':'Conflict: load the current catalog. Your draft is saved.',
 'Сохраните токен в Windows Credential Manager.':'Save a token in Windows Credential Manager.','Сначала загрузите актуальную версию каталога с GitHub.':'Load the current catalog from GitHub first.',
 'Восстановление системы':'System recovery','Системные сценарии используют Root, резервные копии и перезагрузку. Применимость зависит от прошивки.':'System operations use root, backups and reboots. Support depends on the firmware.',
 'Отключение dm-verity — режим из отчёта':'Disable dm-verity — report procedure','Журнал восстановления':'Recovery journal','Возобновить Android после сбоя':'Start Android after an interruption',
 'Подключите устройство из журнала восстановления.':'Connect the device recorded in the recovery journal.',
 'Попытаться запустить Android и восстановить исходный SELinux? Резервные копии остаются на ПК.':'Attempt to start Android and restore the original SELinux mode? PC backups will be retained.',
 'Обнаружена незавершённая системная операция. Откройте журнал восстановления.':'An unfinished system operation was found. Open the recovery journal.',
 'Восстановление состояния перед закрытием…':'Restoring device state before closing…','Системная операция завершена':'System operation completed',
 'Операция прервана. Проверьте журнал восстановления.':'Operation interrupted. Check the recovery journal.','Резервные копии и журнал':'Backups and journal',
 'Проверка системного сценария':'Checking system operation','Получение Root по подтверждённому сценарию':'Obtaining root for the confirmed operation',
 'Ожидание Android на выбранном устройстве':'Waiting for Android on the selected device','Перезагрузка ГУ':'Rebooting head unit','Проверка Qinggan Settings':'Checking Qinggan Settings',
 'Проверка штатных файлов клавиатур':'Checking stock keyboard files','Резервное копирование на ПК':'Backing up to PC','Перемонтирование системного раздела':'Remounting the system partition',
 'Проверка SELinux':'Checking SELinux','Временный Permissive SELinux':'Temporarily setting permissive SELinux','Запись проверенного системного APK':'Writing the verified system APK',
 'Сохранение штатной копии .old без перезаписи':'Preserving the stock .old backup without overwriting','Восстановление исходного SELinux':'Restoring original SELinux mode',
 'Проверка клавиатур после загрузки':'Verifying keyboards after boot','Проверка базы настроек':'Checking settings database','Временная остановка Android':'Temporarily stopping Android',
 'Пересоздание базы Qinggan Settings':'Recreating Qinggan Settings database','Запуск Android после системной операции':'Starting Android after system operation',
 'Восстановление состояния после прерывания':'Restoring state after interruption','Откат клавиатуры к состоянию до операции':'Rolling back keyboard to its previous state',
 'Экраны':'Displays','Кнопки руля':'Steering wheel','Интенты':'Intents',
 'Подождите завершения определения параметров ГУ.':'Wait until device detection has completed.',
 'Некорректная ссылка.':'Invalid URL.','Неподдерживаемая версия каталога.':'Unsupported catalog schema version.',
 'Каталог содержит неизвестные поля.':'The catalog contains unknown fields.','Некорректная ревизия.':'Invalid revision.',
 'Некорректные переключатели функций.':'Invalid feature switches.','Некорректный список каталога.':'Invalid catalog list.',
 'Неизвестные поля записи каталога.':'Unknown catalog entry fields.','ID должен быть постоянным и уникальным.':'The ID must be permanent and unique.',
 'Некорректный текст записи.':'Invalid entry text.','Укажите название.':'Enter a name.','Некорректная доступность.':'Invalid availability.',
 'Некорректный minSdk.':'Invalid minSdk.','Некорректное имя пакета.':'Invalid package name.','Недопустимое дополнительное действие.':'Unsupported post-install action.',
 'Некорректный ABI.':'Invalid ABI.','Неизвестная модель клавиатуры.':'Unknown keyboard model.','Некорректный SHA-256.':'Invalid SHA-256.',
 'Некорректный путь каталога.':'Invalid catalog path.','Не удалось подтвердить публикацию.':'Publication could not be verified.',
 'Нужны два APK клавиатур.':'Two keyboard APKs are required.','Версии двух клавиатур не совпадают.':'Keyboard versions do not match.',
 'Неверный пакет клавиатуры или split вместо полного APK.':'Wrong keyboard package, or a split instead of a complete APK.',
 'Клавиатура несовместима с API устройства.':'The keyboard is incompatible with the device API.',
 'Прошивка отказала в Root. Сценарий остановлен.':'The firmware denied root. The operation has stopped.',
 'Истекло время ожидания загрузки выбранного устройства.':'Timed out waiting for the selected device to boot.',
 'Не удалось проверить SHA-256 системного файла.':'Cannot verify the system file SHA-256.',
 'Резервная копия не прошла проверку. Изменение отменено.':'The backup failed verification. Changes were cancelled.',
 'Не удалось определить режим SELinux.':'Cannot determine SELinux mode.',
 'Системный APK не прошёл проверку записи.':'The written system APK failed verification.',
 'Владелец или права системного APK не подтверждены.':'System APK owner or permissions could not be verified.',
 'Клавиатура не обнаружена после перезагрузки.':'The keyboard was not found after reboot.',
 'Версия клавиатуры после загрузки не подтверждена.':'The keyboard version could not be verified after boot.',
 'Qinggan Settings не обнаружен.':'Qinggan Settings was not found.','Исходная база недоступна. Удаление отменено.':'The original database is unavailable. Deletion was cancelled.',
 'Имя пакета не совпадает с каталогом.':'The package name differs from the catalog.',
 'Результат установки неизвестен. Оставшаяся очередь остановлена.':'The install outcome is unknown. The remaining queue has been stopped.',
 'Не удалось снять блокировку установки Voyah. Выберите Root вручную, если прошивка его поддерживает.':'Cannot remove the Voyah installation lock. Select root manually if the firmware supports it.',
 'Установленная версия не совпадает с проверенным APK.':'The installed version differs from the verified APK.',
 'APK установлен; выдача права установки отклонена.':'The APK is installed; permission to install packages was denied.',
 'APK установлен; право установки не подтверждено.':'The APK is installed; permission to install packages could not be verified.',
 'Заменить две системные клавиатуры? Будут созданы копии .old без перезаписи и резервные копии на ПК. Будет отключён dm-verity, временно изменён SELinux; ГУ перезагрузится дважды.':'Replace both system keyboards? Existing .old backups will be preserved and PC backups created. dm-verity will be disabled, SELinux temporarily changed, and the head unit rebooted twice.',
 'Восстановить штатные клавиатуры из .old? Текущие APK будут сохранены на ПК. ГУ перезагрузится. dm-verity останется отключённым.':'Restore stock keyboards from .old? Current APKs will be backed up to PC. The head unit will reboot. dm-verity will remain disabled.',
 'Починить настройки машины? Android будет остановлен. База Qinggan Settings, WAL и SHM будут сохранены на ПК и удалены на ГУ для пересоздания. Возможна потеря пользовательских настроек автомобиля. Затем Android запустится и ГУ перезагрузится.':'Repair vehicle settings? Android will be stopped. The Qinggan Settings database, WAL and SHM will be backed up to PC and removed on the head unit for recreation. Vehicle preferences may be lost. Android will then start and the head unit will reboot.',
 'Отключение dm-verity — режим из отчёта. Будут выполнены adb root, disable-verity, sync и перезагрузка. Это отключает проверку разделов.':'Disable dm-verity using the report procedure: adb root, disable-verity, sync and reboot. This disables partition verification.',
})
ADMIN_SALT = bytes.fromhex('84ee93f710f0aa245e004c809bc89149c3d5dc0b4a7a022d')
ADMIN_HASH = bytes.fromhex('ea95ed0acc96614777221364a763abe7e3de1e115b61c251e7ada5ed1cf9c0cc')
FEATURES = {
    'catalog': 'Каталог приложений', 'installer': 'APK с ПК', 'keyboards': 'Клавиатуры',
    'inspector': 'Инспектор', 'files': 'Файлы', 'apps': 'Установленные приложения',
    'tweaks': 'Твики', 'terminal': 'Терминал', 'apk.install': 'Установка APK',
    'files.write': 'Изменение файлов', 'apps.freeze': 'Заморозка и включение',
    'apps.clear': 'Очистка данных приложений', 'apps.uninstall': 'Удаление приложений',
    'device.root': 'Управление Root', 'device.reboot': 'Перезагрузки',
    'tweaks.dpi': 'Масштаб DPI', 'tweaks.permissions': 'Аудиофокус и разрешения',
    'tweaks.network': 'Сеть и система', 'repair.settings': 'Починить настройки машины',
    'repair.verity': 'Починить verity', 'keyboard.install': 'Установка клавиатур',
    'keyboard.restore': 'Восстановление клавиатур',
}
SECTION_NAMES = {key: FEATURES[key] for key in ('catalog','installer','keyboards','inspector','files','apps','tweaks','terminal')}
KEYBOARD_MODELS = ('f0506h', 'f6802h', 'f0505h', 'f6804h')
KEYBOARD_PATHS = (
    ('com.qinggan.app.qgime', '/system/priv-app/QGIME-release-signed/QGIME-release-signed.apk'),
    ('com.qinggan.app.qgime.second', '/system/priv-app/QGIME-second-signed/QGIME-second-signed.apk'),
)
SETTINGS_DB = '/data/data/com.qinggan.providers.settings/databases/qinggan_settings.db'

def verify_admin_code(code):
    return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', code.encode('utf-8'), ADMIN_SALT, 310000), ADMIN_HASH)

def default_catalog():
    return {'schema_version': 1, 'revision': 0, 'features': {key: True for key in FEATURES}, 'apps': [], 'keyboards': []}

def public_url(value):
    if not isinstance(value,str) or len(value)>8192: raise ValueError('Некорректная ссылка.')
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Нужна публичная HTTPS-ссылка без пароля.')
    return value

def github_repository(value):
    match = re.fullmatch(r'(?:https://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?', value.strip())
    if not match or any(part in ('.','..') for part in match.groups()):
        raise ValueError('Укажите GitHub-репозиторий: https://github.com/owner/repository')
    return '/'.join(match.groups())

def validate_catalog(value):
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value.get('schema_version') != 1:
        raise ValueError('Неподдерживаемая версия каталога.')
    if set(value) - {'schema_version','revision','features','apps','keyboards'}:
        raise ValueError('Каталог содержит неизвестные поля.')
    result = default_catalog()
    revision = value.get('revision', 0)
    if type(revision) is not int or revision < 0: raise ValueError('Некорректная ревизия.')
    result['revision'] = revision
    flags = value.get('features', {})
    if not isinstance(flags, dict) or any(k not in FEATURES or type(v) is not bool for k,v in flags.items()):
        raise ValueError('Некорректные переключатели функций.')
    result['features'].update(flags)
    for collection in ('apps','keyboards'):
        entries = value.get(collection, [])
        if not isinstance(entries, list) or len(entries) > 500: raise ValueError('Некорректный список каталога.')
        ids = set()
        for entry in entries:
            allowed = {'id','name','description','enabled','source','asset','package','post_install','min_sdk','abis'} if collection == 'apps' else {'id','name','description','enabled','central_url','passenger_url','models','min_sdk','central_sha256','passenger_sha256'}
            if not isinstance(entry, dict) or set(entry) - allowed: raise ValueError('Неизвестные поля записи каталога.')
            item = copy.deepcopy(entry)
            if not isinstance(item.get('id'),str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', item.get('id','')) or item['id'] in ids: raise ValueError('ID должен быть постоянным и уникальным.')
            ids.add(item['id'])
            for key in ('name','description','asset','package'):
                if key in item and (not isinstance(item[key], str) or len(item[key]) > 4000): raise ValueError('Некорректный текст записи.')
            if not item.get('name'): raise ValueError('Укажите название.')
            if type(item.get('enabled', True)) is not bool: raise ValueError('Некорректная доступность.')
            if type(item.get('min_sdk', 1)) is not int or not 1 <= item.get('min_sdk',1) <= 1000: raise ValueError('Некорректный minSdk.')
            if collection == 'apps':
                public_url(item.get('source',''))
                if item.get('package') and not PACKAGE_RE.fullmatch(item['package']): raise ValueError('Некорректное имя пакета.')
                if not isinstance(item.get('post_install',[]), list) or any(x != 'request_install_packages' for x in item.get('post_install',[])):
                    raise ValueError('Недопустимое дополнительное действие.')
                if not isinstance(item.get('abis',[]),list) or any(a not in ('arm64-v8a','armeabi-v7a','x86','x86_64') for a in item.get('abis',[])): raise ValueError('Некорректный ABI.')
            else:
                for key in ('central_url','passenger_url'): public_url(item.get(key,''))
                models = item.get('models', list(KEYBOARD_MODELS))
                if not isinstance(models,list) or not models or any(m not in KEYBOARD_MODELS for m in models): raise ValueError('Неизвестная модель клавиатуры.')
                for key in ('central_sha256','passenger_sha256'):
                    if item.get(key) and (not isinstance(item[key],str) or not re.fullmatch('[0-9a-fA-F]{64}', item[key])): raise ValueError('Некорректный SHA-256.')
            result[collection].append(item)
    return result

def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8'); os.replace(temp, path)

def feature_required(feature, section=None):
    """The same guard protects buttons, shortcuts and direct handler calls."""
    def decorate(fn):
        @functools.wraps(fn)
        def guarded(self, *args, **kwargs):
            main = self.main if hasattr(self, 'main') else self
            if not main.allowed(feature) or (section and not main.allowed(section)): return None
            return fn(self, *args, **kwargs)
        guarded.feature_id = feature
        return guarded
    return decorate

class CredentialStore:
    """Generic Windows credentials; secrets never enter QSettings or profile JSON."""
    @staticmethod
    def _types():
        from ctypes import wintypes as w
        class Credential(ctypes.Structure):
            _fields_ = [('Flags',w.DWORD),('Type',w.DWORD),('TargetName',w.LPWSTR),('Comment',w.LPWSTR),('LastWritten',w.FILETIME),('CredentialBlobSize',w.DWORD),('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),('Persist',w.DWORD),('AttributeCount',w.DWORD),('Attributes',ctypes.c_void_p),('TargetAlias',w.LPWSTR),('UserName',w.LPWSTR)]
        return Credential
    @staticmethod
    def name(repo): return 'VoyahManager/GitHub/' + hashlib.sha256(repo.lower().encode()).hexdigest()
    @classmethod
    def write(cls, repo, token):
        C = cls._types(); raw = token.encode('utf-16-le'); buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        item = C(); item.Type = 1; item.TargetName = cls.name(repo); item.UserName = 'GitHub'; item.Persist = 2; item.CredentialBlobSize = len(raw); item.CredentialBlob = buf
        fn = ctypes.windll.advapi32.CredWriteW; fn.argtypes = [ctypes.POINTER(C),ctypes.c_ulong]; fn.restype = ctypes.c_int
        if not fn(ctypes.byref(item),0): raise OSError('Windows Credential Manager: запись отклонена.')
    @classmethod
    def read(cls, repo):
        C = cls._types(); pointer = ctypes.POINTER(C)(); fn = ctypes.windll.advapi32.CredReadW; fn.argtypes = [ctypes.c_wchar_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.POINTER(ctypes.POINTER(C))]; fn.restype = ctypes.c_int
        if not fn(cls.name(repo),1,0,ctypes.byref(pointer)): return ''
        try: return ctypes.string_at(pointer.contents.CredentialBlob,pointer.contents.CredentialBlobSize).decode('utf-16-le')
        finally:
            ctypes.windll.advapi32.CredFree.argtypes = [ctypes.c_void_p]; ctypes.windll.advapi32.CredFree(pointer)
    @classmethod
    def delete(cls, repo):
        fn = ctypes.windll.advapi32.CredDeleteW; fn.argtypes = [ctypes.c_wchar_p,ctypes.c_ulong,ctypes.c_ulong]; fn(cls.name(repo),1,0)

class HttpJob(QObject):
    """Qt networking with bounded replies, streaming atomic downloads and cancellation."""
    def __init__(self, owner, url, callback, method='GET', payload=None, headers=None, destination=None, expected_size=0, digest='', progress=None):
        super().__init__(owner); self.owner = owner; self.callback = callback; self.destination = Path(destination) if destination else None
        self.expected_size = expected_size; self.expected_digest = digest.removeprefix('sha256:').lower(); self.progress = progress
        self.buffer = bytearray(); self.size = 0; self.hasher = hashlib.sha256(); self.file = None; self.reason = ''; self.ended = False
        public_url(url)
        request = QNetworkRequest(QUrl(url)); request.setTransferTimeout(30000)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute, QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setRawHeader(b'User-Agent', ('Voyah-Manager/' + VERSION).encode()); request.setRawHeader(b'Accept', b'application/vnd.github+json')
        request.setRawHeader(b'X-GitHub-Api-Version', b'2022-11-28')
        for key,value in (headers or {}).items(): request.setRawHeader(key.encode(), value.encode())
        if self.destination:
            self.destination.parent.mkdir(parents=True, exist_ok=True); self.partial = self.destination.with_suffix(self.destination.suffix + '.part')
            self.file = self.partial.open('wb')
        if method == 'PUT':
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, 'application/json'); self.reply = owner.manager.put(request, json.dumps(payload).encode())
        elif method == 'HEAD': self.reply = owner.manager.head(request)
        else: self.reply = owner.manager.get(request)
        self.reply.readyRead.connect(self.consume); self.reply.finished.connect(self.finish)
        self.reply.downloadProgress.connect(self.on_progress)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(lambda: self.cancel('Истекло время ожидания')); self.timer.start(900000 if destination else 45000)
        owner.jobs.add(self)
    def on_progress(self, received,total):
        if self.progress: self.progress(received,total)
    def consume(self):
        if self.reason: return
        chunk = bytes(self.reply.readAll()); self.size += len(chunk); self.hasher.update(chunk)
        if self.size > (8 * 1024**3 if self.file else 4 * 1024**2): self.cancel('Превышен допустимый размер загрузки.'); return
        if self.file:
            try: self.file.write(chunk)
            except OSError: self.cancel('Ошибка записи скачанного файла.')
        else: self.buffer.extend(chunk)
    def cancel(self, reason='Отменено'):
        self.reason = reason; self.reply.abort()
    def finish(self):
        if self.ended: return
        self.ended = True; self.consume(); self.timer.stop(); status = self.reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        error = self.reason or ('' if self.reply.error() == QNetworkReply.NetworkError.NoError or status == 304 else f'HTTP {status}: {self.reply.errorString()}')
        if self.file:
            self.file.close(); self.file = None
            if not error and self.expected_size and self.size != self.expected_size: error = 'Размер загрузки не совпадает с источником.'
            if not error and self.expected_digest and self.hasher.hexdigest() != self.expected_digest: error = 'Контрольная сумма не совпадает.'
            if not error and self.size == 0: error = 'Пустая загрузка.'
            if error: self.partial.unlink(missing_ok=True)
            else: os.replace(self.partial, self.destination)
        data = {'status':status,'body':bytes(self.buffer),'path':self.destination,'sha256':self.hasher.hexdigest(),'size':self.size,'etag':bytes(self.reply.rawHeader('ETag')).decode(),'error':error}
        self.owner.jobs.discard(self); self.reply.deleteLater()
        if not self.owner.main.closing: self.callback(data)
        self.deleteLater()

class WebClient(QObject):
    def __init__(self, main):
        super().__init__(main); self.main = main; self.manager = QNetworkAccessManager(self); self.jobs = set()
    def request(self, url, callback, **kwargs): return HttpJob(self,url,callback,**kwargs)
    def cancel_all(self):
        for job in list(self.jobs): job.cancel()

class CatalogStore(QObject):
    changed = Signal()
    def __init__(self, main):
        super().__init__(main); self.main = main; self.profile = default_catalog(); self.message = ''; self.loading = False; self.pending = None
        self.path = DATA_DIR / ('catalog-qa.json' if main.smoke else 'catalog-cache.json')
        try:
            config = json.loads(main.settings.value('catalog_connection', '{}'))
            self.config = {k:v for k,v in config.items() if k in ('repository','branch','path') and isinstance(v,str)} if isinstance(config,dict) else {}
        except (ValueError,TypeError): self.config = {}
        if not self.config.get('repository') and BOOTSTRAP_REPOSITORY: self.config = {'repository':BOOTSTRAP_REPOSITORY,'branch':'','path':'catalog.json'}
        self.etag = ''; self.remote_sha = None; self.remote_loaded = False
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8')); self.profile = validate_catalog(saved['profile'])
            if saved.get('connection') == self.config:
                self.etag = saved.get('etag','') if isinstance(saved.get('etag',''),str) else ''; self.remote_sha = saved.get('sha') if isinstance(saved.get('sha'),str) else None
        except (OSError,ValueError,KeyError,TypeError,AttributeError): pass
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(300000)
    def endpoint(self):
        repo = github_repository(self.config.get('repository','')); path = self.config.get('path','catalog.json').strip('/')
        if not path or any(p in ('.','..') for p in path.split('/')): raise ValueError('Некорректный путь каталога.')
        return 'https://api.github.com/repos/' + repo + '/contents/' + quote(path, safe='/')
    def public_endpoint(self):
        self.endpoint()  # Validate repository and path using the same rules as publication.
        repo = github_repository(self.config.get('repository','')); branch = self.config.get('branch','') or 'HEAD'
        return 'https://raw.githubusercontent.com/' + repo + '/' + quote(branch, safe='') + '/' + quote(self.config.get('path','catalog.json').strip('/'), safe='/')
    def apply(self, profile, etag='', sha=None):
        profile = validate_catalog(profile)
        if self.main.busy: self.pending = (profile,etag,sha); return
        self.profile = profile; self.etag = etag
        if sha is not None: self.remote_sha = sha
        atomic_json(self.path, {'profile':profile,'etag':etag,'sha':self.remote_sha,'connection':self.config}); self.changed.emit()
    def flush(self):
        if self.pending:
            item = self.pending; self.pending = None; self.apply(*item)
    def refresh(self, callback=None):
        if self.loading: return
        if not self.config.get('repository'):
            self.message = 'Каталог ещё не настроен'; self.changed.emit(); return
        self.loading = True
        try: url = self.public_endpoint()
        except ValueError as error: self.loading = False; self.message = str(error); self.changed.emit(); return
        def done(result):
            self.loading = False
            try:
                if result['status'] == 304:
                    self.message = 'Каталог актуален'; self.remote_loaded = True
                else:
                    if result['error']: raise ValueError(result['error'])
                    body = result['body']; profile = validate_catalog(json.loads(body))
                    # GitHub Contents uses the Git blob SHA, including exact bytes and newlines.
                    sha = hashlib.sha1(b'blob ' + str(len(body)).encode('ascii') + b'\0' + body).hexdigest()
                    self.remote_sha = sha; self.remote_loaded = True; self.apply(profile,result['etag'],sha); self.message = 'Каталог обновлён'
            except (ValueError,KeyError,TypeError,OSError) as error: self.message = 'Нет обновления. Используется сохранённый каталог. ' + str(error)
            self.changed.emit()
            if callable(callback): callback(result)
        self.main.web.request(url,done,headers={'If-None-Match':self.etag} if self.etag else {})
    def publish(self, draft, callback):
        try:
            profile = validate_catalog(draft); repo = github_repository(self.config.get('repository','')); token = CredentialStore.read(repo); url = self.endpoint()
            if not token: raise ValueError('Сохраните токен в Windows Credential Manager.')
            expected_sha = self.remote_sha
            if not self.remote_loaded: raise ValueError('Сначала загрузите актуальную версию каталога с GitHub.')
        except (ValueError,OSError) as error: callback(False,str(error)); return
        headers = {'Authorization':'Bearer ' + token}
        # Compare again immediately before PUT. Never silently overwrite somebody else's revision.
        def checked(result):
            try:
                if result['status'] == 404: sha = None
                elif result['error']: raise ValueError(result['error'])
                else: sha = json.loads(result['body'])['sha']
                if sha != expected_sha: raise ValueError('Конфликт: загрузите актуальный каталог. Черновик сохранён.')
                payload = {'message':'Update Voyah Manager catalog','content':base64.b64encode(json.dumps(profile,ensure_ascii=False,indent=2).encode()).decode()}
                if sha: payload['sha'] = sha
                if self.config.get('branch'): payload['branch'] = self.config['branch']
                def published(r):
                    if r['error']: callback(False, ('Конфликт: загрузите актуальный каталог. Черновик сохранён.' if r['status'] in (409,422) else r['error'])); return
                    try: new_sha = json.loads(r['body'])['content']['sha']; self.apply(profile,'',new_sha); self.remote_sha = new_sha; callback(True,'Опубликовано')
                    except (ValueError,KeyError): callback(False,'Не удалось подтвердить публикацию.')
                self.main.web.request(url,published,method='PUT',payload=payload,headers=headers)
            except (ValueError,KeyError) as error: callback(False,str(error))
        check_url = url + ('?' + urlencode({'ref':self.config['branch']})) if self.config.get('branch') else url
        self.main.web.request(check_url,checked,headers=headers)

@dataclass
class Step:
    args: list[str] | str
    shell: bool = True
    privileged: bool = False
    timeout: int = 30000
    validate: Callable | None = None

class MainWindow(QMainWindow):
    def __init__(self, demo=False, smoke=False):
        super().__init__(); self.demo = demo; self.smoke = smoke; self.closing = False
        self.settings = QSettings('VoyahManager', 'Voyah Manager' + (' QA' if smoke else '') + (' Demo' if demo else ''))
        self.lang = self.settings.value('language', 'ru'); self.tools = Tools(); self.runner = Runner(self)
        self.demo_backend = DemoBackend(self) if demo else None
        self.target: Target | None = None; self.profile = Profile(); self.privilege = 'shell'; self.su_prefix = ['su', 'sh', '-c']
        self.busy = False; self.cancel_requested = False; self.active_job = None; self.workers = set()
        self.binding = []; self.devices = []; self.probing = False; self.operation_name = ''
        self.display_map = self.settings.value('display_map', {'cluster': 0, 'center': 1, 'passenger': 2})
        if isinstance(self.display_map, str): self.display_map = json.loads(self.display_map)
        self.adb_path = self.tools.find_adb(self.settings.value('adb_path', ''))
        self.setWindowTitle('Voyah Manager'); self.setWindowIcon(make_icon()); self.resize(1400, 940); self.setMinimumSize(820, 620); self.setAcceptDrops(True)
        self.web = WebClient(self); self.catalog = CatalogStore(self); self.admin_dialog = None; self.recipe = None
        self.build_ui(); self.retranslate(); self.catalog.changed.connect(self.apply_policy)
        self.admin_shortcut = QShortcut(QKeySequence('Ctrl+Shift+Alt+A'), self, activated=self.open_admin)
        available = QApplication.primaryScreen().availableGeometry(); self.setMinimumSize(min(820,available.width()-32),min(620,available.height()-32)); self.resize(min(1400, available.width()-32), min(940, available.height()-32))
        self.poll = QTimer(self); self.poll.timeout.connect(self.refresh_devices); self.poll.start(5000)
        QTimer.singleShot(100, self.startup)

    def t(self, text, **values): return tr(text, self.lang, **values)

    def bind(self, obj, key, method='setText'):
        self.binding.append((obj, key, method)); getattr(obj, method)(self.t(key)); return obj

    def button(self, key, fn, accent=False):
        w = self.bind(QPushButton(), key); w.clicked.connect(fn)
        if getattr(fn, 'feature_id', None): w.setProperty('feature', fn.feature_id)
        if accent: w.setProperty('accent', True)
        return w

    def build_ui(self):
        root = QWidget(); self.setCentralWidget(root); outer = QVBoxLayout(root); outer.setContentsMargins(22, 18, 22, 12); outer.setSpacing(12)
        brand = QHBoxLayout(); emblem = QLabel(); emblem.setPixmap(make_icon().pixmap(48, 48)); brand.addWidget(emblem)
        names = QVBoxLayout(); label = QLabel('VOYAH MANAGER'); label.setObjectName('title'); names.addWidget(label)
        names.addWidget(self.bind(QLabel(), 'Диагностика • управление • мультимедиа')); brand.addLayout(names); brand.addStretch()
        self.device_info = QLabel('SNAPDRAGON 8155  /  ADB WORKBENCH'); self.device_info.setObjectName('subtitle'); brand.addWidget(self.device_info)
        self.language = QComboBox(); self.language.addItem('Русский', 'ru'); self.language.addItem('English', 'en'); self.language.setCurrentIndex(1 if self.lang == 'en' else 0)
        self.language.currentIndexChanged.connect(self.change_language); brand.addWidget(self.language)
        brand.addWidget(self.button('О приложении', self.about)); outer.addLayout(brand)
        header = QFrame(); header.setObjectName('header'); h = QVBoxLayout(header); h.setContentsMargins(14, 12, 14, 12); h.setSpacing(9)
        row = QHBoxLayout(); self.status_dot = QLabel('●'); self.status_dot.setStyleSheet('color:#EF707B;font-size:18pt;'); row.addWidget(self.status_dot)
        self.connection_status = QLabel(); self.connection_status.setMinimumWidth(115); self.connection_status.setMaximumWidth(270); row.addWidget(self.connection_status)
        self.mode = QComboBox(); self.mode.addItem('USB', 'usb'); self.mode.addItem('Wi-Fi', 'wifi'); self.mode.currentIndexChanged.connect(self.mode_changed); row.addWidget(self.mode)
        self.device_combo = QComboBox(); self.device_combo.setMinimumWidth(120); self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon); self.device_combo.currentIndexChanged.connect(self.device_selected); row.addWidget(self.device_combo, 1)
        self.ip = QLineEdit(self.settings.value('ip', '')); self.ip.setPlaceholderText('192.168.1.100:5555'); self.ip.setMaximumWidth(220)
        self.voyah_wifi = QPushButton('Voyah :5578'); self.voyah_wifi.setToolTip('192.168.43.1:5578 · ' + self.t('Из отчёта установщика; применимость зависит от прошивки.')); self.voyah_wifi.clicked.connect(lambda: self.ip.setText('192.168.43.1:5578'))
        self.connect_btn = self.button('Подключить', self.connect_device, True); row.addWidget(self.connect_btn)
        row.addWidget(self.button('Обновить', self.refresh_devices)); h.addLayout(row)
        self.wifi_row = QWidget(); address_row = QHBoxLayout(self.wifi_row); address_row.setContentsMargins(0,0,0,0); address_row.addWidget(self.ip); address_row.addWidget(self.voyah_wifi); address_row.addStretch(); h.addWidget(self.wifi_row)
        self.connection_details = QFrame(); details = QVBoxLayout(self.connection_details); details.setContentsMargins(0,0,0,0)
        row = FlowLayout(); row.addWidget(self.button('USB → Wi-Fi :5555', self.usb_wifi)); self.adb_label = QLabel(); self.adb_label.setObjectName('subtitle'); self.adb_label.setMaximumWidth(380); self.adb_label.setWordWrap(True); self.adb_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); row.addWidget(self.adb_label)
        row.addWidget(self.button('Выбрать ADB', self.choose_adb)); row.addWidget(self.button('Встроенный ADB', self.use_bundled)); row.addWidget(self.button('Перезапуск ADB', self.restart_adb))
        self.root_button = self.button('Расширенный режим', self.root_menu); row.addWidget(self.root_button)
        self.reboot_button = self.button('Перезагрузка', self.reboot_menu); row.addWidget(self.reboot_button); details.addLayout(row)
        toggle = self.button('Настройки подключения и устройства', lambda: self.connection_details.setVisible(not self.connection_details.isVisible())); h.addWidget(toggle); h.addWidget(self.connection_details); self.connection_details.hide()
        outer.addWidget(header)
        nav = FlowLayout()
        for text, code in [('Назад', 4), ('Домой', 3), ('Недавние', 187)]:
            nav.addWidget(self.button(text, lambda checked=False, c=code: self.keyevent(c)))
        nav.addWidget(self.button('Скриншот', self.screenshot)); nav.addStretch()
        self.operation_label = QLabel(); self.operation_label.setMaximumWidth(220); self.operation_label.setWordWrap(True); self.operation_label.setObjectName('subtitle'); nav.addWidget(self.operation_label)
        self.global_progress = QProgressBar(); self.global_progress.setMaximumWidth(160); self.global_progress.setMaximumHeight(12); self.global_progress.setTextVisible(False); self.global_progress.hide(); nav.addWidget(self.global_progress)
        self.cancel_btn = self.button('Отменить задание', self.cancel_operation); self.cancel_btn.setEnabled(False); nav.addWidget(self.cancel_btn)
        outer.addLayout(nav)
        if self.demo:
            badge = self.bind(QLabel(), 'Демонстрационный режим • команды имитируются'); badge.setStyleSheet('color:#F5CE7E;padding:7px;background:#332D22;border-radius:5px;'); outer.addWidget(badge)
        body = QHBoxLayout(); body.setSpacing(16)
        self.sidebar = QListWidget(); self.sidebar.setObjectName('sidebar'); self.sidebar.setFixedWidth(260); self.sidebar.setSpacing(4); self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stack = QStackedWidget(); self.pages = {}; self.section_items = {}
        factories = {'catalog': CatalogPage, 'installer': InstallerPage, 'keyboards': KeyboardPage, 'inspector': InspectorPage, 'files': ExplorerPage, 'apps': AppsPage, 'tweaks': TweaksPage, 'terminal': TerminalPage}
        symbols = ['◈','↓','⌨','◉','▤','▦','⚙','›_']
        for (key, title), symbol in zip(SECTION_NAMES.items(), symbols):
            page = factories[key](self); self.pages[key] = page
            if key in ('catalog','keyboards','files','apps','tweaks'):
                page.layout.removeWidget(page.log); page.log.hide()
            item = QListWidgetItem(symbol + '  ' + self.t(title)); item.setData(Qt.ItemDataRole.UserRole, key); item.setData(Qt.ItemDataRole.UserRole + 1, symbol); item.setToolTip(self.t(title)); self.sidebar.addItem(item); self.section_items[key] = item
            scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setWidget(page); scroll.setProperty('section',key); self.stack.addWidget(scroll)
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex); self.sidebar.setCurrentRow(0)
        body.addWidget(self.sidebar); body.addWidget(self.stack,1); outer.addLayout(body,1)
        self.journal_toggle = self.button('Журнал операций', lambda: self.shared_log.setVisible(not self.shared_log.isVisible())); outer.addWidget(self.journal_toggle)
        self.shared_log = logbox(); self.shared_log.setMaximumHeight(170); self.shared_log.hide(); outer.addWidget(self.shared_log)
        self.apply_policy()
        foot = QHBoxLayout(); self.notice_label = QLabel(); self.notice_label.setObjectName('subtitle'); foot.addWidget(self.notice_label, 1)
        foot.addWidget(self.button('Открыть журнал', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR / 'voyah-manager.log')))))
        version = QLabel('v' + VERSION + '  •  AOSP 28–30'); version.setObjectName('subtitle'); foot.addWidget(version); outer.addLayout(foot)
        self.mode_changed()

    def current_section(self):
        item = self.sidebar.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else 'catalog'

    def select_section(self, key):
        self.sidebar.setCurrentItem(self.section_items[key])

    def allowed(self, feature, report=True):
        enabled = self.catalog.profile['features'].get(feature, True)
        if not enabled and report: self.error(self.t('Отключено администратором'), self.t(FEATURES.get(feature,feature)))
        return enabled

    def apply_policy(self):
        if not hasattr(self,'pages'): return
        for key,page in self.pages.items():
            enabled = self.allowed(key,False); page.setEnabled(enabled)
            page.setToolTip('' if enabled else self.t('Отключено администратором'))
            self.section_items[key].setForeground(QColor('#E5EBF2' if enabled else '#7C8797'))
        for widget in self.findChildren(QWidget):
            key = widget.property('feature')
            if key:
                enabled = self.allowed(key,False)
                if key in ('repair.settings','repair.verity','keyboard.install','keyboard.restore'): enabled = enabled and self.allowed('device.root',False) and self.allowed('device.reboot',False)
                widget.setEnabled(enabled); widget.setToolTip('' if enabled else self.t('Отключено администратором'))
        catalog_page = self.pages.get('catalog')
        if catalog_page: catalog_page.show_details()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self,'sidebar'): return
        compact = self.width() < 1150; self.sidebar.setFixedWidth(60 if compact else 260)
        self.device_info.setVisible(not compact)
        for key,item in self.section_items.items():
            symbol = item.data(Qt.ItemDataRole.UserRole + 1); item.setText(symbol if compact else symbol + '  ' + self.t(SECTION_NAMES[key]))

    def open_admin(self):
        if self.admin_dialog:
            self.admin_dialog.raise_(); self.admin_dialog.activateWindow(); return
        login = AdminLogin(self)
        if login.exec() != QDialog.DialogCode.Accepted: return
        dialog = AdminDialog(self); self.admin_dialog = dialog
        try: dialog.exec()
        finally: self.admin_dialog = None; dialog.deleteLater()

    def startup(self):
        self.notice(self.t('Подключите ГУ по USB или Wi-Fi, чтобы начать.'))
        QTimer.singleShot(0, self.catalog.refresh)
        if (DATA_DIR / 'operation.json').exists(): self.notice(self.t('Обнаружена незавершённая системная операция. Откройте журнал восстановления.'))
        if not self.adb_path and not self.demo:
            self.use_bundled()
        else: self.refresh_devices()

    def retranslate(self):
        for obj, key, method in self.binding: getattr(obj, method)(self.t(key))
        for key, page in self.pages.items():
            page.retranslate()
            item = self.section_items[key]; symbol = item.data(Qt.ItemDataRole.UserRole + 1); item.setText(symbol if self.width()<1150 else symbol + '  ' + self.t(SECTION_NAMES[key])); item.setToolTip(self.t(SECTION_NAMES[key]))
        self.apply_policy()
        self.update_status(); self.adb_label.setText('ADB  ·  ' + (self.adb_path or '—'))

    def change_language(self):
        self.lang = self.language.currentData(); self.settings.setValue('language', self.lang); self.retranslate()

    def mode_changed(self):
        self.ip.setVisible(self.mode.currentData() == 'wifi'); self.voyah_wifi.setVisible(self.mode.currentData() == 'wifi')
        if hasattr(self,'wifi_row'): self.wifi_row.setVisible(self.mode.currentData() == 'wifi')

    def notice(self, text):
        self.notice_label.setText(text); self.notice_label.setToolTip(text); logging.info(text)
        if hasattr(self, 'shared_log'): append_log(self.shared_log, time.strftime('%H:%M:%S') + '  ' + text + '\n')

    def error(self, text, detail='', modal=True):
        if self.closing: return
        self.notice(text); logging.error('%s %s', text, detail)
        if modal and not self.smoke:
            box = QMessageBox(QMessageBox.Icon.Warning, self.t('Ошибка'), text, parent=self)
            if detail: box.setDetailedText(detail)
            box.exec()

    def confirm(self, text):
        return QMessageBox.question(self, self.t('Подтверждение'), text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def ready(self):
        if not self.target:
            self.error(self.t('Сначала подключите устройство.')); return False
        if self.busy:
            self.error(self.t('Дождитесь завершения или отмените текущее задание.')); return False
        return True

    def begin(self, name):
        if self.busy:
            self.error(self.t('Дождитесь завершения или отмените текущее задание.')); return False
        self.busy = True; self.cancel_requested = False; self.operation_name = name
        if hasattr(self,'pages'): self.pages['terminal'].stop_streams()
        self.operation_label.setText(name); self.global_progress.setRange(0, 0); self.global_progress.show(); self.cancel_btn.setEnabled(True)
        for w in (self.mode, self.device_combo, self.connect_btn): w.setEnabled(False)
        return True

    def end(self, success=True):
        self.busy = False; self.active_job = None; self.global_progress.hide(); self.cancel_btn.setEnabled(False)
        for w in (self.mode, self.device_combo, self.connect_btn): w.setEnabled(True)
        self.catalog.flush(); self.apply_policy()
        self.operation_label.setText(''); self.notice(self.t('Отменено') if self.cancel_requested else self.t('Готово: {name}' if success else 'Ошибка: {name}', name=self.operation_name))

    def cancel_operation(self):
        self.cancel_requested = True
        self.pages['installer'].service.cancel_event.set()
        if getattr(self,'install_service',None): self.install_service.cancel_event.set()
        if self.recipe and self.recipe.running: self.recipe.cancel(); return
        if self.active_job: self.active_job.cancel()
        self.notice(self.t('Отменено'))

    def background(self, fn, callback):
        worker = Worker(fn, lambda result, error: self.worker_done(worker, callback, result, error))
        self.workers.add(worker); QThreadPool.globalInstance().start(worker)

    def worker_done(self, worker, callback, result, error):
        self.workers.discard(worker)
        if not self.closing: callback(result, error)

    def adb(self, args, callback, *, target=None, global_cmd=False, shell=False, privileged=False, **kwargs):
        if self.closing: return None
        current = target if target is not None else self.target
        if not global_cmd and not current:
            QTimer.singleShot(0, lambda: callback(Result(False, stderr=b'no devices')) if callback else None); return None
        argv = [] if global_cmd else current.args()
        if shell:
            command = args if isinstance(args, str) else remote_command(args)
            if privileged and self.privilege == 'su': command = remote_command(self.su_prefix + [command])
            argv += ['shell', command]
        else: argv += list(args)
        logging.info('ADB %s', remote_command(argv))
        if hasattr(self,'shared_log'):
            append_log(self.shared_log,'› adb ' + remote_command(argv) + '\n')
            original_callback = callback; original_stream = kwargs.get('stream')
            if original_stream:
                def streamed(value):
                    append_log(self.shared_log,value); original_stream(value)
                kwargs['stream'] = streamed
            def recorded(result):
                if result.timed_out: result.stderr += b'\nADB command timed out'
                if not original_stream and not kwargs.get('binary') and result.text: append_log(self.shared_log,result.text[-24000:]+'\n')
                if original_callback: original_callback(result)
            callback = recorded
        if self.demo: return self.demo_backend.run(argv, callback, **kwargs)
        if not self.adb_path:
            QTimer.singleShot(0, lambda: callback(Result(False, stderr=b'ADB not found')) if callback else None); return None
        return self.runner.run(self.adb_path, argv, callback, **kwargs)

    def sequence(self, name, steps, done=None, target=None):
        target = target or self.target
        if not target:
            self.error(self.t('Сначала подключите устройство.')); return
        if not self.begin(name): return
        results = []
        def next_step(index=0):
            if self.cancel_requested:
                self.end(False)
                if done: done(False, results)
                return
            if index == len(steps):
                self.end(True)
                if done: done(True, results)
                return
            step = steps[index]
            def complete(result):
                results.append(result)
                if result.ok and step.validate and not step.validate(result): result.ok = False
                if not result.ok:
                    self.end(False)
                    if not result.cancelled:
                        self.error(self.t('Истекло время ожидания') if result.timed_out else self.t(explain_error(result.text)), result.text)
                    if done: done(False, results)
                else: next_step(index + 1)
            self.active_job = self.adb(step.args, complete, target=target, shell=step.shell, privileged=step.privileged, timeout=step.timeout)
        next_step()

    def refresh_devices(self):
        if self.busy or self.probing or self.closing: return
        self.probing = True
        def complete(result):
            self.probing = False
            if not result.ok:
                self.set_target(None); self.update_status(); return
            self.devices = parse_devices(result.text)
            old = self.target.serial if self.target else self.settings.value('last_serial', '')
            self.device_combo.blockSignals(True); self.device_combo.clear()
            for device in self.devices:
                self.device_combo.addItem(f"{device['serial']}  ·  {device['state']}", device)
            if not self.devices: self.device_combo.addItem(self.t('Нет подключённых устройств'), None)
            index = next((i for i, d in enumerate(self.devices) if d['serial'] == old), -1)
            if index < 0: index = next((i for i, d in enumerate(self.devices) if d['state'] == 'device'), 0)
            self.device_combo.setCurrentIndex(index); self.device_combo.blockSignals(False)
            self.device_selected()
        self.adb(['devices', '-l'], complete, global_cmd=True, timeout=8000, check=False)

    def device_selected(self):
        device = self.device_combo.currentData()
        if not device or device['state'] != 'device':
            self.set_target(None); self.update_status(device['state'] if device else ''); return
        usb_count = sum(d['usb'] and d['state'] == 'device' for d in self.devices)
        target = Target(device['serial'], 'usb' if device['usb'] else 'wifi', False)
        if target != self.target:
            self.mode.blockSignals(True); self.mode.setCurrentIndex(0 if target.mode == 'usb' else 1); self.mode.blockSignals(False); self.mode_changed()
            self.set_target(target); self.read_profile()
        self.update_status()

    def set_target(self, target):
        if target == self.target: return
        for page in self.pages.values():
            if hasattr(page, 'stop_streams'): page.stop_streams()
        self.target = target; self.privilege = 'shell'; self.profile = Profile(); self.root_button.setText(self.t('Расширенный режим'))
        if target: self.settings.setValue('last_serial', target.serial)

    def update_status(self, state=''):
        key, color = ('Подключено', '#44D7A0') if self.target else ('Отключено', '#EF707B')
        if state in ('offline', 'unauthorized'):
            key = 'Не авторизовано — подтвердите RSA на ГУ' if state == 'unauthorized' else 'Устройство не отвечает'; color = '#F4C66B'
        self.status_dot.setStyleSheet(f'color:{color};font-size:18pt;')
        suffix = ('  ' + ('USB [-d]' if self.target.use_d else f'{self.target.mode.upper()} [-s {self.target.serial}]')) if self.target else ''
        self.connection_status.setText(self.t(key) + suffix); self.connection_status.setToolTip(self.t(key) + suffix)
        self.adb_label.setText('ADB  ·  ' + (self.adb_path or '—'))

    def choose_adb(self):
        if self.busy: return
        file, _ = QFileDialog.getOpenFileName(self, self.t('Выбрать ADB'), self.adb_path, 'ADB (adb.exe)')
        if file:
            self.set_target(None); self.adb_path = file; self.settings.setValue('adb_path', file); self.refresh_devices(); self.update_status()

    def use_bundled(self):
        if self.busy: return
        if not self.begin(self.t('Встроенный ADB')): return
        def done(path, error):
            self.end(not error)
            if error: self.error(str(error)); return
            self.set_target(None); self.adb_path = path; self.settings.setValue('adb_path', path); self.update_status(); self.refresh_devices()
        self.background(self.tools.bundled_adb, done)

    def connect_device(self):
        if self.busy: return
        if self.mode.currentData() == 'wifi':
            try: endpoint = normalize_endpoint(self.ip.text())
            except ValueError: self.error(self.t('Введите корректный IP-адрес и порт.')); return
            self.settings.setValue('ip', endpoint); target = Target(endpoint, 'wifi')
            if not self.begin(self.t('Подключение')): return
            def connected(result):
                if not result.ok: self.end(False); self.error(self.t(explain_error(result.text)), result.text); return
                def checked(state):
                    self.end(state.ok and state.text == 'device')
                    if state.ok and state.text == 'device': self.set_target(target); self.read_profile(); self.update_status(); self.refresh_devices()
                    else: self.error(self.t(explain_error(state.text)), state.text)
                self.active_job = self.adb(['get-state'], checked, target=target, timeout=10000)
            self.active_job = self.adb(['connect', endpoint], connected, global_cmd=True, timeout=15000)
        else:
            usbs = [d for d in self.devices if d['usb'] and d['state'] == 'device']
            selected = self.device_combo.currentData()
            if len(usbs) > 1 and (not selected or not selected['usb']): self.error(self.t('Требуется выбрать устройство USB.')); return
            target = Target(selected['serial'] if selected and selected['usb'] else 'USB', 'usb', len(usbs) <= 1)
            if not self.begin(self.t('Подключение')): return
            def disconnected(result):
                def checked(state):
                    self.end(state.ok and state.text == 'device')
                    if state.ok and state.text == 'device': self.set_target(None); self.refresh_devices()
                    else: self.error(self.t(explain_error(state.text)), state.text)
                self.active_job = self.adb(['get-state'], checked, target=target, timeout=10000)
            self.active_job = self.adb(['disconnect'], disconnected, global_cmd=True, timeout=8000)

    def usb_wifi(self):
        if not self.ready(): return
        if self.target.mode != 'usb': self.error(self.t('Требуется выбрать устройство USB.')); return
        target = self.target
        def done(ok, results):
            if ok:
                ips = re.findall(r'inet\s+(\d+\.\d+\.\d+\.\d+)/', results[0].text)
                ips = [ip for ip in ips if not ip.startswith('127.')]
                self.ip.setText((ips[0] + ':5555') if ips else '')
                QMessageBox.information(self, 'USB → Wi-Fi :5555', '\n'.join(ips) or results[0].text)
                self.set_target(None); self.refresh_devices()
        self.sequence('USB → Wi-Fi :5555', [Step(['ip', '-4', 'addr', 'show']), Step(['tcpip', '5555'], False)], done, target)

    def restart_adb(self):
        if self.busy: return
        self.set_target(None)
        if not self.begin(self.t('Перезапуск ADB')): return
        def killed(result):
            def started(r):
                self.end(r.ok); self.refresh_devices()
                if not r.ok: self.error(self.t(explain_error(r.text)), r.text)
            self.active_job = self.adb(['start-server'], started, global_cmd=True, timeout=15000)
        self.active_job = self.adb(['kill-server'], killed, global_cmd=True, timeout=10000)

    def read_profile(self):
        target = self.target
        if not target: return
        queries = [('props', ['getprop']), ('display', ['dumpsys', 'display']), ('wm', ['wm', 'help']),
                   ('density', ['wm', 'density']), ('uid', ['id']), ('input', ['input', '--help'])]
        data = {}
        def query(index=0):
            if target != self.target or self.closing: return
            if index == len(queries):
                props = dict(re.findall(r'\[([^]]+)\]:\s*\[([^]]*)\]', data.get('props', '')))
                p = Profile(); p.raw = data
                p.api = int(props.get('ro.build.version.sdk', '0') or 0); p.release = props.get('ro.build.version.release', '?')
                p.model = props.get('ro.product.model', '?'); p.abis = props.get('ro.product.cpu.abilist', 'arm64-v8a').split(',')
                p.model_code = next((props.get(k, '').lower().strip() for k in ('ro.build.product_3rdparty', 'ro.product.name', 'ro.build.product', 'ro.product.device') if props.get(k, '').strip() and props[k].lower().strip() != 'msmnile_gvmq'), '')
                p.vin = props.get('sys.qg.tboxvin', '')
                p.locales = list(dict.fromkeys([props.get('persist.sys.locale', 'ru-RU'), 'ru', 'en']))
                p.per_display = bool(re.search(r'(?im)^\s*density[^\n]*-d\s+DISPLAY_ID', data.get('wm', '')))
                p.input_display = bool(re.search(r'-d\s+(?:DISPLAY_ID|<displayId>)', data.get('input', ''), re.I))
                ids = re.findall(r'(?:mDisplayId=|Display\s*#?\s*)(\d+)', data.get('display', ''))
                if ids: p.displays = sorted(set(map(int, ids)))
                density = re.findall(r'(?:Physical|Override) density:\s*(\d+)', data.get('density', ''))
                if density: p.density = int(density[-1])
                uid = re.search(r'uid=(\d+)', data.get('uid', '')); p.uid = int(uid[1]) if uid else 2000
                self.profile = p
                self.device_info.setText(f'{p.model}  /  Android {p.release}  /  API {p.api}')
                self.device_info.setToolTip('Model: ' + p.model_code + '\nVIN: ' + (p.vin or '—') + '\nUID: ' + str(p.uid))
                self.pages['tweaks'].update_profile(); return
            key, args = queries[index]
            def complete(r):
                data[key] = r.text; query(index + 1)
            self.adb(args, complete, target=target, shell=True, timeout=10000, check=False)
        query()

    @feature_required('device.root')
    def root_menu(self):
        if not self.ready(): return
        menu = QMenu(self)
        for text, method in [('adb root', 'root'), ('Проверить su', 'su'), ('adb unroot', 'unroot'), ('Обычный shell', 'shell')]:
            menu.addAction(self.t(text), lambda m=method: self.set_privilege(m))
        menu.exec(self.root_button.mapToGlobal(self.root_button.rect().bottomLeft()))

    @feature_required('device.root')
    def set_privilege(self, method):
        if not self.ready(): return
        if method == 'shell': self.privilege = 'shell'; self.root_button.setText(self.t('Расширенный режим')); return
        question = {'root':'Повысить права через adb root? adbd будет перезапущен.', 'su':'Проверить su на ГУ? Может потребоваться разрешение на экране.', 'unroot':'Вернуть adbd к обычным правам?'}[method]
        if not self.confirm(self.t(question)): return
        target = self.target
        def verified(result):
            root = bool(re.search(r'uid=0\b', result.text))
            self.end(result.ok and (root if method != 'unroot' else not root))
            self.privilege = ('su' if method == 'su' else 'root') if root else 'shell'
            self.root_button.setText('ROOT · ' + self.privilege if root else self.t('Расширенный режим'))
            if method != 'unroot' and not root: self.error(self.t('Сеанс не имеет Root-прав.'), result.text)
            self.read_profile()
        if not self.begin('Root'): return
        if method == 'su':
            def try_su(index=0):
                prefixes = [['su', 'sh', '-c'], ['su', '-c']]
                def tested(result):
                    if result.ok and re.search(r'uid=0\b', result.text):
                        self.su_prefix = prefixes[index]; verified(result)
                    elif index == 0 and not result.cancelled and not self.cancel_requested: try_su(1)
                    else: verified(result)
                self.active_job = self.adb(prefixes[index] + ['id'], tested, shell=True, timeout=12000)
            try_su(); return
        def restarted(result):
            if not result.ok or 'cannot run as root' in result.text:
                self.end(False); self.error(self.t('Сеанс не имеет Root-прав.'), result.text); return
            def wait_complete(r):
                if not r.ok: self.end(False); self.error(self.t(explain_error(r.text)), r.text); return
                self.active_job = self.adb(['id'], verified, target=target, shell=True)
            def wait():
                if target.mode == 'wifi':
                    self.adb(['connect', target.serial], lambda r: self.adb(['wait-for-device'], wait_complete, target=target, timeout=12000), global_cmd=True, timeout=8000)
                else: self.active_job = self.adb(['wait-for-device'], wait_complete, target=target, timeout=12000)
            QTimer.singleShot(1000, wait)
        self.active_job = self.adb([method], restarted, target=target, timeout=10000)

    @feature_required('device.reboot')
    def reboot_menu(self):
        menu = QMenu(self)
        for text, mode in [('Обычная перезагрузка', ''), ('Перезагрузка в Recovery', 'recovery'), ('Перезагрузка в Bootloader', 'bootloader'), ('Рестарт Android (stop/start)', 'framework')]:
            menu.addAction(self.t(text), lambda m=mode: self.reboot(m))
        menu.exec(self.reboot_button.mapToGlobal(self.reboot_button.rect().bottomLeft()))

    @feature_required('device.reboot')
    def reboot(self, mode):
        if not self.ready() or not self.confirm(self.t('Перезапустить ГУ выбранным способом?') + '\n' + (mode or 'Android')): return
        steps = [Step('stop && start', True, True)] if mode == 'framework' else [Step(['reboot'] + ([mode] if mode else []), False)]
        self.sequence(self.t('Перезагрузка'), steps, lambda ok, r: self.refresh_devices())

    def keyevent(self, code):
        if not self.ready(): return
        self.sequence(self.t('Подключение') + ' · keyevent', [Step(['input', 'keyevent', str(code)])])

    def screenshot(self):
        if not self.ready(): return
        menu = QMenu(self); menu.addAction(self.t('Основной экран SurfaceFlinger'), lambda: self.capture_screen())
        menu.addAction(self.t('Выбрать физический дисплей'), self.select_capture_display)
        menu.exec(self.cursor().pos())

    def select_capture_display(self):
        if not self.ready(): return
        def found(ok, results):
            if not ok: return
            if '-d' not in results[0].text:
                self.error(self.t('Захват этого экрана недоступен на прошивке.')); return
            # SurfaceFlinger physical IDs must not be confused with am/wm logical IDs.
            matches = re.findall(r'(?m)^\s*Display\s+(\d+)\s*\(([^\n]*)', results[1].text)
            if not matches: self.error(self.t('Физические дисплеи не обнаружены. Используйте основной экран SurfaceFlinger.')); return
            labels = [f'{physical} · {description}' for physical, description in matches]
            chosen, accepted = QInputDialog.getItem(self, self.t('Скриншот'), self.t('Выбрать физический дисплей'), labels, 0, False)
            if accepted: self.capture_screen(matches[labels.index(chosen)][0])
        self.sequence(self.t('Скриншот'), [Step(['screencap', '-h']), Step(['dumpsys', 'SurfaceFlinger', '--display-id'])], found)

    def capture_screen(self, physical_id=None):
        if not self.ready(): return
        file, _ = QFileDialog.getSaveFileName(self, self.t('Скриншот'), 'voyah-' + time.strftime('%Y%m%d-%H%M%S') + '.png', 'PNG (*.png)')
        if not file: return
        if not self.begin(self.t('Скриншот')): return
        def captured(r):
            if r.ok and r.stdout.startswith(b'\x89PNG\r\n\x1a\n'):
                self.background(lambda: Path(file).write_bytes(r.stdout), lambda value, err: (self.end(not err), self.error(str(err)) if err else self.notice(self.t('Сохранено: {path}', path=file))))
            else:
                self.end(False); self.error(self.t('Захват этого экрана недоступен на прошивке.'), r.text[:3000])
        self.active_job = self.adb(['exec-out', 'screencap', '-p'] + (['-d', str(physical_id)] if physical_id else []), captured, binary=True, timeout=30000)

    def about(self):
        dialog = QDialog(self); dialog.setWindowTitle(self.t('О приложении')); dialog.resize(620, 440)
        layout = QVBoxLayout(dialog); label = QLabel('VOYAH MANAGER  ' + VERSION); label.setObjectName('section'); layout.addWidget(label)
        text = logbox(); text.setPlainText('Python 3.12 · PySide6 / Qt 6 · Android Debug Bridge\nAAPT2 · bundletool 1.18.3 · Eclipse Temurin Java 17\n\n' + self.t('Совместимость с реальным ГУ ещё не проверена.') + '\n\n' + 'ADB: ' + self.adb_path + '\nData: ' + str(DATA_DIR) + '\n\n' + 'Open-source notices: tools/adb/NOTICE.txt; tools/jre/legal; tools/licenses; THIRD_PARTY_NOTICES.txt\nQt for Python: LGPL v3 / GPL v3 / commercial. Application source and build scripts are supplied for rebuilding with modified Qt libraries.\nhttps://code.qt.io/pyside/pyside-setup.git\nhttps://developer.android.com/tools/adb\nhttps://github.com/google/bundletool\nhttps://adoptium.net/'); layout.addWidget(text)
        btn = QPushButton(self.t('Закрыть')); btn.clicked.connect(dialog.accept); layout.addWidget(btn); dialog.exec()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if self.current_section() == 'files': self.pages['files'].push_paths(paths)
        else: self.select_section('installer'); self.pages['installer'].add_paths(paths)
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.busy and not self.smoke and not self.confirm(self.t('Остановить текущие задания и закрыть программу?')):
            event.ignore(); return
        if self.recipe and self.recipe.running:
            self.recipe.close_after = True; self.recipe.cancel(); self.notice(self.t('Восстановление состояния перед закрытием…')); event.ignore(); return
        self.closing = True; self.poll.stop(); self.catalog.timer.stop(); self.web.cancel_all(); self.cancel_requested = True; self.pages['installer'].service.cancel_event.set()
        if getattr(self,'install_service',None): self.install_service.cancel_event.set()
        for page in self.pages.values():
            if hasattr(page, 'stop_streams'): page.stop_streams()
        self.runner.cancel_all()
        if self.demo_backend:
            for job in list(self.demo_backend.jobs): job.cancel()
        self.settings.sync(); event.accept()

class InspectorPage(Page):
    def __init__(self, main):
        super().__init__(main); self.streams = {}; self.stream_buffers = {'logcat':'', 'getevent':''}; self.full_capture = ''; self.full_dump = ''
        card = self.card('Что сейчас на экранах?'); self.row(card, self.button('Сканировать экраны', self.scan, True), 1)
        self.screen_grid = QGridLayout(); card.addLayout(self.screen_grid); self.fields = {}; self.display_tags = {}; self.last_screens = {}
        for column, display in enumerate((0, 1, 2)):
            panel = QWidget(); panel.setStyleSheet('background:transparent;'); panel_layout = QVBoxLayout(panel); panel_layout.setContentsMargins(0, 0, 8, 0)
            tag = QLabel(f'DISPLAY {display}'); tag.setObjectName('eyebrow'); panel_layout.addWidget(tag); self.display_tags[display] = tag
            for i, key in enumerate(('package', 'activity', 'component')):
                panel_layout.addWidget(QLabel(('Package', 'Activity', 'Component')[i]))
                edit = QLineEdit(); edit.setReadOnly(True); edit.setPlaceholderText('—'); self.fields[display, key] = edit
                row = QHBoxLayout(); row.addWidget(edit, 1)
                button = self.button('Копировать', lambda checked=False, e=edit: QApplication.clipboard().setText(e.text())); button.setMaximumWidth(104); row.addWidget(button); panel_layout.addLayout(row)
            self.screen_grid.addWidget(panel, 0, column); self.screen_grid.setColumnStretch(column, 1)
        card = self.card('Перехват кнопки руля'); self.capture_progress = QProgressBar(); self.capture_progress.setRange(0, 60); self.capture_progress.setValue(0)
        self.capture_btn = self.button('Перехватить 6 секунд', self.capture, True)
        self.row(card, self.capture_btn, self.capture_progress, self.button('Сохранить и открыть в Блокноте', lambda: self.save_text(self.full_capture, 'voyah-capture.txt', True)))
        self.capture_tabs = QTabWidget(); self.capture_views = [logbox() for _ in range(4)]
        for text, view in zip(('Запуски экранов', 'Руль / MCU / ассистенты', 'Сервисы / Broadcast', 'Полный лог'), self.capture_views): self.capture_tabs.addTab(view, self.t(text))
        self.capture_tabs.setMinimumHeight(200); card.addWidget(self.capture_tabs)
        self.capture_timer = QTimer(self); self.capture_timer.setInterval(100); self.capture_timer.timeout.connect(self.capture_tick); self.capture_started = 0
        card = self.card('Live-мониторинг'); self.live_filter = self.edit('Фильтр: слова через запятую'); self.live_filter.textChanged.connect(self.refilter)
        self.row(card, self.live_filter, self.button('Сохранить', lambda: self.save_text('\n'.join(self.stream_buffers.values()), 'voyah-live.txt')))
        self.live_views = {}; self.live_buttons = {}
        splitter = QSplitter(Qt.Orientation.Horizontal)
        for name in ('logcat', 'getevent'):
            panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(0, 0, 0, 0)
            row = QHBoxLayout(); label = QLabel(name.upper()); label.setObjectName('eyebrow'); row.addWidget(label)
            button = self.button('Старт', lambda checked=False, n=name: self.toggle_stream(n)); row.addWidget(button); self.live_buttons[name] = button
            layout.addLayout(row); view = logbox(); view.setMinimumHeight(200); self.live_views[name] = view; layout.addWidget(view); splitter.addWidget(panel)
        card.addWidget(splitter)
        card = self.card('Пакеты и интенты'); self.package_search = self.edit('Поиск пакета'); self.package_combo = QComboBox(); self.package_combo.setEditable(True)
        self.row(card, self.package_search, self.button('Найти', self.search_packages), self.package_combo, self.button('Дамп пакета', self.dump_package, True), self.button('Сохранить', lambda: self.save_text(self.full_dump, 'voyah-package.txt')))
        self.dump_view = logbox(); self.dump_view.setMinimumHeight(240); card.addWidget(self.dump_view); self.layout.addStretch()
        cards = []
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget(): cards.append(item.widget())
        self.sections = QTabWidget()
        for key, widget in zip(('Экраны','Кнопки руля','Live','Интенты'), cards): self.sections.addTab(widget, self.t(key))
        self.layout.addWidget(self.sections)

    def retranslate(self):
        super().retranslate()
        for i, text in enumerate(('Запуски экранов', 'Руль / MCU / ассистенты', 'Сервисы / Broadcast', 'Полный лог')): self.capture_tabs.setTabText(i, self.t(text))
        for i,key in enumerate(('Экраны','Кнопки руля','Live','Интенты')): self.sections.setTabText(i,self.t(key))
        for name, button in self.live_buttons.items(): button.setText(self.t('Стоп' if name in self.streams else 'Старт'))

    @feature_required('inspector')
    def scan(self):
        if not self.main.ready(): return
        target = self.main.target
        def done(ok, results):
            if not ok: return
            window, activity = results[0].text, results[1].text
            self.main.background(lambda: parse_screens(window, activity), lambda screens, err: self.show_screens(screens or {}) if target == self.main.target else None)
        self.main.sequence(self.t('Сканировать экраны'), [Step(['dumpsys', 'window']), Step(['dumpsys', 'activity', 'activities'])], done)

    def show_screens(self, screens):
        self.last_screens = screens
        ids = [self.main.display_map[role] for role in ('cluster', 'center', 'passenger')]
        for display, label in self.display_tags.items(): label.setText(f'DISPLAY {ids[display]}')
        for (display, key), edit in self.fields.items(): edit.setText(screens.get(ids[display], {}).get(key, ''))

    @feature_required('inspector')
    def capture(self):
        if not self.main.ready() or not self.main.begin(self.t('Перехват кнопки руля')): return
        self.capture_target = self.main.target; self.capture_btn.setEnabled(False)
        def cleared(result):
            if not result.ok:
                self.capture_btn.setEnabled(True); self.main.end(False); self.main.error(self.t(explain_error(result.text)), result.text); return
            self.capture_started = time.monotonic(); self.capture_progress.setValue(0); self.capture_timer.start()
            self.main.notice(self.t('Нажмите кнопку на руле сейчас…'))
        self.main.active_job = self.main.adb(['logcat', '-b', 'main', '-b', 'system', '-b', 'events', '-c'], cleared, target=self.capture_target)

    def capture_tick(self):
        elapsed = time.monotonic() - self.capture_started; self.capture_progress.setValue(min(60, int(elapsed * 10)))
        if self.main.cancel_requested:
            self.capture_timer.stop(); self.capture_btn.setEnabled(True); self.main.end(False); return
        if elapsed < 6: return
        self.capture_timer.stop()
        def captured(result):
            self.capture_btn.setEnabled(True); self.main.end(result.ok)
            if not result.ok: self.main.error(self.t(explain_error(result.text)), result.text); return
            self.full_capture = result.text; self.capture_views[3].setPlainText(result.text)
            self.main.background(lambda: classify_capture(result.text), self.show_capture)
        self.main.active_job = self.main.adb(['logcat', '-d', '-b', 'main', '-b', 'system', '-b', 'events', '-v', 'time'], captured, target=self.capture_target, timeout=30000, check=False)

    def show_capture(self, categories, error):
        for view, lines in zip(self.capture_views, categories or [[], [], []]): view.setPlainText('\n'.join(lines) or self.t('События не найдены. CAN/MCU может обходить Android input и публичные логи.'))

    @feature_required('inspector')
    def toggle_stream(self, name):
        if name in self.streams:
            self.streams.pop(name).cancel(); self.live_buttons[name].setText(self.t('Старт')); return
        if not self.main.target: self.main.error(self.t('Сначала подключите устройство.')); return
        if self.main.busy: self.main.error(self.t('Дождитесь завершения или отмените текущее задание.')); return
        args = ['logcat', '-b', 'main', '-b', 'system', '-b', 'events', '-v', 'time'] if name == 'logcat' else ['getevent', '-lt']
        def chunk(text):
            self.stream_buffers[name] = (self.stream_buffers[name] + text)[-2_000_000:]
            filters = [word.strip().lower() for word in self.live_filter.text().split(',') if word.strip()]
            append_log(self.live_views[name], ''.join(line for line in text.splitlines(keepends=True) if not filters or any(word in line.lower() for word in filters)))
        def finished(result):
            self.streams.pop(name, None); self.live_buttons[name].setText(self.t('Старт'))
            if not result.ok and not result.cancelled:
                append_log(self.live_views[name], '\n' + self.t(explain_error(result.text)) + '\n' + result.text + '\n')
        self.streams[name] = self.main.adb(args, finished, shell=name == 'getevent', privileged=name == 'getevent', stream=chunk, timeout=0, check=False)
        self.live_buttons[name].setText(self.t('Стоп'))

    def refilter(self):
        filters = [word.strip().lower() for word in self.live_filter.text().split(',') if word.strip()]
        for name, view in self.live_views.items(): view.setPlainText('\n'.join(line for line in self.stream_buffers[name].splitlines() if not filters or any(w in line.lower() for w in filters)))

    def stop_streams(self):
        self.capture_timer.stop()
        for job in list(self.streams.values()): job.cancel()
        self.streams.clear()

    @feature_required('inspector')
    def search_packages(self):
        if not self.main.ready(): return
        word = self.package_search.text().strip().lower()
        def done(ok, results):
            if ok:
                packages = sorted(line[8:] for line in results[0].text.splitlines() if line.startswith('package:') and word in line.lower())
                self.package_combo.clear(); self.package_combo.addItems(packages)
        self.main.sequence(self.t('Найти'), [Step(['pm', 'list', 'packages'])], done)

    @feature_required('inspector')
    def dump_package(self):
        pkg = self.package_combo.currentText().strip()
        if not self.main.ready(): return
        if not PACKAGE_RE.fullmatch(pkg): self.main.error(self.t('Выберите пакет.')); return
        def done(ok, results):
            if ok:
                self.full_dump = results[0].text; self.dump_view.setPlainText(self.full_dump)
                selections = []
                from PySide6.QtWidgets import QTextEdit
                from PySide6.QtGui import QTextCharFormat
                for match in re.finditer(r'^.*(?:Activity|Receiver|Service) Resolver Table.*$', self.full_dump, re.M):
                    selection = QTextEdit.ExtraSelection(); cursor = self.dump_view.textCursor(); cursor.setPosition(match.start()); cursor.setPosition(match.end(), QTextCursor.MoveMode.KeepAnchor)
                    selection.cursor = cursor; fmt = QTextCharFormat(); fmt.setForeground(QColor('#64DFF4')); fmt.setFontWeight(QFont.Weight.Bold); selection.format = fmt; selections.append(selection)
                self.dump_view.setExtraSelections(selections)
        self.main.sequence(self.t('Дамп пакета'), [Step(['dumpsys', 'package', pkg])], done)

@dataclass
class ApkInfo:
    path: Path
    package: str
    version: str
    min_sdk: int
    split: str = ''
    abis: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    config_for: str = ''

def parse_badging(path: Path, text: str) -> ApkInfo:
    package_line = next((line for line in text.splitlines() if line.startswith('package:')), '')
    attrs = dict(re.findall(r"(\w+)='([^']*)'", package_line))
    if not attrs.get('name') or not PACKAGE_RE.fullmatch(attrs['name']): raise ValueError('Не удалось прочитать манифест APK.')
    sdk = re.search(r"sdkVersion:'(\d+)'", text)
    native = re.search(r'^native-code:(.*)', text, re.M)
    return ApkInfo(path, attrs['name'], attrs.get('versionCode', ''), int(sdk[1]) if sdk else 1,
        attrs.get('split', ''), re.findall(r"'([^']+)'", native[1]) if native else [], re.findall(r"uses-split[^:]*:\s*'([^']+)'", text))

def validate_apks(infos: list[ApkInfo], api=0):
    if not infos: raise ValueError('В архиве нет APK.')
    if len({(i.package, i.version) for i in infos}) != 1: raise ValueError('APK имеют разные package/versionCode.')
    if sum(not i.split for i in infos) != 1: raise ValueError('Не найден единственный base APK.')
    splits = {i.split for i in infos}
    missing = set(req for i in infos for req in i.requires) - splits
    if missing: raise ValueError('Отсутствуют зависимости splits: {names}'.format(names=', '.join(sorted(missing))))
    if len(splits) != len(infos): raise ValueError('Duplicate split names')
    if api and any(i.min_sdk > api for i in infos): raise ValueError('Приложение требует более новую версию Android (minSdk выше API ГУ).')

class InstallerPage(Page):
    def __init__(self, main):
        super().__init__(main); self.setAcceptDrops(True); self.files = []; self.service = InstallService(main); self.cancel_event = self.service.cancel_event
        card = self.card('Установщик APK'); self.mode = QComboBox(); self.mode_keys = ['Одиночный APK', 'Пакетная установка', 'Split / APKS / XAPK / APKM']
        self.mode.addItems([self.t(k) for k in self.mode_keys]); self.row(card, self.label('Режим установки'), self.mode, 1)
        self.row(card, self.button('Добавить файлы', self.add_files), self.button('Добавить папку', self.add_folder), self.button('Очистить', self.clear_files), 1)
        self.drop_hint = self.label('Перетащите APK или архивы сюда', 'subtitle'); card.addWidget(self.drop_hint)
        self.file_table = table([self.t('Файл'), self.t('Размер'), self.t('Статус')]); self.file_table.setMinimumHeight(230); self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        card.addWidget(self.file_table)
        self.flags = []
        for text, checked in [('Переустановка (-r)', True), ('Понижение версии (-d)', False), ('Выдать разрешения (-g)', True)]:
            check = self.bind(QCheckBox(), text); check.setChecked(checked); self.flags.append(check)
        self.row(card, *self.flags, 1)
        self.progress = QProgressBar(); self.progress.setValue(0); self.install_button = self.button('Установить', self.install, True)
        self.row(card, self.install_button, self.progress)
        card = self.card('Журнал операций'); self.log = logbox(); self.log.setMinimumHeight(260); card.addWidget(self.log)
        self.row(card, self.button('Сохранить', lambda: self.save_text(self.log.toPlainText(), 'voyah-install.txt')), 1)
        self.service.log_message.connect(lambda text: append_log(self.log,text)); self.service.status_changed.connect(self.set_status); self.service.progress_changed.connect(self.progress.setValue); self.service.finished.connect(lambda ok: self.install_button.setEnabled(self.main.allowed('apk.install',False)))
        self.layout.addStretch()

    def retranslate(self):
        super().retranslate()
        for i, key in enumerate(self.mode_keys): self.mode.setItemText(i, self.t(key))
        self.file_table.setHorizontalHeaderLabels([self.t(k) for k in ('Файл', 'Размер', 'Статус')])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths([url.toLocalFile() for url in event.mimeData().urls()]); event.acceptProposedAction()

    @feature_required('apk.install', 'installer')
    def add_paths(self, paths):
        if self.main.busy: return
        for path in paths:
            p = Path(path)
            if p.is_dir():
                self.main.background(lambda d=p: sorted(d.glob('*.apk')), lambda result, err: self.add_paths(result or [])); continue
            if p.suffix.lower() in ('.apk', '.apks', '.xapk', '.apkm') and p.is_file() and str(p) not in self.files:
                self.files.append(str(p)); row = self.file_table.rowCount(); self.file_table.insertRow(row)
                for col, text in enumerate((p.name, human_size(p.stat().st_size), self.t('В очереди'))): self.file_table.setItem(row, col, QTableWidgetItem(text))
                self.file_table.item(row, 0).setToolTip(str(p))
        if any(Path(p).suffix.lower() != '.apk' for p in self.files): self.mode.setCurrentIndex(2)
        elif len(self.files) > 1 and self.mode.currentIndex() == 0: self.mode.setCurrentIndex(1)

    @feature_required('apk.install', 'installer')
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, self.t('Добавить файлы'), '', 'Android (*.apk *.apks *.xapk *.apkm)'); self.add_paths(files)

    @feature_required('apk.install', 'installer')
    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.t('Добавить папку'))
        if folder: self.add_paths([folder])

    def clear_files(self):
        if not self.main.busy: self.files.clear(); self.file_table.setRowCount(0)

    def set_status(self, rows, text, success=None):
        for row in rows:
            item = QTableWidgetItem(text)
            if success is not None: item.setForeground(QColor('#51D8A5' if success else '#FF939E'))
            self.file_table.setItem(row, 2, item)

    @feature_required('apk.install', 'installer')
    def install(self):
        if not self.main.ready(): return
        if not self.files: self.main.error(self.t('Выберите файлы для установки.')); return
        mode = self.mode.currentIndex()
        if mode == 0 and (len(self.files) != 1 or Path(self.files[0]).suffix.lower() != '.apk'):
            self.main.error(self.t('Выберите один APK в одиночном режиме.')); return
        if mode == 1 and any(Path(p).suffix.lower() != '.apk' for p in self.files): self.main.error(self.t('Архивы устанавливаются в режиме Split.')); return
        if mode == 2 and any(Path(p).suffix.lower() != '.apk' for p in self.files) and len(self.files) != 1:
            self.main.error(self.t('Для продолжения нужен один комплект приложения.')); return
        self.log.clear(); self.progress.setValue(0)
        if self.service.start(self.files,mode,[flag for flag,check in zip(('-r','-d','-g'),self.flags) if check.isChecked()]): self.install_button.setEnabled(False)

class InstallService(QObject):
    log_message = Signal(str)
    status_changed = Signal(object,str,object)
    progress_changed = Signal(int)
    finished = Signal(bool)
    def __init__(self, main):
        super().__init__(main); self.main = main; self.cancel_event = threading.Event(); self.tempdirs = []; self.current_infos = []; self.obb = []
    def t(self, text, **values): return self.main.t(text, **values)
    def write_log(self, text):
        self.log_message.emit(text); append_log(self.main.shared_log,text)
    def set_status(self, rows, text, success=None): self.status_changed.emit(rows,text,success)
    def start(self, files, mode=0, flags=None, target=None, expected_package='', post_install=None):
        if not self.main.allowed('apk.install') or not self.main.ready(): return False
        if not self.main.profile.api:
            self.main.error(self.t('Подождите завершения определения параметров ГУ.')); return False
        if not files: return False
        if not self.main.begin(self.t('Установщик APK')): return False
        self.main.install_service = self; self.cancel_event.clear(); self.install_target = Target((target or self.main.target).serial,(target or self.main.target).mode)
        self.install_profile = copy.deepcopy(self.main.profile); self.install_flags = flags if flags is not None else ['-r','-g']
        self.expected_package = expected_package; self.post_install = post_install or []
        self.groups = [([Path(p)],[i]) for i,p in enumerate(files)] if mode == 1 else [([Path(p) for p in files],list(range(len(files))))]
        self.group_index = 0; self.any_failed = False; self.current_rows = self.groups[0][1]
        def state(result):
            if not result.ok or result.text != 'device': self.group_error(result.text or 'device offline'); return
            self.prepare_group()
        def waited(result):
            if not result.ok:
                self.set_status(self.current_rows,self.t('Ошибка'),False); self.finish(False); self.main.error(self.t(explain_error(result.text)),result.text); return
            self.main.active_job = self.main.adb(['get-state'],state,target=self.install_target,timeout=8000)
        self.main.active_job = self.main.adb(['wait-for-device'],waited,target=self.install_target,timeout=20000)
        return True

    def prepare_group(self):
        if self.main.cancel_requested or self.cancel_event.is_set(): self.finish(False); return
        if self.group_index >= len(self.groups): self.finish(not self.any_failed); return
        paths, self.current_rows = self.groups[self.group_index]; self.current_infos = []; self.obb = []
        self.set_status(self.current_rows, self.t('Подготовка APK…')); self.write_log( '\n▶ ' + ', '.join(p.name for p in paths) + '\n')
        if paths[0].suffix.lower() == '.apk': self.inspect_paths(paths); return
        temp = tempfile.TemporaryDirectory(prefix='voyah-apk-'); self.tempdirs.append(temp); directory = Path(temp.name)
        def extract():
            files = safe_extract(paths[0], directory / 'contents', self.cancel_event)
            return files
        def extracted(files, error):
            if error: self.group_error(str(error)); return
            self.obb = [p for p in files if p.suffix.lower() == '.obb']
            if (directory / 'contents' / 'toc.pb').exists():
                if not self.install_profile.api: self.group_error('Device API is not known. Reconnect and retry.'); return
                spec = directory / 'device.json'; spec.write_text(json.dumps({'supportedAbis': self.install_profile.abis, 'supportedLocales': self.install_profile.locales,
                    'screenDensity': self.install_profile.density, 'sdkVersion': self.install_profile.api}), encoding='utf-8')
                selected = directory / 'selected'
                args = ['-jar', str(self.main.tools.path('bundletool.jar')), 'extract-apks', '--apks=' + str(paths[0]), '--output-dir=' + str(selected), '--device-spec=' + str(spec)]
                def chosen(result):
                    self.write_log( result.text + '\n')
                    if not result.ok: self.group_error(result.text); return
                    self.inspect_paths(sorted(selected.rglob('*.apk')))
                self.main.active_job = self.main.runner.run(self.main.tools.path('jre/bin/java.exe'), args, chosen, timeout=120000)
            else: self.inspect_paths([p for p in files if p.suffix.lower() == '.apk'])
        self.main.background(extract, extracted)

    def inspect_paths(self, paths, index=0):
        if self.main.cancel_requested: self.finish(False); return
        if not paths: self.group_error('В архиве нет APK.'); return
        if index == len(paths): self.select_and_install(); return
        def inspected(result):
            if not result.ok: self.group_error(result.text); return
            try: info = parse_badging(paths[index], result.text)
            except ValueError as error: self.group_error(str(error)); return
            def xml_read(xml):
                # uses-split names are visible in aapt2's manifest tree even when omitted by badging.
                required = re.findall(r'E: uses-split[^\n]*\n\s*A: android:name[^=]*="([^"]+)"', xml.text)
                info.requires = sorted(set(info.requires + required))
                config = re.search(r'A: (?:android:)?configForSplit(?:\([^)]*\))?="([^"]+)"', xml.text)
                info.config_for = config[1] if config else ''
                self.current_infos.append(info); self.inspect_paths(paths, index + 1)
            self.main.active_job = self.main.runner.run(self.main.tools.path('aapt2.exe'), ['dump', 'xmltree', str(paths[index]), '--file', 'AndroidManifest.xml'], xml_read, timeout=30000)
        self.main.active_job = self.main.runner.run(self.main.tools.path('aapt2.exe'), ['dump', 'badging', str(paths[index])], inspected, timeout=30000)

    def select_and_install(self):
        if self.main.cancel_requested: self.finish(False); return
        infos = self.current_infos
        known = ('arm64_v8a', 'armeabi_v7a', 'x86_64', 'x86')
        available_abis = {abi for i in infos if i.split for abi in known if re.search(r'(?:^|[._])' + abi + r'(?:$|[._])', i.split.lower())}
        preferred = next((a.replace('-', '_') for a in self.install_profile.abis if a.replace('-', '_') in available_abis), '')
        if available_abis and not preferred: self.group_error('APK предназначен для другой архитектуры процессора.'); return
        infos = [i for i in infos if not i.split or not any(a in i.split.lower() for a in known) or preferred in i.split.lower()]
        if any(i.abis and not set(i.abis).intersection(self.install_profile.abis) for i in infos): self.group_error('APK предназначен для другой архитектуры процессора.'); return
        densities = {'ldpi':120, 'mdpi':160, 'tvdpi':213, 'hdpi':240, 'xhdpi':320, 'xxhdpi':480, 'xxxhdpi':640}
        density_infos = [(i, next((v for k, v in densities.items() if re.search(r'(?:^|[._])' + k + r'(?:$|[._])', i.split)), None)) for i in infos]
        by_module = {}
        for info, density in density_infos:
            if density: by_module.setdefault(info.config_for, []).append(density)
        closest = {module:min(values, key=lambda value: abs(value - self.install_profile.density)) for module, values in by_module.items()}
        infos = [i for i, density in density_infos if density is None or density == closest[i.config_for]]
        if sum(not i.split for i in infos) != 1 or len({(i.package, i.version) for i in infos}) != 1 or len({i.split for i in infos}) != len(infos):
            dialog = QDialog(self.main); dialog.setWindowTitle(self.t('Выбор компонентов')); dialog.resize(700, 430); layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel(self.t('Выберите один совместимый base и нужные splits.'))); listing = QListWidget(); layout.addWidget(listing)
            for info in infos:
                item = QListWidgetItem(f'{info.package}  v{info.version}  [{info.split or "base"}]  {info.path.name}'); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Checked); listing.addItem(item)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
            if not dialog.exec(): self.finish(False); return
            infos = [i for n, i in enumerate(infos) if listing.item(n).checkState() == Qt.CheckState.Checked]
        try: validate_apks(infos, self.install_profile.api)
        except ValueError as error: self.group_error(str(error)); return
        if self.expected_package and infos[0].package != self.expected_package:
            self.group_error('Имя пакета не совпадает с каталогом.'); return
        self.current_infos = infos
        self.write_log( f'Package: {infos[0].package}  versionCode={infos[0].version}  API≥{max(i.min_sdk for i in infos)}\n')
        for info in infos: self.write_log( '  ' + (info.split or 'base') + ' → ' + info.path.name + '\n')
        self.prepare_voyah()

    def prepare_voyah(self):
        self.is_voyah = bool(self.install_profile.model_code in KEYBOARD_MODELS or re.search('voyah|qinggan',self.install_profile.model,re.I))
        if not self.is_voyah: self.execute_install(); return
        def read(result):
            if not result.ok: self.group_error(result.text); return
            if result.text.lower() in ('true','1'):
                def changed(r):
                    if not r.ok: self.group_error(r.text); return
                    def verified(v):
                        if not v.ok or v.text.lower() != 'false': self.group_error('Не удалось снять блокировку установки Voyah. Выберите Root вручную, если прошивка его поддерживает.'); return
                        self.execute_install()
                    self.main.active_job = self.main.adb(['getprop','sys.config.app_install_disabled'],verified,target=self.install_target,shell=True)
                self.main.active_job = self.main.adb(['setprop','sys.config.app_install_disabled','false'],changed,target=self.install_target,shell=True,privileged=True)
            else: self.execute_install()
        self.main.active_job = self.main.adb(['getprop','sys.config.app_install_disabled'],read,target=self.install_target,shell=True)

    def execute_install(self):
        if self.main.cancel_requested: self.finish(False); return
        infos = self.current_infos; command = 'install-multiple' if len(infos) > 1 else 'install'
        args = [command] + (['--no-streaming'] if self.is_voyah else []) + self.install_flags + [str(i.path) for i in sorted(infos, key=lambda i: bool(i.split))]
        if self.main.demo: self.main.demo_backend.pending_install = (infos[0].package,infos[0].version)
        self.set_status(self.current_rows, self.t('Выполняется…'))
        def installed(result):
            self.write_log( result.text + '\n')
            if result.timed_out or result.cancelled:
                self.any_failed = True; self.set_status(self.current_rows,self.t('Ошибка'),False)
                self.write_log(self.t('Результат установки неизвестен. Оставшаяся очередь остановлена.')+'\n'); self.finish(False); return
            if not result.ok or not re.search(r'(?m)^Success\s*$', result.text): self.group_error(result.text or 'Установка не подтверждена Package Manager.'); return
            pkg = infos[0].package
            def verified(r):
                if not r.ok or 'package:' not in r.text: self.group_error(r.text or 'Состояние не подтверждено устройством.'); return
                def version_read(v):
                    match = re.search(r'\bversionCode=(\d+)',v.text)
                    if not v.ok or not match or match[1] != infos[0].version: self.group_error('Установленная версия не совпадает с проверенным APK.'); return
                    self.post_install_steps(pkg)
                self.main.active_job = self.main.adb(['dumpsys','package',pkg],version_read,target=self.install_target,shell=True)
            self.main.active_job = self.main.adb(['pm', 'path', pkg], verified, target=self.install_target, shell=True)
        self.main.active_job = self.main.adb(args, installed, target=self.install_target, timeout=600000,
            stream=lambda text: self.transfer_progress(text))

    def post_install_steps(self, package):
        def complete():
            if self.obb and self.main.confirm(self.t('Перенести OBB в память ГУ?') + '\n/sdcard/Android/obb/' + package): self.copy_obb(package)
            else: self.group_success()
        if package != 'ru.vk.store' and 'request_install_packages' not in self.post_install: complete(); return
        def granted(r):
            if not r.ok: self.group_error('APK установлен; выдача права установки отклонена.\n' + r.text); return
            def checked(v):
                if not v.ok or not re.search(r'REQUEST_INSTALL_PACKAGES.*allow',v.text): self.group_error('APK установлен; право установки не подтверждено.\n' + v.text); return
                complete()
            self.main.active_job = self.main.adb(['appops','get',package,'REQUEST_INSTALL_PACKAGES'],checked,target=self.install_target,shell=True)
        self.main.active_job = self.main.adb(['appops','set',package,'REQUEST_INSTALL_PACKAGES','allow'],granted,target=self.install_target,shell=True,privileged=True)

    def transfer_progress(self, text):
        self.write_log( text)
        percent = re.findall(r'(\d+)%', text)
        if percent: self.progress_changed.emit(int(percent[-1]))

    def copy_obb(self, package):
        dest = '/sdcard/Android/obb/' + package
        def mkdir_done(result):
            if not result.ok: self.group_error('Копирование OBB завершилось ошибкой; APK уже установлен.\n' + result.text); return
            def push(index=0):
                if self.main.cancel_requested: self.finish(False); return
                if index == len(self.obb): self.group_success(); return
                path = self.obb[index]
                if not valid_name(path.name): self.group_error('Недопустимое имя.'); return
                def copied(r):
                    self.write_log( 'OBB: ' + r.text + '\n')
                    if not r.ok: self.group_error('Копирование OBB завершилось ошибкой; APK уже установлен.\n' + r.text)
                    else: push(index + 1)
                self.main.active_job = self.main.adb(['push', str(path), dest + '/' + path.name], copied, target=self.install_target, timeout=600000, stream=self.transfer_progress)
            push()
        self.main.active_job = self.main.adb(['mkdir', '-p', dest], mkdir_done, target=self.install_target, shell=True)

    def group_success(self):
        self.set_status(self.current_rows, self.t('Успешно'), True); self.group_index += 1
        self.progress_changed.emit(int(self.group_index / len(self.groups) * 100)); self.cleanup(); self.prepare_group()

    def group_error(self, text):
        self.any_failed = True
        message = self.t(text) if text in EN else self.t(explain_error(text)) + '\n' + text
        self.write_log( '✕ ' + message + '\n'); self.set_status(self.current_rows, self.t('Ошибка'), False)
        if re.search(r'(?:device.*(?:not found|offline)|no devices|closed|disconnected|protocol fault|transport error|connection (?:reset|refused|aborted)|cannot connect|failed to (?:read|write)|broken pipe|ADB command timed out)', text, re.I) or self.main.cancel_requested:
            self.finish(False); return
        self.group_index += 1; self.cleanup(); self.prepare_group()

    def cleanup(self):
        for directory in self.tempdirs:
            try: directory.cleanup()
            except OSError: logging.exception('Temporary APK cleanup')
        self.tempdirs.clear()

    def finish(self, success):
        if self.main.cancel_requested:
            for i in range(self.group_index, len(self.groups)): self.set_status(self.groups[i][1], self.t('Отменено'), False)
        elif not success:
            for i in range(self.group_index + 1, len(self.groups)): self.set_status(self.groups[i][1], self.t('Пропущено'), False)
        self.cleanup(); self.main.install_service = None; self.main.end(success); self.finished.emit(success)


def human_size(size):
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB': return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024

class ExplorerPage(Page):
    def __init__(self, main):
        super().__init__(main); self.setAcceptDrops(True); self.current_path = '/sdcard/'; self.entries = []
        card = self.card('Путь на ГУ'); self.path = QLineEdit('/sdcard/'); self.path.returnPressed.connect(self.refresh)
        self.row(card, self.button('Вверх', self.up), self.path, self.button('Обновить', self.refresh, True))
        bookmarks = QHBoxLayout()
        for path in ('/sdcard/', '/sdcard/Download/', '/storage/', '/system/priv-app/', '/data/local/tmp/'):
            b = QPushButton(path); b.clicked.connect(lambda checked=False, p=path: self.navigate(p)); bookmarks.addWidget(b)
        card.addLayout(bookmarks)
        self.file_table = table([self.t(k) for k in ('Имя', 'Тип', 'Размер', 'Дата')]); self.file_table.setMinimumHeight(180)
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch); self.file_table.cellDoubleClicked.connect(self.open_entry); 
        self.row(card, self.button('Загрузить в ГУ', self.push_files, True), self.button('Скачать на ПК', self.pull_files), self.button('Создать папку', self.mkdir),
                 self.button('Переименовать', self.rename), self.button('Удалить', self.delete, danger=True))
        self.row(card, self.button('Установить APK', self.install_remote), 1); card.addWidget(self.file_table)
        self.progress = QProgressBar(); self.progress.setValue(0); card.addWidget(self.progress)
        self.log = logbox(); self.log.setMinimumHeight(160); self.layout.addWidget(self.log); self.layout.addStretch()

    def retranslate(self):
        super().retranslate(); self.file_table.setHorizontalHeaderLabels([self.t(k) for k in ('Имя', 'Тип', 'Размер', 'Дата')])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event):
        self.push_paths([u.toLocalFile() for u in event.mimeData().urls()]); event.acceptProposedAction()

    def navigate(self, path): self.path.setText(path); self.refresh()

    def up(self): self.navigate(posixpath.dirname(self.current_path.rstrip('/')) or '/')

    @feature_required('files', 'files')
    def refresh(self):
        if not self.main.ready(): return
        path = self.path.text().strip()
        if not path.startswith('/') or '\x00' in path or '\n' in path: self.main.error(self.t('Недопустимое имя.')); return
        path = posixpath.normpath(path)
        def done(ok, results):
            if ok:
                self.current_path = path; self.path.setText(path)
                self.main.background(lambda: parse_listing(results[0].text), self.show_entries)
        self.main.sequence(self.t('Обновить'), [Step(['ls', '-lan', '--', path], privileged=True)], done)

    def show_entries(self, entries, error):
        if error: self.main.error(str(error)); return
        self.entries = entries; self.file_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            kind = 'Папка' if entry['directory'] else 'Ссылка' if entry['symlink'] else 'Файл'
            values = (entry['name'], self.t(kind), human_size(entry['size']), entry['date'])
            for col, text in enumerate(values): self.file_table.setItem(row, col, QTableWidgetItem(text))
            item = self.file_table.item(row, 0); item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(entry['mode'] + (' → ' + entry['link'] if entry['link'] else ''))
            item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon if entry['directory'] else QStyle.StandardPixmap.SP_FileLinkIcon if entry['symlink'] else QStyle.StandardPixmap.SP_FileIcon))

    def selected(self):
        return [self.file_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole) for index in self.file_table.selectionModel().selectedRows()]

    def selected_paths(self): return [posixpath.join(self.current_path, e['name']) for e in self.selected()]

    def open_entry(self, row, column):
        entry = self.file_table.item(row, 0).data(Qt.ItemDataRole.UserRole); path = posixpath.join(self.current_path, entry['name'])
        if entry['directory']: self.navigate(path)
        elif entry['symlink'] and self.main.target:
            self.main.adb(['test', '-d', path], lambda r: self.navigate(path) if r.ok else None, shell=True, privileged=True, check=False)

    @feature_required('files.write', 'files')
    def push_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, self.t('Загрузить в ГУ')); self.push_paths(files)

    @feature_required('files.write', 'files')
    def push_paths(self, paths):
        if not paths or not self.main.ready(): return
        destination = self.current_path
        steps = [Step(['push', str(Path(p)), posixpath.join(destination, Path(p).name)], False, timeout=600000) for p in paths if Path(p).exists()]
        self.transfer(self.t('Загрузить в ГУ'), steps, refresh=True)

    @feature_required('files', 'files')
    def pull_files(self):
        if not self.main.ready(): return
        paths = self.selected_paths()
        if not paths: self.main.error(self.t('Выберите файл или папку.')); return
        destination = QFileDialog.getExistingDirectory(self, self.t('Скачать на ПК'))
        if destination: self.transfer(self.t('Скачать на ПК'), [Step(['pull', p, destination], False, timeout=600000) for p in paths])

    def transfer(self, name, steps, refresh=False):
        if not steps or not self.main.begin(name): return
        target = self.main.target; self.progress.setRange(0, len(steps)); self.progress.setValue(0)
        def next_step(index=0):
            if self.main.cancel_requested: self.main.end(False); return
            if index == len(steps):
                self.main.end(True)
                if refresh: self.refresh()
                return
            step = steps[index]
            def chunk(text):
                append_log(self.log, text)
                perc = re.findall(r'(\d+)%', text)
                if perc: self.main.global_progress.setRange(0, 100); self.main.global_progress.setValue(int(perc[-1]))
            def complete(result):
                if not result.ok:
                    self.main.end(False)
                    if not result.cancelled: self.main.error(self.t(explain_error(result.text)), result.text)
                    return
                self.progress.setValue(index + 1); next_step(index + 1)
            self.main.active_job = self.main.adb(step.args, complete, target=target, shell=step.shell, privileged=step.privileged, timeout=step.timeout, stream=chunk)
        next_step()

    @feature_required('files.write', 'files')
    def mkdir(self):
        if not self.main.ready(): return
        name, ok = QInputDialog.getText(self, self.t('Создать папку'), self.t('Новая папка'))
        if not ok: return
        if not valid_name(name): self.main.error(self.t('Недопустимое имя.')); return
        target = posixpath.join(self.current_path, name)
        self.main.sequence(self.t('Создать папку'), [Step(['mkdir', '--', target], privileged=True), Step(['test', '-d', target], privileged=True)], lambda ok, r: self.refresh() if ok else None)

    @feature_required('files.write', 'files')
    def rename(self):
        if not self.main.ready(): return
        selected = self.selected()
        if len(selected) != 1: self.main.error(self.t('Выберите файл или папку.')); return
        name, ok = QInputDialog.getText(self, self.t('Переименовать'), self.t('Новое имя'), text=selected[0]['name'])
        if not ok: return
        if not valid_name(name): self.main.error(self.t('Недопустимое имя.')); return
        source = posixpath.join(self.current_path, selected[0]['name']); dest = posixpath.join(self.current_path, name)
        # mv -n prevents accidental replacement of an existing destination.
        self.main.sequence(self.t('Переименовать'), [Step(['test', '!', '-e', dest], privileged=True), Step(['test', '!', '-L', dest], privileged=True),
            Step(['mv', '-n', '--', source, dest], privileged=True), Step('test -e ' + shlex.quote(dest) + ' || test -L ' + shlex.quote(dest), privileged=True),
            Step(['test', '!', '-e', source], privileged=True), Step(['test', '!', '-L', source], privileged=True)], lambda ok, r: self.refresh() if ok else None)

    @feature_required('files.write', 'files')
    def delete(self):
        if not self.main.ready(): return
        paths = self.selected_paths()
        if not paths: self.main.error(self.t('Выберите файл или папку.')); return
        protected = {'/', '/sdcard', '/system', '/vendor', '/storage', '/data', '/dev', '/proc', '/sys', '/storage/emulated/0'}
        if any(posixpath.normpath(p) in protected for p in paths): self.main.error(self.t('Недопустимое имя.')); return
        if not self.main.confirm(self.t('Удалить выбранные объекты безвозвратно?') + '\n\n' + '\n'.join(paths)): return
        steps = []
        for p in paths: steps += [Step(['rm', '-rf', '--', p], privileged=True), Step(['test', '!', '-e', p], privileged=True), Step(['test', '!', '-L', p], privileged=True)]
        self.main.sequence(self.t('Удалить'), steps, lambda ok, r: self.refresh() if ok else None)

    @feature_required('apk.install', 'files')
    def install_remote(self):
        if not self.main.ready(): return
        paths = self.selected_paths()
        if len(paths) != 1 or not paths[0].lower().endswith('.apk'): self.main.error(self.t('Выберите один APK в одиночном режиме.')); return
        target = self.main.target; temporary = tempfile.TemporaryDirectory(prefix='voyah-remote-'); local = Path(temporary.name)/'remote.apk'
        def pulled(ok,results):
            if not ok: temporary.cleanup(); return
            self.remote_service = InstallService(self.main); self.remote_service.log_message.connect(lambda text:append_log(self.log,text))
            self.remote_service.finished.connect(lambda _:temporary.cleanup())
            if not self.remote_service.start([local],target=target): temporary.cleanup()
        self.main.sequence(self.t('Установить APK'),[Step(['pull',paths[0],str(local)],False,timeout=600000)],pulled,target=target)

class AppsPage(Page):
    def __init__(self, main):
        super().__init__(main); self.packages = []
        card = self.card('Приложения'); self.filter = QComboBox(); self.filter_keys = ['Все', 'Сторонние', 'Системные', 'Отключённые']; self.filter.addItems([self.t(k) for k in self.filter_keys])
        self.search = self.edit('Поиск по имени пакета'); self.search.textChanged.connect(self.filter_rows)
        self.row(card, self.filter, self.search, self.button('Обновить', self.refresh, True))
        self.package_table = table([self.t('Пакет')]); self.package_table.setMinimumHeight(180); 
        self.display = QComboBox(); self.display.addItems([self.t('Центральный') + ' · 1', self.t('Пассажирский') + ' · 2'])
        self.row(card, self.display, self.button('Запустить', self.launch, True), self.button('Остановить', self.force_stop), self.button('Очистить данные и кэш', self.clear_data), 1)
        self.row(card, self.button('Заморозить', self.disable), self.button('Разморозить', self.enable), self.button('Удалить', self.uninstall, danger=True), self.button('Экспорт APK', self.export), 1)
        note = self.label('Системные пакеты могут отвечать за функции автомобиля.', 'subtitle'); note.setWordWrap(True); card.addWidget(note); card.addWidget(self.package_table)
        self.log = logbox(); self.log.setMinimumHeight(160); self.layout.addWidget(self.log); self.layout.addStretch()

    def retranslate(self):
        super().retranslate()
        for i, k in enumerate(self.filter_keys): self.filter.setItemText(i, self.t(k))
        self.package_table.setHorizontalHeaderLabels([self.t('Пакет')])
        self.display.setItemText(0, self.t('Центральный') + f" · {self.main.display_map['center']}")
        self.display.setItemText(1, self.t('Пассажирский') + f" · {self.main.display_map['passenger']}")

    @feature_required('apps', 'apps')
    def refresh(self):
        if not self.main.ready(): return
        flags = [[], ['-3'], ['-s'], ['-d']][self.filter.currentIndex()]
        def done(ok, results):
            if ok:
                self.packages = sorted(line[8:].strip() for line in results[0].text.splitlines() if line.startswith('package:')); self.filter_rows()
        self.main.sequence(self.t('Приложения'), [Step(['pm', 'list', 'packages', '--user', '0'] + flags)], done)

    def filter_rows(self):
        packages = [p for p in self.packages if self.search.text().strip().lower() in p.lower()]
        self.package_table.setRowCount(len(packages))
        for row, pkg in enumerate(packages): self.package_table.setItem(row, 0, QTableWidgetItem(pkg))

    def selected(self):
        row = self.package_table.currentRow()
        pkg = self.package_table.item(row, 0).text() if row >= 0 else ''
        if not PACKAGE_RE.fullmatch(pkg): self.main.error(self.t('Выберите пакет.')); return ''
        return pkg

    def action(self, name, args, confirm='', verify=None):
        if not self.main.ready(): return
        pkg = self.selected()
        if not pkg or (confirm and not self.main.confirm(self.t(confirm) + '\n' + pkg)): return
        steps = [Step(args(pkg), privileged=True, timeout=120000)]
        if verify: steps.append(verify(pkg))
        def done(ok, results):
            append_log(self.log, name + ' · ' + pkg + '\n' + '\n'.join(r.text for r in results) + '\n')
            if ok: self.refresh()
        self.main.sequence(name, steps, done)

    @feature_required('apps', 'apps')
    def force_stop(self): self.action(self.t('Остановить'), lambda p: ['am', 'force-stop', '--user', '0', p])
    @feature_required('apps.clear', 'apps')
    def clear_data(self): self.action(self.t('Очистить данные и кэш'), lambda p: ['pm', 'clear', '--user', '0', p], 'Данные приложения будут удалены. Продолжить?')
    @feature_required('apps.freeze', 'apps')
    def disable(self):
        self.action(self.t('Заморозить'), lambda p: ['pm', 'disable-user', '--user', '0', p], 'Отключить выбранный пакет?',
            lambda p: Step(['pm', 'list', 'packages', '-d', '--user', '0', p], validate=lambda r: 'package:' + p in r.text))
    @feature_required('apps.freeze', 'apps')
    def enable(self):
        self.action(self.t('Разморозить'), lambda p: ['pm', 'enable', '--user', '0', p],
            verify=lambda p: Step(['pm', 'list', 'packages', '-e', '--user', '0', p], validate=lambda r: 'package:' + p in r.text))
    @feature_required('apps.uninstall', 'apps')
    def uninstall(self):
        if not self.main.ready(): return
        pkg = self.selected()
        if not pkg or not self.main.confirm(self.t('Удалить выбранное приложение?') + '\n' + pkg): return
        self.main.sequence(self.t('Удалить'), [Step(['uninstall', pkg], False),
            Step(['pm', 'list', 'packages', '--user', '0', pkg], validate=lambda r: 'package:' + pkg not in r.text.splitlines())], lambda ok, r: self.refresh() if ok else None)

    @feature_required('apps', 'apps')
    def launch(self):
        if not self.main.ready(): return
        pkg = self.selected()
        if not pkg: return
        display = self.main.display_map['center' if self.display.currentIndex() == 0 else 'passenger']
        if display not in self.main.profile.displays: self.main.error(self.t('Захват этого экрана недоступен на прошивке.')); return
        target = self.main.target
        if not self.main.begin(self.t('Запустить')): return
        def resolved(result):
            match = COMPONENT_RE.search(result.text)
            if not result.ok or not match:
                self.main.end(False); self.main.error(self.t('Этот пакет не содержит launcher Activity.'), result.text); return
            def launched(r):
                self.main.end(r.ok); append_log(self.log, r.text + '\n')
                if not r.ok: self.main.error(self.t(explain_error(r.text)), r.text)
            self.main.active_job = self.main.adb(['am', 'start', '--user', '0', '--display', str(display), '-n', match[0]], launched, target=target, shell=True, privileged=True)
        self.main.active_job = self.main.adb(['cmd', 'package', 'resolve-activity', '--brief', '--user', '0', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', pkg], resolved, target=target, shell=True)

    @feature_required('apps', 'apps')
    def export(self):
        if not self.main.ready(): return
        pkg = self.selected()
        if not pkg: return
        target = self.main.target
        def paths_ready(ok, results):
            if not ok: return
            paths = [line[8:].strip() for line in results[0].text.splitlines() if line.startswith('package:')]
            if not paths: self.main.error(self.t('Выберите пакет.')); return
            if len(paths) > 1 and not self.main.confirm(self.t('Пакет содержит splits. Скачать полный комплект?')):
                paths = [p for p in paths if posixpath.basename(p) == 'base.apk'] or paths[:1]
            destination = QFileDialog.getExistingDirectory(self, self.t('Экспорт APK'))
            if not destination: return
            dest = Path(destination) / pkg; dest.mkdir(exist_ok=True)
            steps = [Step(['pull', p, str(dest / posixpath.basename(p))], False, timeout=600000) for p in paths]
            self.main.sequence(self.t('Экспорт APK'), steps, target=target)
        self.main.sequence(self.t('Экспорт APK'), [Step(['pm', 'path', pkg])], paths_ready, target=target)

class TweaksPage(Page):
    def __init__(self, main):
        super().__init__(main)
        card = self.card('Масштаб и дисплеи'); self.display_info = QLabel('—'); self.display_info.setObjectName('subtitle'); self.display_info.setWordWrap(True); card.addWidget(self.display_info)
        self.display = QComboBox(); self.display_keys = ['Все мультимедийные', 'Центральный', 'Пассажирский', 'Приборная панель']; self.display.addItems([self.t(k) for k in self.display_keys])
        self.dpi = QComboBox(); self.dpi.setEditable(True); self.dpi.addItems(['140', '150', '160']); self.dpi.setCurrentText('160')
        self.row(card, self.display, self.dpi, self.button('Применить DPI', lambda: self.set_density(False), True), self.button('Заводской DPI', lambda: self.set_density(True)), self.button('Обновить', self.refresh_density))
        self.row(card, self.button('Сопоставить экраны', self.map_displays), 1)
        card = self.card('Аудиофокус и разрешения'); self.package = self.edit('Приложение для твиков'); self.row(card, self.package)
        grid = QGridLayout(); card.addLayout(grid)
        actions = [
            ('Не глушить музыку', lambda: self.app_command(['cmd', 'appops', 'set', '{pkg}', 'TAKE_AUDIO_FOCUS', 'ignore'], ['cmd', 'appops', 'get', '{pkg}', 'TAKE_AUDIO_FOCUS'], 'ignore')),
            ('Вернуть аудиофокус', lambda: self.app_command(['cmd', 'appops', 'set', '{pkg}', 'TAKE_AUDIO_FOCUS', 'allow'], ['cmd', 'appops', 'get', '{pkg}', 'TAKE_AUDIO_FOCUS'], 'allow')),
            ('Микрофон', lambda: self.grant('android.permission.RECORD_AUDIO')),
            ('Поверх окон', lambda: self.app_command(['appops', 'set', '{pkg}', 'SYSTEM_ALERT_WINDOW', 'allow'], ['appops', 'get', '{pkg}', 'SYSTEM_ALERT_WINDOW'], 'allow')),
            ('WRITE_SECURE_SETTINGS', lambda: self.grant('android.permission.WRITE_SECURE_SETTINGS')),
            ('Белый список питания', lambda: self.app_command(['dumpsys', 'deviceidle', 'whitelist', '+{pkg}'], ['dumpsys', 'deviceidle', 'whitelist'], '{pkg}')),
        ]
        for i, (text, fn) in enumerate(actions): grid.addWidget(self.button(text, fn), i // 3, i % 3)
        self.row(card, self.button('Отключить Doze', lambda: self.deviceidle('disable')), self.button('Включить Doze', lambda: self.deviceidle('enable')), 1)
        card = self.card('Сеть и система'); grid = QGridLayout(); card.addLayout(grid)
        features = [('Private DNS · AdGuard', 'dns'), ('Captive Portal', 'captive'), ('Immersive · Status bar', 'immersive')]
        for row, (name, key) in enumerate(features):
            label = QLabel(name); label.setMinimumWidth(170); grid.addWidget(label, row, 0)
            grid.addWidget(self.button('Включить', lambda checked=False, k=key: self.setting_feature(k, True)), row, 1)
            grid.addWidget(self.button('Выключить', lambda checked=False, k=key: self.setting_feature(k, False)), row, 2)
            grid.addWidget(self.button('Восстановить', lambda checked=False, k=key: self.restore_feature(k)), row, 3)
        self.row(card, self.button('Скрытые настройки Android', lambda: self.main.sequence(self.t('Скрытые настройки Android'), [Step(['am', 'start', '-a', 'android.settings.SETTINGS'])]) if self.main.ready() else None), 1)
        card = self.card('Восстановление системы')
        note = self.label('Системные сценарии используют Root, резервные копии и перезагрузку. Применимость зависит от прошивки.', 'subtitle'); note.setWordWrap(True); card.addWidget(note)
        self.row(card,self.button('Починить настройки машины',lambda:self.repair('settings')),1)
        self.row(card,self.button('Починить verity',lambda:self.repair('verity')),self.label('Отключение dm-verity — режим из отчёта'),1)
        for button in card.parentWidget().findChildren(QPushButton):
            if button.text() == self.t('Починить настройки машины'): button.setProperty('feature','repair.settings')
            elif button.text() == self.t('Починить verity'): button.setProperty('feature','repair.verity')
        self.row(card,self.button('Журнал восстановления',self.show_recovery),self.button('Возобновить Android после сбоя',self.recover_android),1)
        self.log = logbox(); self.log.setMinimumHeight(190); self.layout.addWidget(self.log); self.layout.addStretch()

    def repair(self, kind):
        if not self.main.allowed('repair.'+kind) or not self.main.allowed('tweaks'): return
        self.main.recipe = SystemRecipe(self.main,kind); self.main.recipe.start()

    def show_recovery(self):
        path = DATA_DIR / 'operation.json'
        if path.is_file(): QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR/'backups')))

    @feature_required('repair.settings','tweaks')
    def recover_android(self):
        if not self.main.ready() or not self.main.allowed('device.root'): return
        try: journal = json.loads((DATA_DIR/'operation.json').read_text(encoding='utf-8'))
        except (OSError,ValueError): self.main.error(self.t('Восстанавливать нечего.')); return
        if journal.get('serial') != self.main.target.serial: self.main.error(self.t('Подключите устройство из журнала восстановления.')); return
        if not self.main.confirm(self.t('Попытаться запустить Android и восстановить исходный SELinux? Резервные копии остаются на ПК.')): return
        steps = [Step(['id'],validate=lambda r:'uid=0' in r.text),Step(['start'])]
        if journal.get('selinux') == 'enforcing': steps.append(Step(['setenforce','1']))
        self.main.sequence(self.t('Восстановление системы'),steps,lambda ok,r:(DATA_DIR/'operation.json').unlink(missing_ok=True) if ok else None)

    def retranslate(self):
        super().retranslate()
        for i, text in enumerate(self.display_keys): self.display.setItemText(i, self.t(text))

    def update_profile(self):
        p = self.main.profile
        self.display_info.setText(f'Android {p.release} / API {p.api}  ·  ABI: {", ".join(p.abis)}  ·  Displays: {p.displays}\n' + p.raw.get('density', ''))

    def selected_displays(self):
        mapping = self.main.display_map
        return [[mapping['center'], mapping['passenger']], [mapping['center']], [mapping['passenger']], [mapping['cluster']]][self.display.currentIndex()]

    def refresh_density(self):
        if not self.main.ready(): return
        ids = self.selected_displays(); steps = []
        for display in ids:
            suffix = ['-d', str(display)] if self.main.profile.per_display else []
            if not suffix and display != 0:
                self.main.error(self.t('Прошивка не поддерживает DPI по дисплеям. Операция недоступна.')); return
            steps += [Step(['wm', 'size'] + suffix), Step(['wm', 'density'] + suffix)]
        def done(ok, results):
            if ok:
                text = '\n\n'.join(f'DISPLAY {ids[i // 2]}\n{r.text}' for i, r in enumerate(results)); self.display_info.setText(text); append_log(self.log, text + '\n')
        self.main.sequence(self.t('Масштаб и дисплеи'), steps, done)

    @feature_required('tweaks.dpi', 'tweaks')
    def set_density(self, reset):
        if not self.main.ready(): return
        ids = self.selected_displays()
        if any(i not in self.main.profile.displays for i in ids): self.main.error(self.t('Прошивка не поддерживает DPI по дисплеям. Операция недоступна.')); return
        if not self.main.profile.per_display and any(i != 0 for i in ids): self.main.error(self.t('Прошивка не поддерживает DPI по дисплеям. Операция недоступна.')); return
        try:
            value = int(self.dpi.currentText())
            if not 72 <= value <= 1000: raise ValueError()
        except ValueError:
            if not reset: self.main.error(self.t('Значение DPI должно быть от 72 до 1000.')); return
            value = 160
        if self.main.display_map['cluster'] in ids and not self.main.confirm(self.t('Изменить DPI приборной панели?')): return
        steps = []
        for display in ids:
            suffix = ['-d', str(display)] if self.main.profile.per_display else []
            steps.append(Step(['wm', 'density', 'reset' if reset else str(value)] + suffix, privileged=True))
            def verified(r, expected=value, resetting=reset):
                values = re.findall(r'(Physical|Override) density:\s*(\d+)', r.text)
                if not values: return False
                data = dict(values)
                return int(data.get('Override', data['Physical'])) == (int(data['Physical']) if resetting else expected)
            steps.append(Step(['wm', 'density'] + suffix, validate=verified))
        self.main.sequence(self.t('Применить DPI'), steps, lambda ok, r: self.refresh_density() if ok else None)

    @feature_required('tweaks.dpi', 'tweaks')
    def map_displays(self):
        if self.main.busy: return
        dialog = QDialog(self); dialog.setWindowTitle(self.t('Сопоставить экраны')); layout = QGridLayout(dialog); boxes = {}
        for row, (key, label) in enumerate((('cluster', 'Приборная панель'), ('center', 'Центральный'), ('passenger', 'Пассажирский'))):
            layout.addWidget(QLabel(self.t(label)), row, 0); box = QSpinBox(); box.setRange(0, 255); box.setValue(self.main.display_map[key]); boxes[key] = box; layout.addWidget(box, row, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons, 3, 0, 1, 2)
        if dialog.exec():
            values = {key: box.value() for key, box in boxes.items()}
            if len(set(values.values())) != 3: self.main.error(self.t('Недопустимое имя.')); return
            self.main.display_map = values; self.main.settings.setValue('display_map', json.dumps(values)); self.main.pages['apps'].retranslate()
            self.main.pages['inspector'].show_screens(self.main.pages['inspector'].last_screens)

    @feature_required('tweaks.permissions', 'tweaks')
    def app_command(self, args, verify=None, expected=''):
        if not self.main.ready(): return
        pkg = self.package.text().strip()
        if not PACKAGE_RE.fullmatch(pkg): self.main.error(self.t('Выберите пакет.')); return
        args = [a.replace('{pkg}', pkg) for a in args]; steps = [Step(args, privileged=True)]
        if verify:
            expected = expected.replace('{pkg}', pkg); steps.append(Step([a.replace('{pkg}', pkg) for a in verify], validate=lambda r: expected in r.text))
        self.main.sequence(pkg, steps, lambda ok, results: append_log(self.log, '\n'.join(r.text for r in results) + '\n'))

    def grant(self, permission):
        self.app_command(['pm', 'grant', '{pkg}', permission], ['dumpsys', 'package', '{pkg}'], permission + ': granted=true')

    @feature_required('tweaks.permissions', 'tweaks')
    def deviceidle(self, mode):
        if not self.main.ready(): return
        self.main.sequence('Doze · ' + mode, [Step(['dumpsys', 'deviceidle', mode], privileged=True), Step(['dumpsys', 'deviceidle'])],
            lambda ok, results: append_log(self.log, '\n'.join(r.text for r in results) + '\n'))

    def saved_key(self, feature):
        serial = self.main.target.serial if self.main.target else ''
        return 'backups/' + hashlib.sha256(serial.encode()).hexdigest()[:24] + '/' + feature

    @feature_required('tweaks.network', 'tweaks')
    def setting_feature(self, feature, enabled):
        if not self.main.ready(): return
        if not enabled and feature == 'immersive': self.restore_feature(feature); return
        values = {'dns': {'private_dns_mode':'hostname' if enabled else 'off', 'private_dns_specifier':'dns.adguard-dns.com' if enabled else ''},
                  'captive': {'captive_portal_mode':'0' if enabled else '1'}, 'immersive': {'policy_control':'immersive.status=*'}}[feature]
        target = self.main.target; key = self.saved_key(feature)
        def apply():
            steps = []
            for setting, value in values.items():
                steps += [Step(['settings', 'put', 'global', setting, value], privileged=True), Step(['settings', 'get', 'global', setting], validate=lambda r, v=value: r.text == v)]
            self.main.sequence(feature, steps, lambda ok, r: append_log(self.log, feature + '\n' + '\n'.join(x.text for x in r) + '\n'), target=target)
        if self.main.settings.contains(key): apply(); return
        keys = list(values)
        def saved(ok, results):
            if not ok: return
            old = {setting: (None if r.text == 'null' else r.text) for setting, r in zip(keys, results)}
            self.main.settings.setValue(key, json.dumps(old)); self.main.settings.sync(); apply()
        self.main.sequence(feature, [Step(['settings', 'get', 'global', setting]) for setting in keys], saved, target=target)

    @feature_required('tweaks.network', 'tweaks')
    def restore_feature(self, feature):
        if not self.main.ready(): return
        key = self.saved_key(feature); saved = self.main.settings.value(key, '')
        if not saved:
            if feature == 'immersive': saved = json.dumps({'policy_control':None})
            else: self.main.error(self.t('Восстанавливать нечего.')); return
        values = json.loads(saved); steps = []
        for setting, value in values.items():
            steps += [Step(['settings', 'delete', 'global', setting] if value is None else ['settings', 'put', 'global', setting, value], privileged=True),
                      Step(['settings', 'get', 'global', setting], validate=lambda r, v=value: r.text == ('null' if v is None else v))]
        self.main.sequence(self.t('Восстановить'), steps, lambda ok, r: append_log(self.log, feature + '\n' + '\n'.join(x.text for x in r) + '\n'))

def windows_argv(command: str) -> list[str]:
    if os.name != 'nt': return shlex.split(command)
    from ctypes import wintypes
    argc = ctypes.c_int()
    fn = ctypes.windll.shell32.CommandLineToArgvW
    fn.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]; fn.restype = ctypes.POINTER(wintypes.LPWSTR)
    pointer = fn(command, ctypes.byref(argc))
    if not pointer: raise ValueError('Invalid command line')
    try: return [pointer[i] for i in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(pointer)

class TerminalInput(QLineEdit):
    history_move = Signal(int)
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down): self.history_move.emit(-1 if event.key() == Qt.Key.Key_Up else 1)
        else: super().keyPressEvent(event)

class TerminalPage(Page):
    def __init__(self, main):
        super().__init__(main); self.job = None; self.shell_job = None; self.history = json.loads(main.settings.value('terminal_history', '[]')); self.history_index = len(self.history)
        card = self.card('Терминал ADB'); self.output = logbox(); self.output.setMinimumHeight(390); card.addWidget(self.output)
        self.input = self.bind(TerminalInput(), 'Команда ADB или adb shell…', 'setPlaceholderText'); self.input.returnPressed.connect(self.run_command); self.input.history_move.connect(self.move_history)
        self.run_button = self.button('Выполнить', self.run_command, True)
        self.row(card, self.input, self.run_button, self.button('Стоп', self.stop))
        self.shell_button = self.button('Интерактивная shell', self.open_shell)
        self.row(card, self.shell_button, self.button('Очистить', self.output.clear), self.button('Сохранить', lambda: self.save_text(self.output.toPlainText(), 'voyah-terminal.txt')), 1)
        self.layout.addStretch(); QShortcut(QKeySequence('Ctrl+L'), self, activated=self.output.clear)

    def move_history(self, direction):
        self.history_index = max(0, min(len(self.history), self.history_index + direction))
        self.input.setText(self.history[self.history_index] if self.history_index < len(self.history) else '')

    def record(self, text):
        if not self.history or self.history[-1] != text: self.history.append(text)
        self.history = self.history[-200:]; self.history_index = len(self.history); self.main.settings.setValue('terminal_history', json.dumps(self.history))
        append_log(self.output, '\n› ' + text + '\n')

    @feature_required('terminal')
    def run_command(self):
        text = self.input.text().strip()
        if not text: return
        if self.shell_job:
            self.record(text)
            if self.shell_job.proc: self.shell_job.proc.write((text + '\n').encode('utf-8'))
            elif self.main.demo: append_log(self.output, '$ ' + text + '\n')
            self.input.clear(); return
        if self.job: return
        try:
            tokens = windows_argv(text)
            if tokens and Path(tokens[0]).name.lower() in ('adb', 'adb.exe'): tokens.pop(0)
            if not tokens: return
        except ValueError as error: self.main.error(str(error)); return
        self.record(text); self.input.clear()
        global_commands = {'devices','connect','disconnect','kill-server','start-server','version','help','server-status','track-devices','pair','mdns','--help','--version'}
        explicit = False; option_index = 0
        while option_index < len(tokens) and tokens[option_index].startswith('-'):
            flag = tokens[option_index]
            if flag in ('-s', '-d', '-e', '-t'): explicit = True
            if flag in ('--help', '--version'): break
            option_index += 2 if flag in ('-s', '-t', '-H', '-P', '-L') else 1
        verb = tokens[option_index] if option_index < len(tokens) else ''
        global_cmd = explicit or verb in global_commands
        if not global_cmd and not self.main.target:
            self.main.error(self.t('Сначала подключите устройство.')); return
        # Preserve remote shell syntax exactly, including pipes, redirects and quotes.
        shell_index = next((i for i, t in enumerate(tokens) if t == 'shell'), -1)
        if shell_index >= 0:
            match = re.search(r'(?<!\S)shell(?:\s+|$)', text)
            remainder = text[match.end():] if match else ''
            if not remainder.strip() and not explicit: self.open_shell(); return
            if len(tokens[shell_index + 1:]) == 1 and remainder.startswith('"') and remainder.endswith('"'):
                remainder = tokens[shell_index + 1]
            tokens = tokens[:shell_index] + ['shell', remainder]
        if not self.main.begin(self.t('Терминал ADB')): return
        def done(result):
            self.job = None; self.main.end(result.ok)
            append_log(self.output, '\n[' + (self.t('Отменено') if result.cancelled else self.t('Истекло время ожидания') if result.timed_out else f'exit {result.code}') + ']\n')
        self.job = self.main.adb(tokens, done, global_cmd=global_cmd, timeout=0, stream=lambda value: append_log(self.output, value), check=False)
        self.main.active_job = self.job

    @feature_required('terminal')
    def open_shell(self):
        if self.shell_job: self.stop(); return
        if not self.main.ready(): return
        self.record('adb shell'); self.shell_button.setText(self.t('Стоп')); self.run_button.setText(self.t('Отправить'))
        def ended(result):
            self.shell_job = None; self.shell_button.setText(self.t('Интерактивная shell')); self.run_button.setText(self.t('Выполнить'))
            append_log(self.output, '\n[exit ' + str(result.code) + ']\n')
        self.shell_job = self.main.adb(['shell'], ended, timeout=0, stream=lambda value: append_log(self.output, value), check=False)

    def stop(self):
        if self.job: self.job.cancel(); self.job = None
        if self.shell_job: self.shell_job.cancel(); self.shell_job = None

    def stop_streams(self): self.stop()

def release_endpoint(source):
    public_url(source); parsed = urlparse(source); parts = parsed.path.strip('/').split('/')
    if parsed.hostname != 'github.com' or len(parts) < 2: return None
    if parsed.path.lower().endswith(('.apk','.apks','.xapk','.apkm')): return None
    repo = github_repository('/'.join(parts[:2])); base = 'https://api.github.com/repos/' + repo + '/releases/'
    if len(parts) == 2 or parts[2:] in (['releases'],['releases','latest']): return base + 'latest'
    if len(parts) >= 5 and parts[2:4] == ['releases','tag']: return base + 'tags/' + quote(unquote('/'.join(parts[4:])),safe='')
    raise ValueError('Нужна ссылка на репозиторий, релиз или APK/архив.')

class DownloadService(QObject):
    def __init__(self, main):
        super().__init__(main); self.main = main; self.job = None; self.cancelled = False
        self.cache = DATA_DIR / 'downloads'; self.index_path = self.cache / 'index.json'
        try:
            loaded = json.loads(self.index_path.read_text(encoding='utf-8'))
            self.index = {k:v for k,v in loaded.items() if isinstance(k,str) and isinstance(v,dict) and isinstance(v.get('file'),str) and isinstance(v.get('sha256'),str)} if isinstance(loaded,dict) else {}
        except (OSError,ValueError): self.index = {}
    def cancel(self):
        self.cancelled = True
        if self.job: self.job.cancel()
    def resolve(self, source, asset, callback):
        try: endpoint = release_endpoint(source)
        except ValueError as error: callback(None,str(error)); return
        if not endpoint:
            parsed = urlparse(source); parts = parsed.path.strip('/').split('/')
            if parsed.hostname == 'github.com' and len(parts)>4 and parts[2]=='blob': source = 'https://raw.githubusercontent.com/'+'/'.join(parts[:2]+parts[3:])
            name = unquote(urlparse(source).path.rsplit('/',1)[-1])
            if Path(name).suffix.lower() not in ('.apk','.apks','.xapk','.apkm'): callback(None,'Ссылка должна вести к APK или Android-архиву.'); return
            callback({'url':source,'name':name,'size':0,'digest':'','version':'—'},''); return
        def resolved(result):
            try:
                if result['error']: raise ValueError(result['error'])
                release = json.loads(result['body'])
                assets = [a for a in release.get('assets',[]) if Path(a.get('name','')).suffix.lower() in ('.apk','.apks','.xapk','.apkm') and (not asset or a.get('name') == asset)]
                if not assets: raise ValueError('В релизе нет подходящего APK/архива.')
                if len(assets) > 1:
                    names = [f"{a['name']}  ({human_size(a.get('size',0))})" for a in assets]
                    selected,ok = QInputDialog.getItem(self.main,self.main.t('Выбор файла'),self.main.t('В релизе несколько файлов. Выберите совместимый комплект.'),names,0,False)
                    if not ok: callback(None,'Отменено'); return
                    chosen = assets[names.index(selected)]
                else: chosen = assets[0]
                digest = chosen.get('digest') or ''
                if digest and not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',digest): digest = ''
                callback({'url':public_url(chosen['browser_download_url']),'name':chosen['name'],'size':chosen.get('size',0),'digest':digest,'version':release.get('tag_name','—')},'')
            except (ValueError,KeyError,TypeError) as error: callback(None,str(error))
        self.job = self.main.web.request(endpoint,resolved)
    def acquire(self, source, callback, asset='', digest=''):
        self.cancelled = False; cache_key = hashlib.sha256((source+'\n'+asset).encode()).hexdigest()
        def cached_or_error(message):
            entry = self.index.get(cache_key)
            if not entry: callback(None,message + '\n' + self.main.t('Подключитесь к интернету для первой загрузки.')); return
            path = self.cache / Path(entry.get('file','')).name
            def checked(value,error):
                if self.cancelled: callback(None,'Отменено'); return
                if error or value != entry.get('sha256') or (digest and value != digest.lower()): callback(None,'Кэш повреждён. Нужна повторная загрузка.'); return
                callback(path,'')
            def cached_hash():
                if not path.is_file(): return ''
                with path.open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()
            self.main.background(cached_hash,checked)
        def resolved(meta,error):
            if self.cancelled: callback(None,'Отменено'); return
            if error:
                if error == 'Отменено': callback(None,error)
                else: cached_or_error(error)
                return
            suffix = Path(meta['name']).suffix.lower(); destination = self.cache / (hashlib.sha256(meta['url'].encode()).hexdigest() + suffix)
            self.main.notice(self.main.t('Скачивание') + ': ' + meta['name'] + '  ' + meta['version'])
            def progress(received,total):
                self.main.global_progress.setRange(0,100 if total > 0 else 0)
                if total > 0: self.main.global_progress.setValue(int(received*100/total))
            def downloaded(result):
                self.job = None
                if self.cancelled: callback(None,'Отменено'); return
                if result['error']: cached_or_error(result['error']); return
                self.index[cache_key] = {'file':destination.name,'sha256':result['sha256'],'source':source,'version':meta['version'],'size':result['size']}
                atomic_json(self.index_path,self.index); callback(destination,'')
            self.job = self.main.web.request(meta['url'],downloaded,destination=destination,expected_size=meta['size'],digest=digest or meta['digest'],progress=progress)
            self.main.active_job = self
        # A known cache remains usable if resolution fails while offline.
        self.resolve(source,asset,resolved)
        self.main.active_job = self

class CatalogPage(Page):
    def __init__(self, main):
        super().__init__(main); self.items = []; self.downloader = DownloadService(main); self.service = InstallService(main); self.versions = {}; self.version_pending = set()
        card = self.card('Каталог приложений'); self.status = QLabel(); self.status.setWordWrap(True); card.addWidget(self.status)
        self.search = self.edit('Поиск приложений'); self.search.textChanged.connect(self.refresh)
        self.row(card,self.search,self.button('Обновить каталог',lambda: main.catalog.refresh()))
        self.listing = table([self.t(k) for k in ('Приложение','Совместимость','Версия')]); self.listing.setMinimumHeight(220); self.listing.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch); card.addWidget(self.listing)
        self.details = QLabel(); self.details.setWordWrap(True); self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); card.addWidget(self.details)
        self.listing.itemSelectionChanged.connect(self.show_details)
        self.install_btn = self.button('Скачать и установить',self.install,True); self.row(card,self.install_btn,1)
        self.log = logbox(); self.log.setMinimumHeight(130); self.layout.addWidget(self.log)
        self.service.log_message.connect(lambda text: append_log(self.log,text)); self.service.finished.connect(lambda ok:self.refresh())
        main.catalog.changed.connect(self.refresh); self.refresh()
    def retranslate(self):
        super().retranslate(); self.listing.setHorizontalHeaderLabels([self.t(k) for k in ('Приложение','Совместимость','Версия')]); self.refresh()
    def refresh(self):
        store = self.main.catalog; self.status.setText(self.t(store.message or ('Каталог ещё не настроен' if not store.config.get('repository') else 'Последний сохранённый каталог')) + f"  ·  r{store.profile['revision']}")
        term = self.search.text().lower(); self.items = [a for a in store.profile['apps'] if term in (a['name'] + ' ' + a.get('description','')).lower()]
        self.listing.setRowCount(len(self.items))
        for row,entry in enumerate(self.items):
            compatible = self.t('Отключено администратором') if not entry.get('enabled',True) else f"API ≥ {entry.get('min_sdk',1)} · {', '.join(entry.get('abis',[])) or 'Android'}"
            key = hashlib.sha256((entry['source']+'\n'+entry.get('asset','')).encode()).hexdigest(); version = self.versions.get(entry['source'],self.downloader.index.get(key,{}).get('version',self.t('Определяется перед загрузкой')))
            for col,value in enumerate((entry['name'],compatible,version)): self.listing.setItem(row,col,QTableWidgetItem(value))
        self.show_details()
    def show_details(self):
        row = self.listing.currentRow()
        if hasattr(self,'install_btn'):
            enabled = 0 <= row < len(self.items) and self.items[row].get('enabled',True) and self.main.allowed('apk.install',False) and self.main.allowed('catalog',False)
            self.install_btn.setEnabled(enabled)
        if 0 <= row < len(self.items):
            item = self.items[row]; self.details.setText(item.get('description','') + '\n' + item['source'])
            source = item['source']
            try: endpoint = release_endpoint(source)
            except ValueError: endpoint = None
            if endpoint and source not in self.versions and source not in self.version_pending:
                self.version_pending.add(source)
                def peeked(result):
                    self.version_pending.discard(source)
                    if result['error']: return
                    try: self.versions[source] = json.loads(result['body'])['tag_name']
                    except (ValueError,KeyError): return
                    for index,entry in enumerate(self.items):
                        if entry['source'] == source: self.listing.item(index,2).setText(self.versions[source])
                self.main.web.request(endpoint,peeked)
        else: self.details.setText(self.t('Выберите приложение из каталога.'))
    @feature_required('apk.install','catalog')
    def install(self):
        if not self.main.ready(): return
        row = self.listing.currentRow()
        if not 0 <= row < len(self.items): self.main.error(self.t('Выберите приложение из каталога.')); return
        entry = copy.deepcopy(self.items[row])
        if not entry.get('enabled',True): self.main.error(self.t('Отключено администратором')); return
        if self.main.profile.api and entry.get('min_sdk',1) > self.main.profile.api: self.main.error(self.t('Приложение требует более новую версию Android (minSdk выше API ГУ).')); return
        if entry.get('abis') and not set(entry['abis']).intersection(self.main.profile.abis): self.main.error(self.t('APK предназначен для другой архитектуры процессора.')); return
        target = self.main.target
        if not self.main.begin(self.t('Скачивание')): return
        def ready(path,error):
            self.main.end(not error)
            if error: self.main.error(self.t(error)); return
            if not self.main.allowed('catalog') or not self.main.allowed('apk.install'): return
            self.service.start([path],2 if path.suffix != '.apk' else 0,target=target,expected_package=entry.get('package',''),post_install=entry.get('post_install',[]))
        self.downloader.acquire(entry['source'],ready,entry.get('asset',''))

class KeyboardPage(Page):
    def __init__(self, main):
        super().__init__(main); self.downloader = DownloadService(main); self.items = []
        card = self.card('Клавиатуры'); note = self.label('Комплект заменяет системные клавиатуры двух экранов. Перед изменениями создаются резервные копии на ГУ и ПК.'); note.setWordWrap(True); card.addWidget(note)
        self.combo = QComboBox(); self.row(card,self.combo,self.button('Обновить каталог',lambda:main.catalog.refresh()))
        self.description = QLabel(); self.description.setWordWrap(True); card.addWidget(self.description); self.combo.currentIndexChanged.connect(self.describe)
        self.row(card,self.button('Скачать и установить комплект',self.install,True),1)
        self.row(card,self.button('Восстановить штатные клавиатуры',self.restore),1)
        self.log = logbox(); self.log.setMinimumHeight(250); self.layout.addWidget(self.log); self.layout.addStretch()
        main.catalog.changed.connect(self.refresh); self.refresh()
    def refresh(self):
        self.items = self.main.catalog.profile['keyboards']; self.combo.clear()
        for entry in self.items: self.combo.addItem(entry['name'])
        self.describe()
    def retranslate(self): super().retranslate(); self.describe()
    def describe(self):
        index = self.combo.currentIndex()
        self.description.setText((self.items[index].get('description','') + '\n' + ', '.join(self.items[index].get('models',KEYBOARD_MODELS))) if index >= 0 else self.t('Комплекты пока не добавлены администратором.'))
    @feature_required('keyboard.install','keyboards')
    def install(self):
        if not self.main.ready(): return
        index = self.combo.currentIndex()
        if index < 0: self.main.error(self.t('Комплекты пока не добавлены администратором.')); return
        entry = copy.deepcopy(self.items[index])
        if not entry.get('enabled',True): self.main.error(self.t('Отключено администратором')); return
        if self.main.profile.model_code not in entry.get('models',KEYBOARD_MODELS): self.main.error(self.t('Модель не поддерживает этот комплект клавиатур.')); return
        target = self.main.target; paths = []
        if not self.main.begin(self.t('Скачивание')): return
        def acquire(index=0):
            if index == 2:
                self.main.end(True)
                if not self.main.allowed('keyboard.install') or not self.main.allowed('keyboards'): return
                self.main.recipe = SystemRecipe(self.main,'keyboard',paths,target); self.main.recipe.start(); return
            key = ('central','passenger')[index]
            def downloaded(path,error):
                if error: self.main.end(False); self.main.error(self.t(error)); return
                paths.append(path); acquire(index+1)
            self.downloader.acquire(entry[key+'_url'],downloaded,digest=entry.get(key+'_sha256',''))
        acquire()
    @feature_required('keyboard.restore','keyboards')
    def restore(self):
        self.main.recipe = SystemRecipe(self.main,'keyboard_restore'); self.main.recipe.start()

class SystemRecipe(QObject):
    """Pinned-device state machine. Fixed paths only; cleanup runs even after cancellation."""
    def __init__(self, main, kind, paths=None, target=None):
        super().__init__(main); self.main = main; self.kind = kind; self.paths = [Path(p) for p in (paths or [])]
        self.target = target or main.target; self.running = False; self.cancelled = False; self.cleaning = False; self.close_after = False
        self.android_stopped = False; self.selinux = None; self.selinux_changed = False; self.changed_files = []; self.infos = []; self.original_hashes = {}; self.expected_hashes = {}; self.pending_files = []
        self.backup_dir = DATA_DIR / 'backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4)); self.journal_path = DATA_DIR / 'operation.json'
        self.journal = {'kind':kind,'serial':self.target.serial if self.target else '', 'mode':self.target.mode if self.target else '', 'status':'preflight','steps':[], 'backups':str(self.backup_dir),'android_stopped':False,'selinux':None,'changed_files':[]}
    def note(self,stage):
        self.journal['stage'] = stage; self.journal['steps'].append({'time':time.strftime('%Y-%m-%d %H:%M:%S'),'stage':stage}); self.journal['android_stopped'] = self.android_stopped; self.journal['selinux'] = self.selinux; self.journal['changed_files'] = list(self.changed_files)
        atomic_json(self.journal_path,self.journal); self.main.notice(self.main.t(stage))
        page = self.main.pages['keyboards' if self.kind.startswith('keyboard') else 'tweaks']; append_log(page.log,self.main.t(stage)+'\n')
    def command(self,args,done,shell=True,stage=None,check=True,timeout=30000):
        if self.cancelled and not self.cleaning: self.fail('Отменено'); return
        if stage: self.note(stage)
        def result(r):
            if not self.running: return
            if check and not r.ok: self.fail(r.text or ('Отменено' if r.cancelled else 'Ошибка команды')); return
            done(r)
        self.main.active_job = self.main.adb(args,result,target=self.target,shell=shell,timeout=timeout,check=check)
    def start(self):
        flag = {'keyboard':'keyboard.install','keyboard_restore':'keyboard.restore','settings':'repair.settings','verity':'repair.verity'}[self.kind]
        section = 'keyboards' if self.kind.startswith('keyboard') else 'tweaks'
        if not all(self.main.allowed(f) for f in (section,flag,'device.root','device.reboot')) or not self.main.ready(): return
        if self.kind.startswith('keyboard') and self.main.profile.model_code not in KEYBOARD_MODELS:
            self.main.error(self.main.t('Модель не поддерживает этот комплект клавиатур.')); return
        descriptions = {
          'keyboard':'Заменить две системные клавиатуры? Будут созданы копии .old без перезаписи и резервные копии на ПК. Будет отключён dm-verity, временно изменён SELinux; ГУ перезагрузится дважды.',
          'keyboard_restore':'Восстановить штатные клавиатуры из .old? Текущие APK будут сохранены на ПК. ГУ перезагрузится. dm-verity останется отключённым.',
          'settings':'Починить настройки машины? Android будет остановлен. База Qinggan Settings, WAL и SHM будут сохранены на ПК и удалены на ГУ для пересоздания. Возможна потеря пользовательских настроек автомобиля. Затем Android запустится и ГУ перезагрузится.',
          'verity':'Отключение dm-verity — режим из отчёта. Будут выполнены adb root, disable-verity, sync и перезагрузка. Это отключает проверку разделов.',
        }
        if not self.main.confirm(self.main.t(descriptions[self.kind])+'\n\n'+str(self.backup_dir)): return
        if not self.main.begin(self.main.t({'keyboard':'Установка клавиатур','keyboard_restore':'Восстановление клавиатур','settings':'Починить настройки машины','verity':'Починить verity'}[self.kind])): return
        self.running = True; self.target = Target(self.target.serial,self.target.mode); self.backup_dir.mkdir(parents=True,exist_ok=True)
        self.journal['status'] = 'running'; self.note('Проверка системного сценария')
        if self.kind == 'keyboard':
            if len(self.paths) != 2: self.fail('Нужны два APK клавиатур.'); return
            self.inspect_keyboard()
        else: self.obtain_root(self.preflight)
    def inspect_keyboard(self,index=0):
        if self.cancelled: self.fail('Отменено'); return
        if index == 2:
            if len({i.version for i in self.infos}) != 1: self.fail('Версии двух клавиатур не совпадают.'); return
            def hashed(values,error):
                if error: self.fail(str(error)); return
                self.expected_hashes = {path:value for (_,path),value in zip(KEYBOARD_PATHS,values)}; self.obtain_root(self.preflight)
            def hashes():
                values=[]
                for path in self.paths:
                    with path.open('rb') as handle: values.append(hashlib.file_digest(handle,'sha256').hexdigest())
                return values
            self.main.background(hashes,hashed); return
        def read(r):
            try:
                if not r.ok: raise ValueError(r.text)
                info = parse_badging(self.paths[index],r.text)
                if info.package != KEYBOARD_PATHS[index][0] or info.split: raise ValueError('Неверный пакет клавиатуры или split вместо полного APK.')
                if not self.main.profile.api or info.min_sdk > self.main.profile.api: raise ValueError('Клавиатура несовместима с API устройства.')
                if info.abis and not set(info.abis).intersection(self.main.profile.abis): raise ValueError('APK предназначен для другой архитектуры процессора.')
                self.infos.append(info); self.inspect_keyboard(index+1)
            except ValueError as error: self.fail(str(error))
        self.main.active_job = self.main.runner.run(self.main.tools.path('aapt2.exe'),['dump','badging',str(self.paths[index])],read)
    def obtain_root(self,done):
        self.command(['root'],lambda r:self.wait_ready(lambda:self.command(['id'],lambda result:self.root_checked(result,done)),boot=False),shell=False,stage='Получение Root по подтверждённому сценарию')
    def root_checked(self,result,done):
        if not re.search(r'\buid=0\b',result.text): self.fail('Прошивка отказала в Root. Сценарий остановлен.'); return
        self.main.privilege = 'root'; done()
    def wait_ready(self,done,boot=True):
        deadline = time.monotonic()+180
        self.note('Ожидание Android на выбранном устройстве')
        def poll():
            if not self.running: return
            if self.cancelled and not self.cleaning: self.fail('Отменено'); return
            if time.monotonic() > deadline: self.fail('Истекло время ожидания загрузки выбранного устройства.'); return
            def state(r):
                if r.ok and r.text == 'device':
                    if not boot: done(); return
                    def booted(b):
                        if b.ok and b.text == '1': done()
                        else: QTimer.singleShot(100 if self.main.demo else 1500,poll)
                    self.command(['getprop','sys.boot_completed'],booted,check=False,timeout=8000)
                elif self.target.mode == 'wifi':
                    self.main.active_job = self.main.adb(['connect',self.target.serial],lambda _:QTimer.singleShot(100 if self.main.demo else 1500,poll),global_cmd=True,timeout=8000,check=False)
                else: QTimer.singleShot(100 if self.main.demo else 1500,poll)
            self.command(['get-state'],state,shell=False,check=False,timeout=8000)
        QTimer.singleShot(100 if self.main.demo else 1500,poll)
    def reboot(self,done):
        self.command(['sync'],lambda _:self.command(['reboot'],lambda r:self.wait_ready(done),shell=False,stage='Перезагрузка ГУ'))
    def preflight(self):
        if self.kind == 'verity': self.disable_verity(lambda:self.reboot(lambda:self.finish(True))); return
        if self.kind == 'settings':
            self.command(['pm','path','com.qinggan.providers.settings'],lambda r:self.settings_package(r),stage='Проверка Qinggan Settings'); return
        self.pending_files = [path for _,path in KEYBOARD_PATHS]
        self.preflight_keyboard_file()
    def preflight_keyboard_file(self,index=0):
        if index == 2:
            self.backup_keyboard(0); return
        path = self.pending_files[index]; old = str(PurePosixPath(path).with_suffix('.old'))
        required = old if self.kind == 'keyboard_restore' else path
        command = 'test -f '+shlex.quote(required)+' && test ! -L '+shlex.quote(required)+' && test -f '+shlex.quote(path)+' && test ! -L '+shlex.quote(path)
        self.command(command,lambda _:self.preflight_keyboard_file(index+1),stage='Проверка штатных файлов клавиатур')
    def remote_hash(self,path,done):
        def hashed(r):
            match = re.search(r'\b[0-9a-fA-F]{64}\b',r.text)
            if not match: self.fail('Не удалось проверить SHA-256 системного файла.'); return
            done(match[0].lower())
        self.command(['toybox','sha256sum',path],hashed)
    def backup_keyboard(self,index):
        if index == 2:
            if self.kind == 'keyboard': self.disable_verity(lambda:self.reboot(lambda:self.obtain_root(self.remount)))
            else: self.remount()
            return
        path = self.pending_files[index]; local = self.backup_dir / ('before-'+str(index)+'.apk')
        def hashed(value):
            self.original_hashes[path] = value
            self.pull_verified(path,local,value,lambda:self.backup_keyboard(index+1))
        self.remote_hash(path,hashed)
    def pull_verified(self,path,local,expected,done):
        def pulled(r):
            def verify():
                with local.open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()
            def verified(value,error):
                if error or value != expected: self.fail('Резервная копия не прошла проверку. Изменение отменено.'); return
                done()
            self.main.background(verify,verified)
        self.command(['pull',path,str(local)],pulled,shell=False,stage='Резервное копирование на ПК',timeout=120000)
    def disable_verity(self,done):
        def disabled(r):
            if re.search(r'(?i)failed|not supported|cannot|error|permission denied',r.text): self.fail(r.text); return
            done()
        self.command(['disable-verity'],disabled,shell=False,stage='Отключение dm-verity — режим из отчёта')
    def remount(self):
        def remounted(r):
            if re.search(r'(?i)failed|not supported|permission denied|read-only',r.text): self.fail(r.text); return
            self.command(['getenforce'],self.selinux_read,stage='Проверка SELinux')
        self.command(['remount'],remounted,shell=False,stage='Перемонтирование системного раздела')
    def selinux_read(self,r):
        value = r.text.strip().lower()
        if value not in ('enforcing','permissive','disabled'): self.fail('Не удалось определить режим SELinux.'); return
        self.selinux = value
        if value == 'enforcing':
            self.selinux_changed = True; self.command(['setenforce','0'],lambda _:self.write_keyboard(0),stage='Временный Permissive SELinux')
        else: self.write_keyboard(0)
    def write_keyboard(self,index):
        if index == 2: self.restore_selinux(lambda:self.reboot(self.verify_keyboards)); return
        path = self.pending_files[index]; old = str(PurePosixPath(path).with_suffix('.old'))
        self.note(('Центральная клавиатура' if index == 0 else 'Пассажирская клавиатура') + ': запись')
        def protected(_):
            self.changed_files.append(index); self.note('Запись проверенного системного APK')
            if self.kind == 'keyboard_restore':
                self.remote_hash(old,lambda value:self.restore_copy(index,path,old,value))
            else:
                self.command(['push',str(self.paths[index]),path],lambda _:self.permissions(index,path,self.expected_hashes[path]),shell=False,timeout=120000)
        # Never replace an existing .old, and reject symlinks before privileged writes.
        command = 'test ! -L '+shlex.quote(old)+' && { test -e '+shlex.quote(old)+' || cp -p '+shlex.quote(path)+' '+shlex.quote(old)+'; }'
        self.command(command,protected,stage='Сохранение штатной копии .old без перезаписи')
    def restore_copy(self,index,path,old,value):
        self.expected_hashes[path] = value; self.command(['cp','-p',old,path],lambda _:self.permissions(index,path,value))
    def permissions(self,index,path,expected):
        commands = [['chown','0:0',path],['chmod','0644',path],['restorecon',path]]
        def apply(n=0):
            if n == len(commands):
                def verified(value):
                    if value != expected: self.fail('Системный APK не прошёл проверку записи.'); return
                    self.note(('Центральная клавиатура' if index == 0 else 'Пассажирская клавиатура') + ': проверена'); self.write_keyboard(index+1)
                def attributes(r):
                    if r.text.strip() != '0:0:644': self.fail('Владелец или права системного APK не подтверждены.'); return
                    self.remote_hash(path,verified)
                self.command(['toybox','stat','-c','%u:%g:%a',path],attributes); return
            self.command(commands[n],lambda _:apply(n+1))
        apply()
    def restore_selinux(self,done):
        if self.selinux_changed:
            def restored(r): self.selinux_changed = not r.ok; done()
            self.command(['setenforce','1'],restored,check=not self.cleaning,stage='Восстановление исходного SELinux')
        else: done()
    def verify_keyboards(self,index=0):
        if index == 2: self.finish(True); return
        package,path = KEYBOARD_PATHS[index]
        def verified(r):
            if 'package:' not in r.text: self.fail('Клавиатура не обнаружена после перезагрузки.'); return
            if self.kind == 'keyboard':
                def version(v):
                    match = re.search(r'\bversionCode=(\d+)',v.text)
                    if not match or match[1] != self.infos[index].version: self.fail('Версия клавиатуры после загрузки не подтверждена.'); return
                    self.verify_keyboards(index+1)
                self.command(['dumpsys','package',package],version)
            else: self.verify_keyboards(index+1)
        self.command(['pm','path',package],verified,stage='Проверка клавиатур после загрузки')
    def settings_package(self,r):
        if 'package:' not in r.text: self.fail('Qinggan Settings не обнаружен.'); return
        self.command(['test','-f',SETTINGS_DB],lambda _:self.stop_android(),stage='Проверка базы настроек')
    def stop_android(self):
        self.android_stopped = True; self.note('Временная остановка Android')
        self.command(['stop'],lambda _:self.settings_backup(0))
    def settings_backup(self,index):
        files = [SETTINGS_DB,SETTINGS_DB+'-wal',SETTINGS_DB+'-shm']
        if index == len(files):
            self.command(['rm','-f','--']+files,lambda _:self.command(['sync'],lambda _:self.start_android(lambda:self.reboot(lambda:self.finish(True)))),stage='Пересоздание базы Qinggan Settings'); return
        path = files[index]
        def exists(r):
            if not r.ok:
                if index == 0 or r.code != 1 or r.text: self.fail(r.text or 'Исходная база недоступна. Удаление отменено.')
                else: self.settings_backup(index+1)
                return
            self.remote_hash(path,lambda value:self.pull_verified(path,self.backup_dir/PurePosixPath(path).name,value,lambda:self.settings_backup(index+1)))
        self.command(['test','-e',path],exists,check=False)
    def start_android(self,done):
        def started(r):
            if r.ok: self.android_stopped = False
            done()
        self.command(['start'],started,check=not self.cleaning,stage='Запуск Android после системной операции')
    def cancel(self):
        self.cancelled = True
        if self.main.active_job and self.main.active_job is not self: self.main.active_job.cancel()
        # Timed boot polling has no active process; cleanup is still guaranteed.
        QTimer.singleShot(0,lambda:self.fail('Отменено') if self.running and not self.cleaning else None)
    def fail(self,message):
        if not self.running or self.cleaning: return
        self.cleaning = True; self.failure = message; self.note('Восстановление состояния после прерывания')
        self.rollback_index = len(self.changed_files)-1; self.cleanup_ok = True; self.rollback_next()
    def rollback_next(self):
        if self.rollback_index < 0:
            self.restore_selinux(lambda:self.start_android(self.failed_done) if self.android_stopped else self.failed_done()); return
        index = self.changed_files[self.rollback_index]; self.rollback_index -= 1
        path = KEYBOARD_PATHS[index][1]; local = self.backup_dir/('before-'+str(index)+'.apk')
        if not local.is_file(): self.cleanup_ok = False; self.rollback_next(); return
        def pushed(r):
            if not r.ok: self.cleanup_ok = False; self.rollback_next(); return
            # Best-effort cleanup must continue even when a single permission command fails.
            commands = [['chown','0:0',path],['chmod','0644',path],['restorecon',path]]
            def next_command(n=0):
                if n == len(commands):
                    def checked(v):
                        if self.original_hashes.get(path,'!') not in v.text: self.cleanup_ok = False
                        self.note(('Центральная клавиатура' if index == 0 else 'Пассажирская клавиатура') + ': откат ' + ('OK' if self.cleanup_ok else 'не подтверждён')); self.rollback_next()
                    self.command(['toybox','sha256sum',path],checked,check=False); return
                def done(v):
                    if not v.ok: self.cleanup_ok = False
                    next_command(n+1)
                self.command(commands[n],done,check=False)
            next_command()
        self.command(['push',str(local),path],pushed,shell=False,check=False,stage='Откат клавиатуры к состоянию до операции',timeout=120000)
    def failed_done(self):
        self.cleanup_ok = self.cleanup_ok and not self.android_stopped and not self.selinux_changed
        self.finish(False)
        if not self.main.closing: self.main.error(self.main.t(self.failure),self.main.t('Резервные копии и журнал') + ': ' + str(self.backup_dir),modal=not self.close_after)
    def finish(self,success):
        if not self.running: return
        self.journal['status'] = 'complete' if success else 'failed'; self.journal['android_stopped'] = self.android_stopped; self.journal['cleanup_ok'] = getattr(self,'cleanup_ok',True); self.journal['error'] = getattr(self,'failure','')
        self.journal['selinux_restore_pending'] = self.selinux_changed; atomic_json(self.backup_dir/'operation.json',self.journal)
        if success or getattr(self,'cleanup_ok',False): self.journal_path.unlink(missing_ok=True)
        else: atomic_json(self.journal_path,self.journal)
        self.running = False; self.main.end(success)
        if success:
            self.main.privilege = 'shell'; self.main.read_profile()
        self.main.notice(self.main.t('Системная операция завершена') if success else self.main.t('Операция прервана. Проверьте журнал восстановления.'))
        if self.close_after: QTimer.singleShot(0,self.main.close)

class AdminLogin(QDialog):
    def __init__(self, main):
        super().__init__(main); self.main = main; self.setWindowTitle(main.t('Вход администратора')); self.setMinimumWidth(370)
        layout = QVBoxLayout(self); layout.addWidget(QLabel(main.t('Введите секретный код'))); self.code = QLineEdit(); self.code.setEchoMode(QLineEdit.EchoMode.Password); self.code.setMaxLength(128); layout.addWidget(self.code)
        self.status = QLabel(); layout.addWidget(self.status); self.submit = QPushButton(main.t('Войти')); layout.addWidget(self.submit); self.submit.clicked.connect(self.verify); self.code.returnPressed.connect(self.verify); self.attempts = 0
    def verify(self):
        if not self.submit.isEnabled(): return
        code = self.code.text(); self.code.clear(); self.submit.setEnabled(False)
        def checked(valid,error):
            if not self.isVisible(): return
            if valid and not error: self.accept(); return
            self.attempts += 1; self.status.setText(self.main.t('Неверный код')); QTimer.singleShot(min(10000,self.attempts*1000),lambda:self.submit.setEnabled(True))
        self.main.background(lambda:verify_admin_code(code),checked)

class CatalogEntryDialog(QDialog):
    def __init__(self, main, kind, entry=None):
        super().__init__(main); self.main = main; self.kind = kind; self.entry = copy.deepcopy(entry or {}); self.setWindowTitle(main.t('Запись каталога')); self.resize(650,530)
        outer = QVBoxLayout(self); form = QFormLayout(); outer.addLayout(form); self.fields = {}
        keys = [('id','Постоянный ID'),('name','Название'),('description','Описание')]
        keys += [('source','Ссылка GitHub / APK'),('asset','Имя файла релиза'),('package','Android-пакет')] if kind == 'apps' else [('central_url','APK центрального экрана'),('passenger_url','APK пассажирского экрана')]
        for key,label in keys:
            field = QLineEdit(str(self.entry.get(key,''))); self.fields[key] = field; form.addRow(main.t(label),field)
        self.enabled = QCheckBox(main.t('Доступно пользователям')); self.enabled.setChecked(self.entry.get('enabled',True)); form.addRow(self.enabled)
        self.sdk = QSpinBox(); self.sdk.setRange(1,1000); self.sdk.setValue(self.entry.get('min_sdk',24 if kind == 'keyboards' else 1)); form.addRow('minSdk',self.sdk)
        self.extra = QCheckBox(main.t('Разрешить установку приложений (REQUEST_INSTALL_PACKAGES)')); self.extra.setChecked('request_install_packages' in self.entry.get('post_install',[]))
        if kind == 'apps': form.addRow(self.extra)
        else:
            note = QLabel(', '.join(KEYBOARD_MODELS) + '\ncom.qinggan.app.qgime / com.qinggan.app.qgime.second'); note.setWordWrap(True); form.addRow(note)
        self.status = QLabel(); self.status.setWordWrap(True); outer.addWidget(self.status)
        check = QPushButton(main.t('Проверить ссылки')); check.clicked.connect(self.check_links); outer.addWidget(check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); outer.addWidget(buttons)
    def value(self):
        item = dict(self.entry); item.update({key:w.text().strip() for key,w in self.fields.items()}); item['enabled'] = self.enabled.isChecked(); item['min_sdk'] = self.sdk.value()
        if self.kind == 'apps': item['post_install'] = ['request_install_packages'] if self.extra.isChecked() else []
        else: item['models'] = item.get('models',list(KEYBOARD_MODELS))
        return item
    def save(self):
        try:
            profile = default_catalog(); profile[self.kind] = [self.value()]; validate_catalog(profile); self.accept()
        except ValueError as error: self.status.setText(self.main.t(str(error)))
    def check_links(self):
        urls = [self.fields[key].text().strip() for key in (('source',) if self.kind == 'apps' else ('central_url','passenger_url'))]
        self.checker = DownloadService(self.main); self.results = []
        def next_url(index=0):
            if index == len(urls): self.status.setText('\n'.join(self.results)); return
            def resolved(meta,error):
                if error: self.results.append(error); next_url(index+1); return
                def head(r): self.results.append(meta['name'] + ': ' + (r['error'] or 'HTTP ' + str(r['status']))); next_url(index+1)
                self.main.web.request(meta['url'],head,method='HEAD')
            self.checker.resolve(urls[index],self.fields.get('asset',QLineEdit()).text() if self.kind == 'apps' else '',resolved)
        next_url()

class AdminDialog(QDialog):
    def __init__(self, main):
        super().__init__(main); self.main = main; self.active = True; self.setWindowTitle(main.t('Администратор')); self.resize(1000,720)
        self.draft_path = DATA_DIR / ('catalog-draft-qa.json' if main.smoke else 'catalog-draft.json')
        try: self.draft = validate_catalog(json.loads(self.draft_path.read_text(encoding='utf-8')))
        except (OSError,ValueError): self.draft = copy.deepcopy(main.catalog.profile)
        layout = QVBoxLayout(self); self.tabs = QTabWidget(); layout.addWidget(self.tabs); self.checks = {}; self.lists = {}
        features = QWidget(); form = QVBoxLayout(features)
        note = QLabel(main.t('Изменения общего профиля вступают в силу после успешной публикации.')); note.setWordWrap(True); form.addWidget(note)
        for key,label in FEATURES.items():
            check = QCheckBox(main.t(label)); check.setChecked(self.draft['features'][key]); self.checks[key] = check; form.addWidget(check)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(features); self.tabs.addTab(scroll,main.t('Функции'))
        for kind,label in (('apps','Приложения'),('keyboards','Клавиатуры')):
            page = QWidget(); box = QVBoxLayout(page); listing = QListWidget(); self.lists[kind] = listing; box.addWidget(listing)
            row = QHBoxLayout()
            for title,method in [('Добавить',self.add_entry),('Изменить',self.edit_entry),('Удалить',self.remove_entry)]:
                button = QPushButton(main.t(title)); button.clicked.connect(lambda checked=False,k=kind,m=method:m(k)); row.addWidget(button)
            box.addLayout(row); self.tabs.addTab(page,main.t(label)); self.refresh_list(kind)
        page = QWidget(); box = QFormLayout(page); self.repo = QLineEdit(main.catalog.config.get('repository','')); self.branch = QLineEdit(main.catalog.config.get('branch','')); self.branch.setPlaceholderText(main.t('Основная ветка репозитория')); self.catalog_path = QLineEdit(main.catalog.config.get('path','catalog.json'))
        self.token = QLineEdit(); self.token.setEchoMode(QLineEdit.EchoMode.Password); self.token.setPlaceholderText(main.t('Сохраняется только в Windows Credential Manager'))
        for title,widget in [('Репозиторий',self.repo),('Ветка',self.branch),('Путь JSON',self.catalog_path),('Токен Contents: write',self.token)]: box.addRow(main.t(title),widget)
        for title,fn in [('Сохранить подключение и токен',self.configure),('Удалить сохранённый токен',self.forget_token),('Загрузить актуальный профиль',self.load_remote),('Опубликовать',self.publish)]:
            button = QPushButton(main.t(title)); button.clicked.connect(fn); box.addRow(button)
        self.tabs.addTab(page,main.t('GitHub и публикация')); self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        row = QHBoxLayout(); save = QPushButton(main.t('Сохранить черновик')); save.clicked.connect(self.save_draft); row.addWidget(save); close = QPushButton(main.t('Закрыть')); close.clicked.connect(self.accept); row.addWidget(close); layout.addLayout(row)
    def collect(self):
        self.draft['features'] = {key:check.isChecked() for key,check in self.checks.items()}; return validate_catalog(self.draft)
    def save_draft(self):
        try: atomic_json(self.draft_path,self.collect()); self.status.setText(self.main.t('Черновик сохранён'))
        except (OSError,ValueError) as error: self.status.setText(self.main.t(str(error)))
    def refresh_list(self,kind):
        self.lists[kind].clear()
        for item in self.draft[kind]: self.lists[kind].addItem(item['name'] + ('  ·  ' + self.main.t('Отключено') if not item.get('enabled',True) else '') + '\n' + item['id'])
    def add_entry(self,kind): self.edit_entry(kind,True)
    def edit_entry(self,kind,new=False):
        index = self.lists[kind].currentRow()
        if not new and index < 0: return
        editor = CatalogEntryDialog(self.main,kind,None if new else self.draft[kind][index])
        if editor.exec():
            if new: self.draft[kind].append(editor.value())
            else: self.draft[kind][index] = editor.value()
            self.refresh_list(kind); self.save_draft()
    def remove_entry(self,kind):
        row = self.lists[kind].currentRow()
        if row >= 0 and self.main.confirm(self.main.t('Удалить запись каталога?')): self.draft[kind].pop(row); self.refresh_list(kind); self.save_draft()
    def configure(self):
        try:
            repo = github_repository(self.repo.text()); config = {'repository':repo,'branch':self.branch.text().strip(),'path':self.catalog_path.text().strip() or 'catalog.json'}
            if config != self.main.catalog.config: self.main.catalog.remote_sha = None; self.main.catalog.remote_loaded = False; self.main.catalog.etag = ''
            self.main.catalog.config = config; self.main.catalog.endpoint(); self.main.settings.setValue('catalog_connection',json.dumps(config)); self.main.settings.sync()
            if self.token.text(): CredentialStore.write(repo,self.token.text().strip()); self.token.clear()
            self.status.setText(self.main.t('Настройки сохранены')); self.main.catalog.refresh()
        except (OSError,ValueError) as error: self.status.setText(self.main.t(str(error)))
    def forget_token(self):
        try: CredentialStore.delete(github_repository(self.repo.text())); self.token.clear(); self.status.setText(self.main.t('Токен удалён'))
        except (OSError,ValueError) as error: self.status.setText(str(error))
    def load_remote(self):
        def loaded(result):
            if not self.active: return
            if result['error'] and result['status'] != 404: self.status.setText(result['error']); return
            if result['status'] == 404:
                self.main.catalog.remote_loaded = True; self.main.catalog.remote_sha = None; self.status.setText(self.main.t('Файл ещё не создан. Можно опубликовать первый каталог.')); return
            if self.main.confirm(self.main.t('Заменить черновик актуальным профилем GitHub?')):
                self.draft = copy.deepcopy(self.main.catalog.pending[0] if self.main.catalog.pending else self.main.catalog.profile)
                for key,check in self.checks.items(): check.setChecked(self.draft['features'][key])
                for kind in self.lists: self.refresh_list(kind)
                self.save_draft()
        self.main.catalog.etag = ''; self.main.catalog.refresh(loaded)
    def publish(self):
        try:
            profile = self.collect(); profile['revision'] = max(profile['revision'],self.main.catalog.profile['revision']) + 1; atomic_json(self.draft_path,profile)
            self.main.catalog.publish(profile,lambda ok,message:self.status.setText(self.main.t(message)) if self.active else self.main.notice(self.main.t(message)))
        except (OSError,ValueError) as error: self.status.setText(str(error))
    def done(self,result):
        self.save_draft(); self.token.clear(); self.active = False; super().done(result)

def setup_logging():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(DATA_DIR / 'voyah-manager.log', maxBytes=3_000_000, backupCount=3, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s')

def main():
    parser = argparse.ArgumentParser(description='Voyah Manager')
    parser.add_argument('--demo', action='store_true'); parser.add_argument('--smoke-dir', type=Path)
    parser.add_argument('--smoke-width',type=int); parser.add_argument('--smoke-height',type=int)
    parser.add_argument('--smoke-online',action='store_true')
    parser.add_argument('--bundled-adb', action='store_true'); parser.add_argument('--export-icon', type=Path)
    args = parser.parse_args()
    setup_logging(); app = QApplication(sys.argv[:1]); app.setStyle('Fusion'); app.setStyleSheet(STYLE); app.setApplicationName('Voyah Manager'); app.setWindowIcon(make_icon())
    if args.export_icon:
        make_icon().pixmap(256, 256).save(str(args.export_icon)); return 0
    def exception_hook(kind, value, traceback):
        logging.error('Unhandled exception', exc_info=(kind, value, traceback))
        if not args.smoke_dir: QMessageBox.critical(None, 'Voyah Manager', str(value))
    sys.excepthook = exception_hook
    window = MainWindow(args.demo, bool(args.smoke_dir)); window.show()
    if args.smoke_dir:
        window.lang = 'ru'; window.language.setCurrentIndex(0); window.retranslate()
        if args.smoke_width or args.smoke_height: window.resize(args.smoke_width or window.width(),args.smoke_height or window.height())
    if args.bundled_adb: QTimer.singleShot(300, window.use_bundled)
    if args.smoke_dir:
        args.smoke_dir.mkdir(parents=True, exist_ok=True)
        tool_checks = {}
        checks_started = [False]
        def check_tools(index=0):
            checks_started[0] = True
            commands = [('adb', window.adb_path, ['version']), ('aapt2', window.tools.path('aapt2.exe'), ['version']),
                        ('bundletool', window.tools.path('jre/bin/java.exe'), ['-jar', str(window.tools.path('bundletool.jar')), 'version'])]
            if index == len(commands):
                if args.smoke_online:
                    def network_checked(result):
                        tool_checks['https'] = {'ok':not bool(result['error']),'status':result['status'],'error':result['error']}; shots()
                    window.web.request(window.catalog.public_endpoint(),network_checked)
                else: shots()
                return
            name, program, arguments = commands[index]
            def checked(result):
                tool_checks[name] = {'ok':result.ok, 'output':result.text, 'code':result.code}; check_tools(index + 1)
            window.runner.run(program, arguments, checked, timeout=30000)
        def shots():
            if args.demo:
                window.pages['inspector'].show_screens(parse_screens(window.demo_backend.response(['shell', 'dumpsys window']).text, ''))
                window.pages['files'].show_entries(parse_listing(window.demo_backend.response(['shell', 'ls -lan /sdcard']).text), None)
                window.pages['apps'].packages = ['com.voyah.launcher', 'com.voyah.music', 'com.voyah.voice', 'com.voyah.video', 'com.android.settings', 'org.videolan.vlc', 'ru.yandex.yandexmaps', 'com.example.mapper']; window.pages['apps'].filter_rows()
            for language in (0,1):
                window.language.setCurrentIndex(language)
                for i in range(len(window.pages)):
                    window.sidebar.setCurrentRow(i); QApplication.processEvents(); window.grab().save(str(args.smoke_dir / f'tab-{i + 1}-{window.lang}.png'))
            inspector = window.pages['inspector']; window.select_section('inspector')
            for i in range(inspector.sections.count()):
                inspector.sections.setCurrentIndex(i); QApplication.processEvents(); window.grab().save(str(args.smoke_dir/f'inspector-{i+1}.png'))
            admin = AdminDialog(window); admin.show()
            for i in range(admin.tabs.count()):
                admin.tabs.setCurrentIndex(i); QApplication.processEvents(); admin.grab().save(str(args.smoke_dir/f'admin-{i+1}.png'))
            admin.reject(); admin.deleteLater()
            window.connection_details.show(); QApplication.processEvents(); window.grab().save(str(args.smoke_dir/'connection-settings.png')); window.connection_details.hide()
            window.select_section('tweaks'); QApplication.processEvents(); window.stack.currentWidget().verticalScrollBar().setValue(window.stack.currentWidget().verticalScrollBar().maximum()); QApplication.processEvents(); window.grab().save(str(args.smoke_dir/'recovery.png'))
            try: build_manifest = json.loads((RESOURCE_DIR/'build_manifest.json').read_text(encoding='utf-8'))
            except (OSError,ValueError): build_manifest = {}
            (args.smoke_dir / 'report.json').write_text(json.dumps({'version':VERSION, 'frozen':bool(getattr(sys, 'frozen', False)), 'adb':window.adb_path, 'tools':{name:window.tools.path(name).exists() for name in ('aapt2.exe','bundletool.jar','jre/bin/java.exe')}, 'tool_checks':tool_checks, 'tabs':window.stack.count(), 'profile':window.profile.api,'catalog':{'repository':window.catalog.config.get('repository',''),'revision':window.catalog.profile['revision']},'build':build_manifest,'size':[window.width(),window.height()],'dpr':window.devicePixelRatio()}, indent=2), encoding='utf-8')
            window.close(); app.quit()
        QTimer.singleShot(4000, check_tools)
    return app.exec()

if __name__ == '__main__':
    raise SystemExit(main())

