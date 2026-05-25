# -*- coding: utf-8 -*-

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "人员信息管理系统"
AI_PACKAGE_NAME = f"{APP_NAME}-AI离线包"
SPEC_FILE = PROJECT_ROOT / f"{APP_NAME}.spec"
DIST_DIR = PROJECT_ROOT / "dist"
APP_DIST_DIR = DIST_DIR / APP_NAME
OLLAMA_RUNTIME_NAMES = ("ollama", "runtime/ollama")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Build the personnel management desktop app.")
    parser.add_argument(
        "--ai-package",
        action="store_true",
        help="Create a separate offline AI asset package with models/ and ollama/.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip PyInstaller and only run the requested packaging steps.",
    )
    parser.add_argument(
        "--skip-runtime-assets",
        action="store_true",
        help="Compatibility flag. Runtime AI assets are skipped by default.",
    )
    return parser.parse_args(argv)


def assert_project_child(path: Path):
    resolved_root = PROJECT_ROOT.resolve()
    resolved_path = path.resolve()
    if resolved_path == resolved_root:
        raise RuntimeError("refusing to remove project root")
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError(f"refusing to operate outside project root: {resolved_path}") from exc


def remove_tree(path: Path, display_name: str):
    if not path.exists():
        return
    assert_project_child(path)
    shutil.rmtree(path)
    print(f"Removed {display_name}: {path}")


def clean_old_builds():
    print("Cleaning old build outputs...")
    remove_tree(PROJECT_ROOT / "build", "build directory")
    remove_tree(APP_DIST_DIR, "app dist directory")
    remove_tree(PROJECT_ROOT / "__pycache__", "__pycache__ directory")
    print("Clean complete.\n")


def print_build_environment() -> bool:
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print("[ERROR] PyInstaller is not installed in the current Python environment.")
        stderr = (result.stderr or "").strip()
        if stderr:
            print(stderr)
        print(r"Run this script with .\.venv\Scripts\python.exe scripts\build_exe.py")
        return False

    print(f"PyInstaller version: {(result.stdout or '').strip()}")
    return True


def build_executable() -> bool:
    if not SPEC_FILE.exists():
        print(f"[ERROR] Spec file not found: {SPEC_FILE}")
        return False

    if not print_build_environment():
        return False

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC_FILE),
    ]
    print("\nRunning PyInstaller...")
    try:
        subprocess.run(command, check=True, cwd=PROJECT_ROOT)
    except subprocess.CalledProcessError as exc:
        print(f"\n[ERROR] Build failed with exit code {exc.returncode}.")
        return False

    exe_path = APP_DIST_DIR / f"{APP_NAME}.exe"
    if not exe_path.exists():
        print(f"\n[ERROR] Expected executable was not created: {exe_path}")
        return False

    print(f"\nBase app build complete: {exe_path}")
    return True


def find_ollama_runtime_source():
    for relative_name in OLLAMA_RUNTIME_NAMES:
        candidate = PROJECT_ROOT / relative_name
        if (candidate / "ollama.exe").exists():
            return candidate

    found = shutil.which("ollama")
    if found:
        return Path(found).resolve().parent

    candidates = [
        Path.home() / "AppData" / "Local" / "Programs" / "Ollama",
        Path("C:/Program Files/Ollama"),
        Path("C:/Program Files (x86)/Ollama"),
    ]
    for candidate in candidates:
        if (candidate / "ollama.exe").exists():
            return candidate
    return None


def copy_directory(source: Path, target: Path, display_name: str):
    print(f"Copying {display_name}: {source} -> {target}")
    shutil.copytree(source, target)


def write_ai_package_readme(target_dir: Path):
    readme = target_dir / "README.txt"
    readme.write_text(
        (
            "人员信息管理系统 AI 离线包\n"
            "\n"
            "使用方法：\n"
            "1. 先解压/复制基础程序目录 dist\\人员信息管理系统。\n"
            "2. 将本目录中的 models 和 ollama 两个文件夹复制到基础程序目录内。\n"
            "3. 最终目录应包含 人员信息管理系统.exe、models、ollama。\n"
            "4. 重新启动程序后，AI 功能会优先使用程序目录内的离线资源。\n"
        ),
        encoding="utf-8",
    )


def create_ai_package() -> bool:
    source_models = PROJECT_ROOT / "models"
    source_ollama = find_ollama_runtime_source()

    missing = []
    if not source_models.exists():
        missing.append(str(source_models))
    if source_ollama is None:
        missing.append("ollama runtime directory containing ollama.exe")
    if missing:
        print("[ERROR] Cannot create AI package. Missing:")
        for item in missing:
            print(f"  - {item}")
        return False

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    final_dir = DIST_DIR / AI_PACKAGE_NAME
    temp_dir = DIST_DIR / f"{AI_PACKAGE_NAME}.tmp"
    remove_tree(temp_dir, "temporary AI package")
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        copy_directory(source_models, temp_dir / "models", "models")
        copy_directory(source_ollama, temp_dir / "ollama", "Ollama runtime")
        write_ai_package_readme(temp_dir)

        remove_tree(final_dir, "previous AI package")
        temp_dir.rename(final_dir)
    except Exception as exc:
        remove_tree(temp_dir, "failed temporary AI package")
        print(f"[ERROR] Failed to create AI package: {exc}")
        return False

    print(f"AI offline package complete: {final_dir}")
    return True


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.skip_runtime_assets:
        print("Runtime AI assets are skipped by default. Use --ai-package to create them separately.")

    if not args.skip_build:
        clean_old_builds()
        if not build_executable():
            return 1

    if args.ai_package and not create_ai_package():
        return 1

    print("\nDone.")
    if not args.ai_package:
        print("Base package only. Run with --ai-package to create the separate offline AI package.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
