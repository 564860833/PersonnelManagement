import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OLLAMA_RUNTIME_NAMES = ("ollama", "runtime/ollama")
EMBEDDING_MODEL_NAME = "bge-m3:latest"


def clean_old_builds():
    """清理之前打包产生的无用文件和文件夹"""
    print("开始清理旧的打包文件...")

    # 需要删除的文件夹和文件列表
    # 注意：使用 -n 参数后，生成的 spec 文件名也会变成 "人员信息管理系统.spec"
    folders_to_delete = ['build', 'dist', '__pycache__']
    files_to_delete = ['main.spec', '人员信息管理系统.spec']

    # 删除文件夹
    for folder in folders_to_delete:
        folder_path = PROJECT_ROOT / folder
        if folder_path.exists():
            try:
                shutil.rmtree(folder_path)
                print(f"  [成功] 已删除文件夹: {folder}")
            except Exception as e:
                print(f"  [失败] 无法删除文件夹 {folder}: {e}")

    # 删除文件
    for file in files_to_delete:
        file_path = PROJECT_ROOT / file
        if file_path.exists():
            try:
                os.remove(file_path)
                print(f"  [成功] 已删除文件: {file}")
            except Exception as e:
                print(f"  [失败] 无法删除文件 {file}: {e}")

    print("清理完成！\n")


def build_executable():
    """使用 PyInstaller 打包程序"""
    print("开始执行打包命令 (这可能需要几分钟时间)...")

    # 定义打包命令
    # -F: 单文件模式
    # -w: 无控制台窗口
    # -i: 指定图标
    # -n: 指定生成的 exe 文件名
    command = [
        "pyinstaller",
        "-F",
        "-w",
        "-i", "app_icon.ico",
        "-n", "人员信息管理系统",
        "main.py"
    ]

    try:
        # 运行打包命令
        subprocess.run(command, check=True, cwd=PROJECT_ROOT)
        print("\n打包成功！生成的可执行文件位于 dist 文件夹中。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[错误] 打包失败，错误代码: {e}")
        return False
    except FileNotFoundError:
        print("\n[错误] 找不到 pyinstaller 命令，请确保已通过 'pip install pyinstaller' 安装。")
        return False


def find_ollama_runtime_source():
    """查找可复制到 dist 的 Ollama 运行时目录。"""
    for relative_name in OLLAMA_RUNTIME_NAMES:
        candidate = PROJECT_ROOT / relative_name
        if (candidate / "ollama.exe").exists():
            return candidate

    found = shutil.which("ollama")
    if found:
        return Path(found).resolve().parent

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    candidates = [
        Path(local_app_data) / "Programs" / "Ollama",
        Path(program_files) / "Ollama",
        Path(program_files_x86) / "Ollama",
    ]
    for candidate in candidates:
        if (candidate / "ollama.exe").exists():
            return candidate
    return None


def copy_directory(source: Path, target: Path, display_name: str):
    if target.exists():
        shutil.rmtree(target)

    print(f"\n正在复制 {display_name} 到 dist（文件较大时可能需要一些时间）...")
    shutil.copytree(source, target)
    print(f"[成功] 已复制 {display_name}: {target}")


def list_ollama_model_names(models_dir: Path):
    manifests_dir = models_dir / "manifests"
    if not manifests_dir.is_dir():
        return []

    names = []
    for manifest in manifests_dir.rglob("*"):
        if not manifest.is_file():
            continue
        try:
            parts = manifest.relative_to(manifests_dir).parts
        except ValueError:
            continue
        if len(parts) < 4:
            continue
        namespace, model, tag = parts[1], parts[2], parts[3]
        if namespace == "library":
            names.append(f"{model}:{tag}")
        else:
            names.append(f"{namespace}/{model}:{tag}")
    return sorted(set(names))


def warn_if_embedding_model_missing(models_dir: Path):
    model_names = list_ollama_model_names(models_dir)
    if EMBEDDING_MODEL_NAME in model_names:
        print(f"[成功] 已检测到 embedding 模型: {EMBEDDING_MODEL_NAME}")
        return
    print(f"\n[警告] 未在 models 中检测到 embedding 模型 {EMBEDDING_MODEL_NAME}。")
    print("       程序仍可运行，但 AI 语义检索会降级为同义词和模糊匹配。")


def copy_runtime_assets():
    """复制运行时外部资源。模型和 Ollama 运行时保持为 exe 同级目录。"""
    dist_dir = PROJECT_ROOT / "dist"
    source_models = PROJECT_ROOT / "models"
    target_models = dist_dir / "models"
    target_ollama = dist_dir / "ollama"

    if not dist_dir.exists():
        print("\n未找到 dist 目录，跳过运行资源复制。")
        return

    if not source_models.exists():
        print("\n未找到 models 目录，跳过模型复制。")
    else:
        copy_directory(source_models, target_models, "models 目录")
        warn_if_embedding_model_missing(target_models)

    source_ollama = find_ollama_runtime_source()
    if source_ollama is None:
        print("\n[警告] 未找到 Ollama 运行时，AI 功能在未安装 Ollama 的离线电脑上不可用。")
        print("       建议将 ollama.exe 所在目录放到项目根目录的 ollama 文件夹后重新打包。")
        return

    copy_directory(source_ollama, target_ollama, "Ollama 运行时")


if __name__ == "__main__":
    # 1. 清理旧文件
    clean_old_builds()

    # 2. 执行打包
    build_ok = build_executable()

    # 3. 复制外部运行资源
    if build_ok:
        copy_runtime_assets()

    print("\n所有流程执行完毕！你可以直接打开 dist 文件夹运行 '人员信息管理系统.exe' 测试了。")
