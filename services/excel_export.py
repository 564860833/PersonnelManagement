"""Excel export helpers."""

import logging

import pandas as pd

from metadata.constants import (
    TABLE_DATE_FIELDS,
    TABLE_LABELS,
    get_table_field_labels,
    validate_table_name,
)

logger = logging.getLogger("ExcelExport")


def export_table_data(data, file_path: str, table_name: str, assessment_years=None) -> int:
    """Export table data to an Excel file and return exported row count."""
    validate_table_name(table_name)
    if not data:
        raise ValueError("没有可导出的数据")

    df = pd.DataFrame(data)
    for field_name in TABLE_DATE_FIELDS.get(table_name, []):
        display_column = f"{field_name}_display"
        if field_name in df.columns and display_column in df.columns:
            display_values = df[display_column]
            has_display_value = display_values.notna() & (display_values.astype(str) != "")
            df.loc[has_display_value, field_name] = display_values[has_display_value]

    internal_columns = [
        column
        for column in df.columns
        if column in {"id", "person_id"} or column.endswith("_display")
    ]
    if internal_columns:
        df = df.drop(columns=internal_columns)

    field_labels = get_table_field_labels(table_name, assessment_years)
    ordered_columns = [
        field_name
        for field_name in field_labels
        if field_name in df.columns
    ]
    df = df.loc[:, ordered_columns].rename(
        columns={
            field_name: field_labels[field_name]
            for field_name in ordered_columns
        }
    )

    df.to_excel(file_path, index=False)

    row_count = len(data)
    table_label = TABLE_LABELS.get(table_name, table_name)
    logger.info(f"成功导出{table_label} {row_count}条记录到: {file_path}")
    return row_count
