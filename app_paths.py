"""Shared filesystem path helpers for development and packaged runtime."""

import ctypes
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


DATA_DIR_NAME = "data"
LEGACY_DIR_NAME = "legacy"
MIGRATED_RUNTIME_FILES = {"personnel_system.db", "application.log"}


def project_root() -> Path:
    """Return the repository root in development mode."""
    return Path(__file__).resolve().parent


def application_dir() -> Path:
    """Return the executable folder when frozen, otherwise the project root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return project_root()


def resource_path(relative_path: str) -> Path:
    """Return a read-only resource path for development and PyInstaller bundles."""
    base_dir = Path(getattr(sys, "_MEIPASS", project_root()))
    return base_dir / relative_path


def runtime_path(relative_path: str) -> Path:
    """Return a writable runtime path beside the executable or project root."""
    return application_dir() / relative_path


def data_dir() -> Path:
    """Return the dedicated runtime data directory beside the executable."""
    return application_dir() / DATA_DIR_NAME


def data_path(relative_path: str) -> Path:
    """Return a writable path inside the dedicated runtime data directory."""
    relative = _validate_relative_path(relative_path)
    directory = ensure_data_dir()
    target = directory / relative
    if len(relative.parts) == 1 and relative.name in MIGRATED_RUNTIME_FILES:
        _migrate_legacy_runtime_file(relative.name, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def ensure_data_dir() -> Path:
    """Create the runtime data directory and hide it on Windows when possible."""
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    _hide_directory_on_windows(directory)
    return directory


def _validate_relative_path(relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise ValueError(f"Invalid data path: {relative_path}")
    return relative


def _hide_directory_on_windows(directory: Path) -> None:
    if os.name != "nt":
        return

    try:
        hidden_attribute = 0x02
        invalid_file_attributes = 0xFFFFFFFF
        kernel32 = ctypes.windll.kernel32
        attributes = kernel32.GetFileAttributesW(str(directory))
        if attributes == invalid_file_attributes:
            return
        if attributes & hidden_attribute:
            return
        kernel32.SetFileAttributesW(str(directory), attributes | hidden_attribute)
    except Exception:
        pass


def _migrate_legacy_runtime_file(file_name: str, target: Path) -> None:
    legacy_source = application_dir() / file_name
    if not legacy_source.is_file():
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.move(str(legacy_source), str(target))
        return

    backup_path = _next_legacy_backup_path(file_name)
    shutil.move(str(legacy_source), str(backup_path))


def _next_legacy_backup_path(file_name: str) -> Path:
    legacy_dir = ensure_data_dir() / LEGACY_DIR_NAME
    legacy_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    candidate = legacy_dir / f"{file_name}.{timestamp}.bak"
    counter = 1
    while candidate.exists():
        candidate = legacy_dir / f"{file_name}.{timestamp}.{counter}.bak"
        counter += 1
    return candidate
