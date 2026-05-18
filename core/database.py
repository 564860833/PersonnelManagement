import os
import sqlite3
import re
import logging
import json
from typing import List, Dict, Any, Optional
from metadata.constants import COLUMN_LABEL_TO_FIELD, DEFAULT_PERMISSIONS, TABLE_NAMES, validate_table_name

# 设置日志
logger = logging.getLogger('Database')


class Database:
    def __init__(self, db_path=None):
        # 禁用 XML 功能
        os.environ["DISABLE_XML"] = "1"

        self.conn = None
        self.connect(db_path)
        self.create_tables()

    def connect(self, db_path=None):
        """连接到SQLite数据库"""
        try:
            # 导入配置模块（在函数内部导入以避免循环依赖）
            from config import config

            # 如果提供了自定义路径，则使用该路径
            path = db_path if db_path else config.DB_PATH
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row  # 允许按列名访问
            logger.info(f"成功连接到数据库: {path}")
        except sqlite3.Error as e:
            logger.error(f"数据库连接失败: {e}")
            raise
        except ImportError as e:
            logger.error(f"无法导入配置模块: {e}")
            # 如果无法导入配置模块，使用默认数据库路径
            default_path = 'personnel_system.db'
            self.conn = sqlite3.connect(default_path)
            self.conn.row_factory = sqlite3.Row
            logger.info(f"使用默认路径连接数据库: {default_path}")

    def create_tables(self):
        """创建核心数据表及用户表"""
        tables = {
            'base_info': """
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
                    -- 改为通用标记字段
                    assessment_0 TEXT,
                    assessment_1 TEXT,
                    assessment_2 TEXT,
                    assessment_3 TEXT,
                    assessment_4 TEXT,
                    remarks TEXT
                );
            """,
            'system_config': """
                CREATE TABLE IF NOT EXISTS system_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_key TEXT UNIQUE NOT NULL,
                    config_value TEXT
                );
            """,
            'rewards': """
                CREATE TABLE IF NOT EXISTS rewards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sequence INTEGER,
                    name TEXT NOT NULL,
                    reward_name TEXT,
                    reward_date TEXT,
                    reward_unit TEXT,
                    reward_authority_type TEXT,
                    punishment_name TEXT,
                    punishment_date TEXT,
                    punishment_unit TEXT,
                    punishment_authority_type TEXT,
                    impact_period TEXT
                );
            """,
            'family': """
                CREATE TABLE IF NOT EXISTS family (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sequence INTEGER,
                    name TEXT NOT NULL,
                    relation TEXT,
                    family_name TEXT,
                    birth_date TEXT,
                    political_status TEXT,
                    work_unit TEXT,
                    position TEXT
                );
            """,
            'resume': """
                CREATE TABLE IF NOT EXISTS resume (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sequence INTEGER,
                    name TEXT NOT NULL,
                    resume_text TEXT
                );
            """,
            'users': """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL
                );
            """,
            'user_permissions': """
                CREATE TABLE IF NOT EXISTS user_permissions (
                    username TEXT PRIMARY KEY,
                    base_info INTEGER DEFAULT 0,
                    rewards INTEGER DEFAULT 0,
                    family INTEGER DEFAULT 0,
                    resume INTEGER DEFAULT 0,
                    FOREIGN KEY(username) REFERENCES users(username)
                );
            """
        }
        cursor = self.conn.cursor()
        for table_name, ddl in tables.items():
            try:
                cursor.execute(ddl)
                logger.info(f"表 {table_name} 创建/验证成功")
            except sqlite3.Error as e:
                logger.error(f"创建表 {table_name} 失败: {e}")
                raise

    def normalize_column_name(self, name: str) -> str:
        """规范化Excel列名到数据库字段的映射，自动处理空格和换行符"""
        # 1. 清理列名中的空格和换行符
        cleaned_name = re.sub(r'[\s\u3000\n]+', '', name)

        # 调试日志
        logger.debug(f"清理列名: '{name}' -> '{cleaned_name}'")

        # 2. 尝试使用清理后的名称进行匹配
        if cleaned_name in COLUMN_LABEL_TO_FIELD:
            return COLUMN_LABEL_TO_FIELD[cleaned_name]

        # 3. 特殊处理"任现职级等级时间"的各种变体（支持带斜杠）
        if re.search(r'任.*现.*职级[\\/]?等级时间', cleaned_name):
            return 'current_grade_date'
        if re.search(r'职级[\\/]?等级', cleaned_name):
            return 'current_grade'
        if re.search(r'籍贯', cleaned_name):
            return 'hometown'

        # 4. 如果没有直接映射，则进行规范化处理
        normalized = re.sub(r'[^\w]', '', cleaned_name).lower()
        return normalized

    def get_assessment_years(self):
        """获取年度考核年份配置"""
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
        """设置年度考核年份配置"""
        try:
            cursor = self.conn.cursor()
            # 使用REPLACE INTO确保唯一性
            cursor.execute("REPLACE INTO system_config (config_key, config_value) VALUES (?, ?)",
                           ('assessment_years', json.dumps(years, ensure_ascii=False)))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"设置考核年份配置失败: {e}")
            return False

    def import_excel_data(self, table_name: str, data: List[Dict[str, Any]]):
        """将Excel数据导入到数据库"""
        validate_table_name(table_name)
        if not data:
            logger.warning(f"尝试导入空数据集到表 {table_name}")
            return

        # 添加导入日志输出
        logger.info(f"开始导入{table_name}，共{len(data)}条记录")

        # 记录前3条数据样本
        if data:
            for i, row in enumerate(data[:3]):
                logger.debug(f"表{table_name} 样本记录{i + 1}: {str(row)}")

        valid_columns = self.get_table_columns(table_name)
        placeholders = []
        normalized_data = []

        # 添加列名映射调试信息
        for row in data:
            normalized_row = {}
            for col_name, value in row.items():
                original_col = col_name
                normalized_col = self.normalize_column_name(col_name)

                # 记录映射关系
                logger.debug(f"列名映射: '{original_col}' -> '{normalized_col}'")

                if normalized_col in valid_columns:
                    # 直接使用原始值，不进行任何日期格式转换
                    normalized_row[normalized_col] = value
                    if normalized_col not in placeholders:
                        placeholders.append(normalized_col)
            if normalized_row:
                normalized_data.append(normalized_row)
        if not placeholders:
            logger.warning(f"导入到表 {table_name} 时未找到有效字段，跳过导入")
            return

        columns = ', '.join(placeholders)
        values_placeholder = ', '.join(['?'] * len(placeholders))
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({values_placeholder})"

        cursor = self.conn.cursor()
        try:
            values_to_insert = [[row.get(col) for col in placeholders] for row in normalized_data]
            cursor.executemany(sql, values_to_insert)
            self.conn.commit()
            logger.info(f"成功导入 {len(normalized_data)} 条数据到表 {table_name}")
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"导入数据到表 {table_name} 失败: {e}")
            raise

    def get_table_columns(self, table_name: str) -> List[str]:
        """获取指定表的所有列名"""
        validate_table_name(table_name)
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [col[1] for col in cursor.fetchall()]

    @staticmethod
    def _normalize_sequence(value) -> str:
        """规范化序号，兼容 Excel 导入时可能出现的 1/1.0 差异。"""
        if value is None:
            return ''

        text = str(value).strip()
        if not text:
            return ''

        try:
            number = float(text)
            if number.is_integer():
                return str(int(number))
        except (TypeError, ValueError):
            pass

        return text

    def _build_person_match_keys(self, base_rows: List[Dict]) -> tuple:
        """构建序号+姓名关联键，避免同名人员数据串联。"""
        sequence_keys = set()
        no_sequence_names = set()

        for row in base_rows:
            name = str(row.get('name') or '').strip()
            if not name:
                continue

            sequence_text = self._normalize_sequence(row.get('sequence'))
            if sequence_text:
                sequence_keys.add((sequence_text, name))
            else:
                no_sequence_names.add(name)

        return sequence_keys, no_sequence_names

    def _fetch_related_person_data(self, table_name: str, sequence_keys: set, no_sequence_names: set) -> List[Dict]:
        """查询与基础信息匹配的关联表数据。"""
        validate_table_name(table_name)
        if not sequence_keys and not no_sequence_names:
            return []

        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")

        rows = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            name = str(row_dict.get('name') or '').strip()
            sequence_text = self._normalize_sequence(row_dict.get('sequence'))

            if sequence_text and (sequence_text, name) in sequence_keys:
                rows.append(row_dict)
            elif not sequence_text and name in no_sequence_names:
                rows.append(row_dict)

        return rows

    def search_personnel(self, name: str = None,
                         grades: list = None,
                         position: list = None,
                         birth_start: str = None,
                         birth_end: str = None,
                         education: str = None,  # 修改为字符串类型
                         parttime_education: str = None):  # 修改为字符串类型
        """搜索人员信息，返回所有相关表的数据"""
        try:
            # 构建基础查询条件
            base_conditions = []
            params = []

            # 添加姓名条件
            if name:
                base_conditions.append("name LIKE ?")
                params.append(f"%{name}%")

            # 添加职级/等级条件（支持多值）
            if grades:
                # 创建OR条件列表
                grade_conditions = []
                for grade in grades:
                    grade_conditions.append("current_grade LIKE ?")
                    params.append(f"%{grade}%")

                # 将多个OR条件组合为一个条件组
                base_conditions.append(f"({' OR '.join(grade_conditions)})")

            # 添加现任职务条件
            if position:
                # 创建OR条件列表
                position_conditions = []
                for pos in position:
                    position_conditions.append("current_position = ?")
                    params.append(pos)  # 直接使用完整职位名称

                # 将多个OR条件组合为一个条件组
                base_conditions.append(f"({' OR '.join(position_conditions)})")

            # 处理出生年月范围条件（格式为yyyy.MM）
            if birth_start and birth_end:
                base_conditions.append("(REPLACE(birth_date, '-', '.') BETWEEN ? AND ?)")
                params.append(birth_start)
                params.append(birth_end)
            elif birth_start:
                base_conditions.append("REPLACE(birth_date, '-', '.') >= ?")
                params.append(birth_start)
            elif birth_end:
                base_conditions.append("REPLACE(birth_date, '-', '.') <= ?")
                params.append(birth_end)

            # 添加全日制学历学位条件（模糊查询）
            if education:
                edu_conditions = []
                for keyword in education:
                    edu_conditions.append("fulltime_education LIKE ?")
                    params.append(f"%{keyword}%")
                base_conditions.append(f"({' OR '.join(edu_conditions)})")


            # 修改在职学历学位条件处理
            if parttime_education:
                parttime_conditions = []
                for keyword in parttime_education:
                    parttime_conditions.append("parttime_education LIKE ?")
                    params.append(f"%{keyword}%")
                base_conditions.append(f"({' OR '.join(parttime_conditions)})")

            # 构建基础查询SQL
            base_sql = "SELECT * FROM base_info"
            if base_conditions:
                base_sql += " WHERE " + " AND ".join(base_conditions)

            cursor = self.conn.cursor()
            cursor.execute(base_sql, params)
            base_results = cursor.fetchall()

            # 转换为字典列表
            base_info_data = []

            for row in base_results:
                row_dict = dict(row)
                base_info_data.append(row_dict)

            # 查询相关的其他表数据
            results = {'base_info': base_info_data}
            sequence_keys, no_sequence_names = self._build_person_match_keys(base_info_data)

            results['rewards'] = self._fetch_related_person_data('rewards', sequence_keys, no_sequence_names)
            results['family'] = self._fetch_related_person_data('family', sequence_keys, no_sequence_names)
            results['resume'] = self._fetch_related_person_data('resume', sequence_keys, no_sequence_names)

            logger.info(f"搜索完成，找到 {len(base_info_data)} 条基础信息记录")
            return results

        except sqlite3.Error as e:
            logger.error(f"搜索人员信息失败: {e}")
            raise

    def get_password(self, username: str) -> Optional[str]:
        """获取指定用户的密码"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username=?", (username,))
        row = cursor.fetchone()
        return row['password'] if row else None

    def change_password(self, username: str, new_password: str) -> bool:
        """修改或插入用户密码"""
        try:
            cursor = self.conn.cursor()
            if self.get_password(username) is None:
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                               (username, new_password))
            else:
                cursor.execute("UPDATE users SET password=? WHERE username=?",
                               (new_password, username))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"修改密码失败: {e}")
            self.conn.rollback()
            return False

    def backup_database(self, backup_path: str) -> bool:
        """备份数据库到指定路径"""
        try:
            with sqlite3.connect(backup_path) as backup_conn:
                self.conn.backup(backup_conn)
            logger.info(f"数据库已备份到: {backup_path}")
            return True
        except sqlite3.Error as e:
            logger.error(f"数据库备份失败: {e}")
            return False

    def get_all_data(self, table_name: str) -> List[Dict]:
        """获取指定表的所有数据"""
        validate_table_name(table_name)
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT * FROM {table_name}")
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"获取表 {table_name} 数据失败: {e}")
            return []

    def get_table_row_count(self, table_name: str) -> int:
        """获取指定业务表的数据行数。"""
        validate_table_name(table_name)
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]

    def _extract_person_key(self, record: Dict, normalize_columns: bool = False) -> Optional[tuple]:
        """提取记录的序号+姓名键。"""
        if normalize_columns:
            normalized_record = {}
            for column_name, value in record.items():
                normalized_record[self.normalize_column_name(column_name)] = value
            record = normalized_record

        name = str(record.get('name') or '').strip()
        if not name:
            return None

        return self._normalize_sequence(record.get('sequence')), name

    def find_duplicate_person_keys(self, table_name: str, records: List[Dict]) -> List[tuple]:
        """找出待导入记录中已存在于目标表的序号+姓名键。"""
        validate_table_name(table_name)
        existing_keys = {
            key
            for key in (self._extract_person_key(row) for row in self.get_all_data(table_name))
            if key
        }

        duplicates = []
        for record in records:
            key = self._extract_person_key(record, normalize_columns=True)
            if key and key in existing_keys:
                duplicates.append(key)

        return duplicates

    def clear_table_data(self, table_name: str) -> bool:
        """清空指定业务表。"""
        validate_table_name(table_name)
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"DELETE FROM {table_name}")
            if table_name == 'base_info':
                cursor.execute("DELETE FROM system_config WHERE config_key='assessment_years'")
            self.conn.commit()
            logger.info(f"业务表 {table_name} 已清空")
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"清空业务表 {table_name} 失败: {e}")
            return False

    def clear_business_data(self) -> bool:
        """清空业务数据表和年度考核配置。"""
        try:
            cursor = self.conn.cursor()
            for table_name in TABLE_NAMES:
                cursor.execute(f"DELETE FROM {table_name}")

            cursor.execute("DELETE FROM system_config WHERE config_key='assessment_years'")
            self.conn.commit()
            logger.info("业务数据表和年度考核配置已清空")
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"清空业务数据失败: {e}")
            return False

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")

    def __del__(self):
        self.close()

    # 以下是新增的用户管理方法
    def add_user(self, username: str, password: str) -> bool:
        """添加新用户"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                           (username, password))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"添加用户失败: {e}")
            self.conn.rollback()
            return False

    def set_user_permissions(self, username: str, permissions: dict):
        """设置用户权限"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO user_permissions 
                (username, base_info, rewards, family, resume) 
                VALUES (?, ?, ?, ?, ?)
            """, (
                username,
                int(permissions.get('base_info', False)),
                int(permissions.get('rewards', False)),
                int(permissions.get('family', False)),
                int(permissions.get('resume', False))
            ))
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"设置权限失败: {e}")
            raise

    def get_user_permissions(self, username: str) -> dict:
        """获取用户权限"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM user_permissions WHERE username=?", (username,))
        row = cursor.fetchone()
        if row:
            return {
                'base_info': bool(row['base_info']),
                'rewards': bool(row['rewards']),
                'family': bool(row['family']),
                'resume': bool(row['resume'])
            }
        return DEFAULT_PERMISSIONS.copy()

    def is_admin(self, username: str) -> bool:
        """检查用户是否是管理员"""
        return username.lower() == "admin"

    def get_all_users(self):
        """获取除admin外的所有用户"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT username FROM users WHERE username != 'admin'")
        return [row[0] for row in cursor.fetchall()]

    def delete_user(self, username):
        """删除用户及其权限"""
        try:
            cursor = self.conn.cursor()

            # 删除用户权限
            cursor.execute("DELETE FROM user_permissions WHERE username=?", (username,))

            # 删除用户
            cursor.execute("DELETE FROM users WHERE username=?", (username,))

            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"删除用户失败: {e}")
            self.conn.rollback()
            return False
