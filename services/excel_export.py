"""Excel export helpers."""

import logging

import pandas as pd

from metadata.constants import TABLE_LABELS, validate_table_name

logger = logging.getLogger("ExcelExport")


def export_table_data(data, file_path: str, table_name: str) -> int:
    """Export table data to an Excel file and return exported row count."""
    validate_table_name(table_name)
    if not data:
        raise ValueError("没有可导出的数据")

    df = pd.DataFrame(data)
    if "id" in df.columns:
        df = df.drop(columns=["id"])

    df.to_excel(file_path, index=False)

    row_count = len(data)
    table_label = TABLE_LABELS.get(table_name, table_name)
    logger.info(f"成功导出{table_label} {row_count}条记录到: {file_path}")
    return row_count
