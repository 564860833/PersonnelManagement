"""Device-aware Ollama context length recommendation."""

import ctypes
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Optional, Tuple

import requests

from services.ollama_manager import ollama_api_url


logger = logging.getLogger("AIContext")

GIB = 1024 ** 3
DEFAULT_CONTEXT_LENGTH = 4096
MIN_CONTEXT_LENGTH = 2048
TOKENS_PER_EFFECTIVE_GIB = 512


@dataclass(frozen=True)
class HardwareSnapshot:
    total_memory_bytes: Optional[int] = None
    available_memory_bytes: Optional[int] = None
    gpu_vram_bytes: Optional[int] = None


@dataclass(frozen=True)
class ContextRecommendation:
    n_ctx: int
    reason: str
    hardware: HardwareSnapshot
    max_n_ctx: int
    model_limit: Optional[int] = None


def recommend_context_length(
    model_name: str = "",
    hardware: Optional[HardwareSnapshot] = None,
    model_limit: Optional[int] = None,
    fetch_model_limit: bool = True,
    timeout: float = 2.0,
) -> ContextRecommendation:
    snapshot = hardware or detect_hardware()
    hardware_max_n_ctx = _recommend_from_hardware(snapshot)
    n_ctx = _apply_available_memory_cap(hardware_max_n_ctx, snapshot.available_memory_bytes)

    resolved_model_limit = model_limit
    if resolved_model_limit is None and fetch_model_limit and _is_real_model_name(model_name):
        resolved_model_limit = fetch_model_context_limit(model_name, timeout=timeout)

    if resolved_model_limit and resolved_model_limit > 0:
        n_ctx = min(n_ctx, resolved_model_limit)
        hardware_max_n_ctx = min(hardware_max_n_ctx, resolved_model_limit)

    return ContextRecommendation(
        n_ctx=max(1, int(n_ctx)),
        reason=_build_reason(snapshot),
        hardware=snapshot,
        max_n_ctx=max(1, int(hardware_max_n_ctx)),
        model_limit=resolved_model_limit,
    )


def detect_hardware() -> HardwareSnapshot:
    total_memory, available_memory = detect_system_memory()
    return HardwareSnapshot(
        total_memory_bytes=total_memory,
        available_memory_bytes=available_memory,
        gpu_vram_bytes=detect_gpu_vram(),
    )


def detect_system_memory() -> Tuple[Optional[int], Optional[int]]:
    if os.name == "nt":
        return _detect_windows_memory()
    return _detect_posix_memory()


def detect_gpu_vram() -> Optional[int]:
    if os.name != "nt":
        return None

    script = (
        "Get-CimInstance Win32_VideoController | "
        "Where-Object { $_.AdapterRAM -gt 0 } | "
        "Select-Object -ExpandProperty AdapterRAM"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except Exception as e:
        logger.debug("检测 GPU 显存失败: %s", e)
        return None

    values = []
    for line in completed.stdout.splitlines():
        value = _safe_int(line.strip())
        if value and value > 0:
            values.append(value)
    return max(values) if values else None


def fetch_model_context_limit(model_name: str, timeout: float = 2.0) -> Optional[int]:
    model_name = (model_name or "").strip()
    if not model_name:
        return None

    try:
        response = requests.post(
            ollama_api_url("/api/show"),
            json={"model": model_name},
            timeout=timeout,
        )
        response.raise_for_status()
        return extract_model_context_limit(response.json())
    except Exception as e:
        logger.debug("读取模型上下文上限失败: model=%s, error=%s", model_name, e)
        return None


def extract_model_context_limit(data: Any) -> Optional[int]:
    if not isinstance(data, dict):
        return None

    for container in (data.get("model_info"), data):
        if not isinstance(container, dict):
            continue
        for key, value in container.items():
            key_text = str(key).lower()
            if key_text.endswith(".context_length") or key_text in {"context_length", "num_ctx"}:
                parsed = _safe_int(value)
                if parsed and parsed > 0:
                    return parsed

    for field_name in ("parameters", "modelfile"):
        parsed = _parse_context_limit_text(data.get(field_name))
        if parsed:
            return parsed
    return None


def _detect_windows_memory() -> Tuple[Optional[int], Optional[int]]:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    if not hasattr(ctypes, "WinDLL"):
        return None, None

    try:
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None, None
        return int(status.ullTotalPhys), int(status.ullAvailPhys)
    except Exception as e:
        logger.debug("检测系统内存失败: %s", e)
        return None, None


def _detect_posix_memory() -> Tuple[Optional[int], Optional[int]]:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        total_pages = os.sysconf("SC_PHYS_PAGES")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        return int(page_size * total_pages), int(page_size * available_pages)
    except Exception:
        return None, None


def _recommend_from_hardware(hardware: HardwareSnapshot) -> int:
    total_gib = _bytes_to_gib(hardware.total_memory_bytes)
    vram_gib = _bytes_to_gib(hardware.gpu_vram_bytes)

    if total_gib is None:
        return DEFAULT_CONTEXT_LENGTH

    effective_gib = total_gib + (vram_gib or 0)
    raw_context = int(effective_gib * TOKENS_PER_EFFECTIVE_GIB)
    return max(MIN_CONTEXT_LENGTH, _floor_power_of_two(raw_context))


def _apply_available_memory_cap(n_ctx: int, available_memory_bytes: Optional[int]) -> int:
    available_gib = _bytes_to_gib(available_memory_bytes)
    if available_gib is None:
        return n_ctx
    if available_gib < 4:
        return min(n_ctx, 2048)
    if available_gib < 8:
        return min(n_ctx, 4096)
    return n_ctx


def _build_reason(hardware: HardwareSnapshot) -> str:
    parts = []
    if hardware.total_memory_bytes is None:
        parts.append("内存未知")
    else:
        parts.append(f"{_format_gib(hardware.total_memory_bytes)} 内存")

    if hardware.gpu_vram_bytes is None:
        parts.append("显存未知")
    else:
        parts.append(f"{_format_gib(hardware.gpu_vram_bytes)} 显存")
    return " / ".join(parts)


def _parse_context_limit_text(value: Any) -> Optional[int]:
    if not isinstance(value, str):
        return None
    match = re.search(r"(?im)^\s*(?:PARAMETER\s+)?(?:num_ctx|context_length)\s+(\d+)\s*$", value)
    if not match:
        return None
    return _safe_int(match.group(1))


def _bytes_to_gib(value: Optional[int]) -> Optional[float]:
    if value is None or value <= 0:
        return None
    return value / GIB


def _floor_power_of_two(value: int) -> int:
    if value < 1:
        return 1
    return 1 << (int(value).bit_length() - 1)


def _format_gib(value: int) -> str:
    gib = value / GIB
    if abs(gib - round(gib)) < 0.05:
        return f"{int(round(gib))}GB"
    return f"{gib:.1f}GB"


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_real_model_name(model_name: str) -> bool:
    model_name = (model_name or "").strip()
    return bool(model_name) and "未检测到模型" not in model_name
