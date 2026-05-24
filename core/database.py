import json
import logging
import os
import re
import sqlite3
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from metadata.constants import (
    COLUMN_LABEL_TO_FIELD,
    DEFAULT_PERMISSIONS,
    TABLE_DATE_FIELDS,
    TABLE_FIELD_LABELS,
    TABLE_NAMES,
    normalize_permissions,
    validate_table_name,
)

logger = logging.getLogger("Database")


RELATED_TABLES = ("rewards", "family", "resume")
RELATED_IMPORT_IDENTITY_COLUMNS = {"id", "person_id", "sequence", "name"}
DATE_DISPLAY_SUFFIX = "_display"
SQLITE_BUSY_TIMEOUT_MS = 10000
SQLITE_CONNECT_TIMEOUT_SECONDS = SQLITE_BUSY_TIMEOUT_MS / 1000
BLANK_PLACEHOLDERS = {"-", "—", "–", "－", "无", "無", "暂无", "无日期", "n/a", "na"}

RELATED_TABLE_COLUMNS = {
    "rewards": [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("person_id", "INTEGER NOT NULL"),
        ("reward_name", "TEXT"),
        ("reward_date", "TEXT"),
        ("reward_unit", "TEXT"),
        ("reward_authority_type", "TEXT"),
        ("punishment_name", "TEXT"),
        ("punishment_date", "TEXT"),
        ("punishment_unit", "TEXT"),
        ("punishment_authority_type", "TEXT"),
        ("impact_period", "TEXT"),
    ],
    "family": [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("person_id", "INTEGER NOT NULL"),
        ("relation", "TEXT"),
        ("family_name", "TEXT"),
        ("birth_date", "TEXT"),
        ("political_status", "TEXT"),
        ("work_unit", "TEXT"),
        ("position", "TEXT"),
    ],
    "resume": [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("person_id", "INTEGER NOT NULL"),
        ("resume_text", "TEXT"),
    ],
}


RELATED_TABLE_DISPLAY_COLUMNS = {
    "rewards": [
        "r.id",
        "r.person_id",
        "b.sequence AS sequence",
        "b.name AS name",
        "r.reward_name",
        "r.reward_date",
        "r.reward_unit",
        "r.reward_authority_type",
        "r.punishment_name",
        "r.punishment_date",
        "r.punishment_unit",
        "r.punishment_authority_type",
        "r.impact_period",
    ],
    "family": [
        "r.id",
        "r.person_id",
        "b.sequence AS sequence",
        "b.name AS name",
        "r.relation",
        "r.family_name",
        "r.birth_date",
        "r.political_status",
        "r.work_unit",
        "r.position",
    ],
    "resume": [
        "r.id",
        "r.person_id",
        "b.sequence AS sequence",
        "b.name AS name",
        "r.resume_text",
    ],
}


class Database:
    def __init__(self, db_path=None):
        os.environ["DISABLE_XML"] = "1"

        self.conn = None
        self.connect(db_path)
        self.create_tables()

    def connect(self, db_path=None):
        """Connect to SQLite and enable foreign-key enforcement."""
        try:
            from config import config

            path = db_path if db_path else config.DB_PATH
            self._open_connection(path)
            logger.info(f"成功连接到数据库: {path}")
        except sqlite3.Error as e:
            logger.error(f"数据库连接失败: {e}")
            raise
        except ImportError as e:
            logger.error(f"无法导入配置模块: {e}")
            default_path = "personnel_system.db"
            self._open_connection(default_path)
            logger.info(f"使用默认路径连接数据库: {default_path}")

    def _open_connection(self, path):
        self.conn = sqlite3.connect(path, timeout=SQLITE_CONNECT_TIMEOUT_SECONDS)
        self.conn.row_factory = sqlite3.Row
        self._register_sqlite_functions()
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        self._enable_wal_mode()

    def _enable_wal_mode(self):
        try:
            self.conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error as e:
            logger.warning(f"启用 SQLite WAL 模式失败: {e}")

    def _register_sqlite_functions(self):
        self.conn.create_function("personnel_month_key", 1, self._month_key)

    @classmethod
    def _month_key(cls, value) -> Optional[str]:
        return cls._normalize_month_value(value)

    @staticmethod
    def _is_blank_value(value) -> bool:
        if value is None:
            return True

        text = str(value).strip()
        return not text or text.lower() in {"nan", "nat", "none", "<na>"} or text.casefold() in BLANK_PLACEHOLDERS

    @staticmethod
    def _date_display_value(value) -> str:
        if Database._is_blank_value(value):
            return ""
        return str(value)

    @classmethod
    def _normalize_month_value(cls, value) -> Optional[str]:
        if cls._is_blank_value(value):
            return None

        if isinstance(value, datetime):
            return f"{value.year:04d}-{value.month:02d}"
        if isinstance(value, date):
            return f"{value.year:04d}-{value.month:02d}"

        text = str(value).strip()
        normalized = (
            text.replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
            .replace("/", "-")
            .replace(".", "-")
        )
        normalized = re.sub(r"-+", "-", normalized).strip("-")
        match = re.match(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?(?:\s|T|$)", normalized)
        if not match:
            return None

        year = int(match.group(1))
        month = int(match.group(2))
        if month < 1 or month > 12:
            return None
        return f"{year:04d}-{month:02d}"

    @staticmethod
    def _date_display_column(field_name: str) -> str:
        return f"{field_name}{DATE_DISPLAY_SUFFIX}"

    @staticmethod
    def _is_date_display_column(table_name: str, column_name: str) -> bool:
        if not column_name.endswith(DATE_DISPLAY_SUFFIX):
            return False
        field_name = column_name[: -len(DATE_DISPLAY_SUFFIX)]
        return field_name in TABLE_DATE_FIELDS.get(table_name, [])

    @staticmethod
    def _field_label(table_name: str, field_name: str) -> str:
        labels = dict(TABLE_FIELD_LABELS.get(table_name, []))
        return labels.get(field_name, field_name)

    def _invalid_date_message(self, table_name: str, row_index: int, field_name: str, value) -> str:
        label = self._field_label(table_name, field_name)
        return (
            f"第 {row_index} 行“{label}”格式无效，当前值为“{value}”。"
            "请填写类似 1990-01、1990.01、1990/01、1990年1月 的年月，或直接留空。"
        )

    def create_tables(self):
        """Create or migrate core data tables."""
        tables = {
            "base_info": """
                CREATE TABLE IF NOT EXISTS base_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sequence INTEGER,
                    name TEXT NOT NULL,
                    next_promotion TEXT,
                    current_position TEXT,
                    current_position_date TEXT,
                    current_grade TEXT,
                    current_grade_date TEXT,
                    previous_position1 TEXT,
                    previous_position1_date TEXT,
                    previous_position2 TEXT,
                    previous_position2_date TEXT,
                    current_legal_position TEXT,
                    current_legal_position_date TEXT,
                    previous_legal_position TEXT,
                    previous_legal_position_date TEXT,
                    admission_date TEXT,
                    entry_date TEXT,
                    gender TEXT,
                    birth_date TEXT,
                    ethnicity TEXT,
                    hometown TEXT,
                    work_start_date TEXT,
                    party_date TEXT,
                    fulltime_education TEXT,
                    fulltime_school TEXT,
                    parttime_education TEXT,
                    parttime_school TEXT,
                    rewards TEXT,
                    assessment_0 TEXT,
                    assessment_1 TEXT,
                    assessment_2 TEXT,
                    assessment_3 TEXT,
                    assessment_4 TEXT,
                    remarks TEXT
                );
            """,
            "system_config": """
                CREATE TABLE IF NOT EXISTS system_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_key TEXT UNIQUE NOT NULL,
                    config_value TEXT
                );
            """,
            "rewards": self._related_table_ddl("rewards"),
            "family": self._related_table_ddl("family"),
            "resume": self._related_table_ddl("resume"),
            "users": """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL
                );
            """,
            "user_permissions": """
                CREATE TABLE IF NOT EXISTS user_permissions (
                    username TEXT PRIMARY KEY,
                    base_info INTEGER DEFAULT 0,
                    rewards INTEGER DEFAULT 0,
                    family INTEGER DEFAULT 0,
                    resume INTEGER DEFAULT 0,
                    FOREIGN KEY(username) REFERENCES users(username)
                );
            """,
        }

        cursor = self.conn.cursor()
        try:
            for table_name, ddl in tables.items():
                cursor.execute(ddl)
                logger.info(f"表 {table_name} 创建/验证成功")

            self._migrate_related_tables()
            self._migrate_date_display_columns()
            self._create_indexes()
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"创建或迁移数据库表失败: {e}")
            raise

    def _related_table_ddl(self, table_name: str, physical_table_name: Optional[str] = None) -> str:
        physical_table_name = physical_table_name or table_name
        columns = [f"{name} {definition}" for name, definition in RELATED_TABLE_COLUMNS[table_name]]
        columns.append(
            "FOREIGN KEY(person_id) REFERENCES base_info(id) ON UPDATE CASCADE ON DELETE CASCADE"
        )
        return f"CREATE TABLE IF NOT EXISTS {physical_table_name} ({', '.join(columns)});"

    def _table_exists(self, table_name: str) -> bool:
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None

    def _migrate_date_display_columns(self):
        cursor = self.conn.cursor()
        for table_name, date_fields in TABLE_DATE_FIELDS.items():
            if not self._table_exists(table_name):
                continue

            columns = set(self.get_table_columns(table_name))
            for field_name in date_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {field_name} TEXT")
                    columns.add(field_name)

                display_column = self._date_display_column(field_name)
                if display_column not in columns:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {display_column} TEXT")
                    columns.add(display_column)

            select_columns = ["id"]
            for field_name in date_fields:
                select_columns.append(field_name)
                select_columns.append(self._date_display_column(field_name))

            rows = cursor.execute(
                f"SELECT {', '.join(select_columns)} FROM {table_name}"
            ).fetchall()
            for row in rows:
                updates = []
                values = []
                for field_name in date_fields:
                    display_column = self._date_display_column(field_name)
                    current_value = row[field_name]
                    display_value = row[display_column]

                    normalized_value = self._normalize_month_value(current_value)
                    if normalized_value is None and self._is_blank_value(current_value):
                        normalized_value = self._normalize_month_value(display_value)

                    target_display = display_value
                    if self._is_blank_value(display_value) and not self._is_blank_value(current_value):
                        target_display = str(current_value)

                    if current_value != normalized_value:
                        updates.append(f"{field_name}=?")
                        values.append(normalized_value)
                    if display_value != target_display:
                        updates.append(f"{display_column}=?")
                        values.append(target_display)

                if updates:
                    values.append(row["id"])
                    cursor.execute(
                        f"UPDATE {table_name} SET {', '.join(updates)} WHERE id=?",
                        values,
                    )

    def _create_indexes(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_base_info_sequence_name
            ON base_info(sequence, name)
            WHERE sequence IS NOT NULL AND TRIM(CAST(sequence AS TEXT)) <> ''
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_base_info_name_without_sequence
            ON base_info(name)
            WHERE sequence IS NULL OR TRIM(CAST(sequence AS TEXT)) = ''
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_base_info_birth_date
            ON base_info(birth_date)
        """)
        for table_name in RELATED_TABLES:
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_person_id ON {table_name}(person_id)"
            )

    def _migrate_related_tables(self):
        for table_name in RELATED_TABLES:
            if "person_id" not in self.get_table_columns(table_name):
                self._migrate_related_table(table_name)

    def _migrate_related_table(self, table_name: str):
        duplicate_keys = self._find_duplicate_base_person_keys()
        if duplicate_keys:
            sample = ", ".join(
                f"sequence={sequence or '空'}, name={name}, count={count}"
                for sequence, name, count in duplicate_keys[:5]
            )
            raise sqlite3.IntegrityError(f"base_info 存在重复人员键，无法迁移: {sample}")

        unmatched = self._find_unmatched_related_rows(table_name)
        if unmatched:
            sample = ", ".join(
                f"id={row['id']}, sequence={row.get('sequence') or '空'}, name={row.get('name') or '空'}"
                for row in unmatched[:5]
            )
            raise sqlite3.IntegrityError(f"{table_name} 存在找不到 base_info 的记录，无法迁移: {sample}")

        cursor = self.conn.cursor()
        temp_table = f"{table_name}_new"
        cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
        cursor.execute(self._related_table_ddl(table_name, temp_table))

        old_columns = self.get_table_columns(table_name)
        target_columns = [name for name, _ in RELATED_TABLE_COLUMNS[table_name]]
        insert_columns = [column for column in target_columns if column in old_columns or column == "person_id"]
        old_rows = cursor.execute(f"SELECT * FROM {table_name}").fetchall()
        for old_row in old_rows:
            row_dict = dict(old_row)
            key = self._extract_person_key(row_dict)
            person_id = self._find_base_person_id_by_key(key)
            insert_values = []
            for column in insert_columns:
                if column == "person_id":
                    insert_values.append(person_id)
                else:
                    insert_values.append(row_dict.get(column))
            placeholders = ", ".join(["?"] * len(insert_columns))
            cursor.execute(
                f"INSERT INTO {temp_table} ({', '.join(insert_columns)}) VALUES ({placeholders})",
                insert_values,
            )
        cursor.execute(f"DROP TABLE {table_name}")
        cursor.execute(f"ALTER TABLE {temp_table} RENAME TO {table_name}")
        logger.info(f"表 {table_name} 已迁移到 person_id 外键结构")

    def _find_duplicate_base_person_keys(self) -> List[tuple]:
        cursor = self.conn.cursor()
        rows = cursor.execute("SELECT sequence, name FROM base_info").fetchall()
        counts = {}
        for row in rows:
            key = (self._normalize_sequence(row["sequence"]), str(row["name"] or "").strip())
            counts[key] = counts.get(key, 0) + 1
        return [
            (sequence, name, count)
            for (sequence, name), count in counts.items()
            if name and count > 1
        ]

    def _find_unmatched_related_rows(self, table_name: str) -> List[Dict]:
        cursor = self.conn.cursor()
        rows = cursor.execute(f"SELECT * FROM {table_name}").fetchall()
        unmatched = []
        for row in rows:
            row_dict = dict(row)
            if self._find_base_person_id_by_key(self._extract_person_key(row_dict)) is None:
                unmatched.append(row_dict)
            if len(unmatched) >= 20:
                break
        return unmatched

    def normalize_column_name(self, name: str) -> str:
        """Normalize Excel headers to database field names."""
        cleaned_name = re.sub(r"[\s\u3000\n]+", "", str(name))
        logger.debug(f"清理列名: '{name}' -> '{cleaned_name}'")

        if cleaned_name in COLUMN_LABEL_TO_FIELD:
            return COLUMN_LABEL_TO_FIELD[cleaned_name]
        if cleaned_name.lower() in {"person_id", "personid"}:
            return "person_id"
        if "职级" in cleaned_name and "等级" in cleaned_name and "时间" in cleaned_name:
            return "current_grade_date"
        if "职级" in cleaned_name and "等级" in cleaned_name:
            return "current_grade"
        if re.search(r"籍贯", cleaned_name):
            return "hometown"

        return re.sub(r"[^\w]", "", cleaned_name).lower()

    def get_assessment_years(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT config_value FROM system_config WHERE config_key='assessment_years'")
        row = cursor.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError) as e:
            logger.error(f"读取考核年份配置失败: {e}")
            return None

    def set_assessment_years(self, years):
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "REPLACE INTO system_config (config_key, config_value) VALUES (?, ?)",
                ("assessment_years", json.dumps(years, ensure_ascii=False)),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"设置考核年份配置失败: {e}")
            return False

    def clear_assessment_years(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM system_config WHERE config_key='assessment_years'")
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"清除考核年份配置失败: {e}")
            return False

    def import_excel_data(self, table_name: str, data: List[Dict[str, Any]]):
        validate_table_name(table_name)
        if not data:
            logger.warning(f"尝试导入空数据集到表 {table_name}")
            return

        logger.info(f"开始导入 {table_name}，共 {len(data)} 条记录")
        for i, row in enumerate(data[:3]):
            logger.debug(f"表 {table_name} 样本记录 {i + 1}: {row}")

        normalized_data = self._normalize_import_rows(table_name, data)
        if not normalized_data:
            logger.warning(f"导入到表 {table_name} 时未找到有效字段，跳过导入")
            return

        if table_name == "base_info":
            self._upsert_base_info_rows(normalized_data)
        else:
            self._insert_related_rows(table_name, normalized_data)

    def _normalize_import_rows(self, table_name: str, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        valid_columns = set(self.get_table_columns(table_name))
        date_fields = set(TABLE_DATE_FIELDS.get(table_name, []))
        related_business_columns = []
        if table_name in RELATED_TABLES:
            valid_columns.update({"sequence", "name"})
            related_business_columns = self._related_business_columns(table_name)

        normalized_data = []
        for row_index, row in enumerate(data, start=1):
            normalized_row = {}
            for col_name, value in row.items():
                normalized_col = self.normalize_column_name(col_name)
                logger.debug(f"列名映射: '{col_name}' -> '{normalized_col}'")
                if normalized_col in valid_columns:
                    if normalized_col == "sequence":
                        value = self._sequence_value_for_storage(value)
                        normalized_row[normalized_col] = value
                        continue

                    if normalized_col in date_fields:
                        normalized_value = self._normalize_month_value(value)
                        if normalized_value is None and not self._is_blank_import_value(value):
                            raise ValueError(self._invalid_date_message(table_name, row_index, normalized_col, value))
                        normalized_row[normalized_col] = normalized_value
                        display_column = self._date_display_column(normalized_col)
                        if display_column in valid_columns and display_column not in normalized_row:
                            normalized_row[display_column] = self._date_display_value(value)
                        continue

                    normalized_row[normalized_col] = value
            if normalized_row:
                if (
                    table_name in RELATED_TABLES
                    and not self._has_related_business_content(normalized_row, related_business_columns)
                ):
                    continue
                normalized_data.append(normalized_row)
        return normalized_data

    @staticmethod
    def _is_blank_import_value(value) -> bool:
        return Database._is_blank_value(value)

    def _related_business_columns(self, table_name: str) -> List[str]:
        return [
            column
            for column in self.get_table_columns(table_name)
            if (
                column not in RELATED_IMPORT_IDENTITY_COLUMNS
                and not self._is_date_display_column(table_name, column)
            )
        ]

    def _has_related_business_content(self, row: Dict[str, Any], business_columns: List[str]) -> bool:
        return any(
            column in row and not self._is_blank_import_value(row.get(column))
            for column in business_columns
        )

    def _sequence_value_for_storage(self, value):
        normalized = self._normalize_sequence(value)
        if not normalized:
            return None
        try:
            number = float(normalized)
            if number.is_integer():
                return int(number)
        except (TypeError, ValueError):
            pass
        return normalized

    def _find_duplicate_base_person_keys_in_records(self, records: List[Dict[str, Any]]):
        seen_keys = {}
        duplicate_keys = []
        duplicate_samples = []
        for index, record in enumerate(records, start=1):
            key = self._extract_person_key(record, normalize_columns=True)
            if not key:
                continue
            if key in seen_keys:
                duplicate_keys.append(key)
                duplicate_samples.append((seen_keys[key], index, key))
                continue
            seen_keys[key] = index
        return duplicate_keys, duplicate_samples

    @staticmethod
    def _format_duplicate_base_person_message(duplicate_samples: List[tuple]) -> str:
        sample = "; ".join(
            f"第 {first_index} 行与第 {duplicate_index} 行 序号={sequence or '空'} 姓名={name or '空'}"
            for first_index, duplicate_index, (sequence, name) in duplicate_samples[:5]
        )
        extra = f" 等 {len(duplicate_samples)} 组" if len(duplicate_samples) > 5 else ""
        return f"人员基本信息导入失败，存在重复人员{extra}: {sample}"

    def _upsert_base_info_rows(self, rows: List[Dict[str, Any]]):
        duplicate_keys, duplicate_samples = self._find_duplicate_base_person_keys_in_records(rows)
        if duplicate_keys:
            raise ValueError(self._format_duplicate_base_person_message(duplicate_samples))

        valid_columns = [column for column in self.get_table_columns("base_info") if column != "id"]
        cursor = self.conn.cursor()
        try:
            for row in rows:
                db_row = {column: row.get(column) for column in valid_columns if column in row}
                if not db_row:
                    continue
                key = self._extract_person_key(db_row)
                existing_id = self._find_base_person_id_by_key(key) if key else None
                if existing_id:
                    update_columns = [column for column in db_row if column not in {"sequence", "name"}]
                    if update_columns:
                        assignments = ", ".join(f"{column}=?" for column in update_columns)
                        values = [db_row[column] for column in update_columns]
                        values.append(existing_id)
                        cursor.execute(f"UPDATE base_info SET {assignments} WHERE id=?", values)
                    continue

                columns = list(db_row.keys())
                placeholders = ", ".join(["?"] * len(columns))
                cursor.execute(
                    f"INSERT INTO base_info ({', '.join(columns)}) VALUES ({placeholders})",
                    [db_row[column] for column in columns],
                )
            self.conn.commit()
            logger.info(f"成功导入 {len(rows)} 条数据到表 base_info")
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"导入数据到表 base_info 失败: {e}")
            raise

    def _insert_related_rows(self, table_name: str, rows: List[Dict[str, Any]]):
        valid_columns = [column for column in self.get_table_columns(table_name) if column != "id"]
        related_business_columns = self._related_business_columns(table_name)
        insert_rows = []
        unresolved = []

        for index, row in enumerate(rows, start=1):
            if not self._has_related_business_content(row, related_business_columns):
                continue

            try:
                person_id = self._resolve_person_id(row)
            except ValueError as e:
                key = self._extract_person_key(row)
                sequence, name = key if key else ("", "")
                unresolved.append((index, sequence, name, str(e)))
                continue

            db_row = {
                column: row.get(column)
                for column in valid_columns
                if column in row and column not in {"sequence", "name"}
            }
            db_row["person_id"] = person_id
            insert_rows.append(db_row)

        if unresolved:
            sample = "; ".join(
                f"第 {index} 行 序号={sequence or '空'} 姓名={name or '空'}: {message}"
                for index, sequence, name, message in unresolved[:5]
            )
            extra = f" 等 {len(unresolved)} 条" if len(unresolved) > 5 else ""
            raise ValueError(f"{table_name} 导入失败，存在无法关联到 base_info 的人员{extra}: {sample}")

        if not insert_rows:
            return

        columns = []
        for row in insert_rows:
            for column in row:
                if column not in columns:
                    columns.append(column)

        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

        cursor = self.conn.cursor()
        try:
            values_to_insert = [[row.get(column) for column in columns] for row in insert_rows]
            cursor.executemany(sql, values_to_insert)
            self.conn.commit()
            logger.info(f"成功导入 {len(insert_rows)} 条数据到表 {table_name}")
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"导入数据到表 {table_name} 失败: {e}")
            raise

    def _resolve_person_id(self, row: Dict[str, Any]) -> int:
        person_id = row.get("person_id")
        if person_id not in (None, ""):
            try:
                person_id_int = int(float(str(person_id).strip()))
            except (TypeError, ValueError):
                raise ValueError(f"person_id 无效: {person_id}")
            cursor = self.conn.cursor()
            existing = cursor.execute("SELECT id FROM base_info WHERE id=?", (person_id_int,)).fetchone()
            if not existing:
                raise ValueError(f"person_id 不存在: {person_id_int}")
            return person_id_int

        key = self._extract_person_key(row)
        if not key:
            raise ValueError("缺少姓名")
        person_id_int = self._find_base_person_id_by_key(key)
        if not person_id_int:
            sequence, name = key
            raise ValueError(f"未找到匹配人员: 序号={sequence or '空'}, 姓名={name}")
        return person_id_int

    def _find_base_person_id_by_key(self, key: Optional[tuple]) -> Optional[int]:
        if not key:
            return None
        sequence, name = key
        cursor = self.conn.cursor()
        rows = cursor.execute(
            "SELECT id, sequence FROM base_info WHERE TRIM(name)=?",
            (name,),
        ).fetchall()
        for row in rows:
            if self._normalize_sequence(row["sequence"]) == sequence:
                return row["id"]
        return None

    def get_table_columns(self, table_name: str) -> List[str]:
        validate_table_name(table_name)
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [col[1] for col in cursor.fetchall()]

    @staticmethod
    def _normalize_sequence(value) -> str:
        if value is None:
            return ""

        text = str(value).strip()
        if not text:
            return ""

        try:
            number = float(text)
            if number.is_integer():
                return str(int(number))
        except (TypeError, ValueError):
            pass

        return text

    def _get_related_select_columns(self, table_name: str) -> List[str]:
        select_columns = list(RELATED_TABLE_DISPLAY_COLUMNS[table_name])
        for field_name in TABLE_DATE_FIELDS.get(table_name, []):
            display_column = f"r.{field_name}{DATE_DISPLAY_SUFFIX}"
            if display_column not in select_columns:
                select_columns.append(display_column)
        return select_columns

    def _fetch_related_person_data(self, table_name: str, person_ids: List[int]) -> List[Dict]:
        validate_table_name(table_name)
        if table_name not in RELATED_TABLES or not person_ids:
            return []

        placeholders = ", ".join(["?"] * len(person_ids))
        select_columns = ", ".join(self._get_related_select_columns(table_name))
        cursor = self.conn.cursor()
        cursor.execute(
            f"""
            SELECT {select_columns}
            FROM {table_name} r
            JOIN base_info b ON b.id = r.person_id
            WHERE r.person_id IN ({placeholders})
            ORDER BY r.person_id, r.id
            """,
            person_ids,
        )
        return [dict(row) for row in cursor.fetchall()]

    def _build_personnel_search_clause(
        self,
        *,
        name: str = None,
        grades: list = None,
        position: list = None,
        birth_start: str = None,
        birth_end: str = None,
        education: list = None,
        parttime_education: list = None,
        table_alias: str = "b",
    ) -> tuple:
        alias = f"{table_alias}." if table_alias else ""
        base_conditions = []
        params = []

        if name:
            base_conditions.append(f"{alias}name LIKE ?")
            params.append(f"%{name}%")

        if grades:
            grade_conditions = []
            for grade in grades:
                grade_conditions.append(f"{alias}current_grade LIKE ?")
                params.append(f"%{grade}%")
            base_conditions.append(f"({' OR '.join(grade_conditions)})")

        if position:
            position_conditions = []
            for pos in position:
                position_conditions.append(f"{alias}current_position = ?")
                params.append(pos)
            base_conditions.append(f"({' OR '.join(position_conditions)})")

        birth_start_key = self._month_key(birth_start)
        birth_end_key = self._month_key(birth_end)
        if birth_start_key and birth_end_key:
            base_conditions.append(f"({alias}birth_date BETWEEN ? AND ?)")
            params.append(birth_start_key)
            params.append(birth_end_key)
        elif birth_start_key:
            base_conditions.append(f"{alias}birth_date >= ?")
            params.append(birth_start_key)
        elif birth_end_key:
            base_conditions.append(f"{alias}birth_date <= ?")
            params.append(birth_end_key)

        if education:
            edu_conditions = []
            for keyword in education:
                edu_conditions.append(f"{alias}fulltime_education LIKE ?")
                params.append(f"%{keyword}%")
            base_conditions.append(f"({' OR '.join(edu_conditions)})")

        if parttime_education:
            parttime_conditions = []
            for keyword in parttime_education:
                parttime_conditions.append(f"{alias}parttime_education LIKE ?")
                params.append(f"%{keyword}%")
            base_conditions.append(f"({' OR '.join(parttime_conditions)})")

        return base_conditions, params

    def search_personnel(
        self,
        name: str = None,
        grades: list = None,
        position: list = None,
        birth_start: str = None,
        birth_end: str = None,
        education: str = None,
        parttime_education: str = None,
        table_name: str = None,
        limit: int = None,
        offset: int = 0,
    ):
        try:
            cursor = self.conn.cursor()
            base_conditions, params = self._build_personnel_search_clause(
                name=name,
                grades=grades,
                position=position,
                birth_start=birth_start,
                birth_end=birth_end,
                education=education,
                parttime_education=parttime_education,
                table_alias="b",
            )
            where_sql = " WHERE " + " AND ".join(base_conditions) if base_conditions else ""
            paginated = limit is not None
            effective_table = table_name or "base_info"

            if table_name is not None:
                validate_table_name(table_name)

            if table_name is None and not paginated:
                base_sql = f"SELECT b.* FROM base_info b{where_sql} ORDER BY b.id"
                cursor.execute(base_sql, params)
                base_info_data = [dict(row) for row in cursor.fetchall()]
                person_ids = [row["id"] for row in base_info_data if row.get("id") is not None]

                results = {"base_info": base_info_data}
                results["rewards"] = self._fetch_related_person_data("rewards", person_ids)
                results["family"] = self._fetch_related_person_data("family", person_ids)
                results["resume"] = self._fetch_related_person_data("resume", person_ids)
                results["total_count"] = len(base_info_data)

                logger.info(f"搜索完成，找到 {len(base_info_data)} 条基础信息记录")
                return results

            if effective_table == "base_info":
                count_sql = f"SELECT COUNT(*) AS total_count FROM base_info b{where_sql}"
                cursor.execute(count_sql, params)
                total_count = int(cursor.fetchone()["total_count"])

                base_sql = f"SELECT b.* FROM base_info b{where_sql} ORDER BY b.id"
                query_params = list(params)
                if paginated:
                    base_sql += " LIMIT ? OFFSET ?"
                    query_params.extend([limit, max(0, offset or 0)])
                cursor.execute(base_sql, query_params)
                rows = [dict(row) for row in cursor.fetchall()]
                results = {"base_info": rows, "total_count": total_count}
                logger.info(f"搜索完成，找到 {total_count} 条基础信息记录")
                return results

            join_sql = f" FROM {effective_table} r JOIN base_info b ON b.id = r.person_id{where_sql}"
            count_sql = f"SELECT COUNT(*) AS total_count{join_sql}"
            cursor.execute(count_sql, params)
            total_count = int(cursor.fetchone()["total_count"])

            select_columns = ", ".join(self._get_related_select_columns(effective_table))
            data_sql = f"SELECT {select_columns}{join_sql} ORDER BY r.person_id, r.id"
            query_params = list(params)
            if paginated:
                data_sql += " LIMIT ? OFFSET ?"
                query_params.extend([limit, max(0, offset or 0)])
            cursor.execute(data_sql, query_params)
            rows = [dict(row) for row in cursor.fetchall()]
            results = {effective_table: rows, "total_count": total_count}
            logger.info(f"搜索完成，找到 {total_count} 条 {effective_table} 记录")
            return results

        except sqlite3.Error as e:
            logger.error(f"搜索人员信息失败: {e}")
            raise

    def get_password(self, username: str) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username=?", (username,))
        row = cursor.fetchone()
        return row["password"] if row else None

    def change_password(self, username: str, new_password: str) -> bool:
        try:
            cursor = self.conn.cursor()
            existing_password = self.get_password(username)
            if existing_password is None:
                if self.is_reserved_admin_username(username) and not self.is_admin(username):
                    logger.warning(f"拒绝创建保留的管理员用户名变体: {username}")
                    return False
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, new_password))
            else:
                cursor.execute("UPDATE users SET password=? WHERE username=?", (new_password, username))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"修改密码失败: {e}")
            self.conn.rollback()
            return False

    def get_all_data(self, table_name: str) -> List[Dict]:
        validate_table_name(table_name)
        try:
            cursor = self.conn.cursor()
            if table_name in RELATED_TABLES:
                select_columns = ", ".join(self._get_related_select_columns(table_name))
                cursor.execute(
                    f"""
                    SELECT {select_columns}
                    FROM {table_name} r
                    JOIN base_info b ON b.id = r.person_id
                    ORDER BY r.id
                    """
                )
            else:
                cursor.execute(f"SELECT * FROM {table_name}")
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"获取表 {table_name} 数据失败: {e}")
            return []

    def _extract_person_key(self, record: Dict, normalize_columns: bool = False) -> Optional[tuple]:
        if normalize_columns:
            normalized_record = {}
            for column_name, value in record.items():
                normalized_record[self.normalize_column_name(column_name)] = value
            record = normalized_record

        name = str(record.get("name") or "").strip()
        if not name:
            return None

        return self._normalize_sequence(record.get("sequence")), name

    @staticmethod
    def _related_import_record_key(person_id: int, record: Dict[str, Any]) -> tuple:
        content_key = tuple(
            sorted(
                (key, str(value))
                for key, value in record.items()
                if key not in RELATED_IMPORT_IDENTITY_COLUMNS
                and not key.endswith(DATE_DISPLAY_SUFFIX)
            )
        )
        return person_id, content_key

    def _filter_duplicate_related_import_rows(
        self,
        table_name: str,
        records: List[Dict[str, Any]],
        skip_existing: bool = True,
    ) -> tuple:
        validate_table_name(table_name)
        if table_name not in RELATED_TABLES:
            return records, 0

        rows = self._normalize_import_rows(table_name, records)
        related_business_columns = self._related_business_columns(table_name)
        filtered_rows = []
        seen_record_keys = set()
        skipped_count = 0

        for row in rows:
            if not self._has_related_business_content(row, related_business_columns):
                continue

            person_id = self._resolve_person_id(row)
            record_key = self._related_import_record_key(person_id, row)
            if record_key in seen_record_keys:
                skipped_count += 1
                continue

            if skip_existing and self._related_record_exists(table_name, person_id, row):
                skipped_count += 1
                continue

            seen_record_keys.add(record_key)
            filtered_rows.append(row)

        return filtered_rows, skipped_count

    def find_duplicate_person_keys(self, table_name: str, records: List[Dict]) -> List[tuple]:
        validate_table_name(table_name)
        if not records:
            return []

        if table_name == "base_info":
            duplicate_keys, _ = self._find_duplicate_base_person_keys_in_records(records)
            existing_keys = {
                key
                for key in (self._extract_person_key(row) for row in self.get_all_data("base_info"))
                if key
            }
            duplicates = []
            for record in records:
                key = self._extract_person_key(record, normalize_columns=True)
                if key and key in existing_keys:
                    duplicates.append(key)
            duplicates.extend(duplicate_keys)
            return duplicates

        duplicates = []
        seen_record_keys = set()
        related_business_columns = self._related_business_columns(table_name)
        normalized_records = self._normalize_import_rows(table_name, records)
        for normalized_record in normalized_records:
            if not self._has_related_business_content(normalized_record, related_business_columns):
                continue

            person_id = None
            try:
                person_id = self._resolve_person_id(normalized_record)
            except ValueError:
                continue

            record_key = self._related_import_record_key(person_id, normalized_record)
            if record_key in seen_record_keys:
                key = self._extract_person_key(normalized_record)
                if key:
                    duplicates.append(key)
                continue
            seen_record_keys.add(record_key)

            if self._related_record_exists(table_name, person_id, normalized_record):
                key = self._extract_person_key(normalized_record)
                if key:
                    duplicates.append(key)
        return duplicates

    def _related_record_exists(self, table_name: str, person_id: int, record: Dict[str, Any]) -> bool:
        table_columns = set(self.get_table_columns(table_name))
        comparable_columns = [
            column
            for column in record
            if (
                column in table_columns
                and column not in {"id", "person_id", "sequence", "name"}
                and not self._is_date_display_column(table_name, column)
            )
        ]
        conditions = ["person_id = ?"]
        params = [person_id]
        for column in comparable_columns:
            conditions.append(f"COALESCE(CAST({column} AS TEXT), '') = ?")
            params.append("" if record.get(column) is None else str(record.get(column)))
        cursor = self.conn.cursor()
        row = cursor.execute(
            f"SELECT 1 FROM {table_name} WHERE {' AND '.join(conditions)} LIMIT 1",
            params,
        ).fetchone()
        return row is not None

    def clear_business_data(self) -> bool:
        try:
            cursor = self.conn.cursor()
            for table_name in RELATED_TABLES:
                cursor.execute(f"DELETE FROM {table_name}")
            cursor.execute("DELETE FROM base_info")
            cursor.execute("DELETE FROM system_config WHERE config_key='assessment_years'")
            self.conn.commit()
            logger.info("业务数据表和年度考核配置已清空")
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"清空业务数据失败: {e}")
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("数据库连接已关闭")

    def __del__(self):
        self.close()

    def add_user(self, username: str, password: str) -> bool:
        if self.is_reserved_admin_username(username):
            logger.warning(f"拒绝新增保留的管理员用户名: {username}")
            return False

        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"添加用户失败: {e}")
            self.conn.rollback()
            return False

    def set_user_permissions(self, username: str, permissions: dict):
        try:
            normalized_permissions = normalize_permissions(permissions)
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO user_permissions
                (username, base_info, rewards, family, resume)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    username,
                    int(normalized_permissions.get("base_info", False)),
                    int(normalized_permissions.get("rewards", False)),
                    int(normalized_permissions.get("family", False)),
                    int(normalized_permissions.get("resume", False)),
                ),
            )
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"设置权限失败: {e}")
            raise

    def get_user_permissions(self, username: str) -> dict:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM user_permissions WHERE username=?", (username,))
        row = cursor.fetchone()
        if row:
            return normalize_permissions({
                "base_info": bool(row["base_info"]),
                "rewards": bool(row["rewards"]),
                "family": bool(row["family"]),
                "resume": bool(row["resume"]),
            })
        return DEFAULT_PERMISSIONS.copy()

    def is_admin(self, username: str) -> bool:
        return username == "admin"

    def is_reserved_admin_username(self, username: str) -> bool:
        return isinstance(username, str) and username.casefold() == "admin"

    def get_all_users(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT username FROM users WHERE username != 'admin'")
        return [row[0] for row in cursor.fetchall()]

    def delete_user(self, username):
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM user_permissions WHERE username=?", (username,))
            cursor.execute("DELETE FROM users WHERE username=?", (username,))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"删除用户失败: {e}")
            self.conn.rollback()
            return False
