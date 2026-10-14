"""Queue behavior at user entry points, without invoking installation on a car."""
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, QMimeData, QPoint, QPointF, QRect, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

import voyah_manager as v
from test_manager import window


def queue_files(tmp_path, count=4):
    result = []
    for index in range(count):
        file = tmp_path / f'Приложение {index + 1}.apk'
        file.write_bytes(b'queue fixture; metadata is not read until installation')
        result.append(file)
    return result


def local_mime(paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return mime


def drop_event(mime):
    return QDropEvent(QPointF(8, 8), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def assert_queue_matches_table(page, expected):
    assert page.files == [str(path.resolve()) for path in expected]
    assert page.file_table.rowCount() == len(expected)
    for row, path in enumerate(expected):
        item = page.file_table.item(row, 0)
        assert item.text() == path.name
        assert item.data(Qt.ItemDataRole.UserRole) == str(path.resolve())
        assert page.file_table.cellWidget(row, 3) is not None


def test_delete_buttons_keep_their_file_after_rows_shift(window, qtbot, tmp_path):
    page = window.pages['installer']; files = queue_files(tmp_path)
    page.add_paths(files)
    # Deleting the second row shifts the third row into its place. Its button
    # must keep targeting that file rather than the old numerical row.
    page.file_table.cellWidget(1, 3).click()
    qtbot.wait(30)
    assert_queue_matches_table(page, [files[0], files[2], files[3]])
    page.file_table.cellWidget(1, 3).click()
    qtbot.wait(30)
    assert_queue_matches_table(page, [files[0], files[3]])
    assert all(path.exists() for path in files)


def test_delete_selected_rows_during_selection_signals(window, qtbot, tmp_path):
    page = window.pages['installer']; files = queue_files(tmp_path, 5)
    page.add_paths(files)
    model = page.file_table.selectionModel(); model.clearSelection()
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    model.select(page.file_table.model().index(1, 0), flags)
    model.select(page.file_table.model().index(3, 0), flags)
    signals = []
    page.file_table.itemSelectionChanged.connect(lambda: signals.append(page.file_table.rowCount()))
    page.remove_selected(); qtbot.wait(30)
    assert_queue_matches_table(page, [files[0], files[2], files[4]])
    assert signals
    assert all(path.exists() for path in files)


def test_delete_shortcut_only_removes_selected_queue_rows(window, qtbot, tmp_path):
    page = window.pages['installer']; files = queue_files(tmp_path, 3)
    window.select_section('installer'); page.add_paths(files)
    page.file_table.selectRow(1); window.activateWindow(); page.file_table.setFocus()
    qtbot.wait(30); qtbot.keyClick(page.file_table, Qt.Key.Key_Delete)
    qtbot.waitUntil(lambda: page.file_table.rowCount() == 2)
    assert_queue_matches_table(page, [files[0], files[2]])
    assert files[1].exists()


def test_local_drop_and_canonical_paths_do_not_duplicate_files(window, qtbot, tmp_path):
    page = window.pages['installer']; files = queue_files(tmp_path, 2)
    mime = local_mime(files)
    enter = QDragEnterEvent(QPoint(8, 8), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    page.drop_area.dragEnterEvent(enter); assert enter.isAccepted()
    event = drop_event(mime); page.drop_area.dropEvent(event); assert event.isAccepted()
    aliases = [files[0].parent / '..' / files[0].parent.name / files[0].name,
               str(files[1]).upper()]
    page.add_paths(aliases)
    assert_queue_matches_table(page, files)
    assert page.feedback_key == 'Эти файлы уже в списке. Повторно не добавлены.'


def test_folder_callback_is_discarded_after_queue_was_cleared(window, monkeypatch, tmp_path):
    page = window.pages['installer']; folder = tmp_path / 'directory'; folder.mkdir()
    files = queue_files(folder, 2); callbacks = []
    monkeypatch.setattr(window, 'background', lambda work, callback: callbacks.append((work, callback)))
    page.add_paths([folder]); assert len(callbacks) == 1
    page.clear_files()
    work, callback = callbacks.pop(); callback(work(), None)
    assert_queue_matches_table(page, [])
    assert all(path.exists() for path in files)


def test_folder_callback_does_not_restore_removed_files(window, monkeypatch, tmp_path):
    page = window.pages['installer']; files = queue_files(tmp_path, 2); callbacks = []
    page.add_paths([files[0]])
    monkeypatch.setattr(window, 'background', lambda work, callback: callbacks.append((work, callback)))
    page.add_paths([tmp_path]); page.remove_path(page.path_key(files[0]))
    work, callback = callbacks.pop(); callback(work(), None)
    assert_queue_matches_table(page, [])


@pytest.mark.parametrize('blocked', ['busy', 'apk.install', 'installer'])
def test_drop_and_row_delete_respect_busy_and_admin_policy(window, monkeypatch, tmp_path, blocked):
    page = window.pages['installer']; files = queue_files(tmp_path, 2)
    page.add_paths([files[0]])
    if blocked == 'busy': window.busy = True
    else: window.catalog.profile['features'][blocked] = False
    # The guarded handlers still have to protect direct calls and deliveries
    # from a drag already in progress when policy changed.
    monkeypatch.setattr(window, 'error', lambda *args, **kwargs: None)
    page.update_actions(); assert not page.clear_button.isEnabled()
    assert not page.file_table.cellWidget(0, 3).isEnabled()
    mime = local_mime([files[1]]); event = drop_event(mime)
    page.drop_area.dropEvent(event); assert not event.isAccepted()
    page.add_paths([files[1]]); page.remove_path(page.path_key(files[0])); page.clear_files()
    assert_queue_matches_table(page, [files[0]])
    if blocked == 'busy': window.busy = False
    else: window.catalog.profile['features'][blocked] = True
    page.update_actions()


@pytest.mark.parametrize('blocked', ['busy', 'apk.install', 'installer'])
def test_pending_directory_scan_cannot_mutate_a_locked_queue(window, monkeypatch, tmp_path, blocked):
    page = window.pages['installer']; queue_files(tmp_path, 2); callbacks = []
    monkeypatch.setattr(window, 'background', lambda work, callback: callbacks.append((work, callback)))
    page.add_paths([tmp_path]); work, callback = callbacks.pop()
    if blocked == 'busy': window.busy = True
    else: window.catalog.profile['features'][blocked] = False
    callback(work(), None)
    assert_queue_matches_table(page, [])
    if blocked == 'busy': window.busy = False
    else: window.catalog.profile['features'][blocked] = True
    page.update_actions()


def test_queue_order_survives_folder_add(window, monkeypatch, tmp_path):
    page = window.pages['installer']; folder = tmp_path / 'parts'; folder.mkdir()
    files = queue_files(folder, 3); callbacks = []
    page.add_paths([files[2]])
    monkeypatch.setattr(window, 'background', lambda work, callback: callbacks.append((work, callback)))
    page.add_paths([folder]); work, callback = callbacks.pop(); callback(work(), None)
    assert_queue_matches_table(page, [files[2], files[0], files[1]])


def test_installer_controls_translate_with_an_existing_queue(window, tmp_path):
    page = window.pages['installer']; files = queue_files(tmp_path, 1); page.add_paths(files)
    window.language.setCurrentIndex(1)
    assert page.add_button.text() == v.tr('Выбрать файлы', 'en')
    assert page.clear_button.accessibleName() == v.tr('Очистить список', 'en')
    assert page.install_button.text() == v.tr('Установить в автомобиль', 'en')
    assert page.mode.itemText(2) == v.tr(page.mode_keys[2], 'en')
    assert page.queue_feedback.text() == v.tr(page.feedback_key, 'en', **page.feedback_values)
    assert page.file_table.cellWidget(0, 3).toolTip() == v.tr('Уберёт этот файл из очереди. Файл на компьютере останется.', 'en')
    assert page.file_table.cellWidget(0, 3).accessibleName() == v.tr('Убрать файл из списка', 'en')
    assert page.file_table.item(0, 2).text() == v.tr('В очереди', 'en')
    window.language.setCurrentIndex(0)


@pytest.mark.parametrize('language', ['ru', 'en'])
@pytest.mark.parametrize('size', [(900, 760), (1080, 760), (1400, 940)])
def test_installer_workspace_fits_without_page_scroll(window, qtbot, tmp_path, size, language):
    """The queue may scroll; its surrounding workflow must stay on one page."""
    page = window.pages['installer']; page.add_paths(queue_files(tmp_path, 3))
    window.language.setCurrentIndex(1 if language == 'en' else 0)
    window.resize(*size); window.select_section('installer'); qtbot.wait(100)
    directory = Path(__file__).resolve().parents[1] / 'qa-installer-geometry'
    directory.mkdir(exist_ok=True)
    assert page.grab().save(str(directory / f'installer-{size[0]}x{size[1]}-{language}.png'))
    assert window.stack.currentWidget() is page
    assert not page.findChildren(v.Disclosure)

    def visible_rect(widget):
        assert widget.isVisible()
        rect = QRect(widget.mapTo(page, QPoint(0, 0)), widget.size())
        assert page.rect().contains(rect), (size, language, widget.objectName(), rect, page.rect())
        return rect

    drop = visible_rect(page.drop_area); queue = visible_rect(page.file_table)
    options = [visible_rect(check) for check in page.flags]
    install = visible_rect(page.install_button)
    for control in (page.add_button, page.folder_button, page.clear_button): visible_rect(control)
    assert not page.mode.isVisible()
    frame = page.layout.itemAt(0).widget()
    metrics = {
        'requested': size, 'language': language, 'window': window.size().toTuple(),
        'devicePixelRatio': window.devicePixelRatioF(),
        'font': [page.font().family(), page.font().pointSizeF()],
        'page': page.rect().getRect(), 'frame': frame.geometry().getRect(),
        'drop': drop.getRect(), 'queueStack': QRect(page.queue_stack.mapTo(page, QPoint()), page.queue_stack.size()).getRect(),
        'queueTable': queue.getRect(), 'options': [rect.getRect() for rect in options], 'install': install.getRect(),
    }
    (directory / f'installer-{size[0]}x{size[1]}-{language}.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    if min(rect.top() for rect in options) <= queue.bottom(): print('OVERLAP', json.dumps(metrics))
    assert 0 <= queue.top() - drop.bottom() <= 140
    assert drop.height() <= 84
    assert queue.height() >= 96
    assert min(rect.top() for rect in options) > queue.bottom()
    assert install.top() > max(rect.bottom() for rect in options)
    assert page.file_table.rowCount() == 3

    window.language.setCurrentIndex(0)

