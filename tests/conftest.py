"""Keep a diagnostic copy of native Qt messages, including fatal assertions."""
from pathlib import Path
import pytest
from PySide6.QtCore import qInstallMessageHandler

@pytest.fixture(autouse=True)
def qt_native_diagnostics():
    def handler(kind, context, message):
        with (Path(__file__).resolve().parents[1] / 'qa-qt-messages.log').open('a', encoding='utf-8') as out:
            out.write(str(kind) + ' ' + message + '\n')
    previous = qInstallMessageHandler(handler)
    yield
    qInstallMessageHandler(previous)
