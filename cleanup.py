import os
import shutil
import glob


def clean_up():
    # 要删除的目录列表
    dirs_to_remove = ['build', 'dist', '__pycache__']

    # 要删除的文件模式
    file_patterns = ['*.spec', '*.log', '*.pyc']

    # 删除目录
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            print(f"删除目录: {dir_name}")
            shutil.rmtree(dir_name)

    # 删除文件
    for pattern in file_patterns:
        for file_path in glob.glob(pattern):
            print(f"删除文件: {file_path}")
            os.remove(file_path)

    print("清理完成！")


if __name__ == "__main__":
    clean_up()