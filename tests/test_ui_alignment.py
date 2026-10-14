"""Layout checks for explanatory labels and the inspector's styled tab bars."""
import pytest
from PySide6.QtCore import QPoint

from test_manager import window


@pytest.mark.parametrize('language', [0, 1])
@pytest.mark.parametrize('width', [1000, 1300])
def test_keyboard_explanation_uses_card_width(window, qtbot, language, width):
    window.language.setCurrentIndex(language)
    window.resize(width, 860)
    window.select_section('keyboards')
    page = window.pages['keyboards']
    hint = page.intro_hint
    card = hint.parentWidget()
    qtbot.waitUntil(lambda: hint.width() > 300)
    qtbot.wait(40)
    margins = card.layout().contentsMargins()
    available = card.width() - margins.left() - margins.right()
    assert hint.wordWrap()
    assert hint.width() >= available - 4
    assert hint.height() <= hint.fontMetrics().lineSpacing() * 3 + 8


@pytest.mark.parametrize('language', [0, 1])
def test_inspector_tabs_have_no_native_baseline_or_overlap(window, qtbot, language):
    window.language.setCurrentIndex(language)
    window.resize(1300, 900)
    window.select_section('inspector')
    page = window.pages['inspector']
    for tabs in (page.sections, page.capture_tabs, page.dump_tabs):
        tabs.ensurePolished()
        bar = tabs.tabBar()
        bar.ensurePolished()
        assert not bar.drawBase()
        for index in range(1, bar.count()):
            assert bar.tabRect(index).left() > bar.tabRect(index - 1).right()
    for index in range(page.sections.count()):
        page.sections.setCurrentIndex(index)
        qtbot.wait(30)
        tabs = page.sections
        bar = tabs.tabBar()
        content_top = tabs.currentWidget().mapTo(tabs, QPoint(0, 0)).y()
        assert content_top >= bar.geometry().bottom() + 1
