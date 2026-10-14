"""DPI choices use numeric item data and keep editable values during translation."""
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget

import voyah_manager as v


@pytest.fixture
def dpi_page(qtbot, tmp_path):
    class Host(QWidget):
        def __init__(self):
            super().__init__()
            self.lang = 'ru'; self.busy = False; self.target = v.Target('dpi-test', 'usb')
            self.profile = v.Profile(); self.profile.api = 30; self.profile.per_display = True; self.profile.displays = [0, 1, 2]
            self.display_map = {'cluster': 0, 'center': 1, 'passenger': 2}
            self.settings = QSettings(str(tmp_path / 'dpi.ini'), QSettings.Format.IniFormat)
            self.errors = []; self.sequences = []; self.confirmations = []
        def t(self, text, **values): return v.tr(text, self.lang, **values)
        def allowed(self, feature, report=True): return True
        def ready(self): return bool(self.target) and not self.busy
        def error(self, text, *args, **kwargs): self.errors.append(text)
        def confirm(self, text): self.confirmations.append(text); return True
        def sequence(self, name, steps, done=None, target=None): self.sequences.append((name, steps))
    host = Host(); qtbot.addWidget(host)
    page = v.TweaksPage(host); page.setParent(host); qtbot.addWidget(page)
    return host, page


def test_presets_have_numeric_data_and_standard_label(dpi_page):
    host, page = dpi_page
    values = [page.dpi.itemData(i) for i in range(page.dpi.count())]
    assert values == [80, 100, 120, 140, 150, 160, 180, 200, 220, 240, 260]
    assert all(type(value) is int for value in values)
    assert page.dpi.currentData() == 160 and page.dpi.currentText() == '160 — стандарт'
    assert page.dpi.isEditable() and page.dpi.insertPolicy() == v.QComboBox.InsertPolicy.NoInsert
    for index, value in enumerate(values):
        page.dpi.setCurrentIndex(index)
        assert page.density_value() == value


@pytest.mark.parametrize('text, expected', [('80', 80), ('260', 260), ('175', 175), ('150', 150), (' 180 ', 180)])
def test_manual_value_overrides_stale_selected_item_data(dpi_page, text, expected):
    host, page = dpi_page
    assert page.dpi.currentData() == 160
    page.dpi.setCurrentText(text)
    assert page.density_value() == expected


@pytest.mark.parametrize('text', ['79', '261', '72', '1000', '0', '-80', '160.5', '', 'text', '160 — invented', '1_6_0'])
def test_invalid_or_out_of_range_input_never_runs_a_command(dpi_page, text):
    host, page = dpi_page
    page.dpi.setCurrentText(text)
    with pytest.raises(ValueError): page.density_value()
    page.set_density(False)
    assert not host.sequences
    assert host.errors == ['Введите целое число от 80 до 260.']


@pytest.mark.parametrize('value', [80, 160, 260])
def test_apply_uses_bare_number_and_retains_display_arguments(dpi_page, value):
    host, page = dpi_page
    page.display.setCurrentIndex(1)
    page.dpi.setCurrentIndex(page.dpi.findData(value))
    page.set_density(False)
    assert not host.errors and len(host.sequences) == 1
    steps = host.sequences[0][1]
    assert steps[0].args == ['wm', 'density', str(value), '-d', '1']
    assert steps[1].args == ['wm', 'density', '-d', '1']


def test_language_switch_keeps_preset_and_manual_text(dpi_page):
    host, page = dpi_page
    page.dpi.setCurrentIndex(page.dpi.findData(180))
    host.lang = 'en'; page.retranslate()
    assert page.dpi.currentData() == 180 and page.dpi.currentText() == '180 — a little larger'
    assert page.density_value() == 180
    page.dpi.setCurrentText('175')
    host.lang = 'ru'; page.retranslate()
    assert page.dpi.currentText() == '175' and page.density_value() == 175
    page.dpi.setCurrentText('not finished')
    host.lang = 'en'; page.retranslate()
    assert page.dpi.currentText() == 'not finished'
    assert page.dpi.lineEdit().placeholderText() == 'Enter a number from 80 to 260'
    assert 'factory size may differ' in page.dpi.toolTip()


def test_factory_reset_ignores_invalid_text_and_does_not_force_160(dpi_page):
    host, page = dpi_page
    page.display.setCurrentIndex(1)
    page.dpi.setCurrentText('not a number')
    page.set_density(True)
    assert not host.errors and len(host.sequences) == 1
    steps = host.sequences[0][1]
    assert steps[0].args == ['wm', 'density', 'reset', '-d', '1']
    assert steps[1].validate(v.Result(True, b'Physical density: 190'))
    assert not steps[1].validate(v.Result(True, b'Physical density: 190\nOverride density: 160'))


def test_existing_display_support_and_cluster_confirmation_are_retained(dpi_page):
    host, page = dpi_page
    host.profile.per_display = False
    page.display.setCurrentIndex(1); page.set_density(False)
    assert not host.sequences and host.errors
    host.errors.clear(); host.profile.per_display = True
    page.display.setCurrentIndex(3); page.set_density(False)
    assert host.confirmations == [host.t('Изменить DPI приборной панели?')]
    assert host.sequences[0][1][0].args == ['wm', 'density', '160', '-d', '0']
