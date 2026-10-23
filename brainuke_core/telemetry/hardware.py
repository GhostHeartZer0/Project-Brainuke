"""
brainuke_core/telemetry/hardware.py
Native Windows platform hardware telemetry monitor.
Queries Dedicated VRAM, Shared VRAM, and System RAM using Windows ctypes & standard library.
Adheres to laziness ladder (Rung 2/3: Standard library & native platform).
"""

import ctypes
import os
import sys
from typing import Dict, Any, Optional

# --- SYSTEM RAM VIA GlobalMemoryStatusEx (Native Windows) ---
class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def get_system_ram_stats() -> Dict[str, Any]:
    """Returns System RAM metrics: used_mb, total_mb, free_mb, pct."""
    if sys.platform != "win32":
        return {"used_mb": 0, "total_mb": 0, "free_mb": 0, "pct": 0}

    try:
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total_mb = int(stat.ullTotalPhys / (1024 * 1024))
            avail_mb = int(stat.ullAvailPhys / (1024 * 1024))
            used_mb = max(0, total_mb - avail_mb)
            pct = int(stat.dwMemoryLoad)
            return {
                "used_mb": used_mb,
                "total_mb": total_mb,
                "free_mb": avail_mb,
                "pct": pct
            }
    except Exception:
        pass
    return {"used_mb": 0, "total_mb": 0, "free_mb": 0, "pct": 0}


# --- DEDICATED VRAM VIA NVML (Native Windows nvml.dll) ---
class _NVML_MEMORY(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


_nvml_handle = None
_nvml_initialized = False

def _init_nvml():
    global _nvml_handle, _nvml_initialized
    if _nvml_initialized:
        return _nvml_handle
    if sys.platform != "win32":
        return None
    try:
        nvml = ctypes.windll.LoadLibrary("nvml.dll")
        if nvml.nvmlInit() == 0:
            dev = ctypes.c_void_p()
            if nvml.nvmlDeviceGetHandleByIndex(0, ctypes.byref(dev)) == 0:
                _nvml_handle = (nvml, dev)
                _nvml_initialized = True
                return _nvml_handle
    except Exception:
        pass
    _nvml_initialized = True
    return None


def get_dedicated_vram_stats() -> Dict[str, Any]:
    """Returns Dedicated VRAM stats: used_mb, total_mb, free_mb, pct."""
    h = _init_nvml()
    if h:
        try:
            nvml, dev = h
            mem = _NVML_MEMORY()
            if nvml.nvmlDeviceGetMemoryInfo(dev, ctypes.byref(mem)) == 0:
                total_mb = int(mem.total // (1024 * 1024))
                used_mb = int(mem.used // (1024 * 1024))
                free_mb = int(mem.free // (1024 * 1024))
                pct = int((used_mb / total_mb * 100)) if total_mb > 0 else 0
                return {
                    "used_mb": used_mb,
                    "total_mb": total_mb,
                    "free_mb": free_mb,
                    "pct": pct,
                    "source": "nvml"
                }
        except Exception:
            pass

    # Fallback to nvidia-smi if nvml direct call fails
    try:
        import subprocess
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=1
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [int(p.strip()) for p in res.stdout.strip().split(",")]
            total_mb, used_mb, free_mb = parts[0], parts[1], parts[2]
            pct = int((used_mb / total_mb * 100)) if total_mb > 0 else 0
            return {
                "used_mb": used_mb,
                "total_mb": total_mb,
                "free_mb": free_mb,
                "pct": pct,
                "source": "nvidia-smi"
            }
    except Exception:
        pass

    return {"used_mb": 0, "total_mb": 0, "free_mb": 0, "pct": 0, "source": "none"}


# --- SHARED VRAM VIA PDH (Performance Data Helper) ---
class _PDH_FMT_COUNTERVALUE_ITEM(ctypes.Structure):
    _fields_ = [
        ("szName", ctypes.c_wchar_p),
        ("CStatus", ctypes.c_ulong),
        ("dummy", ctypes.c_ulong),
        ("doubleValue", ctypes.c_double),
    ]


def get_shared_vram_stats() -> Dict[str, Any]:
    """
    Returns GPU Shared Memory usage via Windows PDH:
    used_mb: current shared VRAM in MB
    total_mb: maximum shared VRAM budget (approx 50% of system RAM on Windows)
    """
    if sys.platform != "win32":
        return {"used_mb": 0, "total_mb": 0, "pct": 0}

    try:
        pdh = ctypes.windll.pdh
        h_query = ctypes.c_void_p()
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(h_query)) != 0:
            return {"used_mb": 0, "total_mb": 0, "pct": 0}

        h_counter = ctypes.c_void_p()
        ret = pdh.PdhAddEnglishCounterW(h_query, "\\GPU Adapter Memory(*)\\Shared Usage", 0, ctypes.byref(h_counter))
        if ret != 0:
            pdh.PdhCloseQuery(h_query)
            return {"used_mb": 0, "total_mb": 0, "pct": 0}

        pdh.PdhCollectQueryData(h_query)

        buffer_size = ctypes.c_ulong(0)
        item_count = ctypes.c_ulong(0)
        pdh.PdhGetFormattedCounterArrayW(h_counter, 0x00000200, ctypes.byref(buffer_size), ctypes.byref(item_count), None)

        if buffer_size.value > 0:
            buf = (ctypes.c_byte * buffer_size.value)()
            if pdh.PdhGetFormattedCounterArrayW(h_counter, 0x00000200, ctypes.byref(buffer_size), ctypes.byref(item_count), buf) == 0:
                items = ctypes.cast(buf, ctypes.POINTER(_PDH_FMT_COUNTERVALUE_ITEM))
                total_shared_bytes = 0.0
                for i in range(item_count.value):
                    val = items[i].doubleValue
                    if val > 0:
                        total_shared_bytes += val
                pdh.PdhCloseQuery(h_query)

                ram_stats = get_system_ram_stats()
                # Windows default shared VRAM limit is half of physical RAM
                shared_budget_mb = int(ram_stats["total_mb"] * 0.5) if ram_stats["total_mb"] > 0 else 16384
                used_mb = int(total_shared_bytes / (1024 * 1024))
                pct = int((used_mb / shared_budget_mb * 100)) if shared_budget_mb > 0 else 0
                return {
                    "used_mb": used_mb,
                    "total_mb": shared_budget_mb,
                    "pct": pct
                }

        pdh.PdhCloseQuery(h_query)
    except Exception:
        pass

    return {"used_mb": 0, "total_mb": 0, "pct": 0}


def get_all_hardware_telemetry() -> Dict[str, Any]:
    """Returns complete combined hardware memory telemetry snapshot."""
    ram = get_system_ram_stats()
    vram_dedicated = get_dedicated_vram_stats()
    vram_shared = get_shared_vram_stats()

    return {
        "ram": ram,
        "vram_dedicated": vram_dedicated,
        "vram_shared": vram_shared
    }
