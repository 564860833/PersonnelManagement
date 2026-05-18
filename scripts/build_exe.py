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
    except subprocess.CalledProcessError as e:
        print(f"\n[错误] 打包失败，错误代码: {e}")
    except FileNotFoundError:
        print("\n[错误] 找不到 pyinstaller 命令，请确保已通过 'pip install pyinstaller' 安装。")


if __name__ == "__main__":
    # 1. 清理旧文件
    clean_old_builds()

    # 2. 执行打包
    build_executable()

    print("\n所有流程执行完毕！你可以直接打开 dist 文件夹运行 '人员信息管理系统.exe' 测试了。")
