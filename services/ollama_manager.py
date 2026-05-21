"""Helpers for using an app-local Ollama models directory."""

import atexit
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import requests


logger = logging.getLogger("OllamaManager")

APP_OLLAMA_HOST = "127.0.0.1:11435"
APP_OLLAMA_URL = f"http://{APP_OLLAMA_HOST}"
APP_OLLAMA_RUNTIME_DIR = "ollama"

_started_process: Optional[subprocess.Popen] = None


@dataclass
class OllamaStatus:
    service_available: bool
    service_models: List[str]
    local_models_dir: Optional[str]
    local_model_names: List[str]
    started_by_app: bool
    ollama_executable: Optional[str]
    message: str
    warning: Optional[str] = None


def get_application_dir() -> Path:
    """Return the executable folder when frozen, otherwise the project root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_local_models_dir() -> Optional[Path]:
    models_dir = get_application_dir() / "models"
    if _is_ollama_models_dir(models_dir):
        return models_dir
    return None


def configure_local_models_env() -> Optional[Path]:
    models_dir = get_local_models_dir()
    if models_dir is None:
        return None

    models_path = str(models_dir)
    current = os.environ.get("OLLAMA_MODELS")
    if current != models_path:
        os.environ["OLLAMA_MODELS"] = models_path
        logger.info("已设置 OLLAMA_MODELS=%s", models_path)
    os.environ["OLLAMA_HOST"] = APP_OLLAMA_HOST
    return models_dir


def ensure_ollama_ready(
    start_if_needed: bool = True,
    timeout: float = 8.0,
) -> OllamaStatus:
    """Start or reuse the app-dedicated Ollama service on a fixed local port."""
    models_dir = configure_local_models_env()
    local_model_names = list_local_model_names(models_dir) if models_dir else []
    executable = find_ollama_executable()

    available, service_models = fetch_ollama_models(timeout=2)
    if available:
        status = _build_available_status(service_models, models_dir, local_model_names, executable, started=False)
        return status

    started = False
    if start_if_needed and executable and models_dir:
        started = start_ollama_serve(executable, models_dir)
        if started:
            available, service_models = wait_for_ollama(timeout=timeout)
            if available:
                return _build_available_status(service_models, models_dir, local_model_names, executable, started=True)

    if not executable:
        message = "未找到 Ollama 运行时，请确认程序目录下存在 ollama/ollama.exe。"
    elif models_dir is None:
        message = "未检测到程序目录下可用的 models 目录。"
    else:
        message = f"无法连接到程序专用 Ollama 服务 ({APP_OLLAMA_HOST})，请确认 Ollama 运行时可启动。"

    return OllamaStatus(
        service_available=False,
        service_models=[],
        local_models_dir=str(models_dir) if models_dir else None,
        local_model_names=local_model_names,
        started_by_app=started,
        ollama_executable=executable,
        message=message,
        warning=message,
    )


def fetch_ollama_models(timeout: float = 3.0) -> Tuple[bool, List[str]]:
    try:
        response = requests.get(ollama_api_url("/api/tags"), timeout=timeout)
        response.raise_for_status()
        data = response.json()
        models = [model["name"] for model in data.get("models", []) if model.get("name")]
        return True, models
    except Exception as e:
        logger.debug("获取 Ollama 模型列表失败: %s", e)
        return False, []


def ollama_api_url(path: str) -> str:
    return APP_OLLAMA_URL.rstrip("/") + "/" + path.lstrip("/")


def list_local_model_names(models_dir: Optional[Path] = None) -> List[str]:
    models_dir = models_dir or get_local_models_dir()
    if models_dir is None:
        return []

    manifests_dir = models_dir / "manifests"
    names = []
    for manifest in manifests_dir.rglob("*"):
        if manifest.is_file():
            name = _model_name_from_manifest(manifest, manifests_dir)
            if name:
                names.append(name)
    return sorted(set(names))


def find_ollama_executable() -> Optional[str]:
    app_dir = get_application_dir()
    local_candidates = [
        app_dir / APP_OLLAMA_RUNTIME_DIR / "ollama.exe",
        app_dir / "ollama.exe",
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)

    found = shutil.which("ollama")
    if found:
        return found

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Ollama" / "ollama.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Ollama" / "ollama.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def start_ollama_serve(executable: str, models_dir: Path) -> bool:
    global _started_process

    env = os.environ.copy()
    env["OLLAMA_HOST"] = APP_OLLAMA_HOST
    env["OLLAMA_MODELS"] = str(models_dir)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        _started_process = subprocess.Popen(
            [executable, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=creationflags,
        )
        logger.info("已启动程序专用 Ollama 服务: host=%s, models=%s", APP_OLLAMA_HOST, models_dir)
        return True
    except Exception as e:
        _started_process = None
        logger.error("启动 Ollama 服务失败: %s", e)
        return False


def stop_started_ollama():
    """Stop only the Ollama process started by this application instance."""
    global _started_process

    process = _started_process
    if process is None:
        return
    if process.poll() is not None:
        _started_process = None
        return

    try:
        process.terminate()
        process.wait(timeout=5)
        logger.info("已停止程序专用 Ollama 服务")
    except Exception as e:
        logger.debug("停止程序专用 Ollama 服务失败: %s", e)
    finally:
        _started_process = None


def wait_for_ollama(timeout: float = 8.0) -> Tuple[bool, List[str]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        available, models = fetch_ollama_models(timeout=1)
        if available:
            return available, models
        time.sleep(0.4)
    return fetch_ollama_models(timeout=1)


def _build_available_status(
    service_models: List[str],
    models_dir: Optional[Path],
    local_model_names: List[str],
    executable: Optional[str],
    started: bool,
) -> OllamaStatus:
    warning = None
    missing_local_models = [
        model_name for model_name in local_model_names
        if model_name not in service_models
    ]

    if models_dir and local_model_names and missing_local_models:
        message = (
            f"程序专用 Ollama 服务已运行在 {APP_OLLAMA_HOST}，"
            "但未识别程序目录 models 中的模型。请确认该端口未被其他 Ollama 占用。"
        )
        warning = message
    elif service_models:
        message = f"程序专用 Ollama 已就绪，识别到 {len(service_models)} 个模型。"
    elif models_dir:
        message = f"程序专用 Ollama 服务已运行在 {APP_OLLAMA_HOST}，但程序目录 models 中没有可识别模型。"
        warning = message
    else:
        message = f"程序专用 Ollama 服务已运行在 {APP_OLLAMA_HOST}，但未检测到程序目录 models。"

    return OllamaStatus(
        service_available=True,
        service_models=service_models,
        local_models_dir=str(models_dir) if models_dir else None,
        local_model_names=local_model_names,
        started_by_app=started,
        ollama_executable=executable,
        message=message,
        warning=warning,
    )


def _is_ollama_models_dir(models_dir: Path) -> bool:
    if not models_dir.exists() or not models_dir.is_dir():
        return False
    blobs_dir = models_dir / "blobs"
    manifests_dir = models_dir / "manifests"
    if not blobs_dir.is_dir() or not manifests_dir.is_dir():
        return False
    return any(path.is_file() for path in manifests_dir.rglob("*"))


def _model_name_from_manifest(manifest: Path, manifests_dir: Path) -> Optional[str]:
    try:
        parts = manifest.relative_to(manifests_dir).parts
    except ValueError:
        return None
    if len(parts) < 4:
        return None

    namespace = parts[1]
    model = parts[2]
    tag = parts[3]
    if namespace == "library":
        return f"{model}:{tag}"
    return f"{namespace}/{model}:{tag}"


atexit.register(stop_started_ollama)
