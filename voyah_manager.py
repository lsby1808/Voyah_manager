"""Voyah Manager 2.1 — single-file PySide6 Android Automotive workbench.

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
                            QRunnable, QSettings, QUrl, QSize, QRect, QPoint, QPointF, QRectF, QEvent,
                            QEasingCurve, QPropertyAnimation, QParallelAnimationGroup, QVariantAnimation)
from PySide6.QtGui import (QFont, QIcon, QPainter, QColor, QPixmap, QDesktopServices,
                           QTextCursor, QKeySequence, QShortcut, QPen, QPalette, QPainterPath, QRegion, QAction)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QPlainTextEdit, QTabWidget, QFrame, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QInputDialog,
    QProgressBar, QSplitter, QAbstractItemView, QSpinBox, QMenu, QDialog,
    QDialogButtonBox, QListWidget, QListWidgetItem, QStyle, QStackedWidget, QFormLayout, QToolButton, QLayout, QWidgetItem, QSizePolicy, QStyleOptionButton, QGraphicsOpacityEffect)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

VERSION = '2.1.0'
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

EN.update({'Ваш автомобиль': 'Your vehicle', 'Готово к работе': 'Ready when you are', 'Автомобиль': 'Vehicle', 'Для опытных': 'Advanced', 'Уменьшить анимацию': 'Reduce animation', 'Твики': 'Tweaks', 'Терминал': 'Terminal', 'Убирает плавные переходы и раскрытие меню. Все действия остаются доступными.': 'Turns off animated transitions and menus. All actions remain available.', 'Подставляет адрес из отчёта установщика. Подходит только для прошивок с таким способом подключения.': 'Fills in the address from the installer report. Suitable only for firmware using this connection method.', 'Выберите готовое приложение — программа скачает его и установит в автомобиль.': 'Choose an app: the program downloads it and installs it in your vehicle.', 'Выберите файлы на компьютере или перетащите их сюда для установки.': 'Choose files on your computer or drop them here to install.', 'Установите выбранную клавиатуру на оба экрана или верните штатную.': 'Install a keyboard on both displays or restore the factory keyboards.', 'Узнайте, что открыто на экранах и какие события происходят в автомобиле.': 'See what is open on the displays and what happens in your vehicle.', 'Передавайте файлы между компьютером и памятью автомобиля.': 'Transfer files between your computer and the vehicle.', 'Запускайте приложения и управляйте тем, что уже установлено.': 'Launch apps and manage what is already installed.', 'Настройте размер элементов, звук и внешний вид. Здесь же доступны действия восстановления.': 'Adjust the size of controls, sound and appearance. Recovery actions are also available here.', 'Для опытных: команды выполняются на выбранном автомобиле. Проверьте их перед запуском.': 'For experienced users: commands run on the selected vehicle. Check them before running.', 'Подключает выбранный автомобиль. Для первого соединения по кабелю подтвердите запрос на экране автомобиля.': 'Connects the selected vehicle. For a first USB connection, accept the prompt on its screen.', 'Проверяет, какие автомобили сейчас доступны для подключения.': 'Checks which vehicles are available for connection.', 'Возвращает на предыдущий экран в автомобиле.': 'Returns to the previous screen in your vehicle.', 'Открывает главный экран автомобиля.': 'Opens the main vehicle screen.', 'Показывает недавно открытые приложения в автомобиле.': 'Shows recently opened apps in your vehicle.', 'Сохраняет снимок экрана автомобиля на компьютер.': 'Saves a screenshot from your vehicle to the computer.', 'Останавливает текущее действие. Уже выполненные изменения могут сохраниться.': 'Stops the current task. Changes already made may remain.', 'Позволяет выбрать файл средства связи с автомобилем на вашем компьютере.': 'Choose the connection tool on your computer.', 'Использует средство связи, которое уже входит в программу.': 'Uses the connection tool already included with this program.', 'Перезапускает связь с автомобилем, если подключение перестало отвечать.': 'Restarts the connection tool when the vehicle stops responding.', 'Подготавливает подключённый по кабелю автомобиль к работе через Wi-Fi и показывает его адреса.': 'Prepares a USB-connected vehicle for Wi-Fi and shows its addresses.', 'Открывает действия для расширенного доступа. Некоторые прошивки не разрешают такой доступ.': 'Opens advanced access actions. Some firmware does not allow this access.', 'Показывает варианты перезапуска автомобиля. Каждое действие требует подтверждения.': 'Shows vehicle restart options. Each action requires confirmation.', 'Открывает сохранённую запись действий и ошибок программы.': 'Opens the saved record of program actions and errors.', 'Показывает версию программы и сведения о её работе.': 'Shows the program version and information about how it works.', 'Показывает способ подключения, адрес автомобиля и дополнительные действия.': 'Shows the connection method, vehicle address and additional actions.', 'Показывает подробную запись выполненных действий и ответов автомобиля.': 'Shows a detailed record of actions and vehicle responses.', 'Создаст новую папку внутри открытой папки автомобиля.': 'Creates a new folder inside the currently open car folder.', 'Изменит имя одного выбранного файла или папки.': 'Renames one selected file or folder.', 'Проверит выбранный APK в памяти автомобиля и установит его как приложение.': 'Checks the selected APK in car storage and installs it as an app.', 'Удалит выбранные файлы и папки из автомобиля. Отменить это действие нельзя.': 'Deletes selected files and folders from your car. This action cannot be undone.', 'Приложение перестанет запускаться. Его можно включить обратно.': 'Stops the app from launching. You can enable it again later.', 'Снова разрешит запуск ранее отключённого приложения.': 'Allows a previously disabled app to launch again.', 'Удалит настройки и личные данные внутри приложения. Само приложение останется.': 'Deletes settings and personal data inside the app. The app itself will remain.', 'Удалит выбранное приложение из автомобиля. Сначала потребуется подтверждение.': 'Uninstalls the selected app from your car. Confirmation is required first.', 'Уберёт текст из окна терминала. Команды и их история останутся.': 'Clears the terminal window. Commands and their history will remain.', 'Сохранит весь отображаемый вывод в текстовый файл на компьютере.': 'Saves all displayed output to a text file on your computer.', 'Перетащите файлы приложения сюда': 'Drop app files here', 'Подойдут APK и готовые комплекты приложений. Можно выбрать несколько файлов или целую папку.': 'Use APK files or prepared app bundles. You can select several files or a whole folder.', 'Приложения с компьютера': 'Apps from your computer', 'Выберите файлы, проверьте список и установите их в автомобиль.': 'Choose files, check the list, then install them in your car.', 'Выбрать файлы': 'Choose files', 'Выберите один APK, несколько приложений или готовый комплект из файлов.': 'Choose one APK, several apps, or a prepared set of app files.', 'Выбрать папку': 'Choose folder', 'Добавит все APK из выбранной папки. Каждое приложение установится по очереди.': 'Adds every APK in the selected folder. Apps will be installed one after another.', 'Одно приложение': 'One app', 'Несколько приложений': 'Several apps', 'Комплект одного приложения': 'One app bundle', 'Укажите, устанавливаете вы один файл, разные приложения или части одного приложения.': 'Choose whether you are installing one file, different apps, or parts of the same app.', 'Как установить': 'Installation mode', 'Один APK — одно приложение.': 'One APK is one app.', 'Разные приложения установятся по очереди. Не выбирайте этот режим для частей одного приложения.': 'Different apps will be installed one after another. Do not use this mode for parts of one app.', 'Выберите все части одного приложения или один готовый архив. Комплект установится целиком.': 'Choose every part of one app, or one prepared archive. The entire bundle will be installed together.', 'Выбранные файлы': 'Selected files', 'Файлы ещё не выбраны': 'No files selected yet', 'Перетащите приложение в область выше или нажмите «Выбрать файлы».': 'Drop an app in the area above or click “Choose files”.', 'Очистить список': 'Clear list', 'Уберёт выбранные файлы из списка. Файлы на компьютере останутся.': 'Removes selected files from this list. Files on your computer will remain.', 'Параметры установки': 'Installation options', 'Обычные параметры уже выбраны. Меняйте их только при необходимости.': 'The usual options are already selected. Change them only when needed.', 'Сохранить данные при переустановке': 'Keep app data when reinstalling', 'Разрешить старую версию': 'Allow an older version', 'Выдать разрешения приложению': 'Grant app permissions', 'Заменит приложение новой версией, сохранив его настройки и личные данные.': 'Replaces the app with a new version while keeping its settings and personal data.', 'Разрешит установить более старую версию. Некоторые приложения это не поддерживают.': 'Allows installing an older version. Some apps do not support this.', 'Сразу разрешит приложению использовать запрошенные возможности, например микрофон и память.': 'Immediately grants requested access, such as microphone and storage permissions.', 'Флаги установки: сохранение данных — -r, старая версия — -d, разрешения — -g. Части одного приложения устанавливаются вместе.': 'Installation flags: keep data — -r, older version — -d, permissions — -g. Parts of one app are installed together.', 'Технические подробности': 'Technical details', 'Установить в автомобиль': 'Install in car', 'Проверит выбранные файлы и установит их на подключённое устройство. Результат появится напротив каждого файла.': 'Checks the selected files and installs them on the connected device. Each file will show its result.', 'Файлов в списке: {count}': 'Files in list: {count}', 'Память автомобиля': 'Car storage', 'Открывайте папки, передавайте файлы в автомобиль и сохраняйте их на компьютер.': 'Browse folders, send files to your car, and save them on your computer.', 'Путь к открытой папке в памяти автомобиля. Можно вставить другой путь и нажать Enter.': 'Path to the open folder in your car. Paste another path and press Enter to open it.', 'Откроет папку на один уровень выше.': 'Opens the parent folder.', 'Заново прочитает содержимое открытой папки.': 'Reads the current folder again.', 'Общая память': 'Shared storage', 'Загрузки': 'Downloads', 'Все накопители': 'All storage', 'Системные приложения': 'System apps', 'Временные файлы': 'Temporary files', 'Быстро откроет эту папку в памяти автомобиля.': 'Quickly opens this folder in your car storage.', 'Передать в автомобиль': 'Send to car', 'Выберите файлы на компьютере. Они будут скопированы в открытую папку автомобиля.': 'Choose files on your computer. They will be copied to the currently open car folder.', 'Скачать на компьютер': 'Save to computer', 'Сохранит выбранные файлы и папки на компьютер. Исходные файлы в автомобиле останутся.': 'Saves selected files and folders on your computer. The originals remain in your car.', 'Ещё': 'More', 'Создание папки, переименование, удаление и установка выбранного APK.': 'Create a folder, rename or delete items, or install a selected APK.', 'Содержимое папки': 'Folder contents', 'Откройте память автомобиля': 'Open car storage', 'Подключите автомобиль и нажмите «Обновить». Файлы появятся здесь.': 'Connect your car and click “Refresh”. Its files will appear here.', 'Папка пуста': 'This folder is empty', 'В этой папке пока нет файлов. Можно передать их с компьютера.': 'This folder has no files yet. You can send some from your computer.', 'Объектов: {count} · Выбрано: {selected}': 'Items: {count} · Selected: {selected}', 'Приложения в автомобиле': 'Apps in your car', 'Выберите приложение, чтобы открыть его на нужном экране или изменить его состояние.': 'Select an app to open it on the screen you want or change its state.', 'Покажет все приложения или только выбранную группу.': 'Shows all apps or just the selected group.', 'Найти приложение': 'Find an app', 'Получит свежий список приложений из автомобиля.': 'Gets a fresh list of apps from your car.', 'Выберите приложение из списка': 'Select an app from the list', 'Системные приложения могут отвечать за функции автомобиля. Если назначение неизвестно, оставьте их включёнными.': 'System apps may control car features. Leave them enabled if you do not know what they do.', 'Выберите экран, на котором откроется приложение.': 'Choose the screen on which the app will open.', 'Открыть приложение': 'Open app', 'Откроет выбранное приложение на центральном или пассажирском экране.': 'Opens the selected app on the centre or passenger screen.', 'Закроет выбранное приложение. Его настройки и файлы останутся.': 'Closes the selected app. Its settings and files will remain.', 'Сохранить APK': 'Save APK', 'Скачает установочные файлы выбранного приложения на компьютер. Само приложение останется в автомобиле.': 'Saves the selected app’s installation files on your computer. The app remains in your car.', 'Включение, отключение, очистка данных и удаление выбранного приложения.': 'Enable, disable, clear data, or uninstall the selected app.', 'Отключить приложение': 'Disable app', 'Включить приложение': 'Enable app', 'Список приложений': 'App list', 'Приложение': 'App', 'Получите список приложений': 'Load the app list', 'Подключите автомобиль и нажмите «Обновить». Затем выберите нужное приложение.': 'Connect your car and click “Refresh”. Then select an app.', 'Приложения не найдены': 'No apps found', 'Попробуйте другое название или измените фильтр.': 'Try another name or change the filter.', 'Найдено: {count}': 'Found: {count}', 'Отправляйте свои команды и читайте ответы автомобиля. Используйте этот раздел, если понимаете, что делает команда.': 'Send your own commands and read the car’s responses. Use this section when you understand what a command does.', 'Готов к команде': 'Ready for a command', 'Интерактивное подключение': 'Interactive connection', 'Откроет постоянное подключение для команд. Следующие строки отправляются прямо в автомобиль.': 'Opens a persistent connection for commands. Subsequent lines are sent directly to your car.', 'Прервёт выполняющуюся команду или закроет интерактивное подключение.': 'Stops the running command or closes the interactive connection.', 'Сохранение вывода и очистка окна терминала.': 'Save the output or clear the terminal window.', 'Очистить вывод': 'Clear output', 'Сохранить вывод': 'Save output', 'Ответы устройства': 'Device responses', 'Здесь появятся команда и её результат. История команд доступна стрелками вверх и вниз.': 'Commands and their results appear here. Use the up and down arrow keys for command history.', 'Введите adb … или adb shell …': 'Enter adb … or adb shell …', 'Введите команду и нажмите Enter. Стрелки вверх и вниз выбирают предыдущие команды.': 'Enter a command and press Enter. The up and down arrow keys select previous commands.', 'Отправит введённую команду. Ответ появится в окне выше.': 'Sends the command you entered. Its response appears above.', 'Для команды, обращающейся к автомобилю, сначала выберите подключённое устройство. Команды вроде adb devices работают и без него.': 'Select a connected device before sending a command to your car. Commands such as adb devices also work without one.', 'Закрыть подключение': 'Close connection', 'Постоянное подключение открыто': 'Persistent connection is open', 'Команда выполняется…': 'Command is running…', 'Выберите готовое приложение. Программа скачает его и установит в машину.': 'Choose an app. We will download it and install it in your car.', 'Загрузить свежий список приложений. Уже скачанные файлы останутся на компьютере.': 'Get the latest app list. Downloaded files will remain on your computer.', 'Каталог пока пуст': 'The catalog is empty', 'Администратор ещё не добавил приложения. Когда они появятся, вы сможете выбрать и установить нужное.': 'The administrator has not added any apps yet. When they appear, you can choose and install them.', 'Выбранное приложение': 'Selected app', 'Скачает выбранное приложение, проверит его и установит в подключённую машину. Дождитесь сообщения о завершении.': 'Downloads and checks the selected app, then installs it in the connected car. Wait for the completion message.', 'Версия будет проверена перед загрузкой': 'Version will be checked before downloading', 'Готовое приложение для вашей машины.': 'A ready-to-install app for your car.', 'Выбрать приложение': 'Select app', 'Ничего не найдено': 'Nothing found', 'Попробуйте другое название или очистите строку поиска.': 'Try another name or clear the search field.', 'Администратору нужно указать адрес каталога. Пока можно устанавливать APK с компьютера.': 'The administrator needs to set up a catalog address. You can still install APKs from your computer.', 'Нажмите «Выбрать приложение» на карточке выше.': 'Click “Select app” on a card above.', 'Нужна более новая версия Android': 'Requires a newer Android version', 'Не подходит подключённой машине': 'Does not match the connected car', 'Совместимость проверим после подключения': 'Compatibility will be checked after connection', 'Первичная проверка пройдена; APK проверим перед установкой': 'Initial checks passed; the APK will be checked before installation', 'Один комплект обновляет клавиатуры центрального и пассажирского экранов.': 'One set updates the keyboards on the center and passenger displays.', 'Выберите комплект из списка. До установки программа проверит оба файла и сохранит штатные клавиатуры.': 'Choose a set. Both files will be checked and the original keyboards backed up before installation.', 'Получить актуальный список клавиатур, который опубликовал администратор.': 'Get the latest keyboard list published by the administrator.', 'Комплектов пока нет': 'No keyboard sets yet', 'Администратор ещё не добавил ссылки на клавиатуры. Штатные клавиатуры можно восстановить отдельно.': 'The administrator has not added keyboard links yet. You can restore the original keyboards separately.', 'Клавиатура для ввода на основном экране автомобиля.': 'Keyboard for typing on the car’s main display.', 'Клавиатура для ввода на экране переднего пассажира.': 'Keyboard for typing on the front passenger’s display.', 'Оба файла будут проверены перед установкой': 'Both files will be checked before installation', 'Скачает две клавиатуры, сохранит текущие файлы и заменит их. Машина перезагрузит мультимедийную систему. Перед началом вы увидите подтверждение.': 'Downloads both keyboards, backs up the current files and replaces them. The multimedia system will reboot. You will see a confirmation before starting.', 'Штатные клавиатуры и резервные копии': 'Original keyboards and backups', 'Старые файлы сохраняются в машине и дополнительно на компьютере. Уже существующие штатные копии не перезаписываются.': 'Original files are backed up in the car and on your computer. Existing original backups will not be overwritten.', 'Вернёт сохранённые штатные клавиатуры для обоих экранов. Текущие файлы тоже будут сохранены на компьютере перед заменой.': 'Restores the backed-up original keyboards for both displays. Current files will also be backed up on your computer before replacement.', 'Установка и восстановление требуют расширенного доступа. Программа спросит подтверждение и покажет все этапы в журнале.': 'Installation and restoration require advanced access. You will be asked to confirm, and each step will appear in the activity log.', 'Подключите машину, чтобы проверить совместимость': 'Connect the car to check compatibility', 'Этот комплект не подходит подключённой машине': 'This set does not match the connected car', 'Модель поддерживается. Оба файла проверим перед заменой.': 'This model is supported. Both files will be checked before replacement.', 'Подберите удобный размер текста и элементов на выбранных экранах.': 'Choose a comfortable size for text and controls on the selected displays.', 'Параметры экранов ещё не проверены': 'Display settings have not been checked yet', 'Экран': 'Display', 'Масштаб интерфейса': 'Interface scale', 'Применить масштаб': 'Apply scale', 'Изменит размер текста и кнопок на выбранном экране. Большее число делает элементы крупнее. Приборная панель требует отдельного подтверждения.': 'Changes text and button sizes on the selected display. A larger number makes items bigger. The instrument display requires a separate confirmation.', 'Вернуть заводской масштаб': 'Restore factory scale', 'Уберёт пользовательский масштаб и вернёт заводской размер элементов на выбранных экранах.': 'Removes your custom scale and restores the factory size on the selected displays.', 'Проверить экраны': 'Check displays', 'Прочитает текущие размеры и масштаб экранов. Ничего не меняет.': 'Reads the current display sizes and scale without changing anything.', 'Поможет указать, какой экран является центральным, пассажирским и приборным, если прошивка использует другой порядок.': 'Choose which display is the center, passenger or instrument display if your firmware uses a different order.', 'Выберите приложение и настройте, к каким возможностям автомобиля у него есть доступ.': 'Choose an app and control which car features it can access.', 'Введите адрес приложения, например ru.vk.store': 'Enter an app address, for example ru.vk.store', 'Музыка без пауз': 'Uninterrupted music', 'Не давайте выбранному приложению прерывать музыку.': 'Prevent the selected app from interrupting music.', 'Вернёт выбранному приложению возможность приостанавливать музыку, когда это нужно.': 'Allows the selected app to pause music again when needed.', 'Доступ к микрофону': 'Microphone access', 'Разрешите выбранному приложению записывать голос.': 'Allow the selected app to record your voice.', 'Разрешить микрофон': 'Allow microphone', 'Поверх других окон': 'Over other windows', 'Разрешите небольшие окна приложения поверх экрана.': 'Allow the app to show small windows over the screen.', 'Разрешить поверх окон': 'Allow over other windows', 'Скрытые настройки': 'Hidden settings', 'Дайте настройщикам и переназначателям кнопок расширенный доступ.': 'Give settings and button-mapping apps additional access.', 'Дать доступ к настройкам': 'Allow settings access', 'Работа в фоне': 'Background activity', 'Помогите приложению работать при экономии энергии.': 'Help the app keep working when energy saving is active.', 'Не ограничивать в фоне': 'Allow background activity', 'Режим экономии энергии': 'Energy-saving mode', 'Управляйте общими ограничениями работы приложений в фоне.': 'Manage overall limits on background app activity.', 'Отключить экономию': 'Disable energy saving', 'Снимет общие ограничения фоновой работы приложений. Это может увеличить расход энергии.': 'Removes overall background activity limits. This may increase energy use.', 'Вернуть экономию': 'Restore energy saving', 'Снова разрешит системе ограничивать приложения в фоне для экономии энергии.': 'Allows the system to limit background apps again to save energy.', 'Полезные настройки интернета и внешнего вида. Для возврата сохранены прежние значения.': 'Useful internet and display settings. Previous values are saved when you make a change.', 'Фильтр рекламы': 'Ad filtering', 'Использует AdGuard для фильтрации сетевых адресов. Доступность зависит от сети.': 'Uses AdGuard to filter network addresses. Availability depends on your network.', 'Включить фильтр': 'Enable filtering', 'Выключить фильтр': 'Disable filtering', 'Значок Wi-Fi без интернета': 'Wi-Fi without internet icon', 'Можно убрать предупреждение, если сеть машины работает без доступа в интернет.': 'Hide the warning if the car’s network works without internet access.', 'Убрать предупреждение': 'Hide warning', 'Вернуть проверку': 'Restore checks', 'Больше места на экране': 'More screen space', 'Скрывает верхнюю панель системы, чтобы приложение занимало больше места.': 'Hides the system’s top bar to give the app more space.', 'Скрыть верхнюю панель': 'Hide top bar', 'Вернуть верхнюю панель': 'Restore top bar', 'Вернёт обычное поведение этой функции.': 'Restores the usual behavior of this feature.', 'Восстановить прежнее значение': 'Restore previous value', 'Вернёт значение, которое было в машине до первого изменения через эту программу.': 'Restores the value the car had before this app first changed it.', 'Результат проверяется после изменения': 'The result is checked after each change', 'Открыть настройки Android': 'Open Android settings', 'Откроет обычные настройки Android на экране машины. Доступные пункты зависят от прошивки.': 'Opens regular Android settings on the car’s display. Available options depend on the firmware.', 'Эти действия меняют системные файлы и перезагружают мультимедийную систему. Перед запуском вы увидите точное описание.': 'These actions change system files and reboot the multimedia system. You will see a detailed description before starting.', 'Пересоздаёт базу настроек автомобиля. Сначала сохраняет резервную копию на компьютере; личные настройки могут сброситься.': 'Recreates the car’s settings database after backing it up on your computer. Personal preferences may be reset.', 'Сохранит настройки автомобиля на компьютере и пересоздаст их в машине. Личные настройки могут сброситься. Перед началом программа спросит подтверждение.': 'Backs up vehicle settings on your computer and recreates them in the car. Personal preferences may be reset. You will be asked to confirm before starting.', 'Отключает проверку системного раздела по процедуре установщика. Требуется расширенный доступ и перезагрузка.': 'Disables system-partition checks using the installer’s procedure. Requires advanced access and a reboot.', 'Отключит проверку системных файлов по процедуре из отчёта и перезагрузит мультимедийную систему. Это не возвращает заводскую защиту.': 'Disables system-file checks using the report’s procedure and reboots the multimedia system. This does not restore factory protection.', 'Откроет сведения о выполненной или прерванной операции и сохранённых резервных копиях.': 'Opens information about completed or interrupted recovery and saved backups.', 'Попытается вернуть систему в рабочее состояние после прерванного восстановления. Используется только для машины, указанной в журнале.': 'Attempts to restart the system after interrupted recovery. Only works with the car recorded in the recovery log.', 'Доступные экраны': 'Available displays', 'Управляйте доступными функциями, приложениями и клавиатурами. Введите секретный код, чтобы продолжить.': 'Manage available features, apps and keyboards. Enter the secret code to continue.', 'Секретный код': 'Secret code', 'Приложение каталога': 'Catalog app', 'Комплект клавиатур': 'Keyboard set', 'Пользователи увидят название и описание. Ссылки нужны программе для скачивания файлов.': 'Users will see the name and description. The app uses the links to download files.', 'Короткое постоянное имя записи. Не меняйте его после публикации, чтобы программа узнавала приложение.': 'A short permanent record name. Keep it unchanged after publication so the app can identify the entry.', 'Название, которое пользователь увидит в каталоге.': 'The name users will see in the catalog.', 'Коротко расскажите, для чего нужно приложение или комплект.': 'Briefly describe what the app or keyboard set is for.', 'Вставьте ссылку на GitHub, страницу выпуска или файл для скачивания.': 'Paste a GitHub link, release page or downloadable file link.', 'Необязательно: точное имя нужного файла, если в выпуске их несколько.': 'Optional: the exact file name if the release contains several files.', 'Необязательно: внутренний адрес приложения для дополнительной проверки скачанного файла.': 'Optional: the app’s internal address for an additional downloaded-file check.', 'Ссылка на клавиатуру основного экрана автомобиля.': 'Link to the keyboard for the car’s main display.', 'Ссылка на клавиатуру экрана переднего пассажира.': 'Link to the keyboard for the front passenger’s display.', 'Выключенная запись останется в каталоге, но установить её будет нельзя.': 'A disabled entry stays in the catalog but cannot be installed.', 'Минимальное поколение Android, которое поддерживает файл. Программа проверит это перед установкой.': 'The minimum Android generation supported by this file. It will be checked before installation.', 'Минимальный Android (API)': 'Minimum Android (API)', 'Разрешить приложению устанавливать другие приложения': 'Allow this app to install other apps', 'Нужно магазинам приложений. Выдаёт дополнительное разрешение после успешной установки.': 'Needed by app stores. Grants an additional permission after successful installation.', 'Поддерживаемые модели': 'Supported models', 'Управление приложением': 'App management', 'Разделы приложения': 'App sections', 'Установка и файлы': 'Installation and files', 'Приложения и твики': 'Apps and tweaks', 'Системные действия': 'System actions', 'Выбор и скачивание приложений из общего каталога.': 'Choose and download apps from the shared catalog.', 'Установка файлов, которые пользователь выбрал на компьютере.': 'Install files the user selected on their computer.', 'Выбор комплектов для двух экранов и восстановление штатных клавиатур.': 'Choose sets for both displays and restore original keyboards.', 'Просмотр того, что открыто на экранах, и поиск событий кнопок.': 'View what is open on each display and find button events.', 'Просмотр памяти автомобиля и копирование файлов.': 'Browse the car’s storage and copy files.', 'Просмотр установленных приложений и управление ими.': 'View and manage installed apps.', 'Настройки экрана, звука, сети и восстановление.': 'Display, sound and network settings, plus recovery.', 'Позволяет опытному пользователю вводить произвольные команды.': 'Allows an experienced user to enter custom commands.', 'Разрешает все способы установки приложений, включая каталог и файлы на компьютере.': 'Allows all app installation methods, including the catalog and local files.', 'Разрешает загрузку, удаление, создание папок и переименование файлов в машине.': 'Allows uploading, deleting, creating folders and renaming files in the car.', 'Разрешает замену двух системных клавиатур из каталога.': 'Allows replacing both system keyboards from the catalog.', 'Разрешает возврат сохранённых штатных клавиатур.': 'Allows restoring backed-up original keyboards.', 'Разрешает временно отключать приложения и включать их обратно.': 'Allows temporarily disabling apps and enabling them again.', 'Разрешает удалять данные и настройки выбранного приложения.': 'Allows deleting the selected app’s data and preferences.', 'Разрешает удалять приложения из машины.': 'Allows uninstalling apps from the car.', 'Разрешает менять размер текста и элементов экрана.': 'Allows changing the size of text and screen controls.', 'Разрешает менять доступ к микрофону, звуку и фоновой работе.': 'Allows changing access to the microphone, sound and background activity.', 'Разрешает настройки сети и верхней панели экрана.': 'Allows network and top-bar settings.', 'Разрешает пользователю самостоятельно включать расширенный системный доступ.': 'Allows the user to enable advanced system access themselves.', 'Разрешает перезагрузку и системные сценарии с перезагрузкой.': 'Allows rebooting and system procedures that require a reboot.', 'Разрешает пересоздание настроек автомобиля с предварительной копией.': 'Allows recreating vehicle settings after making a backup.', 'Разрешает отключить проверку системного раздела по процедуре установщика.': 'Allows disabling system-partition checks using the installer’s procedure.', 'Соберите список приложений для пользователей.': 'Build the app list for your users.', 'Каждая запись содержит две ссылки: для центрального и пассажирского экранов.': 'Each entry contains two links, for the center and passenger displays.', 'Общий каталог на GitHub': 'Shared catalog on GitHub', 'Пользователям не нужен пароль для чтения каталога. Для публикации нужен ваш токен с доступом к этому репозиторию.': 'Users do not need a password to read the catalog. Publishing requires your token with access to this repository.', 'Секрет для публикации. Хранится только на этом компьютере и не попадёт в каталог или сборку.': 'A publishing secret. Stored only on this computer and never included in the catalog or executable.', 'Публикация изменений': 'Publish changes', 'Сначала получите актуальный каталог, затем опубликуйте черновик. Если каталог изменил другой администратор, программа сохранит ваш черновик и сообщит о конфликте.': 'Load the current catalog, then publish your draft. If another administrator changed it, your draft will be kept and a conflict reported.', 'Выберите запись для изменения или добавьте новую.': 'Select an entry to edit or add a new one.', 'Экраны': 'Displays', 'Кнопки руля': 'Steering wheel', 'Наблюдение': 'Live view', 'Сведения о приложении': 'App details', 'Открытие приложений': 'Apps opened', 'Нажатия и голос': 'Buttons and voice', 'Фоновые действия': 'Background actions', 'Вся запись': 'Full recording', 'Экраны приложения': 'App screens', 'Получаемые события': 'Received events', 'Полные сведения': 'Full details', 'Выберите, что хотите узнать: открытые экраны, действие кнопки или работу приложения.': "Choose what to inspect: open screens, a button action, or an app's activity.", 'Копировать эту запись': 'Copy this value', 'Скопировано': 'Copied', 'Что сейчас открыто?': 'What is open right now?', 'Узнайте, какое приложение сейчас видно на каждом экране автомобиля.': "See which app is currently visible on each of the car's displays.", 'Обновить экраны': 'Refresh displays', 'Показывает приложения, которые сейчас открыты на экранах автомобиля.': "Shows the apps currently open on the car's displays.", 'Приборная панель': 'Instrument cluster', 'Центральный экран': 'Centre display', 'Экран пассажира': 'Passenger display', 'Пока нет данных': 'No information yet', 'Подключите автомобиль и нажмите «Обновить экраны».': 'Connect the car and select Refresh displays.', 'Адрес приложения в системе. Его можно скопировать для настройки или диагностики.': "The app's address in the system. You can copy it for setup or inspection.", 'Открытый экран приложения': 'Open app screen', 'Название той части приложения, которая сейчас видна.': 'The name of the part of the app currently on screen.', 'Полная запись': 'Full address', 'Приложение и экран': 'App and screen', 'Полная запись приложения и открытого экрана.': 'The full address of the app and its open screen.', 'Что делает кнопка руля?': 'What does this steering wheel button do?', 'Начните запись, нажмите нужную кнопку в автомобиле и дождитесь результата.': 'Start a recording, press the button in the car, and wait for the result.', '1 · Начните запись': '1 · Start recording', '2 · Нажмите кнопку на руле': '2 · Press the steering wheel button', '3 · Посмотрите результат': '3 · View the result', 'Начать запись на 6 секунд': 'Record for 6 seconds', 'Записывает события в течение шести секунд. Сразу после начала нажмите нужную кнопку на руле.': 'Records events for six seconds. Press the steering wheel button as soon as recording begins.', 'Отменить': 'Cancel', 'Останавливает текущую запись. Можно сразу начать новую.': 'Stops the current recording. You can start a new one straight away.', 'Сохранить запись': 'Save recording', 'Сохраняет все полученные сообщения, включая скрытые в других группах.': 'Saves all received messages, including those outside the other groups.', 'Открыть в Блокноте': 'Open in Notepad', 'Сохраняет запись на компьютер и открывает её в Блокноте.': 'Saves the recording to your computer and opens it in Notepad.', 'Какие приложения и экраны открылись во время записи.': 'Apps and screens that opened during the recording.', 'Сообщения о кнопках руля и голосовых командах.': 'Messages about steering wheel buttons and voice commands.', 'Действия, которые автомобиль выполняет без открытия нового окна.': 'Actions the car performs without opening a new window.', 'Все сообщения, полученные во время записи.': 'Every message received during the recording.', 'Здесь появится результат': 'Results will appear here', 'Нажмите «Начать запись» и затем нужную кнопку на руле.': 'Select Record for 6 seconds, then press the steering wheel button.', 'Наблюдение в реальном времени': 'Watch events live', 'Запустите нужный вид наблюдения и выполните действие в автомобиле.': 'Start the view you need, then perform an action in the car.', 'Показать сообщения с этими словами, например: музыка, голос': 'Show messages with these words, for example: music, voice', 'Введите одно или несколько слов через запятую. Остальные сообщения будут скрыты, но сохранятся в записи.': 'Enter one or more words separated by commas. Other messages are hidden but remain in the recording.', 'Сохранить наблюдение': 'Save live recording', 'Сохраняет сообщения из обоих видов наблюдения, включая скрытые фильтром.': 'Saves messages from both views, including those hidden by the filter.', 'События приложений': 'App activity', 'Показывает, что делают приложения во время вашей работы с экраном.': 'Shows what apps do while you use the display.', 'Нажатия кнопок': 'Button presses', 'Здесь видны только те нажатия, которые автомобиль передаёт системе.': 'Only button presses reported to the system by the car appear here.', 'Начать': 'Start', 'Начинает получать новые сообщения. Второй вид наблюдения работает независимо.': 'Starts receiving new messages. The other view runs independently.', 'Пауза прокрутки': 'Pause scrolling', 'Оставляет нужные строки на экране. Запись продолжает работать.': 'Keeps the current lines on screen. Recording continues.', 'Наблюдение ещё не началось': 'Not running yet', 'Нажмите «Начать», затем выполните нужное действие в автомобиле.': 'Select Start, then perform the action in the car.', 'Какие действия доступны приложению?': 'What can this app do?', 'Найдите установленное приложение или укажите его адрес, затем получите сведения.': 'Find an installed app or enter its address, then request its details.', 'Найти приложение по части адреса': 'Find an app by part of its address', 'Введите часть адреса приложения. Программа найдёт совпадения среди установленных приложений.': "Enter part of an app's address to search among installed apps.", 'Найти': 'Find', 'Выберите приложение или укажите его адрес': 'Select an app or enter its address', 'Например: com.voyah.music': 'For example: com.voyah.music', 'Получить сведения': 'Get details', 'Показывает доступные экраны приложения и действия, на которые оно реагирует.': "Shows the app's available screens and the actions it responds to.", 'Сохранить': 'Save', 'Сохраняет все сведения о выбранном приложении на компьютер.': 'Saves all details about the selected app to your computer.', 'Экраны, которые могут открываться внутри приложения.': 'Screens that can open within this app.', 'События, после которых приложение может выполнять действия.': 'Events that can trigger actions in this app.', 'Действия приложения, которые выполняются без открытия окна.': 'App actions that run without opening a window.', 'Все сведения, полученные от автомобиля. Их можно сохранить для подробного разбора.': 'All details received from the car. You can save them for closer inspection.', 'Выберите приложение': 'Select an app', 'Найдите приложение выше и нажмите «Получить сведения».': 'Find an app above and select Get details.', 'Экран {number}': 'Display {number}', 'Приложение найдено': 'App found', 'Ожидает обновления': 'Waiting for refresh', 'Автомобиль не сообщил, что открыто на этом экране.': 'The car did not report what is open on this display.', 'Обновлено в {time}': 'Updated at {time}', 'Ещё не обновлялось': 'Not refreshed yet', 'Готово к записи': 'Ready to record', 'Подготавливаем запись…': 'Preparing recording…', 'Нажмите кнопку на руле · осталось {seconds} с': 'Press the steering wheel button · {seconds} s remaining', 'Получаем записанные сообщения…': 'Reading recorded messages…', 'Группируем найденные сообщения…': 'Grouping recorded messages…', 'Запись завершена': 'Recording complete', 'Запись отменена': 'Recording cancelled', 'Не удалось завершить запись': 'Recording could not be completed', 'Записать ещё раз': 'Record again', 'Обработано сообщений: {count}. Одно нажатие может создавать несколько сообщений.': 'Messages processed: {count}. A single button press can produce several messages.', 'Остановить': 'Stop', 'Продолжить прокрутку': 'Resume scrolling', 'Запись идёт · просмотр на паузе': 'Recording · scrolling paused', 'Наблюдение идёт': 'Running', 'Нет доступа': 'Access unavailable', 'Наблюдение прервано': 'Interrupted', 'Остановлено': 'Stopped', 'Найдено приложений: {count}': 'Apps found: {count}', 'Можно искать приложение или сразу указать его адрес.': 'Search for an app or enter its address directly.', 'Сведения ещё не запрошены': 'No details requested yet', 'Получаем сведения о приложении…': 'Reading app details…', 'Сведения получены': 'Details received', 'Не удалось получить сведения': 'Could not read details', 'Обновляем экраны…': 'Refreshing displays…', 'Нет открытого приложения': 'No app reported', 'Автомобиль не сообщил, что открыто на этом экране. Можно обновить данные ещё раз.': 'The car did not report what is open on this display. You can try refreshing again.', 'Перехват кнопки руля': 'Steering wheel capture', 'Запись начинается': 'Recording is starting', 'Дождитесь начала отсчёта и нажмите нужную кнопку на руле.': 'Wait for the countdown to start, then press the steering wheel button.', 'Нажмите кнопку на руле сейчас…': 'Press the steering wheel button now…', 'Не удалось обработать запись.': 'Could not process the recording.', 'Подходящих сообщений не найдено': 'No matching messages', 'Попробуйте ещё раз и нажмите кнопку после начала отсчёта. Некоторые кнопки автомобиля не показывают свои действия в доступном журнале.': 'Try again and press the button after the countdown starts. Some car buttons do not report their actions in the available log.', 'Запись пуста': 'The recording is empty', 'Автомобиль не передал сообщений во время записи. Можно попробовать ещё раз.': 'The car sent no messages during the recording. You can try again.', 'Сначала подключите устройство.': 'Connect a device first.', 'Дождитесь завершения или отмените текущее задание.': 'Wait for the current task to finish, or cancel it.', 'Автомобиль не разрешает читать нажатия кнопок.': 'The car does not allow access to button presses.', 'Ожидаем сообщения': 'Waiting for messages', 'Выполните нужное действие в автомобиле. Новые сообщения появятся здесь.': 'Perform the action in the car. New messages will appear here.', 'Совпадений не найдено': 'No matches found', 'Попробуйте изменить слова в фильтре. Полная запись остаётся доступна для сохранения.': 'Try changing the filter words. The full recording can still be saved.', 'Ищем приложения…': 'Searching apps…', 'Приложения не найдены. Попробуйте другую часть адреса.': 'No apps found. Try another part of the address.', 'Выберите пакет.': 'Select an app.', 'Не удалось обработать сведения.': 'Could not process the details.', 'Этот раздел отсутствует': 'This section is unavailable', 'В доступных сведениях приложение не сообщило об этих действиях. Полные сведения доступны в соседнем разделе.': 'The app did not report these actions in the available details. You can still view the full details in the next section.'})

EN.update({'Сначала выберите подходящий объект или заполните необходимые поля.': 'First choose a suitable item or fill in the required fields.', 'Проверяем параметры машины…': 'Checking vehicle compatibility…'})

EN.update({'Экраны': 'Displays', 'Кнопки руля': 'Steering wheel', 'Наблюдение': 'Live view', 'Сведения о приложении': 'App details', 'Открытие приложений': 'Apps opened', 'Нажатия и голос': 'Buttons and voice', 'Фоновые действия': 'Background actions', 'Вся запись': 'Full recording', 'Экраны приложения': 'App screens', 'Получаемые события': 'Received events', 'Полные сведения': 'Full details', 'Выберите, что хотите узнать: открытые экраны, действие кнопки или работу приложения.': "Choose what to inspect: open screens, a button action, or an app's activity.", 'Копировать эту запись': 'Copy this value', 'Скопировано': 'Copied', 'Что сейчас открыто?': 'What is open right now?', 'Узнайте, какое приложение сейчас видно на каждом экране автомобиля.': "See which app is currently visible on each of the car's displays.", 'Обновить экраны': 'Refresh displays', 'Показывает приложения, которые сейчас открыты на экранах автомобиля.': "Shows the apps currently open on the car's displays.", 'Приборная панель': 'Instrument cluster', 'Центральный экран': 'Centre display', 'Экран пассажира': 'Passenger display', 'Пока нет данных': 'No information yet', 'Подключите автомобиль и нажмите «Обновить экраны».': 'Connect the car and select Refresh displays.', 'Приложение': 'App', 'Адрес приложения в системе. Его можно скопировать для настройки или диагностики.': "The app's address in the system. You can copy it for setup or inspection.", 'Открытый экран приложения': 'Open app screen', 'Название той части приложения, которая сейчас видна.': 'The name of the part of the app currently on screen.', 'Полная запись': 'Full address', 'Подробности': 'Details', 'На экране открыто приложение': 'An app is open on this display', 'Приложение и экран': 'App and screen', 'Полная запись приложения и открытого экрана.': 'The full address of the app and its open screen.', 'Что делает кнопка руля?': 'What does this steering wheel button do?', 'Начните запись, нажмите нужную кнопку в автомобиле и дождитесь результата.': 'Start a recording, press the button in the car, and wait for the result.', '1 · Начните запись': '1 · Start recording', '2 · Нажмите кнопку на руле': '2 · Press the steering wheel button', '3 · Посмотрите результат': '3 · View the result', 'Начать запись на 6 секунд': 'Record for 6 seconds', 'Записывает события в течение шести секунд. Сразу после начала нажмите нужную кнопку на руле.': 'Records events for six seconds. Press the steering wheel button as soon as recording begins.', 'Отменить': 'Cancel', 'Останавливает текущую запись. Можно сразу начать новую.': 'Stops the current recording. You can start a new one straight away.', 'Сохранить запись': 'Save recording', 'Сохраняет все полученные сообщения, включая скрытые в других группах.': 'Saves all received messages, including those outside the other groups.', 'Открыть в Блокноте': 'Open in Notepad', 'Сохраняет запись на компьютер и открывает её в Блокноте.': 'Saves the recording to your computer and opens it in Notepad.', 'Какие приложения и экраны открылись во время записи.': 'Apps and screens that opened during the recording.', 'Сообщения о кнопках руля и голосовых командах.': 'Messages about steering wheel buttons and voice commands.', 'Действия, которые автомобиль выполняет без открытия нового окна.': 'Actions the car performs without opening a new window.', 'Все сообщения, полученные во время записи.': 'Every message received during the recording.', 'Здесь появится результат': 'Results will appear here', 'Нажмите «Начать запись» и затем нужную кнопку на руле.': 'Select Record for 6 seconds, then press the steering wheel button.', 'Наблюдение в реальном времени': 'Watch events live', 'Запустите нужный вид наблюдения и выполните действие в автомобиле.': 'Start the view you need, then perform an action in the car.', 'Показать сообщения с этими словами, например: музыка, голос': 'Show messages with these words, for example: music, voice', 'Введите одно или несколько слов через запятую. Остальные сообщения будут скрыты, но сохранятся в записи.': 'Enter one or more words separated by commas. Other messages are hidden but remain in the recording.', 'Сохранить наблюдение': 'Save live recording', 'Сохраняет сообщения из обоих видов наблюдения, включая скрытые фильтром.': 'Saves messages from both views, including those hidden by the filter.', 'События приложений': 'App activity', 'Показывает, что делают приложения во время вашей работы с экраном.': 'Shows what apps do while you use the display.', 'Нажатия кнопок': 'Button presses', 'Здесь видны только те нажатия, которые автомобиль передаёт системе.': 'Only button presses reported to the system by the car appear here.', 'Начать': 'Start', 'Начинает получать новые сообщения. Второй вид наблюдения работает независимо.': 'Starts receiving new messages. The other view runs independently.', 'Пауза прокрутки': 'Pause scrolling', 'Оставляет нужные строки на экране. Запись продолжает работать.': 'Keeps the current lines on screen. Recording continues.', 'Наблюдение ещё не началось': 'Not running yet', 'Нажмите «Начать», затем выполните нужное действие в автомобиле.': 'Select Start, then perform the action in the car.', 'Какие действия доступны приложению?': 'What can this app do?', 'Найдите установленное приложение или укажите его адрес, затем получите сведения.': 'Find an installed app or enter its address, then request its details.', 'Найти приложение по части адреса': 'Find an app by part of its address', 'Введите часть адреса приложения. Программа найдёт совпадения среди установленных приложений.': "Enter part of an app's address to search among installed apps.", 'Найти': 'Find', 'Выберите приложение или укажите его адрес': 'Select an app or enter its address', 'Например: com.voyah.music': 'For example: com.voyah.music', 'Получить сведения': 'Get details', 'Показывает доступные экраны приложения и действия, на которые оно реагирует.': "Shows the app's available screens and the actions it responds to.", 'Сохранить': 'Save', 'Сохраняет все сведения о выбранном приложении на компьютер.': 'Saves all details about the selected app to your computer.', 'Экраны, которые могут открываться внутри приложения.': 'Screens that can open within this app.', 'События, после которых приложение может выполнять действия.': 'Events that can trigger actions in this app.', 'Действия приложения, которые выполняются без открытия окна.': 'App actions that run without opening a window.', 'Все сведения, полученные от автомобиля. Их можно сохранить для подробного разбора.': 'All details received from the car. You can save them for closer inspection.', 'Выберите приложение': 'Select an app', 'Найдите приложение выше и нажмите «Получить сведения».': 'Find an app above and select Get details.', 'Экран {number}': 'Display {number}', 'Приложение найдено': 'App found', 'Ожидает обновления': 'Waiting for refresh', 'Автомобиль не сообщил, что открыто на этом экране.': 'The car did not report what is open on this display.', 'Обновлено в {time}': 'Updated at {time}', 'Ещё не обновлялось': 'Not refreshed yet', 'Готово к записи': 'Ready to record', 'Подготавливаем запись…': 'Preparing recording…', 'Нажмите кнопку на руле · осталось {seconds} с': 'Press the steering wheel button · {seconds} s remaining', 'Получаем записанные сообщения…': 'Reading recorded messages…', 'Группируем найденные сообщения…': 'Grouping recorded messages…', 'Запись завершена': 'Recording complete', 'Запись отменена': 'Recording cancelled', 'Не удалось завершить запись': 'Recording could not be completed', 'Записать ещё раз': 'Record again', 'Обработано сообщений: {count}. Одно нажатие может создавать несколько сообщений.': 'Messages processed: {count}. A single button press can produce several messages.', 'Остановить': 'Stop', 'Продолжить прокрутку': 'Resume scrolling', 'Запись идёт · просмотр на паузе': 'Recording · scrolling paused', 'Наблюдение идёт': 'Running', 'Нет доступа': 'Access unavailable', 'Наблюдение прервано': 'Interrupted', 'Остановлено': 'Stopped', 'Найдено приложений: {count}': 'Apps found: {count}', 'Можно искать приложение или сразу указать его адрес.': 'Search for an app or enter its address directly.', 'Сведения ещё не запрошены': 'No details requested yet', 'Получаем сведения о приложении…': 'Reading app details…', 'Сведения получены': 'Details received', 'Не удалось получить сведения': 'Could not read details', 'Обновляем экраны…': 'Refreshing displays…', 'Нет открытого приложения': 'No app reported', 'Автомобиль не сообщил, что открыто на этом экране. Можно обновить данные ещё раз.': 'The car did not report what is open on this display. You can try refreshing again.', 'Перехват кнопки руля': 'Steering wheel capture', 'Запись начинается': 'Recording is starting', 'Дождитесь начала отсчёта и нажмите нужную кнопку на руле.': 'Wait for the countdown to start, then press the steering wheel button.', 'Нажмите кнопку на руле сейчас…': 'Press the steering wheel button now…', 'Не удалось обработать запись.': 'Could not process the recording.', 'Подходящих сообщений не найдено': 'No matching messages', 'Попробуйте ещё раз и нажмите кнопку после начала отсчёта. Некоторые кнопки автомобиля не показывают свои действия в доступном журнале.': 'Try again and press the button after the countdown starts. Some car buttons do not report their actions in the available log.', 'Запись пуста': 'The recording is empty', 'Автомобиль не передал сообщений во время записи. Можно попробовать ещё раз.': 'The car sent no messages during the recording. You can try again.', 'Сначала подключите устройство.': 'Connect a device first.', 'Дождитесь завершения или отмените текущее задание.': 'Wait for the current task to finish, or cancel it.', 'Автомобиль не разрешает читать нажатия кнопок.': 'The car does not allow access to button presses.', 'Ожидаем сообщения': 'Waiting for messages', 'Выполните нужное действие в автомобиле. Новые сообщения появятся здесь.': 'Perform the action in the car. New messages will appear here.', 'Совпадений не найдено': 'No matches found', 'Попробуйте изменить слова в фильтре. Полная запись остаётся доступна для сохранения.': 'Try changing the filter words. The full recording can still be saved.', 'Ищем приложения…': 'Searching apps…', 'Приложения не найдены. Попробуйте другую часть адреса.': 'No apps found. Try another part of the address.', 'Выберите пакет.': 'Select an app.', 'Не удалось обработать сведения.': 'Could not process the details.', 'Этот раздел отсутствует': 'This section is unavailable', 'В доступных сведениях приложение не сообщило об этих действиях. Полные сведения доступны в соседнем разделе.': 'The app did not report these actions in the available details. You can still view the full details in the next section.'})

EN.update({'1. Начните запись':'1. Start recording', '2. Нажмите кнопку руля':'2. Press the steering button', '3. Посмотрите результат':'3. Read the result', '6 секунд':'6 seconds', '{seconds} с':'{seconds} s', 'Время записи':'Recording time'})

class UiTokens:
    background = '#121417'
    surface = '#1C1F26'
    raised = '#232A34'
    accent = '#00B4D8'
    text = '#EDF2F7'
    secondary = '#B3BECD'
    radius = 12


STYLE = """
QWidget { background: #121417; color: #EDF2F7; font-family: 'Segoe UI'; font-size: 11pt; }
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget { background: #121417; }
QFrame#card, QFrame#catalogCard, QFrame#header, QFrame#operationDock { background: #1C1F26; border: 1px solid #303846; border-radius: 12px; }
QFrame#catalogCard[selected='true'] { border: 2px solid #00B4D8; background: #20323C; }
QFrame#innerCard { background: #171D25; border: 1px solid #303846; border-radius: 12px; }
QFrame#innerCard QLabel { background: transparent; }
QLabel#muted, QLabel#fieldLabel { color: #B3BECD; background: transparent; }
QLabel#statusChip { color: #A1EDFD; background: #203842; border-radius: 12px; padding: 4px 8px; }
QToolButton { padding: 0; }
QFrame#card QLabel, QFrame#catalogCard QLabel, QFrame#header QLabel, QFrame#operationDock QLabel, QFrame#sidebarPanel QLabel { background: transparent; }
QWidget#disclosureContent, QFrame#disclosure { background: transparent; border: 0; }
QFrame#sidebarPanel { background: #171B21; border: 1px solid #29313D; border-radius: 12px; }
QLabel#title { font-size: 20pt; font-weight: 700; }
QLabel#subtitle, QLabel#hint { color: #B3BECD; background: transparent; }
QLabel#section { font-size: 14pt; font-weight: 600; background: transparent; }
QLabel#eyebrow { color: #00B4D8; font-size: 9pt; font-weight: 600; background: transparent; }
QLabel#countdown { font-size: 32pt; font-weight: 700; color: #00B4D8; background: transparent; }
QLabel#badge { color: #A1EDFD; background: #203842; border-radius: 12px; padding: 6px 12px; }
QPushButton, QToolButton { background: #28313D; border: 1px solid #3B4655; border-radius: 12px; padding: 8px 14px; min-height: 26px; }
QPushButton:hover, QToolButton:hover { background: #344152; border-color: #00B4D8; }
QPushButton:pressed, QToolButton:pressed { background: #164C5B; }
QPushButton:disabled, QToolButton:disabled { color: #8491A3; background: #212730; border-color: #303846; }
QPushButton[accent='true'] { background: #00B4D8; color: #071C24; font-weight: 600; }
QPushButton[danger='true'], QToolButton[danger='true'] { color: #FFA4AA; border-color: #80515C; }
QLineEdit, QComboBox, QSpinBox { background: #151A21; border: 1px solid #3B4655; border-radius: 12px; padding: 8px 12px; min-height: 26px; selection-background-color: #126078; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #00B4D8; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: #8491A3; border-color: #303846; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox::down-arrow { image: none; border: 0; width: 0; height: 0; }
QComboBox QAbstractItemView { background: #232A34; color: #EDF2F7; selection-background-color: #164F60; border: 1px solid #48556A; border-radius: 12px; padding: 8px; outline: 0; }
QComboBox QAbstractItemView::item { min-height: 44px; padding: 0 12px; border-radius: 12px; }
QTabWidget::pane { border: 0; padding-top: 16px; }
QTabBar::tab { background: #1C1F26; color: #B3BECD; padding: 12px 16px; border-radius: 12px; margin-right: 8px; }
QTabBar::tab:selected { color: #A1EDFD; background: #203842; }
QTabBar::tab:hover { background: #28313D; }
QPlainTextEdit { background: #10151B; border: 1px solid #303846; border-radius: 12px; padding: 12px; font-family: Consolas; font-size: 10pt; selection-background-color: #126078; }
QTableWidget, QListWidget { background: #181D24; alternate-background-color: #1E252E; border: 1px solid #303846; border-radius: 12px; gridline-color: #2D3542; selection-background-color: #174F60; outline: 0; }
QListWidget::item { min-height: 44px; padding: 0 12px; border-radius: 12px; }
QListWidget#sidebar { background: transparent; border: 0; padding: 0; }
QListWidget#sidebar::item { padding: 8px 12px; min-height: 32px; border-radius: 12px; }
QListWidget#sidebar::item:selected { background: #203B46; color: #A1EDFD; }
QListWidget#sidebar::item:hover { background: #232D38; }
QHeaderView::section { background: #232A34; border: 0; padding: 12px; color: #B3BECD; font-weight: 600; }
QCheckBox { spacing: 12px; background: transparent; min-height: 32px; }
QCheckBox::indicator { width: 20px; height: 20px; border: 1px solid #59677C; border-radius: 6px; background: #151A21; }
QCheckBox::indicator:checked { background: #00B4D8; border-color: #A1EDFD; }
QPushButton[accent='true']:disabled { color:#8491A3; background:#212730; border-color:#303846; }
QLineEdit[technical='true'] { font-family:Consolas; font-size:10pt; }
QProgressBar { border: 0; border-radius: 6px; background: #303B49; text-align: center; min-height: 12px; color: #EDF2F7; }
QProgressBar::chunk { background: #00B4D8; border-radius: 6px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 0; }
QScrollBar::handle:vertical { background: #455166; border-radius: 5px; min-height: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0 4px; }
QScrollBar::handle:horizontal { background: #455166; border-radius: 5px; min-width: 32px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QMenu { background: #232A34; border: 1px solid #48556A; border-radius: 12px; padding: 8px; }
QMenu::item { padding: 12px 28px 12px 16px; border-radius: 12px; }
QMenu::item:selected { background: #164F60; }
QMenu::item:disabled { color: #8491A3; }
QMenu::separator { height: 1px; background: #3B4655; margin: 8px; }
QSplitter::handle { background: #303846; height: 4px; width: 4px; }
QToolTip { background: #232A34; color: #EDF2F7; border: 1px solid #48556A; border-radius: 12px; padding: 12px; }
QDialog, QMessageBox { background: #121417; }
QFrame#dropZone { background: #182B34; border: 2px dashed #367083; border-radius: 12px; }
"""

_ICON_CACHE = {}

def ui_icon(name, color=None, size=20):
    """Resource-free, consistent 24-unit outline icons, including high-DPI pixmaps."""
    color = color or UiTokens.secondary
    key = (name, color, size)
    if key in _ICON_CACHE: return _ICON_CACHE[key]
    pix = QPixmap(size * 3, size * 3); pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.scale(size * 3 / 24, size * 3 / 24)
    p.setPen(QPen(QColor(color), 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)); p.setBrush(Qt.BrushStyle.NoBrush)
    def line(a,b,c,d): p.drawLine(QPointF(a,b), QPointF(c,d))
    def rect(x,y,w,h,r=2): p.drawRoundedRect(QRectF(x,y,w,h),r,r)
    def path(points):
        q=QPainterPath(); q.moveTo(*points[0])
        for pt in points[1:]: q.lineTo(*pt)
        p.drawPath(q)
    if name in ('monitor','camera','recents'):
        rect(3,4,18,13); line(12,17,12,21); line(8,21,16,21)
        if name=='camera': p.drawEllipse(QPointF(12,10),3,3)
        if name=='recents': line(7,8,17,8); line(7,12,14,12)
    elif name in ('apps','catalog'):
        for x,y in ((4,4),(14,4),(4,14),(14,14)): rect(x,y,6,6,1.5)
    elif name=='keyboard':
        rect(2,5,20,14); line(8,16,16,16)
        for y in (9,12):
            for x in (6,10,14,18): line(x,y,x+.2,y)
    elif name in ('folder','file','apk','archive'):
        if name=='folder': path([(3,19),(3,5),(9,5),(11,8),(21,8),(21,19),(3,19)])
        else:
            path([(5,21),(5,3),(14,3),(19,8),(19,21),(5,21)]); path([(14,3),(14,8),(19,8)])
            if name=='apk': path([(9,14),(12,17),(15,14)])
            elif name=='archive': line(11,10,13,10); line(11,13,13,13); line(11,16,13,16)
    elif name in ('upload','download','install','undo','back','chevron'):
        if name in ('back','undo'): path([(10,5),(4,11),(10,17)]); line(4,11,19,11)
        elif name=='chevron': path([(6,9),(12,15),(18,9)])
        else:
            line(12,3,12,16)
            if name=='upload': path([(7,8),(12,3),(17,8)])
            else: path([(7,11),(12,16),(17,11)])
            path([(4,16),(4,21),(20,21),(20,16)])
    elif name in ('search','eye'):
        if name=='search': p.drawEllipse(QPointF(10,10),6,6); line(14.5,14.5,21,21)
        else: path([(2,12),(7,6),(17,6),(22,12),(17,18),(7,18),(2,12)]); p.drawEllipse(QPointF(12,12),3,3)
    elif name in ('play','stop','check','add','delete','rename','edit'):
        if name=='play': path([(7,4),(20,12),(7,20),(7,4)])
        elif name=='stop': rect(5,5,14,14)
        elif name=='check': path([(4,12),(9,17),(20,6)])
        elif name=='add': line(12,4,12,20); line(4,12,20,12)
        elif name=='delete': line(3,6,21,6); path([(6,6),(7,21),(17,21),(18,6)]); path([(9,6),(9,3),(15,3),(15,6)]); line(10,10,10,17); line(14,10,14,17)
        else: path([(4,20),(5,15),(17,3),(21,7),(9,19),(4,20)]); line(15,5,19,9)
    elif name in ('copy','save'):
        if name=='copy': rect(8,8,13,13); path([(16,5),(16,3),(3,3),(3,16),(5,16)])
        else: path([(4,3),(17,3),(21,7),(21,21),(3,21),(3,3),(4,3)]); rect(7,3,9,6,0); rect(7,14,10,7,0)
    elif name in ('info','globe','gauge','steering','recovery','refresh','settings'):
        p.drawEllipse(QPointF(12,12),9,9)
        if name=='info': line(12,10,12,17); line(12,7,12,7.2)
        elif name=='globe': p.drawEllipse(QRectF(8,3,8,18)); line(3,12,21,12)
        elif name in ('gauge','steering'): line(12,12,17,7); line(3,12,21,12); line(12,12,12,21)
        elif name in ('refresh','recovery'): path([(16,2),(20,4),(18,8)]); path([(8,22),(4,20),(6,16)])
        else:
            p.drawEllipse(QPointF(12,12),3,3)
            for x,y,x2,y2 in ((12,1,12,4),(12,20,12,23),(1,12,4,12),(20,12,23,12)): line(x,y,x2,y2)
    elif name in ('wifi','usb','link'):
        if name=='wifi':
            p.drawArc(QRectF(2,4,20,18),40*16,100*16); p.drawArc(QRectF(6,8,12,12),40*16,100*16); p.drawEllipse(QPointF(12,18),1,1)
        elif name=='usb': line(12,3,12,21); path([(8,7),(12,3),(16,7)]); path([(6,10),(6,14),(12,17),(18,14),(18,10)])
        else: rect(3,6,11,7,3); rect(10,11,11,7,3); line(9,10,15,14)
    elif name in ('volume','mic','shield','sliders','terminal','pulse','home','more'):
        if name=='volume': path([(3,10),(7,10),(12,5),(12,19),(7,14),(3,14),(3,10)]); p.drawArc(QRectF(10,4,10,16),-70*16,140*16)
        elif name=='mic': rect(9,3,6,13,3); path([(5,11),(5,15),(8,19),(16,19),(19,15),(19,11)]); line(12,19,12,22)
        elif name=='shield': path([(12,2),(21,6),(19,16),(12,22),(5,16),(3,6),(12,2)])
        elif name=='sliders':
            for y,x in ((5,8),(12,16),(19,10)): line(3,y,21,y); rect(x-2,y-2,4,4,1)
        elif name=='terminal': path([(4,6),(10,12),(4,18)]); line(12,18,21,18)
        elif name=='pulse': path([(2,12),(7,12),(10,5),(14,19),(17,12),(22,12)])
        elif name=='home': path([(2,11),(12,3),(22,11)]); path([(5,9),(5,21),(19,21),(19,9)]); rect(10,14,4,7,0)
        else:
            for x in (5,12,19): p.drawEllipse(QPointF(x,12),1,1)
    else: rect(4,4,16,16); line(8,12,16,12)
    p.end(); pix.setDevicePixelRatio(3); result=QIcon(pix); _ICON_CACHE[key]=result; return result


class MotionController(QObject):
    def __init__(self, main):
        super().__init__(main); self.main=main
        self.reduced = str(main.settings.value('ui.reduce_motion','false')).lower()=='true'
        self.system_enabled=True
        if sys.platform=='win32':
            try:
                value=ctypes.c_int(1)
                if ctypes.windll.user32.SystemParametersInfoW(0x1042,0,ctypes.byref(value),0): self.system_enabled=bool(value.value)
            except (AttributeError,OSError): pass
    @property
    def enabled(self): return self.system_enabled and not self.reduced and not self.main.smoke
    def set_reduced(self,value): self.reduced=bool(value); self.main.settings.setValue('ui.reduce_motion',self.reduced)


def motion_enabled(widget):
    root=widget.window()
    main=getattr(widget,'main',None) or getattr(root,'main',None) or root
    return bool(getattr(getattr(main,'motion',None),'enabled',False))


def update_help(widget, main, reason=None):
    if reason is not None: widget.setProperty('disabled_reason',reason)
    help_key=widget.property('help_key') or ''
    text=main.t(help_key) if help_key else ''
    why=widget.property('disabled_reason') or ''
    if why: text=(text+'\n\n' if text else '')+main.t(why)
    widget.setToolTip(text)


NativePushButton=QPushButton
class VoyahButton(NativePushButton):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self._hover=0.; self._local_enabled=True; self._policy_enabled=True
        self.setMinimumHeight(44); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.animation=QVariantAnimation(self); self.animation.setDuration(110); self.animation.valueChanged.connect(self._hover_changed)
    def _hover_changed(self,value): self._hover=float(value); self.update()
    def _animate(self,value):
        self.animation.stop()
        if motion_enabled(self): self.animation.setStartValue(self._hover); self.animation.setEndValue(value); self.animation.start()
        else: self._hover=value; self.update()
    def enterEvent(self,event): super().enterEvent(event); self._animate(1.)
    def leaveEvent(self,event): super().leaveEvent(event); self._animate(0.)
    def setEnabled(self,value):
        self._local_enabled=bool(value); super().setEnabled(self._local_enabled and self._policy_enabled)
    def setPolicyEnabled(self,value,main=None):
        self._policy_enabled=bool(value); super().setEnabled(self._local_enabled and self._policy_enabled)
        if main: update_help(self,main,'' if value else 'Отключено администратором')
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent=bool(self.property('accent')); danger=bool(self.property('danger'))
        base=QColor('#00B4D8' if accent else '#28313D'); hover=QColor('#34CBE8' if accent else '#344152')
        if not self.isEnabled(): base=hover=QColor('#212730')
        if self.isDown(): base=hover=QColor('#138BA5' if accent else '#164C5B')
        color=QColor.fromRgbF(*(base.getRgbF()[i]*(1-self._hover)+hover.getRgbF()[i]*self._hover for i in range(3)))
        border=QColor('#80515C' if danger else '#3B4655')
        if (self.hasFocus() or self._hover>.3) and self.isEnabled(): border=QColor('#00B4D8')
        p.setPen(QPen(border,1)); p.setBrush(color); p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),12,12)
        option=QStyleOptionButton(); self.initStyleOption(option); option.rect=self.rect().adjusted(12,0,-12,0)
        text_color=QColor('#8491A3' if not self.isEnabled() else '#071C24' if accent else '#FFA4AA' if danger else '#EDF2F7')
        option.palette.setColor(QPalette.ColorRole.ButtonText,text_color)
        self.style().drawControl(QStyle.ControlElement.CE_PushButtonLabel,option,p,self)
    def sizeHint(self):
        result=super().sizeHint(); return QSize(result.width()+8,max(44,result.height()))

QPushButton=VoyahButton


def rounded_mask(widget):
    path=QPainterPath(); path.addRoundedRect(QRectF(widget.rect()),12,12)
    widget.setMask(QRegion(path.toFillPolygon().toPolygon()))


def animate_popup(widget,owner):
    rounded_mask(widget)
    if not motion_enabled(owner): widget.setWindowOpacity(1); return
    old=getattr(owner,'_popup_animation',None)
    if old: old.stop()
    target=widget.pos(); screen=widget.screen().availableGeometry()
    group=QParallelAnimationGroup(owner)
    opacity=QPropertyAnimation(widget,b'windowOpacity',group); opacity.setDuration(160); opacity.setStartValue(0.); opacity.setEndValue(1.)
    position=QPropertyAnimation(widget,b'pos',group); position.setDuration(160); position.setEasingCurve(QEasingCurve.Type.OutCubic)
    start=QPoint(target.x(),min(target.y()+6,screen.bottom()-widget.height()+1)); position.setStartValue(start); position.setEndValue(target)
    owner._popup_animation=group; group.start()


NativeComboBox=QComboBox
class VoyahComboBox(NativeComboBox):
    """Qt's accessible native selection model, with one rounded animated popup."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.setMinimumHeight(44); self.setMaxVisibleItems(8)
        self.setSizeAdjustPolicy(NativeComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)
    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#B3BECD' if self.isEnabled() else '#8491A3'),1.6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        x,y=self.width()-17,self.height()/2
        p.drawLine(QPointF(x-4,y-2),QPointF(x,y+2)); p.drawLine(QPointF(x,y+2),QPointF(x+4,y-2))
    def showPopup(self):
        super().showPopup(); popup=self.view().window()
        popup.setStyleSheet('QFrame { background:#232A34; border:1px solid #48556A; border-radius:12px; } QListView { border:0; padding:8px; background:#232A34; } QListView::item { min-height:44px; padding:0 12px; border-radius:12px; }')
        area=self.screen().availableGeometry(); below=self.mapToGlobal(QPoint(0,self.height()+8)); above=self.mapToGlobal(QPoint(0,-popup.height()-8))
        y=below.y() if below.y()+popup.height()<=area.bottom()+1 else above.y()
        popup.move(max(area.left(),min(below.x(),area.right()-popup.width()+1)),max(area.top(),min(y,area.bottom()-popup.height()+1)))
        animate_popup(popup,self)
    def hidePopup(self):
        if getattr(self,'_popup_animation',None): self._popup_animation.stop()
        self.view().window().setWindowOpacity(1); super().hidePopup()

QComboBox=VoyahComboBox


NativeMenu=QMenu
class RoundedMenu(NativeMenu):
    def addMenu(self,*args):
        if len(args)==1 and isinstance(args[0],NativeMenu): return super().addMenu(args[0])
        title=args[-1]; submenu=RoundedMenu(title,self)
        if len(args)==2: submenu.setIcon(args[0])
        super().addMenu(submenu); return submenu
    def showEvent(self,event): super().showEvent(event); animate_popup(self,self.parentWidget() or self)
    def hideEvent(self,event):
        owner=self.parentWidget() or self
        if getattr(owner,'_popup_animation',None): owner._popup_animation.stop()
        self.setWindowOpacity(1); super().hideEvent(event)
QMenu=RoundedMenu


class SurfaceCard(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent); self.setObjectName('card'); self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)


class ResponsiveGrid(QWidget):
    def __init__(self,min_card_width=280,max_columns=3,parent=None):
        super().__init__(parent); self.min_card_width=min_card_width; self.max_columns=max_columns; self.widgets=[]; self.columns=0
        self.grid=QGridLayout(self); self.grid.setContentsMargins(0,0,0,0); self.grid.setSpacing(16); self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
    def minimumSizeHint(self): return QSize(0,0)
    def sizeHint(self):
        return QSize(self.min_card_width,self.grid.sizeHint().height())
    def addWidget(self,widget): self.widgets.append(widget); self.reflow()
    def addCard(self,widget): self.addWidget(widget)
    def count(self): return len(self.widgets)
    def itemAt(self,index): return QWidgetItem(self.widgets[index]) if 0<=index<len(self.widgets) else None
    def takeAt(self,index):
        if not 0<=index<len(self.widgets): return None
        widget=self.widgets.pop(index); self.grid.removeWidget(widget); self.reflow(); return QWidgetItem(widget)
    def clear(self):
        while self.widgets:
            widget=self.widgets.pop(); self.grid.removeWidget(widget); widget.hide(); widget.deleteLater()
        self.columns=0
    def resizeEvent(self,event): super().resizeEvent(event); self.reflow()
    def reflow(self):
        cols=max(1,min(self.max_columns,(max(1,self.width())+16)//(self.min_card_width+16)))
        while self.grid.count(): self.grid.takeAt(0)
        for col in range(self.max_columns): self.grid.setColumnStretch(col,1 if col<cols else 0)
        for i,widget in enumerate(self.widgets): self.grid.addWidget(widget,i//cols,i%cols,Qt.AlignmentFlag.AlignTop)
        self.columns=cols


class EmptyState(QFrame):
    def __init__(self,title,description,icon='info',parent=None):
        super().__init__(parent); self.setObjectName('card'); row=QVBoxLayout(self); row.setContentsMargins(24,24,24,24); row.setSpacing(12)
        emblem=QLabel(); emblem.setPixmap(ui_icon(icon,UiTokens.accent,32).pixmap(32,32)); row.addWidget(emblem)
        self.title=QLabel(title); self.title.setObjectName('section'); self.title.setWordWrap(True); row.addWidget(self.title)
        self.description=QLabel(description); self.description.setObjectName('hint'); self.description.setWordWrap(True); row.addWidget(self.description)


class Disclosure(QFrame):
    def __init__(self,title,main,parent=None,expanded=False):
        super().__init__(parent); self.main=main; self.setObjectName('disclosure'); self.expanded=expanded
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(8)
        self.toggle=VoyahButton(title); self.toggle.setIcon(ui_icon('chevron')); self.toggle.setCheckable(True); self.toggle.setChecked(expanded); self.toggle.clicked.connect(self.setExpanded); outer.addWidget(self.toggle,0,Qt.AlignmentFlag.AlignLeft)
        self.content=QWidget(); self.content.setObjectName('disclosureContent'); self.body=QVBoxLayout(self.content); self.body.setContentsMargins(0,4,0,0); self.body.setSpacing(12); outer.addWidget(self.content)
        self.content.setVisible(expanded); self.content.setMaximumHeight(16777215 if expanded else 0)
        self.animation=QPropertyAnimation(self.content,b'maximumHeight',self); self.animation.setDuration(200); self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic); self.animation.finished.connect(self._settled)
    def setTitle(self,title): self.toggle.setText(title)
    def setExpanded(self,expanded,animate=True):
        self.expanded=bool(expanded); self.toggle.setChecked(self.expanded); self.animation.stop()
        if animate and self.main.motion.enabled:
            start=self.content.height() if self.content.isVisible() else 0; self.content.setVisible(True)
            self.animation.setStartValue(start); self.animation.setEndValue(self.content.sizeHint().height() if expanded else 0); self.animation.start()
        else: self._settled()
    def _settled(self): self.content.setMaximumHeight(16777215 if self.expanded else 0); self.content.setVisible(self.expanded)


class AnimatedStack(QStackedWidget):
    def __init__(self,main): super().__init__(); self.main=main; self.fade=None
    def setCurrentIndex(self,index):
        if index==self.currentIndex(): return
        if self.fade:
            self.fade.stop()
            if getattr(self,'faded_widget',None): self.faded_widget.setGraphicsEffect(None)
        super().setCurrentIndex(index)
        current=self.currentWidget()
        if current and self.main.motion.enabled:
            effect=QGraphicsOpacityEffect(current); current.setGraphicsEffect(effect); self.faded_widget=current
            self.fade=QPropertyAnimation(effect,b'opacity',self); self.fade.setDuration(140); self.fade.setStartValue(.35); self.fade.setEndValue(1.)
            self.fade.finished.connect(lambda w=current:w.setGraphicsEffect(None)); self.fade.start()


class StatusDot(QLabel):
    def __init__(self): super().__init__(); self.setFixedSize(14,14); self.state_color='#F17783'
    def setStyleSheet(self,style):
        match=re.search(r'color:\s*(#[\da-fA-F]{6})',style)
        if match: self.state_color=match.group(1); self.update()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(self.state_color)); p.drawEllipse(QRectF(2,2,10,10))


ACTION_HELP = {
 'Подключить':'Подключает выбранный автомобиль. Для первого соединения по кабелю подтвердите запрос на экране автомобиля.',
 'Обновить':'Проверяет, какие автомобили сейчас доступны для подключения.',
 'Назад':'Возвращает на предыдущий экран в автомобиле.',
 'Домой':'Открывает главный экран автомобиля.',
 'Недавние':'Показывает недавно открытые приложения в автомобиле.',
 'Скриншот':'Сохраняет снимок экрана автомобиля на компьютер.',
 'Отменить задание':'Останавливает текущее действие. Уже выполненные изменения могут сохраниться.',
 'Выбрать ADB':'Позволяет выбрать файл средства связи с автомобилем на вашем компьютере.',
 'Встроенный ADB':'Использует средство связи, которое уже входит в программу.',
 'Перезапуск ADB':'Перезапускает связь с автомобилем, если подключение перестало отвечать.',
 'USB → Wi-Fi :5555':'Подготавливает подключённый по кабелю автомобиль к работе через Wi-Fi и показывает его адреса.',
 'Расширенный режим':'Открывает действия для расширенного доступа. Некоторые прошивки не разрешают такой доступ.',
 'Перезагрузка':'Показывает варианты перезапуска автомобиля. Каждое действие требует подтверждения.',
 'Открыть журнал':'Открывает сохранённую запись действий и ошибок программы.',
 'О приложении':'Показывает версию программы и сведения о её работе.',
 'Настройки подключения и устройства':'Показывает способ подключения, адрес автомобиля и дополнительные действия.',
 'Журнал операций':'Показывает подробную запись выполненных действий и ответов автомобиля.',
}


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
    w.verticalHeader().hide(); w.verticalHeader().setDefaultSectionSize(44); w.horizontalHeader().setStretchLastSection(True)
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
        self.bindings.append((obj, key, method)); getattr(obj, method)(self.t(key))
        if method=='setToolTip': obj.setProperty('help_key',key); update_help(obj,self.main)
        return obj

    def button(self, key, callback, accent=False, danger=False, icon=None, help_key=None):
        w = self.bind(QPushButton(), key); w.clicked.connect(callback)
        if getattr(callback, 'feature_id', None): w.setProperty('feature', callback.feature_id)
        w.setProperty('accent',accent); w.setProperty('danger',danger)
        if icon: w.setIcon(ui_icon(icon,'#071C24' if accent else None))
        w.setProperty('help_key',help_key or ACTION_HELP.get(key,key)); update_help(w,self.main)
        return w

    def label(self, key, style=None):
        w = self.bind(QLabel(), key)
        if style: w.setObjectName(style)
        w.setWordWrap(True)
        return w

    def edit(self, placeholder=''):
        w = QLineEdit()
        if placeholder: self.bind(w, placeholder, 'setPlaceholderText')
        return w

    def card(self, title, description=''):
        frame=SurfaceCard(); layout=QVBoxLayout(frame); layout.setContentsMargins(16,16,16,16); layout.setSpacing(12); layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        group={'Масштаб и дисплеи':'tweaks.dpi','Аудиофокус и разрешения':'tweaks.permissions','Сеть и система':'tweaks.network'}.get(title)
        if group: frame.setProperty('feature',group)
        if title: layout.addWidget(self.label(title,'section'))
        if description: layout.addWidget(self.hint(description))
        self.layout.addWidget(frame); return layout

    def row(self, layout, *widgets):
        stretch=any(isinstance(w,(QLineEdit,QComboBox,QSpinBox)) for w in widgets)
        row=QHBoxLayout() if stretch else FlowLayout(); row.setSpacing(8)
        for w in widgets:
            if isinstance(w,QWidget):
                if stretch: row.addWidget(w,1 if isinstance(w,QLineEdit) else 0)
                else: row.addWidget(w)
            elif isinstance(w,int): row.addStretch(w)
        layout.addLayout(row); return row

    def retranslate(self):
        for obj,key,method in self.bindings:
            try:
                getattr(obj,method)(self.t(key))
                if obj.property('help_key'): update_help(obj,self.main)
            except RuntimeError: continue

    def hint(self,text):
        w=self.label(text,'hint'); w.setWordWrap(True); return w

    def disclosure(self,title,layout,expanded=False):
        w=Disclosure(self.t(title),self.main,expanded=expanded); self.bind(w,title,'setTitle'); layout.addWidget(w); return w

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
SECTION_NAMES = {'catalog':'Каталог приложений','installer':'APK с ПК','keyboards':'Клавиатуры','inspector':'Инспектор','files':'Файлы','apps':'Установленные приложения','tweaks':'Твики','terminal':'Терминал'}
SECTION_HELP = {'catalog': 'Выберите готовое приложение — программа скачает его и установит в автомобиль.', 'installer': 'Выберите файлы на компьютере или перетащите их сюда для установки.', 'keyboards': 'Установите выбранную клавиатуру на оба экрана или верните штатную.', 'inspector': 'Узнайте, что открыто на экранах и какие события происходят в автомобиле.', 'files': 'Передавайте файлы между компьютером и памятью автомобиля.', 'apps': 'Запускайте приложения и управляйте тем, что уже установлено.', 'tweaks': 'Настройте размер элементов, звук и внешний вид. Здесь же доступны действия восстановления.', 'terminal': 'Для опытных: команды выполняются на выбранном автомобиле. Проверьте их перед запуском.'}
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
        self.motion=MotionController(self); self.build_ui(); self.retranslate(); self.catalog.changed.connect(self.apply_policy)
        self.admin_shortcut = QShortcut(QKeySequence('Ctrl+Shift+Alt+A'), self, activated=self.open_admin)
        available = QApplication.primaryScreen().availableGeometry(); self.setMinimumSize(min(820,available.width()-32),min(620,available.height()-32)); self.resize(min(1400, available.width()-32), min(940, available.height()-32))
        self.poll = QTimer(self); self.poll.timeout.connect(self.refresh_devices); self.poll.start(5000)
        QTimer.singleShot(100, self.startup)

    def t(self, text, **values): return tr(text, self.lang, **values)

    def bind(self, obj, key, method='setText'):
        self.binding.append((obj, key, method)); getattr(obj, method)(self.t(key))
        if method=='setToolTip': obj.setProperty('help_key',key); update_help(obj,self)
        return obj

    def button(self, key, fn, accent=False, icon=None, help_key=None):
        w = self.bind(QPushButton(), key); w.clicked.connect(fn)
        if getattr(fn,'feature_id',None): w.setProperty('feature',fn.feature_id)
        w.setProperty('accent',accent)
        if icon: w.setIcon(ui_icon(icon, '#071C24' if accent else None))
        w.setAccessibleName(self.t(key))
        w.setProperty('help_key',help_key or ACTION_HELP.get(key,key)); update_help(w,self)
        return w

    def build_ui(self):
        root=QWidget(); self.setCentralWidget(root); outer=QHBoxLayout(root); outer.setContentsMargins(16,16,16,16); outer.setSpacing(16)
        self.sidebar_panel=QFrame(); self.sidebar_panel.setObjectName('sidebarPanel'); self.sidebar_panel.setFixedWidth(240)
        side=QVBoxLayout(self.sidebar_panel); side.setContentsMargins(12,20,12,16); side.setSpacing(16)
        brand=QHBoxLayout(); logo=QLabel(); logo.setPixmap(make_icon().pixmap(36,36)); brand.addWidget(logo)
        self.brand_label=QLabel('VOYAH\nMANAGER'); self.brand_label.setStyleSheet('font-size:12pt;font-weight:700;letter-spacing:1px;'); brand.addWidget(self.brand_label,1); side.addLayout(brand)
        self.sidebar=QListWidget(); self.sidebar.setObjectName('sidebar'); self.sidebar.setSpacing(4); self.sidebar.setWordWrap(True); self.sidebar.setIconSize(QSize(22,22)); self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side.addWidget(self.sidebar,1)
        self.sidebar_version=QLabel('v'+VERSION); self.sidebar_version.setObjectName('subtitle'); side.addWidget(self.sidebar_version)
        self.about_button=self.button('О приложении',self.about,icon='info'); side.addWidget(self.about_button)
        outer.addWidget(self.sidebar_panel)
        right=QVBoxLayout(); right.setSpacing(16); outer.addLayout(right,1)
        header=QFrame(); header.setObjectName('header'); h=QVBoxLayout(header); h.setContentsMargins(16,12,16,12); h.setSpacing(12)
        row=QHBoxLayout(); row.setSpacing(12)
        self.status_dot=StatusDot(); row.addWidget(self.status_dot)
        status=QVBoxLayout(); status.setSpacing(2); self.vehicle_label=self.bind(QLabel(),'Ваш автомобиль'); self.vehicle_label.setStyleSheet('font-weight:600;background:transparent;'); status.addWidget(self.vehicle_label)
        self.connection_status=QLabel(); self.connection_status.setObjectName('subtitle'); self.connection_status.setWordWrap(True); status.addWidget(self.connection_status); row.addLayout(status,1)
        self.connect_btn=self.button('Подключить',self.connect_device,True,icon='link'); row.addWidget(self.connect_btn)
        self.connection_toggle=self.button('Настройки подключения и устройства',lambda:self.connection_disclosure.setExpanded(not self.connection_disclosure.expanded),icon='settings')
        self.connection_toggle.setText(''); self.connection_toggle.setFixedSize(44,44); row.addWidget(self.connection_toggle)
        self.nav_buttons=[]
        for key,code,icon in [('Назад',4,'back'),('Домой',3,'home'),('Недавние',187,'recents')]:
            button=self.button(key,lambda checked=False,c=code:self.keyevent(c),icon=icon); button.setProperty('icon_only',True); button.setText(''); button.setFixedSize(36,36); button.setMinimumHeight(36); row.addWidget(button); self.nav_buttons.append(button)
        shot=self.button('Скриншот',self.screenshot,icon='camera'); shot.setProperty('icon_only',True); shot.setText(''); shot.setFixedSize(36,36); shot.setMinimumHeight(36); row.addWidget(shot); self.nav_buttons.append(shot)
        self.language=QComboBox(); self.language.addItem('Русский','ru'); self.language.addItem('English','en'); self.language.setCurrentIndex(1 if self.lang=='en' else 0); self.language.setMinimumContentsLength(6); self.language.setFixedWidth(120); self.language.currentIndexChanged.connect(self.change_language); row.addWidget(self.language)
        h.addLayout(row)
        self.connection_disclosure=Disclosure('',self); self.connection_disclosure.toggle.hide(); self.connection_details=self.connection_disclosure.content
        details=self.connection_disclosure.body
        selection=QHBoxLayout(); self.mode=QComboBox(); self.mode.addItem('USB','usb'); self.mode.addItem('Wi-Fi','wifi'); self.mode.setFixedWidth(130); self.mode.currentIndexChanged.connect(self.mode_changed); selection.addWidget(self.mode)
        self.device_combo=QComboBox(); self.device_combo.setMinimumWidth(140); self.device_combo.currentIndexChanged.connect(self.device_selected); selection.addWidget(self.device_combo,1); selection.addWidget(self.button('Обновить',self.refresh_devices,icon='refresh')); details.addLayout(selection)
        self.ip=QLineEdit(self.settings.value('ip','')); self.ip.setPlaceholderText('192.168.1.100:5555')
        self.voyah_wifi=self.button('Voyah :5578',lambda:self.ip.setText('192.168.43.1:5578'),help_key='Подставляет адрес из отчёта установщика. Подходит только для прошивок с таким способом подключения.')
        self.wifi_row=QWidget(); address=QHBoxLayout(self.wifi_row); address.setContentsMargins(0,0,0,0); address.addWidget(self.ip,1); address.addWidget(self.voyah_wifi); details.addWidget(self.wifi_row)
        self.device_info=QLabel(); self.device_info.setObjectName('subtitle'); self.device_info.setWordWrap(True); details.addWidget(self.device_info)
        tools_row=FlowLayout(); tools_row.addWidget(self.button('USB → Wi-Fi :5555',self.usb_wifi,icon='wifi')); tools_row.addWidget(self.button('Выбрать ADB',self.choose_adb,icon='folder')); tools_row.addWidget(self.button('Встроенный ADB',self.use_bundled,icon='archive')); tools_row.addWidget(self.button('Перезапуск ADB',self.restart_adb,icon='refresh')); details.addLayout(tools_row)
        self.adb_label=QLabel(); self.adb_label.setObjectName('subtitle'); self.adb_label.setWordWrap(True); self.adb_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); details.addWidget(self.adb_label)
        access=FlowLayout(); self.root_button=self.button('Расширенный режим',self.root_menu,icon='shield'); access.addWidget(self.root_button); self.reboot_button=self.button('Перезагрузка',self.reboot_menu,icon='recovery'); access.addWidget(self.reboot_button)
        self.reduce_motion=self.bind(QCheckBox(),'Уменьшить анимацию'); self.reduce_motion.setChecked(self.motion.reduced or not self.motion.system_enabled); self.reduce_motion.toggled.connect(self.motion.set_reduced); self.reduce_motion.setProperty('help_key','Убирает плавные переходы и раскрытие меню. Все действия остаются доступными.'); access.addWidget(self.reduce_motion); details.addLayout(access)
        h.addWidget(self.connection_disclosure); right.addWidget(header)
        if self.demo:
            badge=self.bind(QLabel(),'Демонстрационный режим • команды имитируются'); badge.setStyleSheet('color:#F5CE7E;padding:8px 12px;background:#332D22;border-radius:12px;'); right.addWidget(badge)
        titles=QVBoxLayout(); titles.setSpacing(4); self.section_title=QLabel(); self.section_title.setObjectName('title'); titles.addWidget(self.section_title); self.section_description=QLabel(); self.section_description.setWordWrap(True); self.section_description.setObjectName('subtitle'); titles.addWidget(self.section_description); right.addLayout(titles)
        self.stack=AnimatedStack(self); self.pages={}; self.section_items={}; self.section_indices={}; self.group_items=[]
        factories={'catalog':CatalogPage,'installer':InstallerPage,'keyboards':KeyboardPage,'inspector':InspectorPage,'files':ExplorerPage,'apps':AppsPage,'tweaks':TweaksPage,'terminal':TerminalPage}
        groups=[('Приложения',['catalog','installer','keyboards']),('Автомобиль',['inspector','files','apps','tweaks']),('Для опытных',['terminal'])]
        icons={'catalog':'catalog','installer':'download','keyboards':'keyboard','inspector':'search','files':'folder','apps':'apps','tweaks':'sliders','terminal':'terminal'}
        for group,keys in groups:
            heading=QListWidgetItem(self.t(group)); heading.setFlags(Qt.ItemFlag.NoItemFlags); heading.setForeground(QColor('#8F9EB1')); heading.setSizeHint(QSize(180,32)); self.sidebar.addItem(heading); self.group_items.append((heading,group))
            for key in keys:
                page=factories[key](self); self.pages[key]=page
                page.layout.setSpacing(16)
                if hasattr(page,'log'):
                    page.layout.removeWidget(page.log); page.log.hide()
                item=QListWidgetItem(ui_icon(icons[key]),self.t(SECTION_NAMES[key])); item.setData(Qt.ItemDataRole.UserRole,key); item.setToolTip(self.t(SECTION_HELP[key])); self.sidebar.addItem(item); self.section_items[key]=item
                if key in ('files','apps','terminal'): container=page
                else:
                    container=QScrollArea(); container.setWidgetResizable(True); container.setFrameShape(QFrame.Shape.NoFrame); container.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); container.setWidget(page)
                container.setProperty('section',key); self.section_indices[key]=self.stack.addWidget(container)
        self.sidebar.currentItemChanged.connect(self.section_changed); right.addWidget(self.stack,1)
        dock=QFrame(); dock.setObjectName('operationDock'); d=QVBoxLayout(dock); d.setContentsMargins(16,12,16,12); d.setSpacing(8)
        operation=QHBoxLayout(); operation.setSpacing(12); self.operation_label=QLabel(self.t('Готово к работе')); self.operation_label.setObjectName('subtitle'); self.operation_label.setWordWrap(True); operation.addWidget(self.operation_label,1)
        self.global_progress=QProgressBar(); self.global_progress.setFixedHeight(12); self.global_progress.setTextVisible(False); self.global_progress.setMaximumWidth(240); self.global_progress.hide(); operation.addWidget(self.global_progress)
        self.cancel_btn=self.button('Отменить задание',self.cancel_operation,icon='stop'); self.cancel_btn.setEnabled(False); operation.addWidget(self.cancel_btn)
        self.log_disclosure=Disclosure(self.t('Журнал операций'),self); self.log_disclosure.toggle.setIcon(ui_icon('terminal')); self.log_disclosure.toggle.setProperty('help_key',ACTION_HELP['Журнал операций']); self.journal_toggle=self.log_disclosure.toggle
        operation.addWidget(self.journal_toggle); d.addLayout(operation)
        self.shared_log=logbox(); self.shared_log.setMinimumHeight(120); self.shared_log.setMaximumHeight(220); self.log_disclosure.body.addWidget(self.shared_log); d.addWidget(self.log_disclosure)
        self.notice_label=QLabel(); self.notice_label.setObjectName('subtitle'); self.notice_label.setWordWrap(True); self.notice_label.setMaximumHeight(56); d.addWidget(self.notice_label)
        right.addWidget(dock); self.select_section('catalog'); self.mode_changed(); self.apply_policy()

    def section_changed(self,item,previous=None):
        key=item.data(Qt.ItemDataRole.UserRole) if item else None
        if key not in self.section_indices: return
        self.stack.setCurrentIndex(self.section_indices[key]); self.section_title.setText(self.t(SECTION_NAMES[key])); self.section_description.setText(self.t(SECTION_HELP[key]))

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
            enabled=self.allowed(key,False); page.setEnabled(enabled)
            page.setToolTip('' if enabled else self.t('Отключено администратором'))
            self.section_items[key].setForeground(QColor(UiTokens.text if enabled else '#8491A3'))
        for widget in self.findChildren(QWidget):
            key=widget.property('feature')
            if key:
                enabled=self.allowed(key,False)
                if key in ('repair.settings','repair.verity','keyboard.install','keyboard.restore'): enabled=enabled and self.allowed('device.root',False) and self.allowed('device.reboot',False)
                if isinstance(widget,VoyahButton): widget.setPolicyEnabled(enabled,self)
                else:
                    widget.setEnabled(enabled); update_help(widget,self,'' if enabled else 'Отключено администратором')
            elif widget.property('help_key'): update_help(widget,self)
        for action in self.findChildren(QAction):
            key=action.property('feature')
            if key:
                action.setEnabled(self.allowed(key,False) and not self.busy)
                update_help(action,self,'' if self.allowed(key,False) else 'Отключено администратором')
        for page in self.pages.values():
            if hasattr(page,'update_actions'): page.update_actions()
        for widget in self.findChildren(QWidget):
            if not widget.property('help_key'): continue
            feature=widget.property('feature')
            section=next((key for key,page in self.pages.items() if page.isAncestorOf(widget)),None)
            reason=''
            if (feature and not self.allowed(feature,False)) or (section and not self.allowed(section,False)): reason='Отключено администратором'
            elif not widget.isEnabled():
                if self.busy: reason='Дождитесь завершения или отмените текущее задание.'
                elif not self.target and section!='terminal': reason='Сначала подключите устройство.'
                else: reason='Сначала выберите подходящий объект или заполните необходимые поля.'
            update_help(widget,self,reason)
        for button in getattr(self,'nav_buttons',[]):
            button.setEnabled(bool(self.target) and not self.busy); update_help(button,self,'' if self.target else 'Сначала подключите устройство.')
        self.root_button.setEnabled(not self.busy and bool(self.target)); self.reboot_button.setEnabled(not self.busy and bool(self.target))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not hasattr(self,'sidebar'): return
        compact=self.width()<1120; self.sidebar_panel.setFixedWidth(72 if compact else 240); self.brand_label.setVisible(not compact); self.sidebar_version.setVisible(not compact)
        self.sidebar_panel.layout().setContentsMargins(8 if compact else 12,20,8 if compact else 12,16)
        self.about_button.setText('' if compact else self.t('О приложении')); self.about_button.setFixedWidth(44 if compact else 214)
        for item,key in self.group_items: item.setText('' if compact else self.t(key)); item.setSizeHint(QSize(40 if compact else 180,8 if compact else 32))
        for key,item in self.section_items.items():
            item.setText('' if compact else self.t(SECTION_NAMES[key])); item.setSizeHint(QSize(44 if compact else 206,52 if compact or key!='apps' else 68))

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
        for obj,key,method in self.binding:
            getattr(obj,method)(self.t(key))
            if obj.property('icon_only'): obj.setText('')
            if obj.property('help_key'): update_help(obj,self)
        self.connection_toggle.setText('')
        for key,page in self.pages.items():
            page.retranslate(); self.section_items[key].setToolTip(self.t(SECTION_HELP[key]))
        self.journal_toggle.setText(self.t('Журнал операций'))
        self.section_changed(self.sidebar.currentItem())
        compact=self.width()<1120
        for key,item in self.section_items.items():
            item.setText('' if compact else self.t(SECTION_NAMES[key])); item.setSizeHint(QSize(44 if compact else 206,52 if compact or key!='apps' else 68))
        for item,key in self.group_items: item.setText('' if compact else self.t(key))
        self.about_button.setText('' if compact else self.t('О приложении'))
        self.apply_policy(); self.update_status(); self.adb_label.setText('ADB  ·  '+(self.adb_path or '—'))

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
        self.apply_policy()
        return True

    def end(self, success=True):
        self.busy = False; self.active_job = None; self.global_progress.hide(); self.cancel_btn.setEnabled(False)
        for w in (self.mode, self.device_combo, self.connect_btn): w.setEnabled(True)
        self.catalog.flush(); self.apply_policy()
        self.operation_label.setText(self.t('Отменено') if self.cancel_requested else self.t('Готово к работе')); self.notice(self.t('Отменено') if self.cancel_requested else self.t('Готово: {name}' if success else 'Ошибка: {name}', name=self.operation_name))

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
        self.pages['catalog'].refresh(); self.pages['keyboards'].describe(); self.pages['tweaks'].update_profile(); self.apply_policy()
        self.apply_policy()

    def update_status(self, state=''):
        key, color = ('Подключено', '#44D7A0') if self.target else ('Отключено', '#EF707B')
        if state in ('offline', 'unauthorized'):
            key = 'Не авторизовано — подтвердите RSA на ГУ' if state == 'unauthorized' else 'Устройство не отвечает'; color = '#F4C66B'
        self.status_dot.setStyleSheet(f'color:{color};font-size:18pt;')
        suffix = ('  ' + ('USB [-d]' if self.target.use_d else f'{self.target.mode.upper()} [-s {self.target.serial}]')) if self.target else ''
        self.connection_status.setText(self.t(key)); self.vehicle_label.setText(self.target.serial if self.target else self.t('Ваш автомобиль'));  self.connection_status.setToolTip(self.t(key) + suffix)
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
                self.pages['tweaks'].update_profile(); self.pages['catalog'].refresh(); self.pages['keyboards'].describe(); self.apply_policy(); return
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
    """Four task-oriented inspection views; device commands remain asynchronous."""
    SECTION_KEYS = ('Экраны', 'Кнопки руля', 'Наблюдение', 'Сведения о приложении')
    CAPTURE_KEYS = ('Открытие приложений', 'Нажатия и голос', 'Фоновые действия', 'Вся запись')
    DUMP_KEYS = ('Экраны приложения', 'Получаемые события', 'Фоновые действия', 'Полные сведения')

    class CurrentStack(QWidget):
        """Hidden details must not force compact display cards to their full height."""
        def __init__(self):
            super().__init__(); self.pages = []; self.index = 0
            self.body = QVBoxLayout(self); self.body.setContentsMargins(0, 0, 0, 0); self.body.setSpacing(0); self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        def addWidget(self, widget):
            index = len(self.pages); self.pages.append(widget); self.body.addWidget(widget); widget.setVisible(index == self.index); return index
        def currentWidget(self): return self.pages[self.index] if self.pages else None
        def currentIndex(self): return self.index
        def widget(self, index): return self.pages[index]
        def setCurrentIndex(self, index):
            self.index = index
            for number, widget in enumerate(self.pages): widget.setVisible(number == index)
            self.body.invalidate(); self.updateGeometry()

    def __init__(self, main):
        super().__init__(main)
        self.streams = {}; self.stream_buffers = {'logcat': '', 'getevent': ''}
        self.live_pending = {'logcat': '', 'getevent': ''}; self.live_paused = {'logcat': False, 'getevent': False}
        self.live_states = {'logcat': 'stopped', 'getevent': 'stopped'}
        self.full_capture = ''; self.full_dump = ''; self.last_screens = {}
        self.empty_keys = {}
        self.screen_time = ''; self.capture_state = 'idle'; self.capture_counts = [0, 0, 0, 0]
        self.capture_started = 0; self.capture_target = None; self.package_found = None; self.package_state = 'idle'; self.dump_generation = 0
        self.sections = QTabWidget(); self.sections.setDocumentMode(True); self.sections.setObjectName('inspectorSections')
        self.sections.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.layout.addWidget(self.sections, 1)
        self._build_screens(); self._build_capture(); self._build_live(); self._build_package()
        for i, name in enumerate(('monitor', 'steering', 'pulse', 'apps')):
            self.sections.setTabIcon(i, ui_icon(name))
        self.capture_timer = QTimer(self); self.capture_timer.setInterval(100); self.capture_timer.timeout.connect(self.capture_tick)
        self.live_timer = QTimer(self); self.live_timer.setInterval(100); self.live_timer.timeout.connect(self._flush_live)
        self.retranslate()

    def _section(self, key):
        page = QWidget(); page.setObjectName('inspectorScenario')
        body = QVBoxLayout(page); body.setContentsMargins(0, 16, 0, 0); body.setSpacing(16)
        self.sections.addTab(page, self.t(key))
        return body

    def _card(self, layout, title, description=''):
        panel = QFrame(); panel.setObjectName('card'); body = QVBoxLayout(panel)
        body.setContentsMargins(20, 18, 20, 18); body.setSpacing(12)
        if title: body.addWidget(self.label(title, 'section'))
        if description: body.addWidget(self.hint(description))
        layout.addWidget(panel)
        return body

    def _empty(self, layout, title, description, icon='info'):
        widget = EmptyState(self.t(title), self.t(description), icon)
        self.bind(widget.title, title); self.bind(widget.description, description)
        layout.addWidget(widget)
        self.empty_keys[widget] = (title, description)
        return widget

    def _set_empty(self, widget, title, description):
        self.empty_keys[widget] = (title, description)
        widget.title.setText(self.t(title)); widget.description.setText(self.t(description))

    def _copy_button(self, edit):
        button = QToolButton(); button.setObjectName('iconButton'); button.setIcon(ui_icon('copy'))
        button.setIconSize(QSize(18, 18)); button.setFixedSize(36, 36)
        button.setStyleSheet('QToolButton#iconButton { padding:0; }')
        self.bind(button, 'Копировать эту запись', 'setToolTip')
        self.bind(button, 'Копировать эту запись', 'setAccessibleName')
        button.clicked.connect(lambda checked=False, e=edit, b=button: self._copy(e, b))
        return button

    def _copy(self, edit, button):
        if not edit.text(): return
        QApplication.clipboard().setText(edit.text()); button.setToolTip(self.t('Скопировано'))
        self.main.notice(self.t('Скопировано'))
        timer=QTimer(button); timer.setSingleShot(True)
        timer.timeout.connect(lambda: button.setToolTip(self.t('Копировать эту запись'))); timer.start(1200)

    def _screen_field(self, layout, display, key, label, help_key):
        field_label = self.label(label, 'fieldLabel'); layout.addWidget(field_label)
        row = QHBoxLayout(); row.setSpacing(8)
        edit = QLineEdit(); edit.setReadOnly(True); edit.setPlaceholderText('—'); edit.setMinimumWidth(0)
        edit.setProperty('technical',True)
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        field_label.setBuddy(edit)
        self.bind(edit, help_key, 'setToolTip'); self.fields[display, key] = edit
        row.addWidget(edit, 1); copy_btn = self._copy_button(edit); copy_btn.setEnabled(False)
        self.screen_copy_buttons[display, key] = copy_btn; row.addWidget(copy_btn)
        layout.addLayout(row)

    def _build_screens(self):
        layout = self._section('Экраны')
        card = self._card(layout, 'Что сейчас открыто?', 'Узнайте, какое приложение сейчас видно на каждом экране автомобиля.')
        row = QHBoxLayout(); row.setSpacing(12)
        self.scan_btn = self.button('Обновить экраны', self.scan, True, icon='refresh', help_key='Показывает приложения, которые сейчас открыты на экранах автомобиля.')
        row.addWidget(self.scan_btn); row.addStretch(1)
        self.screen_updated = QLabel(); self.screen_updated.setObjectName('muted'); row.addWidget(self.screen_updated)
        card.addLayout(row)
        self.screen_grid = ResponsiveGrid(min_card_width=285, max_columns=3)
        card.addWidget(self.screen_grid)
        self.fields = {}; self.display_tags = {}; self.screen_status = {}; self.screen_stacks = {}; self.screen_copy_buttons = {}; self.screen_empty = {}; self.screen_names = {}; self.screen_times = {}; self.screen_disclosures = {}
        roles = ('Приборная панель', 'Центральный экран', 'Экран пассажира')
        for display, role in enumerate(roles):
            panel = QFrame(); panel.setObjectName('innerCard'); body = QVBoxLayout(panel); body.setContentsMargins(16, 16, 16, 16); body.setSpacing(10); body.setAlignment(Qt.AlignmentFlag.AlignTop)
            header = QHBoxLayout(); icon = QLabel(); icon.setPixmap(ui_icon('gauge' if display == 0 else 'monitor').pixmap(22, 22))
            header.addWidget(icon); header.addWidget(self.label(role, 'section'), 1); body.addLayout(header)
            tag = QLabel(); tag.setObjectName('eyebrow'); self.display_tags[display] = tag
            meta = QHBoxLayout(); meta.addWidget(tag); meta.addStretch(1)
            updated = QLabel(); updated.setObjectName('muted'); self.screen_times[display] = updated; meta.addWidget(updated); body.addLayout(meta)
            status = QLabel(); status.setObjectName('muted'); status.setWordWrap(True); self.screen_status[display] = status; body.addWidget(status)
            stack = self.CurrentStack(); stack.setObjectName('screenStack'); stack.setStyleSheet('QWidget#screenStack, QWidget#screenValues, QWidget#screenEmptyPage { background:transparent; }')
            stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            empty_page = QWidget(); empty_page.setObjectName('screenEmptyPage'); empty_layout = QVBoxLayout(empty_page); empty_layout.setContentsMargins(0, 0, 0, 0)
            self.screen_empty[display] = self._empty(empty_layout, 'Пока нет данных', 'Подключите автомобиль и нажмите «Обновить экраны».', 'monitor'); stack.addWidget(empty_page)
            values = QWidget(); values.setObjectName('screenValues'); values_layout = QVBoxLayout(values); values_layout.setContentsMargins(0, 0, 0, 0); values_layout.setSpacing(8); values_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            name = QLabel(); name.setObjectName('fieldLabel'); name.setWordWrap(True); name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self.screen_names[display] = name; values_layout.addWidget(name)
            details = self.disclosure('Подробности', values_layout, expanded=False); self.screen_disclosures[display] = details
            self._screen_field(details.body, display, 'package', 'Приложение', 'Адрес приложения в системе. Его можно скопировать для настройки или диагностики.')
            self._screen_field(details.body, display, 'activity', 'Открытый экран приложения', 'Название той части приложения, которая сейчас видна.')
            self._screen_field(details.body, display, 'component', 'Приложение и экран', 'Полная запись приложения и открытого экрана.')
            stack.addWidget(values); body.addWidget(stack); self.screen_stacks[display] = stack
            body.addStretch(1); self.screen_grid.addWidget(panel)
        layout.addStretch(1)

    def _build_capture(self):
        layout = self._section('Кнопки руля')
        card = self._card(layout, 'Что делает кнопка руля?', 'Начните запись, нажмите нужную кнопку в автомобиле и дождитесь результата.')
        steps=FlowLayout()
        for step in ('1. Начните запись', '2. Нажмите кнопку руля', '3. Посмотрите результат'):
            label=self.label(step,'badge'); steps.addWidget(label)
        card.addLayout(steps)
        self.countdown=self.label('6 секунд','countdown'); self.bind(self.countdown,'Время записи','setAccessibleName'); card.addWidget(self.countdown)
        self.capture_state_label = QLabel(); self.capture_state_label.setObjectName('section'); self.capture_state_label.setWordWrap(True); card.addWidget(self.capture_state_label)
        self.capture_progress = QProgressBar(); self.capture_progress.setRange(0, 60); self.capture_progress.setValue(0); self.capture_progress.setTextVisible(False)
        self.capture_progress.setFixedHeight(8); card.addWidget(self.capture_progress)
        actions = FlowLayout(); actions.setSpacing(10)
        self.capture_btn = self.button('Начать запись на 6 секунд', self.capture, True, icon='steering', help_key='Записывает события в течение шести секунд. Сразу после начала нажмите нужную кнопку на руле.')
        self.capture_cancel_btn = self.button('Отменить', self.main.cancel_operation, icon='stop', help_key='Останавливает текущую запись. Можно сразу начать новую.')
        self.capture_cancel_btn.setEnabled(False)
        actions.addWidget(self.capture_btn); actions.addWidget(self.capture_cancel_btn)
        self.capture_save_btn = self.button('Сохранить запись', lambda: self.save_text(self.full_capture, 'voyah-capture.txt'), icon='save', help_key='Сохраняет все полученные сообщения, включая скрытые в других группах.')
        self.capture_open_btn = self.button('Открыть в Блокноте', lambda: self.save_text(self.full_capture, 'voyah-capture.txt', True), help_key='Сохраняет запись на компьютер и открывает её в Блокноте.')
        self.capture_save_btn.setEnabled(False); self.capture_open_btn.setEnabled(False)
        actions.addWidget(self.capture_save_btn); actions.addWidget(self.capture_open_btn); card.addLayout(actions)
        self.capture_summary = QLabel(); self.capture_summary.setObjectName('muted'); self.capture_summary.setWordWrap(True); card.addWidget(self.capture_summary)
        self.capture_tabs = QTabWidget(); self.capture_tabs.setDocumentMode(True); self.capture_tabs.setObjectName('resultTabs')
        self.capture_views = [logbox() for _ in range(4)]; self.capture_empty = []; self.capture_stacks = []
        descriptions = ('Какие приложения и экраны открылись во время записи.', 'Сообщения о кнопках руля и голосовых командах.', 'Действия, которые автомобиль выполняет без открытия нового окна.', 'Все сообщения, полученные во время записи.')
        for key, description, view in zip(self.CAPTURE_KEYS, descriptions, self.capture_views):
            page = QWidget(); body = QVBoxLayout(page); body.setContentsMargins(0, 12, 0, 0); body.setSpacing(10)
            body.addWidget(self.hint(description)); stack = QStackedWidget(); stack.setMinimumHeight(240)
            empty_page = QWidget(); empty_body = QVBoxLayout(empty_page); empty_body.setContentsMargins(0, 0, 0, 0)
            empty = self._empty(empty_body, 'Здесь появится результат', 'Нажмите «Начать запись» и затем нужную кнопку на руле.', 'steering')
            stack.addWidget(empty_page); stack.addWidget(view); body.addWidget(stack, 1)
            self.capture_empty.append(empty); self.capture_stacks.append(stack); self.capture_tabs.addTab(page, self.t(key))
        card.addWidget(self.capture_tabs, 1)

    def _build_live(self):
        layout = self._section('Наблюдение')
        card = self._card(layout, 'Наблюдение в реальном времени', 'Запустите нужный вид наблюдения и выполните действие в автомобиле.')
        filters = QHBoxLayout(); filters.setSpacing(10)
        self.live_filter = self.edit('Показать сообщения с этими словами, например: музыка, голос')
        self.bind(self.live_filter, 'Введите одно или несколько слов через запятую. Остальные сообщения будут скрыты, но сохранятся в записи.', 'setToolTip')
        self.live_filter.textChanged.connect(self.refilter); filters.addWidget(self.live_filter, 1)
        self.live_save_btn = self.button('Сохранить наблюдение', lambda: self.save_text('\n'.join(self.stream_buffers.values()), 'voyah-live.txt'), icon='save', help_key='Сохраняет сообщения из обоих видов наблюдения, включая скрытые фильтром.')
        self.live_save_btn.setEnabled(False); filters.addWidget(self.live_save_btn); card.addLayout(filters)
        self.live_views = {}; self.live_buttons = {}; self.live_pause_buttons = {}; self.live_status = {}; self.live_stacks = {}; self.live_empty = {}
        grid = ResponsiveGrid(min_card_width=370, max_columns=2); card.addWidget(grid)
        for name, key, description in (('logcat', 'События приложений', 'Показывает, что делают приложения во время вашей работы с экраном.'), ('getevent', 'Нажатия кнопок', 'Здесь видны только те нажатия, которые автомобиль передаёт системе.')):
            panel = QFrame(); panel.setObjectName('innerCard'); body = QVBoxLayout(panel); body.setContentsMargins(16, 16, 16, 16); body.setSpacing(10)
            row = QHBoxLayout(); row.addWidget(self.label(key, 'section'), 1)
            state = QLabel(); state.setObjectName('statusChip'); self.live_status[name] = state; row.addWidget(state); body.addLayout(row)
            body.addWidget(self.hint(description))
            actions = QHBoxLayout(); actions.setSpacing(8)
            button = self.button('Начать', lambda checked=False, n=name: self.toggle_stream(n), True, icon='play', help_key='Начинает получать новые сообщения. Второй вид наблюдения работает независимо.')
            pause = self.button('Пауза прокрутки', lambda checked=False, n=name: self.toggle_pause(n), icon='pulse', help_key='Оставляет нужные строки на экране. Запись продолжает работать.')
            pause.setEnabled(False); self.live_buttons[name] = button; self.live_pause_buttons[name] = pause
            actions.addWidget(button); actions.addWidget(pause); actions.addStretch(1); body.addLayout(actions)
            stack = QStackedWidget(); stack.setMinimumHeight(250)
            empty_page = QWidget(); empty_body = QVBoxLayout(empty_page); empty_body.setContentsMargins(0, 0, 0, 0)
            self.live_empty[name] = self._empty(empty_body, 'Наблюдение ещё не началось', 'Нажмите «Начать», затем выполните нужное действие в автомобиле.', 'pulse')
            view = logbox(); stack.addWidget(empty_page); stack.addWidget(view); body.addWidget(stack, 1)
            self.live_views[name] = view; self.live_stacks[name] = stack; grid.addWidget(panel)
        layout.addStretch(1)

    def _build_package(self):
        layout = self._section('Сведения о приложении')
        card = self._card(layout, 'Какие действия доступны приложению?', 'Найдите установленное приложение или укажите его адрес, затем получите сведения.')
        search_row = QHBoxLayout(); search_row.setSpacing(10)
        self.package_search = self.edit('Найти приложение по части адреса'); self.package_search.returnPressed.connect(self.search_packages)
        self.bind(self.package_search, 'Введите часть адреса приложения. Программа найдёт совпадения среди установленных приложений.', 'setToolTip')
        self.package_find_btn = self.button('Найти', self.search_packages, icon='search')
        search_row.addWidget(self.package_search, 1); search_row.addWidget(self.package_find_btn)
        card.addLayout(search_row)
        self.package_search_status = QLabel(); self.package_search_status.setObjectName('muted'); self.package_search_status.setWordWrap(True); card.addWidget(self.package_search_status)
        card.addWidget(self.label('Выберите приложение или укажите его адрес', 'fieldLabel'))
        select_row = QHBoxLayout(); select_row.setSpacing(10)
        self.package_combo = QComboBox(); self.package_combo.setEditable(True); self.package_combo.setMinimumWidth(0)
        self.package_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if self.package_combo.lineEdit(): self.bind(self.package_combo.lineEdit(), 'Например: com.voyah.music', 'setPlaceholderText')
        select_row.addWidget(self.package_combo, 1)
        self.dump_btn = self.button('Получить сведения', self.dump_package, True, icon='apps', help_key='Показывает доступные экраны приложения и действия, на которые оно реагирует.')
        select_row.addWidget(self.dump_btn)
        self.dump_save_btn = self.button('Сохранить', lambda: self.save_text(self.full_dump, 'voyah-package.txt'), icon='save', help_key='Сохраняет все сведения о выбранном приложении на компьютер.')
        self.dump_save_btn.setEnabled(False); select_row.addWidget(self.dump_save_btn); card.addLayout(select_row)
        self.package_combo.currentTextChanged.connect(self.update_actions)
        self.dump_status = QLabel(); self.dump_status.setObjectName('muted'); self.dump_status.setWordWrap(True); card.addWidget(self.dump_status)
        self.dump_tabs = QTabWidget(); self.dump_tabs.setDocumentMode(True); self.dump_tabs.setObjectName('resultTabs')
        self.dump_views = [logbox() for _ in range(4)]; self.dump_view = self.dump_views[3]
        self.dump_empty = []; self.dump_stacks = []
        descriptions = ('Экраны, которые могут открываться внутри приложения.', 'События, после которых приложение может выполнять действия.', 'Действия приложения, которые выполняются без открытия окна.', 'Все сведения, полученные от автомобиля. Их можно сохранить для подробного разбора.')
        for key, description, view in zip(self.DUMP_KEYS, descriptions, self.dump_views):
            page = QWidget(); body = QVBoxLayout(page); body.setContentsMargins(0, 12, 0, 0); body.setSpacing(10); body.addWidget(self.hint(description))
            stack = QStackedWidget(); stack.setMinimumHeight(240)
            empty_page = QWidget(); empty_body = QVBoxLayout(empty_page); empty_body.setContentsMargins(0, 0, 0, 0)
            self.dump_empty.append(self._empty(empty_body, 'Выберите приложение', 'Найдите приложение выше и нажмите «Получить сведения».', 'apps'))
            stack.addWidget(empty_page); stack.addWidget(view); body.addWidget(stack, 1); self.dump_stacks.append(stack); self.dump_tabs.addTab(page, self.t(key))
        card.addWidget(self.dump_tabs, 1)

    def retranslate(self):
        super().retranslate()
        for widget, (title, description) in self.empty_keys.items():
            widget.title.setText(self.t(title)); widget.description.setText(self.t(description))
        for i, key in enumerate(self.SECTION_KEYS): self.sections.setTabText(i, self.t(key))
        self._screen_labels(); self._capture_labels(); self._live_labels(); self._package_labels()
        for i, key in enumerate(self.DUMP_KEYS): self.dump_tabs.setTabText(i, self.t(key))
        self.update_actions()

    def update_actions(self):
        if not hasattr(self, 'dump_save_btn'): return
        allowed = self.main.allowed('inspector', False)
        ready = allowed and bool(self.main.target) and not self.main.busy
        active = self.capture_state in ('clearing', 'recording', 'reading', 'processing')
        self.scan_btn.setEnabled(ready); self.capture_btn.setEnabled(ready and not active)
        # A running operation remains cancellable even while other actions are disabled.
        self.capture_cancel_btn.setEnabled(active and self.main.busy)
        self.package_find_btn.setEnabled(ready); self.package_search.setEnabled(ready)
        self.package_combo.setEnabled(ready); self.dump_btn.setEnabled(ready and bool(PACKAGE_RE.fullmatch(self.package_combo.currentText().strip())))
        self.capture_save_btn.setEnabled(allowed and bool(self.full_capture)); self.capture_open_btn.setEnabled(allowed and bool(self.full_capture))
        self.dump_save_btn.setEnabled(allowed and bool(self.full_dump)); self.live_save_btn.setEnabled(allowed and any(self.stream_buffers.values()))
        for name, button in self.live_buttons.items():
            button.setEnabled(allowed and (name in self.streams or ready))
            self.live_pause_buttons[name].setEnabled(allowed and (name in self.streams or bool(self.stream_buffers[name])))
        for (display, key), button in self.screen_copy_buttons.items(): button.setEnabled(allowed and bool(self.fields[display, key].text()))

    def _screen_labels(self):
        ids = [self.main.display_map[role] for role in ('cluster', 'center', 'passenger')]
        for display, label in self.display_tags.items():
            label.setText(self.t('Экран {number}', number=ids[display]))
            found = bool(self.last_screens.get(ids[display], {}).get('component'))
            self.screen_status[display].setText(self.t('На экране открыто приложение' if found else 'Ожидает обновления' if not self.screen_time else 'Автомобиль не сообщил, что открыто на этом экране.'))
            info = self.last_screens.get(ids[display], {})
            self.screen_names[display].setText(info.get('label') or info.get('name') or info.get('package', ''))
            self.screen_names[display].setToolTip(self.screen_names[display].text())
            self.screen_times[display].setText(self.screen_time or '—')
        self.screen_updated.setText(self.t('Обновлено в {time}', time=self.screen_time) if self.screen_time else self.t('Ещё не обновлялось'))

    def _capture_labels(self):
        remaining = max(0, 6 - int(time.monotonic() - self.capture_started)) if self.capture_state == 'recording' else 6
        self.countdown.setText(self.t('{seconds} с',seconds=remaining) if self.capture_state=='recording' else self.t('6 секунд'))
        messages = {'idle': 'Готово к записи', 'clearing': 'Подготавливаем запись…', 'recording': 'Нажмите кнопку на руле · осталось {seconds} с', 'reading': 'Получаем записанные сообщения…', 'processing': 'Группируем найденные сообщения…', 'done': 'Запись завершена', 'cancelled': 'Запись отменена', 'error': 'Не удалось завершить запись'}
        self.capture_state_label.setText(self.t(messages.get(self.capture_state, 'Готово к записи'), seconds=remaining))
        active = self.capture_state in ('clearing', 'recording', 'reading', 'processing')
        self.capture_btn.setText(self.t('Записать ещё раз' if self.capture_state in ('done', 'cancelled', 'error') else 'Начать запись на 6 секунд'))
        self.capture_summary.setText(self.t('Обработано сообщений: {count}. Одно нажатие может создавать несколько сообщений.', count=self.capture_counts[3]) if self.capture_state == 'done' else '')
        self.capture_summary.setVisible(self.capture_state == 'done')
        for i, key in enumerate(self.CAPTURE_KEYS):
            self.capture_tabs.setTabText(i, self.t(key) + (f' · {self.capture_counts[i]}' if self.capture_state == 'done' else ''))
        self.update_actions()

    def _live_labels(self):
        for name, button in self.live_buttons.items():
            running = name in self.streams; button.setText(self.t('Остановить' if running else 'Начать')); button.setIcon(ui_icon('stop' if running else 'play'))
            self.live_pause_buttons[name].setText(self.t('Продолжить прокрутку' if self.live_paused[name] else 'Пауза прокрутки'))
            self.live_pause_buttons[name].setEnabled(running or bool(self.stream_buffers[name]))
            state = 'Запись идёт · просмотр на паузе' if running and self.live_paused[name] else 'Наблюдение идёт' if running else 'Нет доступа' if self.live_states[name] == 'denied' else 'Наблюдение прервано' if self.live_states[name] == 'error' else 'Остановлено'
            self.live_status[name].setText(self.t(state)); self.live_status[name].setProperty('active', running)
        self.live_save_btn.setEnabled(any(self.stream_buffers.values()))
        self.update_actions()

    def _package_labels(self):
        self.package_search_status.setText(self.t('Найдено приложений: {count}', count=self.package_found) if self.package_found is not None else self.t('Можно искать приложение или сразу указать его адрес.'))
        self.package_search_status.setVisible(self.package_found is not None)
        messages = {'idle': 'Сведения ещё не запрошены', 'loading': 'Получаем сведения о приложении…', 'done': 'Сведения получены', 'error': 'Не удалось получить сведения'}
        self.dump_status.setText(self.t(messages[self.package_state])); self.dump_save_btn.setEnabled(bool(self.full_dump))
        self.dump_status.setVisible(self.package_state != 'idle')
        self.update_actions()

    @feature_required('inspector')
    def scan(self):
        if not self.main.ready(): return
        target = self.main.target; self.scan_btn.setEnabled(False); self.screen_updated.setText(self.t('Обновляем экраны…'))
        def done(ok, results):
            self.scan_btn.setEnabled(self.main.allowed('inspector', False))
            if not ok: self._screen_labels(); return
            window, activity = results[0].text, results[1].text
            self.main.background(lambda: parse_screens(window, activity), lambda screens, err: self.show_screens(screens or {}) if target == self.main.target else None)
        self.main.sequence(self.t('Обновить экраны'), [Step(['dumpsys', 'window']), Step(['dumpsys', 'activity', 'activities'])], done)

    def show_screens(self, screens):
        self.last_screens = screens; self.screen_time = time.strftime('%H:%M:%S')
        ids = [self.main.display_map[role] for role in ('cluster', 'center', 'passenger')]
        for (display, key), edit in self.fields.items():
            edit.setText(screens.get(ids[display], {}).get(key, '')); edit.setCursorPosition(0)
            self.screen_copy_buttons[display, key].setEnabled(bool(edit.text()))
        for display, stack in self.screen_stacks.items():
            found = bool(screens.get(ids[display], {}).get('component')); stack.setCurrentIndex(1 if found else 0)
            if not found: self._set_empty(self.screen_empty[display], 'Нет открытого приложения', 'Автомобиль не сообщил, что открыто на этом экране. Можно обновить данные ещё раз.')
        self._screen_labels()
        self.update_actions()

    def _set_capture_state(self, state):
        if state in ('cancelled', 'error'): self.capture_progress.setValue(0)
        self.capture_state = state; self._capture_labels()

    @feature_required('inspector')
    def capture(self):
        if not self.main.ready() or not self.main.begin(self.t('Перехват кнопки руля')): return
        self.capture_target = self.main.target; self.full_capture = ''; self.capture_counts = [0, 0, 0, 0]
        self.capture_progress.setValue(0); self._set_capture_state('clearing')
        for view, stack in zip(self.capture_views, self.capture_stacks): view.clear(); stack.setCurrentIndex(0)
        for empty in self.capture_empty: self._set_empty(empty, 'Запись начинается', 'Дождитесь начала отсчёта и нажмите нужную кнопку на руле.')
        def cleared(result):
            if not result.ok:
                self._set_capture_state('cancelled' if result.cancelled else 'error'); self.main.end(False)
                if not result.cancelled: self.main.error(self.t(explain_error(result.text)), result.text)
                return
            if self.main.cancel_requested:
                self._set_capture_state('cancelled'); self.main.end(False); return
            self.capture_started = time.monotonic(); self._set_capture_state('recording'); self.capture_timer.start()
            self.main.notice(self.t('Нажмите кнопку на руле сейчас…'))
        self.main.active_job = self.main.adb(['logcat', '-b', 'main', '-b', 'system', '-b', 'events', '-c'], cleared, target=self.capture_target)

    def capture_tick(self):
        elapsed = time.monotonic() - self.capture_started; self.capture_progress.setValue(min(60, int(elapsed * 10)))
        self.main.global_progress.setRange(0,60); self.main.global_progress.setValue(self.capture_progress.value())
        if self.main.cancel_requested:
            self.capture_timer.stop(); self.capture_progress.setValue(0); self._set_capture_state('cancelled'); self.main.end(False); return
        self._capture_labels()
        if elapsed < 6: return
        self.capture_timer.stop(); self._set_capture_state('reading')
        def captured(result):
            if not result.ok:
                self._set_capture_state('cancelled' if result.cancelled else 'error'); self.main.end(False)
                if not result.cancelled: self.main.error(self.t(explain_error(result.text)), result.text)
                return
            if self.main.cancel_requested:
                self._set_capture_state('cancelled'); self.main.end(False); return
            self.full_capture = result.text; self.capture_views[3].setPlainText(result.text)
            self.capture_stacks[3].setCurrentIndex(1 if result.text.strip() else 0); self._set_capture_state('processing')
            self.main.background(lambda: classify_capture(result.text), self.show_capture)
        self.main.active_job = self.main.adb(['logcat', '-d', '-b', 'main', '-b', 'system', '-b', 'events', '-v', 'time'], captured, target=self.capture_target, timeout=30000, check=False)

    def show_capture(self, categories, error):
        if self.main.cancel_requested:
            self._set_capture_state('cancelled'); self.main.end(False); return
        if error:
            self._set_capture_state('error'); self.main.end(False); self.main.error(self.t('Не удалось обработать запись.'), str(error)); return
        for i, (view, lines) in enumerate(zip(self.capture_views, categories or [[], [], []])):
            view.setPlainText('\n'.join(lines)); self.capture_counts[i] = len(lines); self.capture_stacks[i].setCurrentIndex(1 if lines else 0)
            self._set_empty(self.capture_empty[i], 'Подходящих сообщений не найдено', 'Попробуйте ещё раз и нажмите кнопку после начала отсчёта. Некоторые кнопки автомобиля не показывают свои действия в доступном журнале.')
        self.capture_counts[3] = len(self.full_capture.splitlines())
        if not self.full_capture.strip():
            self._set_empty(self.capture_empty[3], 'Запись пуста', 'Автомобиль не передал сообщений во время записи. Можно попробовать ещё раз.')
        self._set_capture_state('done'); self.main.end(True)

    @feature_required('inspector')
    def toggle_stream(self, name):
        if name in self.streams:
            self.streams.pop(name).cancel(); self.live_states[name] = 'stopped'; self._flush_live(); self._live_labels(); return
        if not self.main.target: self.main.error(self.t('Сначала подключите устройство.')); return
        if self.main.busy: self.main.error(self.t('Дождитесь завершения или отмените текущее задание.')); return
        args = ['logcat', '-b', 'main', '-b', 'system', '-b', 'events', '-v', 'time'] if name == 'logcat' else ['getevent', '-lt']
        def chunk(text):
            self.stream_buffers[name] = (self.stream_buffers[name] + text)[-2_000_000:]
            if not self.live_paused[name]: self.live_pending[name] = (self.live_pending[name] + text)[-2_000_000:]
            if not self.live_timer.isActive(): self.live_timer.start()
            self.live_save_btn.setEnabled(True)
        def finished(result):
            self.streams.pop(name, None); self._flush_live(); self.live_states[name] = 'error' if not result.ok and not result.cancelled else 'stopped'
            if not result.ok and not result.cancelled:
                denied = bool(name == 'getevent' and re.search(r'Permission denied|not permitted|SecurityException', result.text, re.I))
                if denied: self.live_states[name] = 'denied'
                explanation = self.t('Автомобиль не разрешает читать нажатия кнопок.') if denied else self.t(explain_error(result.text))
                self.stream_buffers[name] = (self.stream_buffers[name] + '\n' + explanation + '\n' + result.text)[-2_000_000:]
                append_log(self.live_views[name], '\n' + explanation + '\n' + result.text + '\n'); self.live_stacks[name].setCurrentIndex(1)
            self._live_labels()
        self.live_states[name] = 'running'; self.streams[name] = self.main.adb(args, finished, shell=name == 'getevent', privileged=name == 'getevent', stream=chunk, timeout=0, check=False)
        self._set_empty(self.live_empty[name], 'Ожидаем сообщения', 'Выполните нужное действие в автомобиле. Новые сообщения появятся здесь.')
        self._live_labels()

    def toggle_pause(self, name):
        self.live_paused[name] = not self.live_paused[name]; self.live_pending[name] = ''
        if not self.live_paused[name]: self._render_live(name)
        self._live_labels()

    def _filtered_lines(self, text):
        filters = [word.strip().lower() for word in self.live_filter.text().split(',') if word.strip()]
        return ''.join(line for line in text.splitlines(keepends=True) if not filters or any(word in line.lower() for word in filters))

    def _flush_live(self):
        for name in self.live_views:
            if self.live_paused[name]: continue
            pending = self.live_pending[name]; self.live_pending[name] = ''
            if pending:
                visible = self._filtered_lines(pending)
                if visible: append_log(self.live_views[name], visible); self.live_stacks[name].setCurrentIndex(1)
        if not any(self.live_pending.values()) and not self.streams: self.live_timer.stop()

    def _render_live(self, name):
        visible = self._filtered_lines(self.stream_buffers[name]); self.live_views[name].setPlainText(visible)
        self.live_stacks[name].setCurrentIndex(1 if visible else 0)
        if self.stream_buffers[name] and not visible:
            self._set_empty(self.live_empty[name], 'Совпадений не найдено', 'Попробуйте изменить слова в фильтре. Полная запись остаётся доступна для сохранения.')
        if visible:
            cursor = self.live_views[name].textCursor(); cursor.movePosition(QTextCursor.MoveOperation.End); self.live_views[name].setTextCursor(cursor)

    def refilter(self):
        for name in self.live_views:
            if not self.live_paused[name]: self.live_pending[name] = ''; self._render_live(name)

    def stop_streams(self):
        self.capture_timer.stop(); self.live_timer.stop()
        for job in list(self.streams.values()): job.cancel()
        self.streams.clear(); self._live_labels()

    @feature_required('inspector')
    def search_packages(self):
        if not self.main.ready(): return
        word = self.package_search.text().strip().lower(); self.package_search_status.setText(self.t('Ищем приложения…'))
        target = self.main.target
        def done(ok, results):
            if ok and target == self.main.target:
                packages = sorted(line[8:] for line in results[0].text.splitlines() if line.startswith('package:') and word in line.lower())
                self.package_combo.clear(); self.package_combo.addItems(packages); self.package_found = len(packages); self._package_labels()
                if not packages: self.package_search_status.setText(self.t('Приложения не найдены. Попробуйте другую часть адреса.'))
            elif not ok: self._package_labels()
        self.main.sequence(self.t('Найти'), [Step(['pm', 'list', 'packages'])], done)

    @staticmethod
    def resolver_sections(text):
        """Preserve complete lines; group only exact resolver-table boundaries."""
        sections = {'Activity': [], 'Receiver': [], 'Service': []}; current = None; header_indent = 0
        for line in text.splitlines(keepends=True):
            header = re.match(r'^\s*(Activity|Receiver|Service) Resolver Table\s*:', line)
            if header:
                current = header[1]; header_indent = len(line) - len(line.lstrip(' \t')); sections[current].append(line); continue
            indent = len(line) - len(line.lstrip(' \t'))
            if current and line.strip() and indent <= header_indent: current = None
            if current: sections[current].append(line)
        return [''.join(sections[key]).strip() for key in ('Activity', 'Receiver', 'Service')]

    @feature_required('inspector')
    def dump_package(self):
        pkg = self.package_combo.currentText().strip()
        if not self.main.ready(): return
        if not PACKAGE_RE.fullmatch(pkg): self.main.error(self.t('Выберите пакет.')); return
        target = self.main.target; self.package_state = 'loading'; self._package_labels(); self.dump_generation += 1; generation = self.dump_generation
        def parsed(sections, error):
            if target != self.main.target or generation != self.dump_generation: return
            self.package_state = 'error' if error else 'done'; self._package_labels()
            if error: self.main.error(self.t('Не удалось обработать сведения.'), str(error)); return
            for i, (view, text) in enumerate(zip(self.dump_views, sections + [self.full_dump])):
                view.setPlainText(text); self.dump_stacks[i].setCurrentIndex(1 if text.strip() else 0)
                if not text.strip():
                    self._set_empty(self.dump_empty[i], 'Этот раздел отсутствует', 'В доступных сведениях приложение не сообщило об этих действиях. Полные сведения доступны в соседнем разделе.')
            from PySide6.QtWidgets import QTextEdit
            from PySide6.QtGui import QTextCharFormat
            highlights = []
            for match in re.finditer(r'^.*(?:Activity|Receiver|Service) Resolver Table.*$', self.full_dump, re.M):
                selection = QTextEdit.ExtraSelection(); cursor = self.dump_view.textCursor(); cursor.setPosition(match.start()); cursor.setPosition(match.end(), QTextCursor.MoveMode.KeepAnchor)
                selection.cursor = cursor; fmt = QTextCharFormat(); fmt.setForeground(QColor('#64DFF4')); fmt.setFontWeight(QFont.Weight.Bold); selection.format = fmt; highlights.append(selection)
            self.dump_view.setExtraSelections(highlights)
        def done(ok, results):
            if ok and target == self.main.target and generation == self.dump_generation:
                self.full_dump = results[0].text; self.dump_save_btn.setEnabled(bool(self.full_dump)); dump_text = self.full_dump
                self.main.background(lambda: self.resolver_sections(dump_text), parsed)
            elif not ok: self.package_state = 'error'; self._package_labels()
        self.main.sequence(self.t('Получить сведения'), [Step(['dumpsys', 'package', pkg])], done)

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

    class DropArea(QFrame):
        paths_dropped = Signal(object)
        def __init__(self, page):
            super().__init__(page); self.page = page; self.setAcceptDrops(True); self.setObjectName('dropZone')
            self.setMinimumHeight(168); layout = QVBoxLayout(self); layout.setContentsMargins(24, 24, 24, 24); layout.setSpacing(12)
            image = QLabel(); image.setPixmap(ui_icon('apk', size=32).pixmap(32, 32)); image.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(image)
            heading = page.label('Перетащите файлы приложения сюда', 'section'); heading.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(heading)
            caption = page.hint('Подойдут APK и готовые комплекты приложений. Можно выбрать несколько файлов или целую папку.'); caption.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(caption)
        def dragEnterEvent(self, event):
            if event.mimeData().hasUrls() and not self.page.main.busy and self.page.main.allowed('apk.install', False):
                self.setProperty('dragActive', True); self.style().unpolish(self); self.style().polish(self); event.acceptProposedAction()
        def dragLeaveEvent(self, event):
            self.setProperty('dragActive', False); self.style().unpolish(self); self.style().polish(self)
        def dropEvent(self, event):
            self.setProperty('dragActive', False); self.style().unpolish(self); self.style().polish(self)
            self.paths_dropped.emit([url.toLocalFile() for url in event.mimeData().urls()]); event.acceptProposedAction()

    def __init__(self, main):
        super().__init__(main); self.setAcceptDrops(True); self.files = []; self.service = InstallService(main); self.cancel_event = self.service.cancel_event
        card = self.card('Приложения с компьютера', 'Выберите файлы, проверьте список и установите их в автомобиль.')
        self.drop_area = self.DropArea(self); self.drop_area.paths_dropped.connect(self.add_paths); card.addWidget(self.drop_area)
        self.drop_hint = self.drop_area.findChildren(QLabel)[-1]
        self.add_button = self.button('Выбрать файлы', self.add_files, True, icon='add', help_key='Выберите один APK, несколько приложений или готовый комплект из файлов.')
        self.folder_button = self.button('Выбрать папку', self.add_folder, icon='folder', help_key='Добавит все APK из выбранной папки. Каждое приложение установится по очереди.')
        self.row(card, self.add_button, self.folder_button)
        self.mode = QComboBox(); self.mode_keys = ['Одно приложение', 'Несколько приложений', 'Комплект одного приложения']; self.mode.addItems([self.t(k) for k in self.mode_keys])
        self.mode.setProperty('feature', 'apk.install'); self.bind(self.mode, 'Укажите, устанавливаете вы один файл, разные приложения или части одного приложения.', 'setToolTip')
        options = QHBoxLayout(); options.setSpacing(12); options.addWidget(self.label('Как установить')); options.addWidget(self.mode, 1); card.addLayout(options)
        self.mode_hint = self.hint('Один APK — одно приложение.'); card.addWidget(self.mode_hint); self.mode.currentIndexChanged.connect(self.update_mode_hint)
        queue = self.card('Выбранные файлы')
        self.queue_summary = QLabel(); self.queue_summary.setObjectName('subtitle'); queue.addWidget(self.queue_summary)
        self.file_table = table([self.t('Файл'), self.t('Размер'), self.t('Статус')]); self.file_table.setMinimumHeight(176); self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_table.horizontalHeader().setMinimumSectionSize(90); queue.addWidget(self.file_table)
        self.empty_queue = EmptyState(self.t('Файлы ещё не выбраны'), self.t('Перетащите приложение в область выше или нажмите «Выбрать файлы».'), icon='apk'); queue.addWidget(self.empty_queue)
        self.clear_button = self.button('Очистить список', self.clear_files, icon='delete', help_key='Уберёт выбранные файлы из списка. Файлы на компьютере останутся.')
        self.row(queue, self.clear_button)
        settings = self.card('Параметры установки', 'Обычные параметры уже выбраны. Меняйте их только при необходимости.')
        self.flags = []
        for title, checked, help_key in [
            ('Сохранить данные при переустановке', True, 'Заменит приложение новой версией, сохранив его настройки и личные данные.'),
            ('Разрешить старую версию', False, 'Разрешит установить более старую версию. Некоторые приложения это не поддерживают.'),
            ('Выдать разрешения приложению', True, 'Сразу разрешит приложению использовать запрошенные возможности, например микрофон и память.')]:
            check = self.bind(QCheckBox(), title); check.setChecked(checked); check.setProperty('feature', 'apk.install'); self.bind(check, help_key, 'setToolTip'); self.flags.append(check); settings.addWidget(check)
        details_layout = QVBoxLayout(); details_layout.setContentsMargins(0, 0, 0, 0); details_layout.addWidget(self.hint('Флаги установки: сохранение данных — -r, старая версия — -d, разрешения — -g. Части одного приложения устанавливаются вместе.'))
        technical=self.disclosure('Технические подробности',settings)
        technical.body.addLayout(details_layout)
        self.install_button = self.button('Установить в автомобиль', self.install, True, icon='download', help_key='Проверит выбранные файлы и установит их на подключённое устройство. Результат появится напротив каждого файла.')
        action = QHBoxLayout(); action.addWidget(self.install_button); action.addStretch(); settings.addLayout(action)
        self.progress = QProgressBar(self); self.progress.setValue(0); self.progress.hide(); self.log = logbox(); self.log.setParent(self); self.log.hide()
        self.service.log_message.connect(lambda text: append_log(self.log, text)); self.service.status_changed.connect(self.set_status); self.service.progress_changed.connect(self.progress.setValue)
        self.service.progress_changed.connect(self.update_progress); self.service.finished.connect(lambda _: self.update_actions()); self.file_table.itemSelectionChanged.connect(self.update_actions)
        self.layout.addStretch(); self.update_mode_hint(); self.update_actions()

    def update_progress(self, value):
        if self.main.busy and hasattr(self.main, 'global_progress'):
            self.main.global_progress.setRange(0, 100); self.main.global_progress.setValue(value)

    def update_mode_hint(self):
        keys = ['Один APK — одно приложение.', 'Разные приложения установятся по очереди. Не выбирайте этот режим для частей одного приложения.', 'Выберите все части одного приложения или один готовый архив. Комплект установится целиком.']
        self.mode_hint.setText(self.t(keys[self.mode.currentIndex()])); self.update_actions()

    def update_actions(self):
        editable = not self.main.busy and self.main.allowed('installer', False) and self.main.allowed('apk.install', False)
        for widget in [self.add_button, self.folder_button, self.mode, self.drop_area, *self.flags]: widget.setEnabled(editable)
        self.clear_button.setEnabled(editable and bool(self.files)); self.install_button.setEnabled(editable and bool(self.files) and bool(self.main.target))
        self.file_table.setVisible(bool(self.files)); self.empty_queue.setVisible(not self.files)
        self.queue_summary.setText(self.t('Файлов в списке: {count}', count=len(self.files)))

    def retranslate(self):
        super().retranslate()
        for i, key in enumerate(self.mode_keys): self.mode.setItemText(i, self.t(key))
        self.file_table.setHorizontalHeaderLabels([self.t(k) for k in ('Файл', 'Размер', 'Статус')])
        self.empty_queue.title.setText(self.t('Файлы ещё не выбраны')); self.empty_queue.description.setText(self.t('Перетащите приложение в область выше или нажмите «Выбрать файлы».')); self.update_mode_hint(); self.update_actions()

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
        self.update_actions()

    @feature_required('apk.install', 'installer')
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, self.t('Добавить файлы'), '', 'Android (*.apk *.apks *.xapk *.apkm)'); self.add_paths(files)

    @feature_required('apk.install', 'installer')
    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.t('Добавить папку'))
        if folder: self.add_paths([folder])

    def clear_files(self):
        if not self.main.busy: self.files.clear(); self.file_table.setRowCount(0); self.update_actions()

    def set_status(self, rows, text, success=None):
        for row in rows:
            item = QTableWidgetItem(text)
            if success is not None: item.setForeground(QColor('#51D8A5' if success else '#FF939E'))
            self.file_table.setItem(row, 2, item)
        self.update_actions()

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
        if self.service.start(self.files,mode,[flag for flag,check in zip(('-r','-d','-g'),self.flags) if check.isChecked()]): self.update_actions()

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
        card = self.card('Память автомобиля', 'Открывайте папки, передавайте файлы в автомобиль и сохраняйте их на компьютер.')
        self.toolbar_layout = card; self.toolbar_frame = card.parentWidget(); self.toolbar_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toolbar_title = card.itemAt(0).widget(); self.toolbar_description = card.itemAt(1).widget()
        self.path = QLineEdit('/sdcard/'); self.path.returnPressed.connect(self.refresh); self.bind(self.path, 'Путь к открытой папке в памяти автомобиля. Можно вставить другой путь и нажать Enter.', 'setToolTip')
        self.up_button = self.button('Вверх', self.up, icon='folder', help_key='Откроет папку на один уровень выше.')
        self.refresh_button = self.button('Обновить', self.refresh, icon='refresh', help_key='Заново прочитает содержимое открытой папки.')
        self.up_button.setProperty('feature', 'files'); path_row = QHBoxLayout(); path_row.setSpacing(12); path_row.addWidget(self.up_button); path_row.addWidget(self.path, 1); path_row.addWidget(self.refresh_button); card.addLayout(path_row)
        self.bookmarks_widget = QWidget(); bookmarks = FlowLayout(); self.bookmarks_widget.setLayout(bookmarks); self.bookmark_buttons = []
        for label, path in [('Общая память', '/sdcard/'), ('Загрузки', '/sdcard/Download/'), ('Все накопители', '/storage/'), ('Системные приложения', '/system/priv-app/'), ('Временные файлы', '/data/local/tmp/')]:
            button = self.button(label, lambda checked=False, p=path: self.navigate(p), icon='folder', help_key='Быстро откроет эту папку в памяти автомобиля.'); button.setProperty('feature', 'files'); button.setProperty('quiet', True); bookmarks.addWidget(button); self.bookmark_buttons.append(button)
        card.addWidget(self.bookmarks_widget)
        self.push_button = self.button('Передать в автомобиль', self.push_files, True, icon='upload', help_key='Выберите файлы на компьютере. Они будут скопированы в открытую папку автомобиля.')
        self.pull_button = self.button('Скачать на компьютер', self.pull_files, icon='download', help_key='Сохранит выбранные файлы и папки на компьютер. Исходные файлы в автомобиле останутся.')
        self.more_button = self.button('Ещё', lambda: None, icon='more', help_key='Создание папки, переименование, удаление и установка выбранного APK.')
        self.more_menu = QMenu(self); self.more_menu.setToolTipsVisible(True); self.more_actions = {}
        for key, handler, feature, icon in [('Создать папку', self.mkdir, 'files.write', 'add'), ('Переименовать', self.rename, 'files.write', 'rename'), ('Установить APK', self.install_remote, 'apk.install', 'apk'), ('Удалить', self.delete, 'files.write', 'delete')]:
            action = self.more_menu.addAction(ui_icon(icon), self.t(key)); self.bind(action, key); action.setProperty('feature', feature); action.triggered.connect(handler); self.more_actions[key] = action
            help_key = {'Создать папку': 'Создаст новую папку внутри открытой папки автомобиля.', 'Переименовать': 'Изменит имя одного выбранного файла или папки.', 'Установить APK': 'Проверит выбранный APK в памяти автомобиля и установит его как приложение.', 'Удалить': 'Удалит выбранные файлы и папки из автомобиля. Отменить это действие нельзя.'}[key]
            self.bind(action, help_key, 'setToolTip'); action.setProperty('danger', key == 'Удалить')
        self.bookmark_menu = self.more_menu.addMenu(ui_icon('folder'), self.t('Путь на ГУ')); self.bind(self.bookmark_menu, 'Путь на ГУ', 'setTitle'); self.bookmark_actions = []
        for button, remote_path in zip(self.bookmark_buttons, ('/sdcard/', '/sdcard/Download/', '/storage/', '/system/priv-app/', '/data/local/tmp/')):
            action = self.bookmark_menu.addAction(ui_icon('folder'), button.text()); action.setProperty('feature', 'files'); action.triggered.connect(lambda checked=False, p=remote_path: self.navigate(p)); self.bookmark_actions.append(action)
        self.more_button.setMenu(self.more_menu); actions = QHBoxLayout(); actions.setSpacing(8)
        for button in (self.push_button, self.pull_button, self.more_button): actions.addWidget(button)
        actions.addStretch(1); card.addLayout(actions)
        listing = self.card('Содержимое папки'); self.list_summary = QLabel(); self.list_summary.setObjectName('subtitle'); listing.addWidget(self.list_summary)
        self.listing_title = listing.itemAt(0).widget(); listing.setAlignment(Qt.AlignmentFlag(0)); listing.parentWidget().setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.file_table = table([self.t(k) for k in ('Имя', 'Тип', 'Размер', 'Дата')]); self.file_table.setMinimumHeight(120); self.file_table.horizontalHeader().setMinimumSectionSize(80)
        self.file_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch); self.file_table.cellDoubleClicked.connect(self.open_entry); self.file_table.itemSelectionChanged.connect(self.update_actions)
        self.file_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.file_table.customContextMenuRequested.connect(self.open_context_menu); listing.addWidget(self.file_table, 1)
        self.empty_files = EmptyState(self.t('Откройте память автомобиля'), self.t('Подключите автомобиль и нажмите «Обновить». Файлы появятся здесь.'), icon='folder'); listing.addWidget(self.empty_files)
        self.layout.setStretch(self.layout.count() - 1, 1)
        self.progress = QProgressBar(self); self.progress.setValue(0); self.progress.hide(); self.log = logbox(); self.log.setParent(self); self.log.hide(); self.update_actions()

    def resizeEvent(self, event):
        super().resizeEvent(event); self.adapt_layout()

    def adapt_layout(self):
        if not hasattr(self, 'toolbar_frame'): return
        compact = self.height() < 500 or self.width() < 820
        self.toolbar_title.setVisible(not compact); self.toolbar_description.setVisible(not compact)
        self.bookmarks_widget.setVisible(not compact); self.listing_title.setVisible(not compact)
        self.bookmark_menu.menuAction().setVisible(compact)
        self.up_button.setText('' if compact else self.t('Вверх')); self.up_button.setFixedWidth(44 if compact else self.up_button.sizeHint().width())
        self.toolbar_layout.invalidate()
        height = self.toolbar_layout.heightForWidth(max(1, self.width())) if self.toolbar_layout.hasHeightForWidth() else self.toolbar_layout.minimumSize().height()
        self.toolbar_frame.setMinimumHeight(max(0, height)); self.toolbar_frame.updateGeometry()

    def open_context_menu(self, position):
        self.update_actions(); self.more_menu.exec(self.file_table.viewport().mapToGlobal(position))

    def update_actions(self):
        ready = bool(self.main.target) and not self.main.busy and self.main.allowed('files', False); selected = self.selected() if hasattr(self, 'file_table') else []
        for widget in [self.up_button, self.refresh_button, self.path, *self.bookmark_buttons]: widget.setEnabled(ready)
        self.push_button.setEnabled(ready and self.main.allowed('files.write', False)); self.pull_button.setEnabled(ready and bool(selected))
        enabled = {'Создать папку': ready, 'Переименовать': ready and len(selected) == 1, 'Удалить': ready and bool(selected), 'Установить APK': ready and len(selected) == 1 and not selected[0]['directory'] and selected[0]['name'].lower().endswith('.apk')}
        for key, action in self.more_actions.items(): action.setEnabled(bool(enabled[key]) and self.main.allowed(action.property('feature'), False))
        for action in self.bookmark_actions: action.setEnabled(ready)
        self.more_button.setEnabled(ready or any(action.isEnabled() for action in self.more_actions.values()))
        self.list_summary.setText(self.t('Объектов: {count} · Выбрано: {selected}', count=len(self.entries), selected=len(selected)))

    def retranslate(self):
        super().retranslate(); self.file_table.setHorizontalHeaderLabels([self.t(k) for k in ('Имя', 'Тип', 'Размер', 'Дата')]); self.update_actions()
        for action, button in zip(self.bookmark_actions, self.bookmark_buttons): action.setText(button.text())
        self.adapt_layout()
        if not self.entries:
            self.empty_files.title.setText(self.t('Папка пуста' if getattr(self, 'loaded', False) else 'Откройте память автомобиля'))
            self.empty_files.description.setText(self.t('В этой папке пока нет файлов. Можно передать их с компьютера.' if getattr(self, 'loaded', False) else 'Подключите автомобиль и нажмите «Обновить». Файлы появятся здесь.'))

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
            item.setIcon(ui_icon('folder' if entry['directory'] else 'link' if entry['symlink'] else 'apk' if entry['name'].lower().endswith('.apk') else 'file'))
        self.loaded = True; self.file_table.setVisible(bool(entries)); self.empty_files.setVisible(not entries); self.retranslate()

    def selected(self):
        entries = []
        for index in self.file_table.selectionModel().selectedRows():
            item = self.file_table.item(index.row(), 0)
            entry = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(entry, dict): entries.append(entry)
        return entries

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
        card = self.card('Приложения в автомобиле', 'Выберите приложение, чтобы открыть его на нужном экране или изменить его состояние.')
        self.toolbar_layout = card; self.toolbar_frame = card.parentWidget(); self.toolbar_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toolbar_title = card.itemAt(0).widget(); self.toolbar_description = card.itemAt(1).widget()
        self.filter = QComboBox(); self.filter_keys = ['Все', 'Сторонние', 'Системные', 'Отключённые']; self.filter.addItems([self.t(k) for k in self.filter_keys]); self.filter.setProperty('feature', 'apps')
        self.bind(self.filter, 'Покажет все приложения или только выбранную группу.', 'setToolTip')
        self.search = self.edit('Найти приложение'); self.search.textChanged.connect(self.filter_rows)
        self.refresh_button = self.button('Обновить', self.refresh, icon='refresh', help_key='Получит свежий список приложений из автомобиля.')
        filters = QHBoxLayout(); filters.setSpacing(12); filters.addWidget(self.filter); filters.addWidget(self.search, 1); filters.addWidget(self.refresh_button); card.addLayout(filters)
        self.selection_title = self.label('Выберите приложение из списка', 'section'); self.selection_title.setWordWrap(True); card.addWidget(self.selection_title)
        self.selection_note = self.hint('Системные приложения могут отвечать за функции автомобиля. Если назначение неизвестно, оставьте их включёнными.'); card.addWidget(self.selection_note)
        self.display = QComboBox(); self.display.addItems([self.t('Центральный') + ' · 1', self.t('Пассажирский') + ' · 2']); self.bind(self.display, 'Выберите экран, на котором откроется приложение.', 'setToolTip'); self.display.setProperty('feature', 'apps')
        self.launch_button = self.button('Открыть приложение', self.launch, True, icon='play', help_key='Откроет выбранное приложение на центральном или пассажирском экране.')
        self.stop_button = self.button('Остановить', self.force_stop, icon='stop', help_key='Закроет выбранное приложение. Его настройки и файлы останутся.')
        self.export_button = self.button('Сохранить APK', self.export, icon='download', help_key='Скачает установочные файлы выбранного приложения на компьютер. Само приложение останется в автомобиле.')
        self.more_button = self.button('Ещё', lambda: None, icon='more', help_key='Включение, отключение, очистка данных и удаление выбранного приложения.')
        self.more_menu = QMenu(self); self.more_menu.setToolTipsVisible(True); self.more_actions = {}
        for key, handler, feature, icon in [('Отключить приложение', self.disable, 'apps.freeze', 'stop'), ('Включить приложение', self.enable, 'apps.freeze', 'play'), ('Очистить данные и кэш', self.clear_data, 'apps.clear', 'delete'), ('Удалить приложение', self.uninstall, 'apps.uninstall', 'delete')]:
            action = self.more_menu.addAction(ui_icon(icon), self.t(key)); self.bind(action, key); action.setProperty('feature', feature); action.triggered.connect(handler); self.more_actions[key] = action
            help_key = {'Отключить приложение': 'Приложение перестанет запускаться. Его можно включить обратно.', 'Включить приложение': 'Снова разрешит запуск ранее отключённого приложения.', 'Очистить данные и кэш': 'Удалит настройки и личные данные внутри приложения. Само приложение останется.', 'Удалить приложение': 'Удалит выбранное приложение из автомобиля. Сначала потребуется подтверждение.'}[key]
            self.bind(action, help_key, 'setToolTip'); action.setProperty('danger', key in ('Очистить данные и кэш', 'Удалить приложение'))
        self.secondary_actions = {}
        for key, handler, icon, help_key in [('Остановить', self.force_stop, 'stop', 'Закроет выбранное приложение. Его настройки и файлы останутся.'), ('Сохранить APK', self.export, 'download', 'Скачает установочные файлы выбранного приложения на компьютер. Само приложение останется в автомобиле.')]:
            action = self.more_menu.addAction(ui_icon(icon), self.t(key)); self.bind(action, key); self.bind(action, help_key, 'setToolTip'); action.setProperty('feature', 'apps'); action.triggered.connect(handler); self.secondary_actions[key] = action
        self.more_button.setMenu(self.more_menu); self.action_row = QHBoxLayout(); self.action_row.setSpacing(8)
        for widget in (self.display, self.launch_button, self.stop_button, self.export_button, self.more_button): self.action_row.addWidget(widget)
        self.action_row.addStretch(1); card.addLayout(self.action_row)
        listing = self.card('Список приложений'); self.list_summary = QLabel(); self.list_summary.setObjectName('subtitle'); listing.addWidget(self.list_summary)
        self.listing_title = listing.itemAt(0).widget(); listing.setAlignment(Qt.AlignmentFlag(0)); listing.parentWidget().setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.package_table = table([self.t('Приложение')]); self.package_table.setMinimumHeight(120); self.package_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.package_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.package_table.itemSelectionChanged.connect(self.update_actions); self.package_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.package_table.customContextMenuRequested.connect(self.open_context_menu)
        listing.addWidget(self.package_table, 1); self.empty_apps = EmptyState(self.t('Получите список приложений'), self.t('Подключите автомобиль и нажмите «Обновить». Затем выберите нужное приложение.'), icon='apk'); listing.addWidget(self.empty_apps)
        self.layout.setStretch(self.layout.count() - 1, 1); self.log = logbox(); self.log.setParent(self); self.log.hide(); self.filter.currentIndexChanged.connect(self.refresh); self.update_actions()

    def resizeEvent(self, event):
        super().resizeEvent(event); self.adapt_layout()

    def adapt_layout(self):
        if not hasattr(self, 'secondary_actions'): return
        compact = self.height() < 500 or self.width() < 820
        self.toolbar_title.setVisible(not compact); self.toolbar_description.setVisible(not compact)
        self.selection_title.setVisible(not compact); self.selection_note.setVisible(not compact); self.listing_title.setVisible(not compact)
        all_width = sum(widget.sizeHint().width() for widget in (self.display, self.launch_button, self.stop_button, self.export_button, self.more_button)) + 32
        secondary = compact or all_width > self.width() - 32
        self.stop_button.setVisible(not secondary); self.export_button.setVisible(not secondary)
        for action in self.secondary_actions.values(): action.setVisible(secondary)
        self.toolbar_layout.invalidate()
        height = self.toolbar_layout.heightForWidth(max(1, self.width())) if self.toolbar_layout.hasHeightForWidth() else self.toolbar_layout.minimumSize().height()
        self.toolbar_frame.setMinimumHeight(max(0, height)); self.toolbar_frame.updateGeometry()

    def open_context_menu(self, position):
        self.update_actions(); self.more_menu.exec(self.package_table.viewport().mapToGlobal(position))

    def update_actions(self):
        item = self.package_table.item(self.package_table.currentRow(), 0); package = item.text() if item else ''
        ready = bool(self.main.target) and not self.main.busy and self.main.allowed('apps', False); selected = bool(PACKAGE_RE.fullmatch(package))
        self.refresh_button.setEnabled(ready); self.filter.setEnabled(ready); self.search.setEnabled(self.main.allowed('apps', False))
        for button in [self.launch_button, self.stop_button, self.export_button]: button.setEnabled(ready and selected)
        self.display.setEnabled(ready and selected)
        for action in self.more_actions.values(): action.setEnabled(ready and selected and self.main.allowed(action.property('feature'), False))
        for action in self.secondary_actions.values(): action.setEnabled(ready and selected)
        self.more_button.setEnabled(any(action.isEnabled() for action in [*self.more_actions.values(), *self.secondary_actions.values()]))
        self.selection_title.setText(package if selected else self.t('Выберите приложение из списка'))
        self.package_table.setToolTip(self.t('Системные приложения могут отвечать за функции автомобиля. Если назначение неизвестно, оставьте их включёнными.'))
        self.list_summary.setText(self.t('Найдено: {count}', count=self.package_table.rowCount()))

    def retranslate(self):
        super().retranslate()
        for i, k in enumerate(self.filter_keys): self.filter.setItemText(i, self.t(k))
        self.package_table.setHorizontalHeaderLabels([self.t('Приложение')]); self.filter_rows()
        self.display.setItemText(0, self.t('Центральный') + f" · {self.main.display_map['center']}")
        self.display.setItemText(1, self.t('Пассажирский') + f" · {self.main.display_map['passenger']}")
        self.adapt_layout()

    @feature_required('apps', 'apps')
    def refresh(self):
        if not self.main.ready(): return
        flags = [[], ['-3'], ['-s'], ['-d']][self.filter.currentIndex()]
        def done(ok, results):
            if ok:
                self.loaded = True; self.packages = sorted(line[8:].strip() for line in results[0].text.splitlines() if line.startswith('package:')); self.filter_rows()
        self.main.sequence(self.t('Приложения'), [Step(['pm', 'list', 'packages', '--user', '0'] + flags)], done)

    def filter_rows(self):
        current = self.package_table.item(self.package_table.currentRow(), 0); selected = current.text() if current else ''
        packages = [p for p in self.packages if self.search.text().strip().lower() in p.lower()]
        self.package_table.setRowCount(len(packages))
        for row, pkg in enumerate(packages):
            item = QTableWidgetItem(pkg); item.setIcon(ui_icon('apk')); self.package_table.setItem(row, 0, item)
            if pkg == selected: self.package_table.selectRow(row)
        self.package_table.setVisible(bool(packages)); self.empty_apps.setVisible(not packages)
        searched = bool(self.search.text().strip()); loaded = bool(getattr(self, 'loaded', False))
        self.empty_apps.title.setText(self.t('Приложения не найдены' if searched or loaded else 'Получите список приложений'))
        self.empty_apps.description.setText(self.t('Попробуйте другое название или измените фильтр.' if searched or loaded else 'Подключите автомобиль и нажмите «Обновить». Затем выберите нужное приложение.')); self.update_actions()

    def selected(self):
        row = self.package_table.currentRow()
        item = self.package_table.item(row, 0); pkg = item.text() if item else ''
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
        super().__init__(main); self.action_buttons = []
        card = self.card('Масштаб и дисплеи', 'Подберите удобный размер текста и элементов на выбранных экранах.')
        self.display_info = self.label('Параметры экранов ещё не проверены', 'subtitle'); self.display_info.setWordWrap(True); card.addWidget(self.display_info)
        form = QGridLayout(); form.setHorizontalSpacing(16); form.setVerticalSpacing(8)
        form.addWidget(self.label('Экран'), 0, 0); form.addWidget(self.label('Масштаб интерфейса'), 0, 1)
        self.display = QComboBox(); self.display_keys = ['Все мультимедийные', 'Центральный', 'Пассажирский', 'Приборная панель']; self.display.addItems([self.t(k) for k in self.display_keys]); self.display.currentIndexChanged.connect(self.update_actions)
        self.dpi = QComboBox(); self.dpi.setEditable(True); self.dpi.addItems(['140', '150', '160']); self.dpi.setCurrentText('160')
        form.addWidget(self.display, 1, 0); form.addWidget(self.dpi, 1, 1); form.setColumnStretch(0, 1); form.setColumnStretch(1, 1); card.addLayout(form)
        self.row(card, self.action_button('Применить масштаб', lambda: self.set_density(False), 'tweaks.dpi', icon='sliders', accent=True, help_key='Изменит размер текста и кнопок на выбранном экране. Большее число делает элементы крупнее. Приборная панель требует отдельного подтверждения.'), self.action_button('Вернуть заводской масштаб', lambda: self.set_density(True), 'tweaks.dpi', icon='undo', help_key='Уберёт пользовательский масштаб и вернёт заводской размер элементов на выбранных экранах.'), self.action_button('Проверить экраны', self.refresh_density, 'tweaks.dpi', icon='monitor', help_key='Прочитает текущие размеры и масштаб экранов. Ничего не меняет.'))
        self.row(card, self.action_button('Сопоставить экраны', self.map_displays, 'tweaks.dpi', icon='settings', help_key='Поможет указать, какой экран является центральным, пассажирским и приборным, если прошивка использует другой порядок.'))
        card = self.card('Аудиофокус и разрешения', 'Выберите приложение и настройте, к каким возможностям автомобиля у него есть доступ.')
        self.package = self.edit('Введите адрес приложения, например ru.vk.store'); self.package.textChanged.connect(self.update_actions); card.addWidget(self.package)
        permissions = ResponsiveGrid(min_card_width=260, max_columns=3); card.addWidget(permissions)
        definitions = [
            ('volume', 'Музыка без пауз', 'Не давайте выбранному приложению прерывать музыку.', 'Не глушить музыку', lambda: self.app_command(['cmd', 'appops', 'set', '{pkg}', 'TAKE_AUDIO_FOCUS', 'ignore'], ['cmd', 'appops', 'get', '{pkg}', 'TAKE_AUDIO_FOCUS'], 'ignore'), 'Вернуть аудиофокус', lambda: self.app_command(['cmd', 'appops', 'set', '{pkg}', 'TAKE_AUDIO_FOCUS', 'allow'], ['cmd', 'appops', 'get', '{pkg}', 'TAKE_AUDIO_FOCUS'], 'allow')),
            ('mic', 'Доступ к микрофону', 'Разрешите выбранному приложению записывать голос.', 'Разрешить микрофон', lambda: self.grant('android.permission.RECORD_AUDIO'), None, None),
            ('eye', 'Поверх других окон', 'Разрешите небольшие окна приложения поверх экрана.', 'Разрешить поверх окон', lambda: self.app_command(['appops', 'set', '{pkg}', 'SYSTEM_ALERT_WINDOW', 'allow'], ['appops', 'get', '{pkg}', 'SYSTEM_ALERT_WINDOW'], 'allow'), None, None),
            ('settings', 'Скрытые настройки', 'Дайте настройщикам и переназначателям кнопок расширенный доступ.', 'Дать доступ к настройкам', lambda: self.grant('android.permission.WRITE_SECURE_SETTINGS'), None, None),
            ('shield', 'Работа в фоне', 'Помогите приложению работать при экономии энергии.', 'Не ограничивать в фоне', lambda: self.app_command(['dumpsys', 'deviceidle', 'whitelist', '+{pkg}'], ['dumpsys', 'deviceidle', 'whitelist'], '{pkg}'), None, None),
        ]
        for icon, title, explanation, primary, callback, secondary, secondary_callback in definitions:
            panel, box = self.tile(icon, title, explanation)
            box.addWidget(self.action_button(primary, callback, 'tweaks.permissions', icon=icon, needs_package=True, help_key=explanation))
            if secondary: box.addWidget(self.action_button(secondary, secondary_callback, 'tweaks.permissions', icon='undo', needs_package=True, help_key='Вернёт выбранному приложению возможность приостанавливать музыку, когда это нужно.'))
            permissions.addWidget(panel)
        panel, box = self.tile('shield', 'Режим экономии энергии', 'Управляйте общими ограничениями работы приложений в фоне.')
        box.addWidget(self.action_button('Отключить экономию', lambda: self.deviceidle('disable'), 'tweaks.permissions', icon='shield', help_key='Снимет общие ограничения фоновой работы приложений. Это может увеличить расход энергии.'))
        box.addWidget(self.action_button('Вернуть экономию', lambda: self.deviceidle('enable'), 'tweaks.permissions', icon='undo', help_key='Снова разрешит системе ограничивать приложения в фоне для экономии энергии.')); permissions.addWidget(panel)
        card = self.card('Сеть и система', 'Полезные настройки интернета и внешнего вида. Для возврата сохранены прежние значения.')
        network = ResponsiveGrid(min_card_width=280, max_columns=3); card.addWidget(network)
        features = [
            ('shield', 'Фильтр рекламы', 'Использует AdGuard для фильтрации сетевых адресов. Доступность зависит от сети.', 'dns', 'Включить фильтр', 'Выключить фильтр'),
            ('wifi', 'Значок Wi-Fi без интернета', 'Можно убрать предупреждение, если сеть машины работает без доступа в интернет.', 'captive', 'Убрать предупреждение', 'Вернуть проверку'),
            ('eye', 'Больше места на экране', 'Скрывает верхнюю панель системы, чтобы приложение занимало больше места.', 'immersive', 'Скрыть верхнюю панель', 'Вернуть верхнюю панель'),
        ]
        for icon, title, explanation, key, on, off in features:
            panel, box = self.tile(icon, title, explanation)
            box.addWidget(self.action_button(on, lambda checked=False, k=key: self.setting_feature(k, True), 'tweaks.network', icon=icon, help_key=explanation))
            box.addWidget(self.action_button(off, lambda checked=False, k=key: self.setting_feature(k, False), 'tweaks.network', icon='undo', help_key='Вернёт обычное поведение этой функции.'))
            restore = self.action_button('Восстановить прежнее значение', lambda checked=False, k=key: self.restore_feature(k), 'tweaks.network', icon='undo', help_key='Вернёт значение, которое было в машине до первого изменения через эту программу.')
            restore.setProperty('restoreKey', key); box.addWidget(restore)
            hint = self.label('Результат проверяется после изменения', 'subtitle'); hint.setWordWrap(True); box.addWidget(hint); network.addWidget(panel)
        self.row(card, self.action_button('Открыть настройки Android', lambda: self.main.sequence(self.t('Скрытые настройки Android'), [Step(['am', 'start', '-a', 'android.settings.SETTINGS'])]) if self.main.ready() else None, 'tweaks.network', icon='settings', help_key='Откроет обычные настройки Android на экране машины. Доступные пункты зависят от прошивки.'))
        card = self.card('Восстановление системы', 'Эти действия меняют системные файлы и перезагружают мультимедийную систему. Перед запуском вы увидите точное описание.')
        repairs = ResponsiveGrid(min_card_width=300, max_columns=2); card.addWidget(repairs)
        panel, box = self.tile('recovery', 'Починить настройки машины', 'Пересоздаёт базу настроек автомобиля. Сначала сохраняет резервную копию на компьютере; личные настройки могут сброситься.')
        box.addWidget(self.action_button('Починить настройки машины', lambda: self.repair('settings'), 'repair.settings', icon='recovery', help_key='Сохранит настройки автомобиля на компьютере и пересоздаст их в машине. Личные настройки могут сброситься. Перед началом программа спросит подтверждение.')); repairs.addWidget(panel)
        panel, box = self.tile('shield', 'Починить verity', 'Отключает проверку системного раздела по процедуре установщика. Требуется расширенный доступ и перезагрузка.')
        box.addWidget(self.action_button('Починить verity', lambda: self.repair('verity'), 'repair.verity', icon='shield', help_key='Отключит проверку системных файлов по процедуре из отчёта и перезагрузит мультимедийную систему. Это не возвращает заводскую защиту.')); repairs.addWidget(panel)
        self.row(card, self.button('Журнал восстановления', self.show_recovery, icon='info', help_key='Откроет сведения о выполненной или прерванной операции и сохранённых резервных копиях.'), self.action_button('Возобновить Android после сбоя', self.recover_android, 'repair.settings', icon='undo', help_key='Попытается вернуть систему в рабочее состояние после прерванного восстановления. Используется только для машины, указанной в журнале.'))
        self.log = logbox(); self.log.hide(); self.layout.addStretch()

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
        self.update_profile(); self.update_actions()

    def update_profile(self):
        p = self.main.profile
        if not self.main.target or not p.api:
            self.display_info.setText(self.t('Параметры экранов ещё не проверены'))
        else:
            density = p.raw.get('density', '').strip()
            self.display_info.setText('Android ' + str(p.release) + '  ·  ' + self.t('Доступные экраны') + ': ' + ', '.join(str(i) for i in p.displays) + ('\n' + density if density else ''))
        self.update_actions()

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

    def tile(self, icon_name, title, explanation):
        frame = QFrame(); frame.setObjectName('card'); box = QVBoxLayout(frame); box.setContentsMargins(18, 18, 18, 18); box.setSpacing(12)
        heading = QHBoxLayout(); icon = QLabel(); icon.setPixmap(ui_icon(icon_name).pixmap(26, 26)); heading.addWidget(icon); heading.addWidget(self.label(title, 'section'), 1); box.addLayout(heading)
        description = self.label(explanation); description.setWordWrap(True); box.addWidget(description); box.addStretch(); return frame, box

    def action_button(self, key, callback, feature, icon=None, accent=False, help_key=None, needs_package=False):
        button = self.button(key, callback, accent, icon=icon, help_key=help_key); button.setProperty('feature', feature); button.setProperty('needsPackage', needs_package); self.action_buttons.append(button); return button

    def update_actions(self):
        if not hasattr(self, 'action_buttons'): return
        base = bool(self.main.target and not self.main.busy and self.main.allowed('tweaks', False))
        pkg_ok = bool(hasattr(self, 'package') and PACKAGE_RE.fullmatch(self.package.text().strip()))
        for button in self.action_buttons:
            feature = button.property('feature'); enabled = base and self.main.allowed(feature, False)
            if button.property('needsPackage'): enabled = enabled and pkg_ok
            if feature.startswith('repair.'):
                enabled = enabled and self.main.allowed('device.root', False) and self.main.allowed('device.reboot', False)
            restore = button.property('restoreKey')
            if restore: enabled = enabled and (restore == 'immersive' or self.main.settings.contains(self.saved_key(restore)))
            if feature == 'tweaks.dpi' and hasattr(self, 'display') and self.main.profile.api:
                ids = self.selected_displays(); enabled = enabled and all(i in self.main.profile.displays for i in ids) and (self.main.profile.per_display or all(i == 0 for i in ids))
            button.setEnabled(bool(enabled))
        if hasattr(self, 'display'): self.display.setEnabled(not self.main.busy)
        if hasattr(self, 'dpi'): self.dpi.setEnabled(not self.main.busy)

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
        card = self.card('Терминал ADB', 'Отправляйте свои команды и читайте ответы автомобиля. Используйте этот раздел, если понимаете, что делает команда.')
        self.toolbar_layout = card; self.toolbar_frame = card.parentWidget(); self.toolbar_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toolbar_title = card.itemAt(0).widget(); self.toolbar_description = card.itemAt(1).widget()
        self.state_label = self.label('Готов к команде', 'subtitle'); card.addWidget(self.state_label)
        self.shell_button = self.button('Интерактивное подключение', self.open_shell, icon='terminal', help_key='Откроет постоянное подключение для команд. Следующие строки отправляются прямо в автомобиль.')
        self.stop_button = self.button('Остановить', self.stop, icon='stop', help_key='Прервёт выполняющуюся команду или закроет интерактивное подключение.')
        self.more_button = self.button('Ещё', lambda: None, icon='more', help_key='Сохранение вывода и очистка окна терминала.')
        self.more_menu = QMenu(self); self.clear_action = self.more_menu.addAction(ui_icon('delete'), self.t('Очистить вывод')); self.bind(self.clear_action, 'Очистить вывод'); self.clear_action.triggered.connect(self.output_clear)
        self.save_action = self.more_menu.addAction(ui_icon('save'), self.t('Сохранить вывод')); self.bind(self.save_action, 'Сохранить вывод'); self.save_action.triggered.connect(lambda: self.save_text(self.output.toPlainText(), 'voyah-terminal.txt'))
        self.more_menu.setToolTipsVisible(True); self.bind(self.clear_action, 'Уберёт текст из окна терминала. Команды и их история останутся.', 'setToolTip'); self.bind(self.save_action, 'Сохранит весь отображаемый вывод в текстовый файл на компьютере.', 'setToolTip')
        self.more_button.setMenu(self.more_menu); actions = QHBoxLayout(); actions.setSpacing(8)
        for button in (self.shell_button, self.stop_button, self.more_button): actions.addWidget(button)
        actions.addStretch(1); card.addLayout(actions)
        console = self.card('Ответы устройства'); self.output = logbox(); self.output.setMinimumHeight(120); self.bind(self.output, 'Здесь появятся команда и её результат. История команд доступна стрелками вверх и вниз.', 'setPlaceholderText'); console.addWidget(self.output, 1)
        self.console_title = console.itemAt(0).widget(); console.setAlignment(Qt.AlignmentFlag(0)); console.parentWidget().setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding); self.output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.input = self.bind(TerminalInput(), 'Введите adb … или adb shell …', 'setPlaceholderText'); self.input.returnPressed.connect(self.run_command); self.input.history_move.connect(self.move_history); self.input.textChanged.connect(self.update_actions)
        self.bind(self.input, 'Введите команду и нажмите Enter. Стрелки вверх и вниз выбирают предыдущие команды.', 'setToolTip'); self.input.setProperty('feature', 'terminal')
        self.run_button = self.button('Выполнить', self.run_command, True, icon='play', help_key='Отправит введённую команду. Ответ появится в окне выше.')
        command = QHBoxLayout(); command.setSpacing(12); command.addWidget(self.input, 1); command.addWidget(self.run_button); console.addLayout(command)
        self.command_note = self.hint('Для команды, обращающейся к автомобилю, сначала выберите подключённое устройство. Команды вроде adb devices работают и без него.'); console.addWidget(self.command_note)
        self.layout.setStretch(self.layout.count() - 1, 1); QShortcut(QKeySequence('Ctrl+L'), self, activated=self.output_clear); self.update_actions()

    def resizeEvent(self, event):
        super().resizeEvent(event); self.adapt_layout()

    def adapt_layout(self):
        if not hasattr(self, 'command_note'): return
        compact = self.height() < 500 or self.width() < 820
        self.toolbar_title.setVisible(not compact); self.toolbar_description.setVisible(not compact)
        self.state_label.setVisible(not compact); self.console_title.setVisible(not compact); self.command_note.setVisible(not compact)
        self.toolbar_layout.invalidate()
        height = self.toolbar_layout.heightForWidth(max(1, self.width())) if self.toolbar_layout.hasHeightForWidth() else self.toolbar_layout.minimumSize().height()
        self.toolbar_frame.setMinimumHeight(max(0, height)); self.toolbar_frame.updateGeometry()

    def output_clear(self):
        self.output.clear()

    def update_actions(self):
        allowed = self.main.allowed('terminal', False); shell = self.shell_job is not None; running = self.job is not None
        self.input.setEnabled(allowed and (shell or not self.main.busy)); self.run_button.setEnabled(allowed and bool(self.input.text().strip()) and not running and (shell or not self.main.busy))
        self.stop_button.setEnabled(running or shell); self.shell_button.setEnabled((shell or bool(self.main.target)) and not running and (shell or not self.main.busy) and allowed)
        self.shell_button.setText(self.t('Закрыть подключение' if shell else 'Интерактивное подключение')); self.shell_button.setIcon(ui_icon('stop' if shell else 'terminal'))
        self.run_button.setText(self.t('Отправить' if shell else 'Выполнить'))
        self.state_label.setText(self.t('Постоянное подключение открыто' if shell else 'Команда выполняется…' if running else 'Готов к команде'))

    def retranslate(self):
        super().retranslate(); self.update_actions(); self.adapt_layout()

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
            self.update_actions(); append_log(self.output, '\n[' + (self.t('Отменено') if result.cancelled else self.t('Истекло время ожидания') if result.timed_out else f'exit {result.code}') + ']\n')
        self.job = self.main.adb(tokens, done, global_cmd=global_cmd, timeout=0, stream=lambda value: append_log(self.output, value), check=False)
        self.main.active_job = self.job; self.update_actions()

    @feature_required('terminal')
    def open_shell(self):
        if self.shell_job: self.stop(); return
        if not self.main.ready(): return
        self.record('adb shell'); self.shell_button.setText(self.t('Стоп')); self.run_button.setText(self.t('Отправить'))
        def ended(result):
            self.shell_job = None; self.shell_button.setText(self.t('Интерактивная shell')); self.run_button.setText(self.t('Выполнить'))
            append_log(self.output, '\n[exit ' + str(result.code) + ']\n'); self.update_actions()
        self.shell_job = self.main.adb(['shell'], ended, timeout=0, stream=lambda value: append_log(self.output, value), check=False); self.update_actions()

    def stop(self):
        if self.job: self.job.cancel(); self.job = None
        if self.shell_job: self.shell_job.cancel(); self.shell_job = None
        self.update_actions()

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
        super().__init__(main)
        self.items = []; self.downloader = DownloadService(main); self.service = InstallService(main)
        self.versions = {}; self.version_pending = set(); self.selected_id = ''; self.card_widgets = {}; self.version_labels = {}
        card = self.card('Каталог приложений', 'Выберите готовое приложение. Программа скачает его и установит в машину.')
        row = QHBoxLayout(); row.setSpacing(12)
        self.search = self.edit('Поиск приложений'); self.search.textChanged.connect(self.refresh); row.addWidget(self.search, 1)
        row.addWidget(self.button('Обновить каталог', lambda: main.catalog.refresh(), icon='undo', help_key='Загрузить свежий список приложений. Уже скачанные файлы останутся на компьютере.'))
        card.addLayout(row)
        self.status = QLabel(); self.status.setObjectName('subtitle'); self.status.setWordWrap(True); self.status.setTextFormat(Qt.TextFormat.PlainText); card.addWidget(self.status)
        self.listing = table([self.t(k) for k in ('Приложение', 'Совместимость', 'Версия')]); self.listing.hide()
        self.listing.setParent(self); self.listing.itemSelectionChanged.connect(self.show_details)
        self.catalog_grid = ResponsiveGrid(min_card_width=280, max_columns=3); self.catalog_host = self.catalog_grid; card.addWidget(self.catalog_host)
        self.empty = EmptyState('Каталог пока пуст', 'Администратор ещё не добавил приложения. Когда они появятся, вы сможете выбрать и установить нужное.', icon='apps'); card.addWidget(self.empty)
        detail_card = self.card('Выбранное приложение')
        self.selection_name = QLabel(); self.selection_name.setObjectName('section'); self.selection_name.setWordWrap(True); self.selection_name.setTextFormat(Qt.TextFormat.PlainText); detail_card.addWidget(self.selection_name)
        self.details = QLabel(); self.details.setWordWrap(True); self.details.setTextFormat(Qt.TextFormat.PlainText); self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); detail_card.addWidget(self.details)
        self.selection_status = QLabel(); self.selection_status.setObjectName('subtitle'); self.selection_status.setWordWrap(True); detail_card.addWidget(self.selection_status)
        self.install_btn = self.button('Скачать и установить', self.install, True, icon='download', help_key='Скачает выбранное приложение, проверит его и установит в подключённую машину. Дождитесь сообщения о завершении.')
        self.install_btn.setProperty('feature', 'apk.install'); self.row(detail_card, self.install_btn)
        self.log = logbox(); self.log.hide()
        self.service.log_message.connect(lambda text: append_log(self.log, text))
        self.service.finished.connect(lambda ok: self.refresh())
        main.catalog.changed.connect(self.refresh); self.refresh(); self.layout.addStretch()

    def retranslate(self):
        super().retranslate(); self.listing.setHorizontalHeaderLabels([self.t(k) for k in ('Приложение', 'Совместимость', 'Версия')]); self.refresh()

    def refresh(self):
        store = self.main.catalog
        old_row = self.listing.currentRow()
        chosen = self.items[old_row]['id'] if 0 <= old_row < len(self.items) else self.selected_id
        term = self.search.text().strip().casefold()
        self.items = [a for a in store.profile['apps'] if term in (a['name'] + ' ' + a.get('description', '')).casefold()]
        self.status.setText(self.t(store.message or ('Каталог ещё не настроен' if not store.config.get('repository') else 'Последний сохранённый каталог')) + f"  ·  r{store.profile['revision']}")
        self.listing.blockSignals(True); self.listing.setRowCount(len(self.items))
        while self.catalog_grid.count():
            item = self.catalog_grid.takeAt(0)
            if item and item.widget(): item.widget().deleteLater()
        self.card_widgets = {}; self.version_labels = {}
        for row, entry in enumerate(self.items):
            key = hashlib.sha256((entry['source'] + '\n' + entry.get('asset', '')).encode()).hexdigest()
            known = self.versions.get(entry['source'], self.downloader.index.get(key, {}).get('version', ''))
            version = str(known) if known else self.t('Версия будет проверена перед загрузкой')
            compatible = self.compatibility_text(entry)
            for col, value in enumerate((entry['name'], compatible, version)): self.listing.setItem(row, col, QTableWidgetItem(value))
            frame = QFrame(); frame.setObjectName('catalogCard'); frame.setProperty('selected', False)
            box = QVBoxLayout(frame); box.setContentsMargins(18, 18, 18, 18); box.setSpacing(12)
            heading = QHBoxLayout(); icon = QLabel(); icon.setPixmap(ui_icon('apps').pixmap(28, 28)); heading.addWidget(icon)
            title = QLabel(entry['name']); title.setObjectName('section'); title.setTextFormat(Qt.TextFormat.PlainText); title.setWordWrap(True); heading.addWidget(title, 1); box.addLayout(heading)
            description = QLabel(entry.get('description', '') or self.t('Готовое приложение для вашей машины.')); description.setTextFormat(Qt.TextFormat.PlainText); description.setWordWrap(True); box.addWidget(description)
            badge = QLabel(compatible); badge.setObjectName('subtitle'); badge.setWordWrap(True); box.addWidget(badge)
            version_label = QLabel(version); version_label.setObjectName('subtitle'); version_label.setWordWrap(True); box.addWidget(version_label)
            source = QLabel(urlparse(entry['source']).netloc); source.setObjectName('eyebrow'); source.setToolTip(entry['source']); box.addWidget(source); box.addStretch()
            choose = QPushButton(self.t('Выбрать приложение')); choose.setIcon(ui_icon('check')); choose.setAccessibleName(self.t('Выбрать приложение') + ': ' + entry['name'])
            choose.clicked.connect(lambda checked=False, app_id=entry['id']: self.select_app(app_id)); box.addWidget(choose)
            self.card_widgets[entry['id']] = frame; self.version_labels[entry['id']] = version_label; self.catalog_grid.addWidget(frame)
        row = next((i for i, entry in enumerate(self.items) if entry['id'] == chosen), -1)
        if row < 0 and self.items and not term: row = 0
        self.listing.clearSelection()
        if row >= 0: self.listing.setCurrentCell(row, 0); self.listing.selectRow(row)
        else: self.listing.setCurrentCell(-1, -1)
        self.listing.blockSignals(False)
        self.catalog_host.setVisible(bool(self.items)); self.empty.setVisible(not self.items)
        if not self.items:
            if term:
                title, description = 'Ничего не найдено', 'Попробуйте другое название или очистите строку поиска.'
            elif not store.config.get('repository'):
                title, description = 'Каталог ещё не настроен', 'Администратору нужно указать адрес каталога. Пока можно устанавливать APK с компьютера.'
            else:
                title, description = 'Каталог пока пуст', 'Администратор ещё не добавил приложения. Когда они появятся, вы сможете выбрать и установить нужное.'
            self.empty.title.setText(self.t(title)); self.empty.description.setText(self.t(description))
        self.show_details()

    def show_details(self):
        row = self.listing.currentRow()
        selected = self.items[row] if 0 <= row < len(self.items) else None
        self.selected_id = selected['id'] if selected else ''
        for app_id, frame in self.card_widgets.items():
            frame.setProperty('selected', app_id == self.selected_id); frame.style().unpolish(frame); frame.style().polish(frame); frame.update()
        if selected:
            self.selection_name.setText(selected['name']); self.details.setText(selected.get('description', '') + '\n' + selected['source'])
            self.selection_status.setText(self.compatibility_text(selected))
            source = selected['source']
            try: endpoint = release_endpoint(source)
            except ValueError: endpoint = None
            if endpoint and source not in self.versions and source not in self.version_pending:
                self.version_pending.add(source)
                def peeked(result):
                    self.version_pending.discard(source)
                    if result['error']: return
                    try: version = str(json.loads(result['body'])['tag_name'])
                    except (ValueError, KeyError): return
                    self.versions[source] = version
                    for index, entry in enumerate(self.items):
                        if entry['source'] == source:
                            self.listing.item(index, 2).setText(version)
                            if entry['id'] in self.version_labels: self.version_labels[entry['id']].setText(version)
                self.main.web.request(endpoint, peeked)
        else:
            self.selection_name.setText(self.t('Выберите приложение')); self.details.setText(self.t('Нажмите «Выбрать приложение» на карточке выше.')); self.selection_status.clear()
        self.update_actions()

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

    def compatibility_text(self, entry):
        if not entry.get('enabled', True): return self.t('Отключено администратором')
        profile = self.main.profile
        if profile.api and entry.get('min_sdk', 1) > profile.api: return self.t('Нужна более новая версия Android')
        if entry.get('abis') and profile.abis and not set(entry['abis']).intersection(profile.abis): return self.t('Не подходит подключённой машине')
        if not self.main.target: return self.t('Совместимость проверим после подключения')
        if not profile.api: return self.t('Проверяем параметры машины…')
        return self.t('Первичная проверка пройдена; APK проверим перед установкой')

    def select_app(self, app_id):
        row = next((i for i, entry in enumerate(self.items) if entry['id'] == app_id), -1)
        if row >= 0: self.listing.setCurrentCell(row, 0); self.listing.selectRow(row); self.show_details()

    def update_actions(self):
        if not hasattr(self, 'install_btn'): return
        row = self.listing.currentRow(); selected = self.items[row] if 0 <= row < len(self.items) else None
        allowed = self.main.allowed('apk.install', False) and self.main.allowed('catalog', False)
        compatible = bool(selected and selected.get('enabled', True))
        if selected and self.main.profile.api: compatible = compatible and selected.get('min_sdk', 1) <= self.main.profile.api
        if selected and selected.get('abis') and self.main.profile.abis: compatible = compatible and bool(set(selected['abis']).intersection(self.main.profile.abis))
        self.install_btn.setEnabled(bool(allowed and compatible and self.main.target and self.main.profile.api and not self.main.busy))

class KeyboardPage(Page):
    def __init__(self, main):
        super().__init__(main); self.downloader = DownloadService(main); self.items = []
        card = self.card('Клавиатуры', 'Один комплект обновляет клавиатуры центрального и пассажирского экранов.')
        self.row(card, self.hint('Выберите комплект из списка. До установки программа проверит оба файла и сохранит штатные клавиатуры.'))
        row = QHBoxLayout(); row.setSpacing(12)
        self.combo = QComboBox(); self.combo.setMinimumContentsLength(20); self.combo.currentIndexChanged.connect(self.describe); row.addWidget(self.combo, 1)
        row.addWidget(self.button('Обновить каталог', lambda: main.catalog.refresh(), icon='undo', help_key='Получить актуальный список клавиатур, который опубликовал администратор.')); card.addLayout(row)
        self.empty = EmptyState('Комплектов пока нет', 'Администратор ещё не добавил ссылки на клавиатуры. Штатные клавиатуры можно восстановить отдельно.', icon='keyboard'); card.addWidget(self.empty)
        self.description = QLabel(); self.description.setTextFormat(Qt.TextFormat.PlainText); self.description.setWordWrap(True); card.addWidget(self.description)
        self.compatibility = QLabel(); self.compatibility.setObjectName('subtitle'); self.compatibility.setWordWrap(True); card.addWidget(self.compatibility)
        screens = ResponsiveGrid(min_card_width=260, max_columns=2); card.addWidget(screens)
        self.screen_panels = []
        for title, explanation in [('Центральный экран', 'Клавиатура для ввода на основном экране автомобиля.'), ('Пассажирский экран', 'Клавиатура для ввода на экране переднего пассажира.')]:
            panel = QFrame(); panel.setObjectName('card'); box = QVBoxLayout(panel); box.setContentsMargins(18, 18, 18, 18); box.setSpacing(12)
            icon = QLabel(); icon.setPixmap(ui_icon('monitor').pixmap(30, 30)); box.addWidget(icon); box.addWidget(self.label(title, 'section'))
            description = self.label(explanation); description.setWordWrap(True); box.addWidget(description)
            note = self.label('Оба файла будут проверены перед установкой', 'subtitle'); note.setWordWrap(True); box.addWidget(note)
            screens.addWidget(panel); self.screen_panels.append(panel)
        self.install_btn = self.button('Скачать и установить комплект', self.install, True, icon='download', help_key='Скачает две клавиатуры, сохранит текущие файлы и заменит их. Машина перезагрузит мультимедийную систему. Перед началом вы увидите подтверждение.')
        self.install_btn.setProperty('feature', 'keyboard.install'); self.row(card, self.install_btn)
        backup = self.card('Штатные клавиатуры и резервные копии', 'Старые файлы сохраняются в машине и дополнительно на компьютере. Уже существующие штатные копии не перезаписываются.')
        self.restore_btn = self.button('Восстановить штатные клавиатуры', self.restore, icon='undo', help_key='Вернёт сохранённые штатные клавиатуры для обоих экранов. Текущие файлы тоже будут сохранены на компьютере перед заменой.')
        self.restore_btn.setProperty('feature', 'keyboard.restore'); self.row(backup, self.restore_btn)
        note = self.label('Установка и восстановление требуют расширенного доступа. Программа спросит подтверждение и покажет все этапы в журнале.', 'subtitle'); note.setWordWrap(True); backup.addWidget(note)
        self.log = logbox(); self.log.hide(); main.catalog.changed.connect(self.refresh); self.refresh(); self.layout.addStretch()

    def refresh(self):
        index = self.combo.currentIndex(); old_id = self.items[index]['id'] if 0 <= index < len(self.items) else ''
        self.items = self.main.catalog.profile['keyboards']; self.combo.blockSignals(True); self.combo.clear()
        for entry in self.items: self.combo.addItem(entry['name'], entry['id'])
        chosen = next((i for i, entry in enumerate(self.items) if entry['id'] == old_id), 0 if self.items else -1)
        self.combo.setCurrentIndex(chosen); self.combo.blockSignals(False); self.describe()

    def retranslate(self):
        super().retranslate(); self.empty.title.setText(self.t('Комплектов пока нет')); self.empty.description.setText(self.t('Администратор ещё не добавил ссылки на клавиатуры. Штатные клавиатуры можно восстановить отдельно.')); self.describe()

    def describe(self):
        index = self.combo.currentIndex(); entry = self.items[index] if 0 <= index < len(self.items) else None
        self.empty.setVisible(not self.items); self.combo.setVisible(bool(self.items))
        self.description.setVisible(bool(entry)); self.compatibility.setVisible(bool(entry))
        for panel in self.screen_panels: panel.setVisible(bool(entry))
        self.description.setText(entry.get('description', '') if entry else '')
        if entry:
            models = entry.get('models', KEYBOARD_MODELS)
            if not entry.get('enabled', True): text = self.t('Отключено администратором')
            elif not self.main.target: text = self.t('Подключите машину, чтобы проверить совместимость')
            elif self.main.profile.model_code not in models: text = self.t('Этот комплект не подходит подключённой машине')
            else: text = self.t('Модель поддерживается. Оба файла проверим перед заменой.')
            self.compatibility.setText(text)
        self.update_actions()

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

    def update_actions(self):
        if not hasattr(self, 'install_btn'): return
        base = bool(self.main.target and not self.main.busy and self.main.allowed('keyboards', False) and self.main.allowed('device.root', False) and self.main.allowed('device.reboot', False))
        index = self.combo.currentIndex(); entry = self.items[index] if 0 <= index < len(self.items) else None
        model_ok = self.main.profile.model_code in KEYBOARD_MODELS
        install_ok = bool(entry and entry.get('enabled', True) and self.main.profile.model_code in entry.get('models', KEYBOARD_MODELS))
        self.combo.setEnabled(bool(self.items) and not self.main.busy)
        self.install_btn.setEnabled(base and install_ok and self.main.allowed('keyboard.install', False))
        self.restore_btn.setEnabled(base and model_ok and self.main.allowed('keyboard.restore', False))

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
        super().__init__(main); self.main = main; self.setWindowTitle(main.t('Вход администратора')); self.setMinimumWidth(360); self.resize(440, 330)
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); layout.setSpacing(16)
        icon = QLabel(); icon.setPixmap(ui_icon('shield').pixmap(40, 40)); layout.addWidget(icon)
        title = QLabel(main.t('Вход администратора')); title.setObjectName('section'); layout.addWidget(title)
        note = QLabel(main.t('Управляйте доступными функциями, приложениями и клавиатурами. Введите секретный код, чтобы продолжить.')); note.setWordWrap(True); note.setObjectName('subtitle'); layout.addWidget(note)
        self.code = QLineEdit(); self.code.setEchoMode(QLineEdit.EchoMode.Password); self.code.setMaxLength(128); self.code.setPlaceholderText(main.t('Секретный код')); self.code.setAccessibleName(main.t('Секретный код')); layout.addWidget(self.code)
        self.status = QLabel(); self.status.setWordWrap(True); self.status.setObjectName('dangerText'); layout.addWidget(self.status)
        self.submit = QPushButton(main.t('Войти')); self.submit.setIcon(ui_icon('shield')); self.submit.setProperty('accent', True); layout.addWidget(self.submit); self.submit.clicked.connect(self.verify); self.code.returnPressed.connect(self.verify); self.attempts = 0
        self.code.setFocus()

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
        super().__init__(main); self.main = main; self.kind = kind; self.entry = copy.deepcopy(entry or {}); self.setWindowTitle(main.t('Запись каталога'))
        available = QApplication.primaryScreen().availableGeometry(); self.resize(min(720, available.width() - 64), min(800, available.height() - 64))
        outer = QVBoxLayout(self); outer.setContentsMargins(24, 24, 24, 24); outer.setSpacing(16)
        title = QLabel(main.t('Приложение каталога' if kind == 'apps' else 'Комплект клавиатур')); title.setObjectName('section'); outer.addWidget(title)
        note = QLabel(main.t('Пользователи увидят название и описание. Ссылки нужны программе для скачивания файлов.')); note.setObjectName('subtitle'); note.setWordWrap(True); outer.addWidget(note)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); body = QWidget(); form = QFormLayout(body); form.setContentsMargins(0, 0, 8, 0); form.setSpacing(14); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows); scroll.setWidget(body); outer.addWidget(scroll, 1)
        self.fields = {}
        keys = [('id', 'Постоянный ID'), ('name', 'Название'), ('description', 'Описание')]
        keys += [('source', 'Ссылка GitHub / APK'), ('asset', 'Имя файла релиза'), ('package', 'Android-пакет')] if kind == 'apps' else [('central_url', 'APK центрального экрана'), ('passenger_url', 'APK пассажирского экрана')]
        helps = {'id':'Короткое постоянное имя записи. Не меняйте его после публикации, чтобы программа узнавала приложение.', 'name':'Название, которое пользователь увидит в каталоге.', 'description':'Коротко расскажите, для чего нужно приложение или комплект.', 'source':'Вставьте ссылку на GitHub, страницу выпуска или файл для скачивания.', 'asset':'Необязательно: точное имя нужного файла, если в выпуске их несколько.', 'package':'Необязательно: внутренний адрес приложения для дополнительной проверки скачанного файла.', 'central_url':'Ссылка на клавиатуру основного экрана автомобиля.', 'passenger_url':'Ссылка на клавиатуру экрана переднего пассажира.'}
        for key, label in keys:
            field = QLineEdit(str(self.entry.get(key, ''))); field.setToolTip(main.t(helps[key])); self.fields[key] = field; form.addRow(main.t(label), field)
        self.enabled = QCheckBox(main.t('Доступно пользователям')); self.enabled.setChecked(self.entry.get('enabled', True)); self.enabled.setToolTip(main.t('Выключенная запись останется в каталоге, но установить её будет нельзя.')); form.addRow(self.enabled)
        self.sdk = QSpinBox(); self.sdk.setRange(1, 1000); self.sdk.setValue(self.entry.get('min_sdk', 24 if kind == 'keyboards' else 1)); self.sdk.setToolTip(main.t('Минимальное поколение Android, которое поддерживает файл. Программа проверит это перед установкой.')); form.addRow(main.t('Минимальный Android (API)'), self.sdk)
        self.extra = QCheckBox(main.t('Разрешить приложению устанавливать другие приложения')); self.extra.setChecked('request_install_packages' in self.entry.get('post_install', [])); self.extra.setToolTip(main.t('Нужно магазинам приложений. Выдаёт дополнительное разрешение после успешной установки.'))
        if kind == 'apps': form.addRow(self.extra)
        else:
            note = QLabel(main.t('Поддерживаемые модели') + ': ' + ', '.join(KEYBOARD_MODELS) + '\ncom.qinggan.app.qgime / com.qinggan.app.qgime.second'); note.setObjectName('subtitle'); note.setWordWrap(True); form.addRow(note)
        self.status = QLabel(); self.status.setWordWrap(True); outer.addWidget(self.status)
        check = QPushButton(main.t('Проверить ссылки')); check.setIcon(ui_icon('check')); check.clicked.connect(self.check_links); outer.addWidget(check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel); buttons.button(QDialogButtonBox.StandardButton.Save).setText(main.t('Сохранить')); buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(main.t('Отмена')); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); outer.addWidget(buttons)

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
        super().__init__(main); self.main = main; self.active = True; self.setWindowTitle(main.t('Администратор'))
        available = QApplication.primaryScreen().availableGeometry(); self.resize(min(1040, available.width() - 64), min(850, available.height() - 64)); self.setMinimumSize(min(600, available.width() - 64), min(500, available.height() - 64))
        self.draft_path = DATA_DIR / ('catalog-draft-qa.json' if main.smoke else 'catalog-draft.json')
        try: self.draft = validate_catalog(json.loads(self.draft_path.read_text(encoding='utf-8')))
        except (OSError, ValueError): self.draft = copy.deepcopy(main.catalog.profile)
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 24, 24, 20); layout.setSpacing(16)
        heading = QHBoxLayout(); icon = QLabel(); icon.setPixmap(ui_icon('shield').pixmap(32, 32)); heading.addWidget(icon); title = QLabel(main.t('Управление приложением')); title.setObjectName('section'); heading.addWidget(title, 1); layout.addLayout(heading)
        note = QLabel(main.t('Изменения общего профиля вступают в силу после успешной публикации.')); note.setWordWrap(True); note.setObjectName('subtitle'); layout.addWidget(note)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1); self.checks = {}; self.lists = {}; self.entry_details = {}; self.entry_buttons={}
        features = QWidget(); form = QVBoxLayout(features); form.setContentsMargins(12, 16, 12, 16); form.setSpacing(16)
        groups = [
            ('Разделы приложения', ('catalog', 'installer', 'keyboards', 'inspector', 'files', 'apps', 'tweaks', 'terminal')),
            ('Установка и файлы', ('apk.install', 'files.write', 'keyboard.install', 'keyboard.restore')),
            ('Приложения и твики', ('apps.freeze', 'apps.clear', 'apps.uninstall', 'tweaks.dpi', 'tweaks.permissions', 'tweaks.network')),
            ('Системные действия', ('device.root', 'device.reboot', 'repair.settings', 'repair.verity')),
        ]
        feature_help = {
            'catalog':'Выбор и скачивание приложений из общего каталога.', 'installer':'Установка файлов, которые пользователь выбрал на компьютере.', 'keyboards':'Выбор комплектов для двух экранов и восстановление штатных клавиатур.', 'inspector':'Просмотр того, что открыто на экранах, и поиск событий кнопок.', 'files':'Просмотр памяти автомобиля и копирование файлов.', 'apps':'Просмотр установленных приложений и управление ими.', 'tweaks':'Настройки экрана, звука, сети и восстановление.', 'terminal':'Позволяет опытному пользователю вводить произвольные команды.',
            'apk.install':'Разрешает все способы установки приложений, включая каталог и файлы на компьютере.', 'files.write':'Разрешает загрузку, удаление, создание папок и переименование файлов в машине.', 'keyboard.install':'Разрешает замену двух системных клавиатур из каталога.', 'keyboard.restore':'Разрешает возврат сохранённых штатных клавиатур.', 'apps.freeze':'Разрешает временно отключать приложения и включать их обратно.', 'apps.clear':'Разрешает удалять данные и настройки выбранного приложения.', 'apps.uninstall':'Разрешает удалять приложения из машины.', 'tweaks.dpi':'Разрешает менять размер текста и элементов экрана.', 'tweaks.permissions':'Разрешает менять доступ к микрофону, звуку и фоновой работе.', 'tweaks.network':'Разрешает настройки сети и верхней панели экрана.', 'device.root':'Разрешает пользователю самостоятельно включать расширенный системный доступ.', 'device.reboot':'Разрешает перезагрузку и системные сценарии с перезагрузкой.', 'repair.settings':'Разрешает пересоздание настроек автомобиля с предварительной копией.', 'repair.verity':'Разрешает отключить проверку системного раздела по процедуре установщика.'}
        for group, keys in groups:
            frame, box = self.admin_card(group)
            for key in keys:
                check = QCheckBox(main.t(FEATURES[key])); check.setChecked(self.draft['features'][key]); check.setToolTip(main.t(feature_help[key])); self.checks[key] = check; box.addWidget(check)
            form.addWidget(frame)
        form.addStretch(); scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setWidget(features); self.tabs.addTab(scroll, main.t('Функции'))
        for kind, label in (('apps', 'Приложения'), ('keyboards', 'Клавиатуры')):
            page = QWidget(); box = QVBoxLayout(page); box.setContentsMargins(12, 16, 12, 16); box.setSpacing(14)
            description = QLabel(main.t('Соберите список приложений для пользователей.' if kind == 'apps' else 'Каждая запись содержит две ссылки: для центрального и пассажирского экранов.')); description.setObjectName('subtitle'); description.setWordWrap(True); box.addWidget(description)
            row = QHBoxLayout(); row.setSpacing(10)
            self.entry_buttons[kind]=[]
            for title, method, icon_name in [('Добавить', self.add_entry, 'add'), ('Изменить', self.edit_entry, 'edit'), ('Удалить', self.remove_entry, 'delete')]:
                button = QPushButton(main.t(title)); button.setIcon(ui_icon(icon_name)); button.clicked.connect(lambda checked=False, k=kind, m=method: m(k)); row.addWidget(button)
                if title!='Добавить': self.entry_buttons[kind].append(button)
            row.addStretch(); box.addLayout(row)
            listing = QListWidget(); listing.setSpacing(6); listing.setWordWrap(True); self.lists[kind] = listing; box.addWidget(listing, 1)
            detail = QLabel(); detail.setObjectName('subtitle'); detail.setWordWrap(True); detail.setTextFormat(Qt.TextFormat.PlainText); self.entry_details[kind] = detail; box.addWidget(detail)
            listing.currentRowChanged.connect(lambda index, k=kind: self.show_entry_detail(k)); self.tabs.addTab(page, main.t(label)); self.refresh_list(kind)
        page = QWidget(); contents = QVBoxLayout(page); contents.setContentsMargins(12, 16, 12, 16); contents.setSpacing(16)
        connection, box = self.admin_card('Общий каталог на GitHub')
        intro = QLabel(main.t('Пользователям не нужен пароль для чтения каталога. Для публикации нужен ваш токен с доступом к этому репозиторию.')); intro.setWordWrap(True); intro.setObjectName('subtitle'); box.addWidget(intro)
        fields = QFormLayout(); fields.setSpacing(12); fields.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.repo = QLineEdit(main.catalog.config.get('repository', '')); self.repo.setPlaceholderText('owner/repository')
        self.branch = QLineEdit(main.catalog.config.get('branch', '')); self.branch.setPlaceholderText(main.t('Основная ветка репозитория'))
        self.catalog_path = QLineEdit(main.catalog.config.get('path', 'catalog.json'))
        self.token = QLineEdit(); self.token.setEchoMode(QLineEdit.EchoMode.Password); self.token.setPlaceholderText(main.t('Сохраняется только в Windows Credential Manager')); self.token.setToolTip(main.t('Секрет для публикации. Хранится только на этом компьютере и не попадёт в каталог или сборку.'))
        for title, widget in [('Репозиторий', self.repo), ('Ветка', self.branch), ('Путь JSON', self.catalog_path), ('Токен Contents: write', self.token)]: fields.addRow(main.t(title), widget)
        box.addLayout(fields)
        for title, fn, icon_name in [('Сохранить подключение и токен', self.configure, 'save'), ('Удалить сохранённый токен', self.forget_token, 'delete')]:
            button = QPushButton(main.t(title)); button.setIcon(ui_icon(icon_name)); button.clicked.connect(fn); box.addWidget(button)
        contents.addWidget(connection)
        publication, box = self.admin_card('Публикация изменений')
        note = QLabel(main.t('Сначала получите актуальный каталог, затем опубликуйте черновик. Если каталог изменил другой администратор, программа сохранит ваш черновик и сообщит о конфликте.')); note.setWordWrap(True); note.setObjectName('subtitle'); box.addWidget(note)
        for title, fn, icon_name in [('Загрузить актуальный профиль', self.load_remote, 'download'), ('Опубликовать', self.publish, 'upload')]:
            button = QPushButton(main.t(title)); button.setIcon(ui_icon(icon_name)); button.setProperty('accent', fn == self.publish); button.clicked.connect(fn); box.addWidget(button)
        contents.addWidget(publication); contents.addStretch()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setWidget(page); self.tabs.addTab(scroll, main.t('GitHub и публикация'))
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        row = QHBoxLayout(); save = QPushButton(main.t('Сохранить черновик')); save.setIcon(ui_icon('save')); save.clicked.connect(self.save_draft); row.addWidget(save); row.addStretch(); close = QPushButton(main.t('Закрыть')); close.clicked.connect(self.accept); row.addWidget(close); layout.addLayout(row)

    def collect(self):
        self.draft['features'] = {key:check.isChecked() for key,check in self.checks.items()}; return validate_catalog(self.draft)

    def save_draft(self):
        try: atomic_json(self.draft_path,self.collect()); self.status.setText(self.main.t('Черновик сохранён'))
        except (OSError,ValueError) as error: self.status.setText(self.main.t(str(error)))

    def refresh_list(self, kind):
        listing = self.lists[kind]; old_row = listing.currentRow(); old_id = listing.currentItem().data(Qt.ItemDataRole.UserRole) if listing.currentItem() else ''
        listing.blockSignals(True); listing.clear()
        for entry in self.draft[kind]:
            text = entry['name'] + ('  ·  ' + self.main.t('Отключено') if not entry.get('enabled', True) else '')
            item = QListWidgetItem(ui_icon('apps' if kind == 'apps' else 'keyboard'), text + '\n' + entry.get('description', ''))
            item.setData(Qt.ItemDataRole.UserRole, entry['id']); item.setToolTip(entry['id']); item.setSizeHint(QSize(300, 70)); listing.addItem(item)
        chosen = next((i for i, entry in enumerate(self.draft[kind]) if entry['id'] == old_id), min(old_row, len(self.draft[kind]) - 1))
        listing.setCurrentRow(chosen); listing.blockSignals(False); self.show_entry_detail(kind)

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

    def admin_card(self, title):
        frame = QFrame(); frame.setObjectName('card'); box = QVBoxLayout(frame); box.setContentsMargins(18, 16, 18, 16); box.setSpacing(12)
        label = QLabel(self.main.t(title)); label.setObjectName('section'); box.addWidget(label); return frame, box

    def show_entry_detail(self, kind):
        if kind not in self.entry_details: return
        row = self.lists[kind].currentRow()
        for button in self.entry_buttons.get(kind,[]): button.setEnabled(0<=row<len(self.draft[kind]))
        if 0 <= row < len(self.draft[kind]):
            entry = self.draft[kind][row]; self.entry_details[kind].setText(entry.get('description', '') + '\nID: ' + entry['id'])
        else: self.entry_details[kind].setText(self.main.t('Выберите запись для изменения или добавьте новую.'))

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
                    window.select_section(list(window.pages)[i]); QApplication.processEvents(); QApplication.processEvents(); QApplication.processEvents(); window.grab().save(str(args.smoke_dir / f'tab-{i + 1}-{window.lang}.png'))
            inspector = window.pages['inspector']; window.select_section('inspector')
            for i in range(inspector.sections.count()):
                inspector.sections.setCurrentIndex(i); QApplication.processEvents(); window.grab().save(str(args.smoke_dir/f'inspector-{i+1}.png'))
            admin = AdminDialog(window); admin.show()
            for i in range(admin.tabs.count()):
                admin.tabs.setCurrentIndex(i); QApplication.processEvents(); admin.grab().save(str(args.smoke_dir/f'admin-{i+1}.png'))
            admin.reject(); admin.deleteLater()
            window.connection_disclosure.setExpanded(True,False); QApplication.processEvents(); window.grab().save(str(args.smoke_dir/'connection-settings.png')); window.connection_disclosure.setExpanded(False,False)
            window.select_section('tweaks'); QApplication.processEvents(); window.stack.currentWidget().verticalScrollBar().setValue(window.stack.currentWidget().verticalScrollBar().maximum()); QApplication.processEvents(); window.grab().save(str(args.smoke_dir/'recovery.png'))
            try: build_manifest = json.loads((RESOURCE_DIR/'build_manifest.json').read_text(encoding='utf-8'))
            except (OSError,ValueError): build_manifest = {}
            (args.smoke_dir / 'report.json').write_text(json.dumps({'version':VERSION, 'frozen':bool(getattr(sys, 'frozen', False)), 'adb':window.adb_path, 'tools':{name:window.tools.path(name).exists() for name in ('aapt2.exe','bundletool.jar','jre/bin/java.exe')}, 'tool_checks':tool_checks, 'tabs':window.stack.count(), 'profile':window.profile.api,'catalog':{'repository':window.catalog.config.get('repository',''),'revision':window.catalog.profile['revision']},'build':build_manifest,'size':[window.width(),window.height()],'dpr':window.devicePixelRatio()}, indent=2), encoding='utf-8')
            window.close(); app.quit()
        QTimer.singleShot(4000, check_tools)
    return app.exec()

if __name__ == '__main__':
    raise SystemExit(main())

