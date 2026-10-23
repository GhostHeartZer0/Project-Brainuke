"""
brainuke_core/cognition/runner_manager.py
PC Llama-Server Runner & Model Manager for Project Brainuke Throne.

Handles:
- Straightforward switching between Normal (Supervisor) and Secret (Uncensored Heretic) models.
- Live detection of model load and health status on port 8081.
- Model load initiation and launch command generation.
- Dynamic inference configuration persistence (temperature, min_p, context_window, gpu_layers, KV cache).
"""

import json
import os
import sys
import shutil
import subprocess
import atexit
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class PCRunnerManager:
    NORMAL_MODEL_ID = "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL"
    SECRET_MODEL_ID = "gemma-4-26B-A4B-uncensored-heretic-v2"

    def __init__(self, config_path: Optional[str] = None):
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = Path(__file__).resolve().parent.parent.parent / "config" / "models.json"
        
        self.workspace_root = Path(__file__).resolve().parent.parent.parent
        self._managed_process: Optional[subprocess.Popen] = None
        self._ensure_config()
        atexit.register(self.stop_runner)

    def _ensure_config(self) -> Dict[str, Any]:
        """Loads models.json, ensuring valid default structure."""
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self, data: Dict[str, Any]) -> None:
        """Persists config back to models.json."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_active_model_id(self) -> str:
        cfg = self._ensure_config()
        return cfg.get("active_model", self.NORMAL_MODEL_ID)

    def get_active_alias(self) -> str:
        active_id = self.get_active_model_id()
        if active_id == self.SECRET_MODEL_ID:
            return "secret"
        return "normal"

    def resolve_model_path(self, model_id: str) -> Tuple[str, bool]:
        """
        Resolves model file path on disk, checking configured path and local workspace fallbacks.
        Returns (resolved_path, exists_on_disk).
        """
        cfg = self._ensure_config()
        models = cfg.get("pc_runner", {}).get("models", {})
        model_info = models.get(model_id, {})
        configured_path = model_info.get("path", "")

        # 1. Check configured path
        if configured_path and os.path.exists(configured_path):
            return configured_path, True

        # 2. Check workspace models/ folder fallback and candidate model folders
        candidate_model_dirs = self.get_candidate_model_dirs()
        if model_id == self.NORMAL_MODEL_ID:
            for m_dir in candidate_model_dirs:
                c1 = m_dir / "26B" / "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
                if c1.exists():
                    return str(c1), True
                c2 = m_dir / "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
                if c2.exists():
                    return str(c2), True
        elif model_id == self.SECRET_MODEL_ID:
            for m_dir in candidate_model_dirs:
                c1 = m_dir / "26B-unc" / "gemma-4-26B-A4B-it-qat-q4_0-unquantized-uncensored-heretic-v2.i1-Q4_K_M.gguf"
                if c1.exists():
                    return str(c1), True
                c2 = m_dir / "gemma-4-26B-A4B-it-qat-q4_0-unquantized-uncensored-heretic-v2.i1-Q4_K_M.gguf"
                if c2.exists():
                    return str(c2), True

        # 3. Automatic fallback: scan candidate directories for ANY valid .gguf file
        discovered = self.scan_available_models()
        if discovered:
            return discovered[0]["path"], True

        return configured_path or "unknown", False

    def get_candidate_model_dirs(self) -> List[Path]:
        """Returns candidate directories allowed for model files."""
        dirs = [
            self.workspace_root / "models",
            self.workspace_root,
            self.workspace_root.parent / "Models",
            self.workspace_root.parent / "models",
            self.workspace_root.parent.parent.parent / "Models",
            self.workspace_root.parent.parent.parent / "models",
        ]
        if self.config_path:
            dirs.append(self.config_path.parent)

        s_llm = Path("S:/LLM")
        if s_llm.exists():
            dirs.append(s_llm)

        cfg = self._ensure_config()
        models = cfg.get("pc_runner", {}).get("models", {})
        for m_info in models.values():
            cfg_p = m_info.get("path")
            if cfg_p:
                try:
                    p_obj = Path(cfg_p).resolve().parent
                    if p_obj not in dirs:
                        dirs.append(p_obj)
                except Exception:
                    pass
        for extra in cfg.get("allowed_model_dirs", []):
            if extra and isinstance(extra, str):
                try:
                    dirs.append(Path(extra).resolve())
                except Exception:
                    pass

        seen = set()
        resolved_dirs = []
        for d in dirs:
            try:
                res = d.resolve()
                if res.is_dir() and str(res) not in seen:
                    seen.add(str(res))
                    resolved_dirs.append(res)
            except Exception:
                pass
        return resolved_dirs

    def is_path_within_allowed_dirs(self, target_path: Union[str, Path]) -> bool:
        """Verifies target path resides within an allowed model directory."""
        try:
            normalized_path = os.path.normpath(os.path.abspath(str(target_path)))
            for base in self.get_candidate_model_dirs():
                safe_root = os.path.normpath(os.path.abspath(str(base)))
                safe_prefix = safe_root if safe_root.endswith(os.sep) else safe_root + os.sep
                if normalized_path.startswith(safe_prefix) or normalized_path.lower().startswith(safe_prefix.lower()):
                    return True
                if normalized_path == safe_root or normalized_path.lower() == safe_root.lower():
                    return True
        except Exception:
            return False
        return False

    def scan_available_models(self) -> List[Dict[str, Any]]:
        """Scans candidate directories for available .gguf model files."""
        candidate_model_dirs = self.get_candidate_model_dirs()
        found = []
        seen = set()
        for m_dir in candidate_model_dirs:
            if m_dir.is_dir():
                try:
                    for gguf in sorted(m_dir.glob("**/*.gguf")):
                        if gguf.is_file():
                            p_str = str(gguf.resolve())
                            if p_str not in seen:
                                seen.add(p_str)
                                found.append({
                                    "name": gguf.name,
                                    "path": p_str,
                                    "size_mb": round(gguf.stat().st_size / (1024 * 1024), 1)
                                })
                except Exception:
                    pass
        return found

    def set_custom_model_path(self, model_path: str, model_id: Optional[str] = None) -> Dict[str, Any]:
        """Sets a custom model path for active or custom model."""
        raw_path = str(model_path).strip()
        if not raw_path.lower().endswith(".gguf"):
            return {"status": "error", "error": "Model file must have a .gguf extension"}

        # Lexical containment check against allowed candidate model directories
        if not self.is_path_within_allowed_dirs(raw_path):
            return {"status": "error", "error": f"Model path outside permitted directories: {raw_path}"}

        # Resolve against server-confirmed models discovered by scanning candidate directories
        norm_requested = os.path.normpath(raw_path).lower()
        base_requested = os.path.basename(raw_path).lower()

        available_models = self.scan_available_models()
        model_lookup = {}
        for m in available_models:
            model_lookup[os.path.normpath(m["path"]).lower()] = m["path"]
            model_lookup[m["name"].lower()] = m["path"]

        matched_path = model_lookup.get(norm_requested) or model_lookup.get(base_requested)
        if not matched_path:
            return {"status": "error", "error": f"Model file not found on disk: {raw_path}"}

        cfg = self._ensure_config()
        target_id = model_id or self.get_active_model_id()
        models = cfg.setdefault("pc_runner", {}).setdefault("models", {})
        target_cfg = models.setdefault(target_id, {})
        target_cfg["path"] = matched_path
        self._save_config(cfg)
        return {"status": "updated", "active_model": target_id, "path": matched_path}

    def select_model(self, alias_or_id: str, auto_reload: bool = True) -> Dict[str, Any]:
        """
        Selects between 'normal' and 'secret' models.
        """
        cfg = self._ensure_config()
        alias_clean = alias_or_id.strip().lower()

        if alias_clean in ("normal", "supervisor", "default"):
            target_id = self.NORMAL_MODEL_ID
            alias = "normal"
        elif alias_clean in ("secret", "heretic", "uncensored"):
            target_id = self.SECRET_MODEL_ID
            alias = "secret"
        elif alias_or_id in cfg.get("pc_runner", {}).get("models", {}):
            target_id = alias_or_id
            alias = "secret" if target_id == self.SECRET_MODEL_ID else "normal"
        else:
            target_id = self.NORMAL_MODEL_ID
            alias = "normal"

        cfg["active_model"] = target_id
        self._save_config(cfg)

        load_res = None
        if auto_reload and self._managed_process is not None and self._managed_process.poll() is None:
            load_res = self.initiate_load(target_id)

        resolved_path, exists = self.resolve_model_path(target_id)
        result = {
            "status": "selected",
            "active_model": target_id,
            "alias": alias,
            "model_path": resolved_path,
            "path_exists": exists
        }
        if load_res:
            result["reload_status"] = load_res.get("status")
        return result

    def get_status(self, llama_client: Optional[Any] = None) -> Dict[str, Any]:
        """
        Returns full status of PC runner:
        - Health / Loaded status
        - Active model & alias
        - Available models
        - Current inference settings
        - Resolved path & file presence
        """
        cfg = self._ensure_config()
        active_id = self.get_active_model_id()
        alias = self.get_active_alias()

        is_loaded = False
        if llama_client is not None:
            try:
                is_loaded = bool(llama_client.is_healthy())
            except Exception:
                is_loaded = False

        models = cfg.get("pc_runner", {}).get("models", {})
        active_model_cfg = models.get(active_id, {})
        resolved_path, path_exists = self.resolve_model_path(active_id)

        # Build inference settings dict
        inference_settings = {
            "temperature": active_model_cfg.get("temperature", 0.8),
            "min_p": active_model_cfg.get("min_p", 0.05),
            "context_window": active_model_cfg.get("context_window", 32768),
            "gpu_layers": active_model_cfg.get("gpu_layers", 8),
            "repeat_penalty": active_model_cfg.get("repeat_penalty", 1.1),
            "cache_type_k": "q8_0",
            "cache_type_v": "q5_1",
            "flash_attn": True
        }

        # Extract flags if present
        default_flags = cfg.get("pc_runner", {}).get("default_flags", [])
        for i in range(len(default_flags) - 1):
            if default_flags[i] == "--cache-type-k":
                inference_settings["cache_type_k"] = default_flags[i + 1]
            elif default_flags[i] == "--cache-type-v":
                inference_settings["cache_type_v"] = default_flags[i + 1]
            elif default_flags[i] == "-fa":
                inference_settings["flash_attn"] = (default_flags[i + 1] == "on")

        models_summary = {}
        for m_id, m_cfg in models.items():
            r_path, r_exists = self.resolve_model_path(m_id)
            models_summary[m_id] = {
                "alias": "secret" if m_id == self.SECRET_MODEL_ID else "normal",
                "role": m_cfg.get("role", "general"),
                "path": r_path,
                "exists": r_exists,
                "gpu_layers": m_cfg.get("gpu_layers", 8),
                "context_window": m_cfg.get("context_window", 32768)
            }

        launch_cmd = self.get_launch_command(active_id)

        hw_telemetry = {}
        try:
            from brainuke_core.telemetry.hardware import get_all_hardware_telemetry
            hw_telemetry = get_all_hardware_telemetry()
        except Exception:
            pass

        client_telemetry = {}
        if llama_client is not None and hasattr(llama_client, "get_telemetry"):
            try:
                client_telemetry = llama_client.get_telemetry()
            except Exception:
                pass

        return {
            "online": is_loaded,
            "status": "loaded" if is_loaded else "offline",
            "active_model": active_id,
            "active_alias": alias,
            "active_path": resolved_path,
            "active_path_exists": path_exists,
            "port": cfg.get("pc_runner", {}).get("port", 8081),
            "host": cfg.get("pc_runner", {}).get("host", "127.0.0.1"),
            "inference_settings": inference_settings,
            "models": models_summary,
            "launch_command": launch_cmd,
            "process_managed": (self._managed_process is not None and self._managed_process.poll() is None),
            "hardware": hw_telemetry,
            "telemetry": client_telemetry,
            "discovered_models": self.scan_available_models()
        }

    def update_inference_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates basic inference settings in models.json for the active model.
        """
        cfg = self._ensure_config()
        active_id = self.get_active_model_id()
        models = cfg.setdefault("pc_runner", {}).setdefault("models", {})
        active_model_cfg = models.setdefault(active_id, {})

        if "temperature" in settings:
            active_model_cfg["temperature"] = float(settings["temperature"])
        if "min_p" in settings:
            active_model_cfg["min_p"] = float(settings["min_p"])
        if "context_window" in settings:
            active_model_cfg["context_window"] = int(settings["context_window"])
        if "gpu_layers" in settings:
            active_model_cfg["gpu_layers"] = int(settings["gpu_layers"])
        if "repeat_penalty" in settings:
            active_model_cfg["repeat_penalty"] = float(settings["repeat_penalty"])

        # Default flags updates
        flags = cfg["pc_runner"].setdefault("default_flags", [])
        if "cache_type_k" in settings:
            k = str(settings["cache_type_k"])
            if "--cache-type-k" in flags:
                idx = flags.index("--cache-type-k")
                if idx + 1 < len(flags):
                    flags[idx + 1] = k
            else:
                flags.extend(["--cache-type-k", k])

        if "cache_type_v" in settings:
            v = str(settings["cache_type_v"])
            if "--cache-type-v" in flags:
                idx = flags.index("--cache-type-v")
                if idx + 1 < len(flags):
                    flags[idx + 1] = v
            else:
                flags.extend(["--cache-type-v", v])

        if "flash_attn" in settings:
            fa_val = "on" if settings["flash_attn"] else "off"
            if "-fa" in flags:
                idx = flags.index("-fa")
                if idx + 1 < len(flags):
                    flags[idx + 1] = fa_val
            else:
                flags.extend(["-fa", fa_val])

        self._save_config(cfg)
        return {"status": "updated", "active_model": active_id, "settings": settings}

    @classmethod
    def find_llama_server_binary(cls) -> Optional[str]:
        env_bin = os.environ.get("LLAMA_SERVER_BIN")
        if env_bin and os.path.exists(env_bin):
            return env_bin

        on_path = shutil.which("llama-server") or shutil.which("llama-server.exe")
        if on_path:
            return on_path

        ws = Path(__file__).resolve().parent.parent.parent
        candidates = [
            r"C:\Program Files\Android\Android Studio\plugins\gemini\resources\llamacpp\llama-server.exe",
            str(ws.parent / "Tools" / "llama-dist" / "llama-server.exe"),
            str(ws.parent / "_internal" / "Tools" / "llama-dist" / "llama-server.exe"),
            str(ws.parent / "temp_zip" / "llama-server.exe"),
            str(ws.parent.parent.parent / "Tools" / "llama-dist" / "llama-server.exe"),
            str(ws.parent.parent.parent / "temp_zip" / "llama-server.exe"),
            str(ws / "temp_zip" / "llama-server.exe"),
            os.path.expanduser(r"~\Desktop\Desktop\Hub\SerenityPC\temp_zip\llama-server.exe"),
            os.path.expanduser(r"~\Desktop\Hub\Serenities\SerenityPC\temp_zip\llama-server.exe"),
            os.path.expanduser(r"~\llama-server.exe"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def get_launch_command(self, model_id: Optional[str] = None) -> str:
        """
        Builds the exact llama-server command line invocation string.
        """
        cfg = self._ensure_config()
        target_id = model_id or self.get_active_model_id()
        models = cfg.get("pc_runner", {}).get("models", {})
        m_cfg = models.get(target_id, {})

        path, _ = self.resolve_model_path(target_id)
        port = cfg.get("pc_runner", {}).get("port", 8081)
        host = cfg.get("pc_runner", {}).get("host", "127.0.0.1")
        ctx = m_cfg.get("context_window", 32768)
        ngl = m_cfg.get("gpu_layers", 8)
        binary = self.find_llama_server_binary() or "llama-server"
        bin_invoc = f'"{binary}"' if " " in binary else binary

        cmd_parts = [
            bin_invoc,
            f"-m \"{path}\"",
            f"-c {ctx}",
            f"-ngl {ngl}",
            f"--port {port}",
            f"--host {host}",
            "-np 1",
            "--no-warmup"
        ]

        flags = cfg.get("pc_runner", {}).get("default_flags", [])
        if flags:
            cmd_parts.append(" ".join(flags))

        return " ".join(cmd_parts)

    def initiate_load(self, model_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Initiates model load:
        1. Selects model if specified.
        2. Checks model binary and path on disk.
        3. Spawns llama-server if binary is installed/found, or generates launch script.
        """
        if model_key:
            self.select_model(model_key, auto_reload=False)

        active_id = self.get_active_model_id()
        model_path, exists = self.resolve_model_path(active_id)
        cfg = self._ensure_config()
        models = cfg.get("pc_runner", {}).get("models", {})
        m_cfg = models.get(active_id, {})
        port = cfg.get("pc_runner", {}).get("port", 8081)
        host = cfg.get("pc_runner", {}).get("host", "127.0.0.1")
        ctx = m_cfg.get("context_window", 32768)
        ngl = m_cfg.get("gpu_layers", 8)

        cmd_str = self.get_launch_command(active_id)
        binary = self.find_llama_server_binary()

        # Stop existing managed process if running
        self.stop_runner()

        # Update launcher bat script
        launcher_bat = self.workspace_root / "start_llama_server.bat"
        try:
            with open(launcher_bat, "w", encoding="utf-8") as f:
                f.write(f"@echo off\ntitle Llama-Server ({active_id})\necho Launching {active_id} on port {port}...\n{cmd_str}\npause\n")
        except Exception:
            pass

        if binary:
            try:
                cmd = [
                    binary,
                    "-m", model_path,
                    "-c", str(ctx),
                    "-ngl", str(ngl),
                    "--port", str(port),
                    "--host", host,
                    "-np", "1",
                    "--no-warmup"
                ]
                flags = cfg.get("pc_runner", {}).get("default_flags", [])
                for f in flags:
                    cmd.append(str(f))

                import threading
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                self._managed_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creationflags
                )

                def _drain(stream):
                    try:
                        for _ in iter(stream.readline, ''):
                            pass
                    except Exception:
                        pass
                    finally:
                        try:
                            stream.close()
                        except Exception:
                            pass

                threading.Thread(target=_drain, args=(self._managed_process.stdout,), daemon=True).start()
                threading.Thread(target=_drain, args=(self._managed_process.stderr,), daemon=True).start()

                return {
                    "status": "launched",
                    "pid": self._managed_process.pid,
                    "model_id": active_id,
                    "command": cmd_str,
                    "note": f"Started llama-server (PID {self._managed_process.pid}) for {active_id}."
                }
            except Exception:
                return {
                    "status": "error",
                    "error": "Failed to launch runner process.",
                    "model_id": active_id,
                    "command": cmd_str
                }
        else:
            return {
                "status": "ready_command",
                "model_id": active_id,
                "model_path": model_path,
                "path_exists": exists,
                "command": cmd_str,
                "launcher_script": str(launcher_bat),
                "note": "Executable not found on system PATH. Generated 'start_llama_server.bat' with configured parameters."
            }

    def reset_model_slot(self, llama_client: Optional[Any] = None) -> Dict[str, Any]:
        """
        Erases the active KV cache slot in llama-server (port 8081).
        Preserves context window buffer capacity intact.
        """
        erased = False
        if llama_client is not None and hasattr(llama_client, "reset_slot"):
            erased = llama_client.reset_slot(0)

        cfg = self._ensure_config()
        active_id = self.get_active_model_id()
        ctx_window = cfg.get("pc_runner", {}).get("models", {}).get(active_id, {}).get("context_window", 32768)

        return {
            "status": "reset",
            "kv_cache_erased": erased,
            "active_model": active_id,
            "context_window": ctx_window,
            "note": f"Model KV cache slot erased. Context window capacity ({ctx_window}) preserved intact."
        }

    def stop_runner(self) -> Dict[str, Any]:
        """
        Stops the managed llama-server process cleanly, waits for exit,
        falls back to kill(), and ensures port 8081 is freed.
        """
        stopped = False
        pid = None
        if self._managed_process is not None:
            pid = self._managed_process.pid
            if self._managed_process.poll() is None:
                try:
                    self._managed_process.terminate()
                    self._managed_process.wait(timeout=3)
                    stopped = True
                except Exception:
                    try:
                        self._managed_process.kill()
                        self._managed_process.wait(timeout=2)
                        stopped = True
                    except Exception:
                        pass
            self._managed_process = None

        cfg = self._ensure_config()
        port = cfg.get("pc_runner", {}).get("port", 8081)
        try:
            from brainuke_throne.tls.provisioner import TLSProvisioner
            TLSProvisioner.free_port(port)
        except Exception:
            pass

        return {
            "status": "stopped",
            "pid": pid,
            "stopped": stopped,
            "port_freed": port,
            "note": f"Llama-server stopped and port {port} freed."
        }

