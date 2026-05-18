import os
import shutil
import glob
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def clean_up():
    # 要删除的目录列表
    dirs_to_remove = ['build', 'dist', '__pycache__']

    # 要删除的文件模式
    file_patterns = ['*.spec', '*.log', '*.pyc']

    # 删除目录
    for dir_name in dirs_to_remove:
        dir_path = PROJECT_ROOT / dir_name
        if dir_path.exists():
            print(f"删除目录: {dir_name}")
            shutil.rmtree(dir_path)

    # 删除文件
    for pattern in file_patterns:
        for file_path in glob.glob(str(PROJECT_ROOT / pattern)):
            print(f"删除文件: {file_path}")
            os.remove(file_path)

    print("清理完成！")


if __name__ == "__main__":
    clean_up()
