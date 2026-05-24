from pathlib import Path
import shutil


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def assert_project_child(path: Path):
    resolved_root = PROJECT_ROOT.resolve()
    resolved_path = path.resolve()
    if resolved_path == resolved_root:
        raise RuntimeError("refusing to remove project root")
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError(f"refusing to remove outside project root: {resolved_path}") from exc


def remove_tree(path: Path):
    if not path.exists():
        return
    assert_project_child(path)
    print(f"Removing directory: {path}")
    shutil.rmtree(path)


def remove_file(path: Path):
    if not path.exists():
        return
    assert_project_child(path)
    print(f"Removing file: {path}")
    path.unlink()


def clean_up():
    for dir_name in ("build", "dist", "__pycache__"):
        remove_tree(PROJECT_ROOT / dir_name)

    for pattern in ("*.log", "*.pyc"):
        for file_path in PROJECT_ROOT.glob(pattern):
            remove_file(file_path)

    print("Cleanup complete.")


if __name__ == "__main__":
    clean_up()
