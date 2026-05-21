import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


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


def copy_runtime_assets():
    """复制运行时外部资源。models 不打进 exe，保持为 exe 同级目录。"""
    dist_dir = PROJECT_ROOT / "dist"
    source_models = PROJECT_ROOT / "models"
    target_models = dist_dir / "models"

    if not dist_dir.exists():
        print("\n未找到 dist 目录，跳过模型复制。")
        return

    if not source_models.exists():
        print("\n未找到 models 目录，跳过模型复制。")
        return

    if target_models.exists():
        shutil.rmtree(target_models)

    print("\n正在复制 models 目录到 dist（模型文件较大，可能需要一些时间）...")
    shutil.copytree(source_models, target_models)
    print(f"[成功] 已复制模型目录: {target_models}")


if __name__ == "__main__":
    # 1. 清理旧文件
    clean_old_builds()

    # 2. 执行打包
    build_ok = build_executable()

    # 3. 复制外部运行资源
    if build_ok:
        copy_runtime_assets()

    print("\n所有流程执行完毕！你可以直接打开 dist 文件夹运行 '人员信息管理系统.exe' 测试了。")
