"""Regression coverage for empty-folder artwork and bookmark backgrounds."""
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor

from test_manager import window
import voyah_manager as v


def test_explorer_initial_empty_state_has_full_folder_icon(window, qtbot):
    window.select_section('files'); page = window.pages['files']; qtbot.wait(20)
    assert page.empty_files.isVisible()
    assert not page.file_table.isVisible()
    emblem = page.empty_files.emblem; image = emblem.pixmap()
    width = round(image.width() / image.devicePixelRatio()); height = round(image.height() / image.devicePixelRatio())
    expected = QRect((emblem.width() - width) // 2, (emblem.height() - height) // 2, width, height)
    assert emblem.isVisible() and emblem.contentsRect().contains(expected)
    assert page.empty_files.rect().contains(QRect(emblem.mapTo(page.empty_files, QPoint(0, 0)), emblem.size()))
    assert emblem.grab().height() >= image.height() / image.devicePixelRatio()


def test_empty_directory_keeps_empty_state_instead_of_empty_table(window, qtbot):
    window.select_section('files'); page = window.pages['files']; page.show_entries([], None); qtbot.wait(20)
    assert page.empty_files.isVisible() and not page.file_table.isVisible()
    assert page.empty_files.title.text() == window.t('Папка пуста')
    emblem = page.empty_files.emblem
    assert emblem.height() >= 32 and emblem.width() >= 32
    assert emblem.geometry().bottom() < page.empty_files.height()


def test_bookmark_group_background_matches_card_surface(window, qtbot):
    window.resize(1400, 1040); window.select_section('files'); page = window.pages['files']; qtbot.wait(20)
    bookmarks = page.bookmarks_widget; first = page.bookmark_buttons[0]; second = page.bookmark_buttons[1]
    # Read an actual gap between two buttons, where the group background is exposed.
    if second.geometry().top() == first.geometry().top():
        point = QPoint((first.geometry().right() + second.geometry().left()) // 2, first.geometry().center().y())
    else:
        point = QPoint(bookmarks.width() - 4, first.geometry().center().y())
    captured = page.toolbar_frame.grab(); ratio = captured.devicePixelRatio(); mapped = bookmarks.mapTo(page.toolbar_frame, point)
    pixel = captured.toImage().pixelColor(round(mapped.x() * ratio), round(mapped.y() * ratio))
    assert pixel == QColor(v.UiTokens.surface)
