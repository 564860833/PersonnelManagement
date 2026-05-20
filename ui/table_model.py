import re

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtGui import QColor

from metadata.constants import TABLE_DATE_FIELDS
from ui.styles import (
    TABLE_ROW_ALTERNATE_BACKGROUND,
    TABLE_ROW_BACKGROUND,
)


class ResultTableModel(QAbstractTableModel):
    """Lazy table model for one page of query results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.fields = []
        self.headers = []
        self.table_name = ""
        self.start_index = 0

    def set_data(self, rows, table_name: str, fields, headers, start_index: int = 0):
        self.beginResetModel()
        self.rows = rows or []
        self.table_name = table_name
        self.fields = fields or []
        self.headers = headers or []
        self.start_index = start_index
        self.endResetModel()

    def clear(self):
        self.set_data([], "", [], [], 0)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if index.row() >= len(self.rows) or index.column() >= len(self.fields):
            return None

        row = self.rows[index.row()]
        field_name = self.fields[index.column()]
        value = row.get(field_name, "")
        if value is None:
            value = ""

        if role == Qt.DisplayRole:
            return self.format_value(field_name, value)

        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter

        if role == Qt.ToolTipRole:
            return str(value)

        if role == Qt.BackgroundRole:
            if index.row() % 2 == 1:
                return QColor(TABLE_ROW_ALTERNATE_BACKGROUND)
            return QColor(TABLE_ROW_BACKGROUND)

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None

        if orientation == Qt.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
            return None

        return str(self.start_index + section + 1)

    def format_value(self, field_name: str, value):
        if field_name not in TABLE_DATE_FIELDS.get(self.table_name, []):
            return str(value)

        text = str(value)
        if re.match(r'^\d{4}-\d{2}-\d{2}$', text):
            return text[:7].replace('-', '.')
        if re.match(r'^\d{4}\.\d{2}$', text):
            return text
        if re.match(r'^\d{6}$', text):
            return f"{text[:4]}.{text[4:6]}"
        return text
