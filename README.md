# 人员信息管理系统 v2.0

基于 PyQt5 + SQLite 的桌面端人员信息管理系统，集成本地 Ollama 大语言模型实现 AI 数据分析功能。适用于检察院等组织的人员档案管理场景。

## 功能特性

**数据管理**
- 人员基本信息、奖惩记录、家庭成员、简历四类数据的增删改查
- Excel 批量导入（支持 .xlsx/.xls），自动去重、合并/追加模式
- Excel 导出，含公式注入防护

**智能查询**
- 多条件组合查询：姓名、职级、职务、出生日期范围、学历等
- 分页展示，支持大数据量浏览

**AI 分析助手**
- 集成本地 Ollama 大模型，完全离线运行，数据不出本机
- 自动检测硬件（内存/显存）推荐上下文长度
- 可选择发送给 AI 的数据表和字段
- 上下文压力可视化，Markdown 格式回复渲染

**系统管理**
- 用户登录与角色权限（管理员/普通用户）
- 按数据表粒度的读取权限控制
- 系统日志查看与清理
- 数据库清空（仅管理员）

## 技术栈

| 组件 | 技术 |
|------|------|
| GUI | PyQt5 5.15 |
| 数据库 | SQLite（WAL 模式） |
| 数据处理 | pandas + openpyxl + xlrd |
| AI 推理 | Ollama（本地部署，端口 11435） |
| 打包 | PyInstaller |

## 项目结构

```
├── main.py                 # 程序入口
├── config.py               # 全局配置
├── core/database.py        # 数据库层
├── metadata/               # 表结构定义、字段常量、下拉选项
├── services/               # 业务逻辑
│   ├── ollama_manager.py   #   Ollama 进程管理
│   ├── ai_context.py       #   硬件感知的上下文推荐
│   ├── ai_direct.py        #   AI 对话接口
│   ├── excel_import.py     #   Excel 导入
│   └── excel_export.py     #   Excel 导出
├── ui/                     # 界面层
│   ├── main_window.py      #   主窗口
│   ├── login.py            #   登录
│   ├── query.py            #   查询
│   ├── ai_chat.py          #   AI 对话
│   ├── user_management.py  #   用户管理
│   └── ...
├── scripts/                # 构建与初始化脚本
├── tests/                  # 单元测试（pytest）
└── models/                 # 本地模型文件（不纳入版本控制）
```

## 快速开始

### 环境要求

- Python 3.8+
- Windows 10/11
- Ollama（可选，用于 AI 功能）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
python main.py
```

默认管理员账号：`admin` / `123456`（首次运行自动创建）

### AI 功能

程序会自动在以下位置查找 Ollama：
1. 项目目录下的 `ollama/` 文件夹
2. 系统 PATH
3. Windows 默认安装路径

找到后会在 `127.0.0.1:11435` 启动独立的 Ollama 服务，模型文件存储在项目 `models/` 目录。

## 构建发布包

```bash
# 标准构建
python scripts/build_exe.py

# 含 AI 离线包（打包 Ollama 运行时和模型文件）
python scripts/build_exe.py --ai-package
```

输出位于 `dist/` 目录。

## 测试

```bash
pytest tests/
```

## 数据库设计

- `base_info` — 人员基本信息（主表）
- `rewards` — 奖惩记录（通过 person_id 关联，级联删除）
- `family` — 家庭成员信息
- `resume` — 简历

日期字段统一存储为 `YYYY-MM` 格式，保留 `_display` 列记录原始输入格式。

## 安全特性

- 登录密码加密存储
- SQL 参数化查询防注入
- Excel 导出公式注入防护
- AI 对话数据仅本地处理，不外传
- 按角色的权限隔离
