import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QFrame

from ui.query import MonthRangeDialog, MonthRangePicker


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

    def test_month_panels_have_bottom_dividers(self):
        dialog = self.make_dialog()

        for panel in (dialog.start_panel, dialog.end_panel):
            divider = panel.findChild(QFrame, "monthPanelDivider")
            self.assertIsNotNone(divider)
            self.assertEqual(1, divider.height())

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


if __name__ == "__main__":
    unittest.main()
