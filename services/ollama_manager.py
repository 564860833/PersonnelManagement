"""Helpers for using an app-local Ollama models directory."""

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

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


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
    return models_dir


def ensure_ollama_ready(
    start_if_needed: bool = True,
    timeout: float = 8.0,
    restart_empty_service: bool = True,
) -> OllamaStatus:
    """Point Ollama at app-local models and start it if the API is unavailable."""
    models_dir = configure_local_models_env()
    local_model_names = list_local_model_names(models_dir) if models_dir else []
    executable = find_ollama_executable()

    available, service_models = fetch_ollama_models(timeout=2)
    if available:
        status = _build_available_status(service_models, models_dir, local_model_names, executable, started=False)
        if (
            restart_empty_service
            and models_dir
            and local_model_names
            and executable
            and not service_models
        ):
            logger.info("Ollama 已运行但模型列表为空，尝试用程序目录 models 重启 Ollama。")
            if restart_ollama_with_local_models(executable, models_dir):
                available, service_models = wait_for_ollama(timeout=timeout)
                if available:
                    return _build_available_status(service_models, models_dir, local_model_names, executable, started=True)
        return status

    started = False
    if start_if_needed and executable and models_dir:
        started = start_ollama_serve(executable, models_dir)
        if started:
            available, service_models = wait_for_ollama(timeout=timeout)
            if available:
                return _build_available_status(service_models, models_dir, local_model_names, executable, started=True)

    if not executable:
        message = "未找到 Ollama 命令，请先安装 Ollama。"
    elif models_dir is None:
        message = "未检测到程序目录下可用的 models 目录。"
    else:
        message = "无法连接到 Ollama 服务。请确认 Ollama 已安装并可启动。"

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
    base_url = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_URL).strip()
    if not base_url.startswith(("http://", "https://")):
        base_url = "http://" + base_url
    return base_url.rstrip("/") + "/" + path.lstrip("/")


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
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = str(models_dir)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        subprocess.Popen(
            [executable, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=creationflags,
        )
        logger.info("已使用程序目录 models 启动 Ollama 服务: %s", models_dir)
        return True
    except Exception as e:
        logger.error("启动 Ollama 服务失败: %s", e)
        return False


def restart_ollama_with_local_models(executable: str, models_dir: Path) -> bool:
    stop_running_ollama()
    time.sleep(1.0)
    return start_ollama_serve(executable, models_dir)


def stop_running_ollama():
    if os.name == "nt":
        for image_name in ("ollama.exe", "ollama app.exe"):
            try:
                subprocess.run(
                    ["taskkill", "/IM", image_name, "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as e:
                logger.debug("停止 %s 失败: %s", image_name, e)
        return

    try:
        subprocess.run(
            ["pkill", "-f", "ollama"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except Exception as e:
        logger.debug("停止 Ollama 进程失败: %s", e)


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
            "Ollama 服务已运行，但未识别程序目录 models 中的模型。"
            "请完全退出 Ollama 后重新启动本程序。"
        )
        warning = message
    elif service_models:
        message = f"Ollama 已就绪，识别到 {len(service_models)} 个模型。"
    elif models_dir:
        message = "Ollama 服务已运行，但程序目录 models 中没有可识别模型。"
        warning = message
    else:
        message = "Ollama 服务已运行，但未检测到程序目录 models。"

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
