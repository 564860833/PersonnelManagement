import os
import sqlite3
import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

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

        # 完整的列名映射字典（使用清理后的名称）
        mappings = {
            # 基本信息表映射
            '序号': 'sequence',
            '姓名': 'name',
            '距离下次职级晋升时间': 'next_promotion',  # 新增映射
            '距离下次职级晋升': 'next_promotion',  # 兼容不同命名
            '晋升时间': 'next_promotion',  # 兼容不同命名
            '现任职务': 'current_position',
            '任现职务时间': 'current_position_date',
            # 处理带斜杠的"职级/等级"
            '职级/等级': 'current_grade',
            '职级等级': 'current_grade',  # 兼容无斜杠情况
            # 处理带斜杠的"任现职级/等级时间"
            '任现职级/等级时间': 'current_grade_date',
            '任现职级等级时间': 'current_grade_date',  # 兼容无斜杠情况
            '前一职务': 'previous_position1',
            '前一职务任职时间': 'previous_position1_date',
            '前二职务': 'previous_position2',
            '前二职务任职时间': 'previous_position2_date',
            '现任法律职务': 'current_legal_position',
            '现任法律职务任职时间': 'current_legal_position_date',
            '前一法律职务': 'previous_legal_position',
            '前一法律职务任职时间': 'previous_legal_position_date',
            '入额时间': 'admission_date',
            '进入检察机关时间': 'entry_date',
            '性别': 'gender',
            '出生年月': 'birth_date',
            '民族': 'ethnicity',
            '籍贯': 'hometown',  # 确保"籍贯"被识别
            '参加工作时间': 'work_start_date',
            '入党时间': 'party_date',
            '全日制学历学位': 'fulltime_education',
            '全日制毕业院校及专业': 'fulltime_school',
            '在职学历学位': 'parttime_education',
            '在职毕业院校及专业': 'parttime_school',
            '奖惩': 'rewards',
            '2021年年度考核结果': 'assessment_2021',
            '2022年年度考核结果': 'assessment_2022',
            '2023年年度考核结果': 'assessment_2023',
            '2024年年度考核结果': 'assessment_2024',
            '2025年年度考核结果': 'assessment_2025',
            '备注': 'remarks',

            # 奖惩信息表映射
            '奖励名称': 'reward_name',
            '奖励批准日期': 'reward_date',
            '奖励批准单位': 'reward_unit',
            '批准机关性质': 'reward_authority_type',
            '惩戒名称': 'punishment_name',
            '惩处批准日期': 'punishment_date',
            '惩戒批准单位': 'punishment_unit',
            '惩戒批准机关性质': 'punishment_authority_type',
            '影响期': 'impact_period',

            # 家庭成员信息表映射
            '称谓': 'relation',
            '家庭成员姓名': 'family_name',
            '出生日期': 'birth_date',
            '政治面貌': 'political_status',
            '家庭成员工作单位': 'work_unit',
            '职务': 'position',

            # 简历信息表映射
            '简历信息': 'resume_text',
            '简历': 'resume_text',
        }

        # 2. 尝试使用清理后的名称进行匹配
        if cleaned_name in mappings:
            return mappings[cleaned_name]

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
        return eval(row[0]) if row else None

    def set_assessment_years(self, years):
        """设置年度考核年份配置"""
        try:
            cursor = self.conn.cursor()
            # 使用REPLACE INTO确保唯一性
            cursor.execute("REPLACE INTO system_config (config_key, config_value) VALUES (?, ?)",
                           ('assessment_years', str(years)))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"设置考核年份配置失败: {e}")
            return False

    def import_excel_data(self, table_name: str, data: List[Dict[str, Any]]):
        """将Excel数据导入到数据库"""
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
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [col[1] for col in cursor.fetchall()]

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
            matching_names = []

            for row in base_results:
                row_dict = dict(row)
                base_info_data.append(row_dict)
                matching_names.append(row_dict['name'])

            # 查询相关的其他表数据
            results = {'base_info': base_info_data}

            if matching_names:
                # 构建IN条件
                name_placeholders = ','.join(['?' for _ in matching_names])

                # 查询奖惩信息
                rewards_sql = f"SELECT * FROM rewards WHERE name IN ({name_placeholders})"
                cursor.execute(rewards_sql, matching_names)
                rewards_data = [dict(row) for row in cursor.fetchall()]
                results['rewards'] = rewards_data

                # 查询家庭成员信息
                family_sql = f"SELECT * FROM family WHERE name IN ({name_placeholders})"
                cursor.execute(family_sql, matching_names)
                family_data = [dict(row) for row in cursor.fetchall()]
                results['family'] = family_data

                # 查询简历信息
                resume_sql = f"SELECT * FROM resume WHERE name IN ({name_placeholders})"
                cursor.execute(resume_sql, matching_names)
                resume_data = [dict(row) for row in cursor.fetchall()]
                results['resume'] = resume_data
            else:
                results['rewards'] = []
                results['family'] = []
                results['resume'] = []

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
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT * FROM {table_name}")
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"获取表 {table_name} 数据失败: {e}")
            return []

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
                INSERT INTO user_permissions 
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
        return {
            'base_info': False,
            'rewards': False,
            'family': False,
            'resume': False
        }

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