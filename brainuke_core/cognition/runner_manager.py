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
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


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

        # 2. Check workspace models/ folder fallback
        if model_id == self.NORMAL_MODEL_ID:
            ws_fallback = self.workspace_root / "models" / "26B" / "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
            if ws_fallback.exists():
                return str(ws_fallback), True
        elif model_id == self.SECRET_MODEL_ID:
            ws_fallback = self.workspace_root / "models" / "26B-unc" / "gemma-4-26B-A4B-it-qat-q4_0-unquantized-uncensored-heretic-v2.i1-Q4_K_M.gguf"
            if ws_fallback.exists():
                return str(ws_fallback), True

        return configured_path or "unknown", False

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
            "process_managed": (self._managed_process is not None and self._managed_process.poll() is None)
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

        candidates = [
            r"C:\Program Files\Android\Android Studio\plugins\gemini\resources\llamacpp\llama-server.exe",
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
        if self._managed_process is not None and self._managed_process.poll() is None:
            try:
                self._managed_process.terminate()
                self._managed_process.wait(timeout=3)
            except Exception:
                try:
                    self._managed_process.kill()
                except Exception:
                    pass
            self._managed_process = None

        # Cleanly free port 8081 if occupied by any zombie/prior process
        try:
            from brainuke_throne.tls.provisioner import TLSProvisioner
            TLSProvisioner.free_port(port)
        except Exception:
            pass

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
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
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
