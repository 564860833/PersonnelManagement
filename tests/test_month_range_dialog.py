import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QFrame
from PyQt5.QtCore import Qt

from ui.query import MonthRangeDialog, MonthRangePicker
from ui.table_model import ResultTableModel


class MonthRangeDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self):
        dialog = MonthRangeDialog()
        dialog.show()
        self.app.processEvents()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_dialog_buttons_use_chinese_labels(self):
        dialog = self.make_dialog()

        self.assertEqual("确认", dialog.ok_button.text())
        self.assertEqual("取消", dialog.cancel_button.text())

    def test_month_panels_use_card_containers(self):
        dialog = self.make_dialog()

        self.assertIn("QFrame#monthPanel", dialog.styleSheet())
        for panel in (dialog.start_panel, dialog.end_panel):
            self.assertIsInstance(panel, QFrame)
            self.assertEqual("monthPanel", panel.objectName())
            self.assertTrue(panel.testAttribute(Qt.WA_StyledBackground))
            self.assertIsNotNone(panel.graphicsEffect())
            divider = panel.findChild(QFrame, "monthPanelDivider")
            self.assertIsNone(divider)
            margins = panel.layout().contentsMargins()
            self.assertEqual((16, 16, 16, 16), (
                margins.left(),
                margins.top(),
                margins.right(),
                margins.bottom(),
            ))

    def test_year_navigation_stays_within_month_grid_width(self):
        dialog = self.make_dialog()

        for panel in (dialog.start_panel, dialog.end_panel):
            self.assertLessEqual(panel.header_widget.width(), panel.month_container.width())
            self.assertEqual(panel.content_width, panel.header_widget.width())
            self.assertEqual(panel.content_width, panel.month_container.width())
            self.assertGreaterEqual(panel.content_width, 230)
            self.assertGreaterEqual(panel.year_button.width(), 140)

    def test_year_grid_cells_are_wide_enough_for_four_digit_years(self):
        dialog = self.make_dialog()
        dialog.start_panel.year_button.click()
        self.app.processEvents()

        for button in dialog.start_panel.year_buttons.values():
            if button.isVisible():
                self.assertGreaterEqual(button.width(), 70)
                self.assertEqual(38, button.minimumHeight())
                self.assertEqual(38, button.maximumHeight())

    def test_month_cells_match_year_grid_cell_size(self):
        dialog = self.make_dialog()
        panel = dialog.start_panel

        self.assertEqual(38, panel.month_buttons[1].minimumHeight())
        self.assertEqual(38, panel.month_buttons[1].maximumHeight())
        self.assertEqual(38, panel.year_buttons[0].minimumHeight())
        self.assertEqual(38, panel.year_buttons[0].maximumHeight())
        self.assertEqual(
            panel.year_buttons[0].size(),
            panel.month_buttons[1].size(),
        )

    def test_toggling_year_view_does_not_resize_dialog(self):
        dialog = self.make_dialog()
        initial_size = dialog.size()

        dialog.start_panel.year_button.click()
        self.app.processEvents()
        self.assertEqual(initial_size, dialog.size())

        dialog.start_panel.year_button.click()
        self.app.processEvents()
        self.assertEqual(initial_size, dialog.size())

    def test_month_range_picker_keeps_existing_api_behavior(self):
        picker = MonthRangePicker()
        self.addCleanup(picker.deleteLater)

        picker.set_range("1990.01", "1999.12")
        self.assertEqual(("1990.01", "1999.12"), picker.get_range())
        self.assertEqual("1990-01 至 1999-12", picker.text())

        picker.clear()
        self.assertEqual((None, None), picker.get_range())
        self.assertEqual("", picker.text())

    def test_result_table_model_prefers_date_display_value(self):
        model = ResultTableModel()

        model.set_data(
            [{"birth_date": "1990-01", "birth_date_display": "1990.1"}],
            "base_info",
            ["birth_date"],
            ["birth_date"],
        )
        self.assertEqual("1990.1", model.data(model.index(0, 0), Qt.DisplayRole))

        model.set_data(
            [{"birth_date": "1990-01"}],
            "base_info",
            ["birth_date"],
            ["birth_date"],
        )
        self.assertEqual("1990-01", model.data(model.index(0, 0), Qt.DisplayRole))


if __name__ == "__main__":
    unittest.main()
