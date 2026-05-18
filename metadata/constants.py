"""Shared table metadata for import, export, query display, and permissions."""

TABLE_LABELS = {
    "base_info": "人员基本信息",
    "rewards": "人员奖惩信息",
    "family": "人员家庭成员信息",
    "resume": "人员简历信息",
}

TABLE_NAMES = tuple(TABLE_LABELS.keys())

DEFAULT_PERMISSIONS = {table_name: False for table_name in TABLE_NAMES}
ADMIN_PERMISSIONS = {table_name: True for table_name in TABLE_NAMES}

TABLE_FIELD_LABELS = {
    "base_info": [
        ("sequence", "序号"),
        ("name", "姓名"),
        ("next_promotion", "距离下次职级晋升时间"),
        ("current_position", "现任职务"),
        ("current_position_date", "任现职务时间"),
        ("current_grade", "职级/等级"),
        ("current_grade_date", "任现职级/等级时间"),
        ("previous_position1", "前一职务"),
        ("previous_position1_date", "前一职务任职时间"),
        ("previous_position2", "前二职务"),
        ("previous_position2_date", "前二职务任职时间"),
        ("current_legal_position", "现任法律职务"),
        ("current_legal_position_date", "现任法律职务任职时间"),
        ("previous_legal_position", "前一法律职务"),
        ("previous_legal_position_date", "前一法律职务任职时间"),
        ("admission_date", "入额时间"),
        ("entry_date", "进入检察机关时间"),
        ("gender", "性别"),
        ("birth_date", "出生年月"),
        ("ethnicity", "民族"),
        ("hometown", "籍贯出生地"),
        ("work_start_date", "参加工作时间"),
        ("party_date", "入党时间"),
        ("fulltime_education", "全日制学历学位"),
        ("fulltime_school", "全日制毕业院校及专业"),
        ("parttime_education", "在职学历学位"),
        ("parttime_school", "在职毕业院校及专业"),
        ("rewards", "奖惩"),
        ("remarks", "备注"),
    ],
    "rewards": [
        ("sequence", "序号"),
        ("name", "姓名"),
        ("reward_name", "奖励名称"),
        ("reward_date", "奖励批准日期"),
        ("reward_unit", "奖励批准单位"),
        ("reward_authority_type", "批准机关性质"),
        ("punishment_name", "惩戒名称"),
        ("punishment_date", "惩处批准日期"),
        ("punishment_unit", "惩戒批准单位"),
        ("punishment_authority_type", "惩戒批准机关性质"),
        ("impact_period", "影响期"),
    ],
    "family": [
        ("sequence", "序号"),
        ("name", "姓名"),
        ("relation", "称谓"),
        ("family_name", "家庭成员姓名"),
        ("birth_date", "出生日期"),
        ("political_status", "政治面貌"),
        ("work_unit", "家庭成员工作单位"),
        ("position", "职务"),
    ],
    "resume": [
        ("sequence", "序号"),
        ("name", "姓名"),
        ("resume_text", "简历信息"),
    ],
}

TABLE_DATE_FIELDS = {
    "base_info": [
        "birth_date",
        "work_start_date",
        "party_date",
        "current_position_date",
        "current_grade_date",
        "previous_position1_date",
        "previous_position2_date",
        "current_legal_position_date",
        "previous_legal_position_date",
        "admission_date",
        "entry_date",
        "next_promotion",
    ],
    "rewards": [
        "reward_date",
        "punishment_date",
    ],
    "family": [
        "birth_date",
    ],
}

COLUMN_LABEL_ALIASES = {
    "距离下次职级晋升": "next_promotion",
    "晋升时间": "next_promotion",
    "职级等级": "current_grade",
    "任现职级等级时间": "current_grade_date",
    "籍贯": "hometown",
    "简历": "resume_text",
}

COLUMN_LABEL_TO_FIELD = {}
for table_fields in TABLE_FIELD_LABELS.values():
    for field_name, label in table_fields:
        COLUMN_LABEL_TO_FIELD[label] = field_name
COLUMN_LABEL_TO_FIELD.update(COLUMN_LABEL_ALIASES)


def get_table_label(table_name):
    return TABLE_LABELS.get(table_name, table_name)


def validate_table_name(table_name):
    if table_name not in TABLE_NAMES:
        raise ValueError(f"无效的表名: {table_name}")
    return table_name


def get_table_field_items(table_name, assessment_years=None):
    fields = TABLE_FIELD_LABELS.get(table_name, [])
    if table_name != "base_info":
        return list(fields)

    items = []
    for field_name, label in fields:
        if field_name == "remarks" and assessment_years:
            for index, year in enumerate(assessment_years):
                items.append((f"assessment_{index}", f"{year}年年度考核结果"))
        items.append((field_name, label))
    return items


def get_table_field_labels(table_name, assessment_years=None):
    return dict(get_table_field_items(table_name, assessment_years))


def get_table_headers(table_name, assessment_years=None):
    return [label for _, label in get_table_field_items(table_name, assessment_years)]


def get_table_field_by_header(table_name, assessment_years=None):
    return {label: field_name for field_name, label in get_table_field_items(table_name, assessment_years)}
