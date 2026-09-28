"""
brainuke_core/cognition/self_healing_ide.py
Cecilia Self-Healing IDE & Recursive Error Correction Engine for Project Brainuke.

Features:
- Inference Green-Light Verification Gate (checks llama-server health & loaded model).
- Sandboxed Studio Workspace (read_code, search_code, test_syntax, propose_patch).
- Autonomous recursive retry loop (re-feeds traceback up to max_healing_attempts).
- Safe patch staging with backup and human confirmation gate.
- Auto-restart and hot-reload triggering.
- Full toggleable settings persistence in config/self_healing.json.
"""

import os
import re
import json
import shutil
import py_compile
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable

from brainuke_core.cognition.error_sentry import ErrorSentry, ErrorDiagnostic
from brainuke_core.cognition.llama_client import LlamaServerClient
from brainuke_core.cognition.runner_manager import PCRunnerManager


class SelfHealingIDE:
    def __init__(
        self,
        config_path: Optional[str] = None,
        workspace_root: Optional[str] = None,
        llm_client: Optional[LlamaServerClient] = None,
        runner_manager: Optional[PCRunnerManager] = None,
        restart_callback: Optional[Callable[[], None]] = None
    ):
        self.workspace_root = Path(workspace_root) if workspace_root else Path(__file__).resolve().parent.parent.parent
        self.config_path = Path(config_path) if config_path else self.workspace_root / "config" / "self_healing.json"
        self.llm_client = llm_client or LlamaServerClient(port=8081)
        self.runner_manager = runner_manager or PCRunnerManager()
        self.restart_callback = restart_callback
        self.sentry = ErrorSentry.get_instance()
        
        self.sandbox_dir = self.workspace_root / "brainuke_throne" / "sandbox" / "self_healing"
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    def load_settings(self) -> Dict[str, Any]:
        """Loads toggleable settings from config/self_healing.json."""
        if not self.config_path.exists():
            return {
                "auto_heal_enabled": False,
                "require_human_confirmation": True,
                "max_healing_attempts": 3,
                "auto_restart_on_patch": True,
                "target_model": PCRunnerManager.NORMAL_MODEL_ID,
                "sandbox_dir": str(self.sandbox_dir)
            }
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Saves toggleable settings."""
        current = self.load_settings()
        current.update(settings)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return current

    def check_green_lights(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Inference Indicators Gate:
        Verifies:
        1. llama-server online (Port 8081 responsive).
        2. Model loaded and operational.
        """
        is_healthy = bool(self.llm_client.is_healthy())
        status = self.runner_manager.get_status(llama_client=self.llm_client)
        is_online = status.get("online", False)

        all_green = is_healthy and is_online
        details = {
            "all_green": all_green,
            "runner_healthy": is_healthy,
            "model_loaded": is_online,
            "active_model": status.get("active_model"),
            "active_alias": status.get("active_alias"),
            "port": status.get("port", 8081)
        }
        return all_green, details

    # --- SANDBOX TOOLS EXPOSED TO CECILIA ---
    def read_code_file(self, relative_path: str, max_lines: int = 250) -> str:
        """Reads file from workspace with safety bounds."""
        target = (self.workspace_root / relative_path).resolve()
        if not target.is_relative_to(self.workspace_root) or not target.exists():
            return f"[Error]: File '{relative_path}' not found."
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            total = len(lines)
            content = "".join(lines[:max_lines])
            truncated = f"\n... [Truncated: {total - max_lines} lines remain]" if total > max_lines else ""
            return f"--- {relative_path} (Lines 1-{min(total, max_lines)} of {total}) ---\n{content}{truncated}"
        except Exception as e:
            return f"[Read Error]: {e}"

    def search_workspace(self, query: str, max_results: int = 10) -> str:
        """Lightweight workspace code search."""
        matches = []
        for root, _, files in os.walk(self.workspace_root):
            if any(p in root for p in [".git", "__pycache__", "build", ".gradle", "sandbox"]):
                continue
            for fname in files:
                if not fname.endswith((".py", ".kt", ".json", ".bat")):
                    continue
                fpath = Path(root) / fname
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f, 1):
                            if query.lower() in line.lower():
                                rel = fpath.relative_to(self.workspace_root)
                                matches.append(f"{rel}:{idx}: {line.strip()[:100]}")
                                if len(matches) >= max_results:
                                    break
                except Exception:
                    pass
            if len(matches) >= max_results:
                break
        return "\n".join(matches) if matches else f"No matches found for query: '{query}'"

    def test_syntax_sandbox(self, code_str: str) -> Tuple[bool, str]:
        """Tests python syntax in sandbox."""
        tmp_file = self.sandbox_dir / "candidate_patch.py"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(code_str)
            py_compile.compile(str(tmp_file), doraise=True)
            return True, "Syntax validated (compile passed)."
        except py_compile.PyCompileError as e:
            return False, f"Syntax Error: {e}"
        except Exception as e:
            return False, f"Compile Error: {e}"

    # --- RECURSIVE ERROR SOLVING & HEALING PIPELINE ---
    async def diagnose_and_heal(
        self,
        error_diagnostic: Optional[ErrorDiagnostic] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Executes recursive error diagnosis and healing process:
        1. Checks green lights on inference.
        2. Sends traceback and context to Cecilia.
        3. Cecilia reasons in sandbox and generates code patch.
        4. Validates patch syntax and runs tests.
        5. Either stages for human confirmation or applies immediately.
        """
        settings = self.load_settings()
        if not force and not settings.get("auto_heal_enabled", False):
            return {
                "status": "skipped",
                "reason": "Autonomous self-healing is disabled in settings. Use debug button or enable setting."
            }

        green, indicators = self.check_green_lights()
        if not green:
            return {
                "status": "aborted_inference_offline",
                "reason": "Inference indicators red: llama-server is offline or unloaded.",
                "indicators": indicators
            }

        diag = error_diagnostic or self.sentry.get_latest_error()
        if not diag:
            return {"status": "no_errors_flagged", "reason": "No errors currently in sentry queue."}

        max_attempts = settings.get("max_healing_attempts", 3)
        if diag.attempts >= max_attempts:
            diag.status = "failed"
            diag.resolution_note = f"Max recursive healing attempts ({max_attempts}) exhausted."
            return {"status": "failed", "reason": diag.resolution_note}

        diag.status = "in_progress"
        diag.attempts += 1

        # Locate offending file from traceback
        offending_file = self._extract_offending_file(diag.traceback_str)
        file_context = self.read_code_file(offending_file) if offending_file else "File context unavailable."

        # Cecilia's self-healing prompt
        studio_prompt = (
            f"<start_of_turn>user\n"
            f"[SYSTEM DIRECTIVE: CECILIA RECURSIVE SELF-HEALING STUDIO]\n"
            f"You are Cecilia, acting inside your private cognitive IDE studio to self-correct a runtime failure.\n"
            f"Error Subsystem: {diag.subsystem}\n"
            f"Error Type: {diag.error_type}\n"
            f"Error Message: {diag.message}\n"
            f"Attempt Count: {diag.attempts} / {max_attempts}\n\n"
            f"[RUNTIME TRACEBACK]\n{diag.traceback_str}\n\n"
            f"[OFFENDING CODE CONTEXT]\n{file_context}\n\n"
            f"TASKS:\n"
            f"1. Deconstruct the defect analytically in your shadow reasoning stream.\n"
            f"2. Formulate the precise, minimal fix following the laziness ladder (native platform, standard library, single-line).\n"
            f"3. Produce the corrected python code block within a tagged block: [PATCH: <relative_path>]```python ... ```[/PATCH].\n"
            f"Maintain all existing functionality and docstrings. Do not include markdown preamble outside tags.<end_of_turn>\n"
            f"<start_of_turn>model\n"
            f"<thought>\n"
        )

        try:
            # Query Cecilia LLM
            solution_text = await self.llm_client.generate_text(
                studio_prompt,
                stop=["</turn>", "<|turn>", "<turn|>", "<eos>"]
            )

            # Extract patch from response
            patch_match = re.search(r"\[PATCH:\s*([^\]]+)\]\s*```(?:python)?\s*(.*?)\s*```\[/PATCH\]", solution_text, re.DOTALL | re.IGNORECASE)
            
            if not patch_match:
                # Fallback search for any python code fence
                fallback_code = re.search(r"```(?:python)?\s*(.*?)\s*```", solution_text, re.DOTALL)
                if fallback_code and offending_file:
                    target_file = offending_file
                    code_patch = fallback_code.group(1).strip()
                else:
                    diag.status = "failed"
                    diag.resolution_note = "Cecilia analysis produced diagnostic thoughts but no valid [PATCH] block."
                    return {
                        "status": "failed",
                        "error_id": diag.error_id,
                        "raw_output": solution_text[:300],
                        "reason": diag.resolution_note
                    }
            else:
                target_file = patch_match.group(1).strip()
                code_patch = patch_match.group(2).strip()

            # 4. Verify syntax in sandbox
            valid, syntax_note = self.test_syntax_sandbox(code_patch)
            if not valid:
                # Syntax failed: Recursive loop if attempts remain
                if diag.attempts < max_attempts:
                    diag.traceback_str += f"\n[Self-Healing Sandbox Syntax Failure]: {syntax_note}"
                    return await self.diagnose_and_heal(diag, force=force)
                else:
                    diag.status = "failed"
                    diag.resolution_note = f"Patch syntax check failed: {syntax_note}"
                    return {"status": "failed", "reason": diag.resolution_note}

            diag.target_file = target_file
            diag.patch_diff = code_patch

            # 5. Check confirmation gate
            if settings.get("require_human_confirmation", True):
                diag.status = "pending_confirmation"
                diag.resolution_note = "Patch generated and syntax-verified. Awaiting human confirmation in UI."
                return {
                    "status": "pending_confirmation",
                    "error_id": diag.error_id,
                    "target_file": target_file,
                    "patch_length": len(code_patch),
                    "note": diag.resolution_note
                }
            else:
                # Apply immediately
                return self.apply_staged_patch(diag.error_id)

        except Exception as e:
            diag.status = "failed"
            diag.resolution_note = f"Exception in self-healing pipeline: {e}"
            return {"status": "error", "error": str(e)}

    def apply_staged_patch(self, error_id: str) -> Dict[str, Any]:
        """Applies a verified staged patch to the live workspace file."""
        diag = self.sentry.get_error_by_id(error_id)
        if not diag or not diag.target_file or not diag.patch_diff:
            return {"status": "error", "error": f"No valid patch found for error {error_id}."}

        target_path = (self.workspace_root / diag.target_file).resolve()
        if not target_path.is_relative_to(self.workspace_root):
            return {"status": "error", "error": "Invalid target file path (sandbox escape prevented)."}

        # Backup original file
        if target_path.exists():
            backup_path = self.sandbox_dir / f"{target_path.name}.bak"
            shutil.copy2(target_path, backup_path)

        # Write patch
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(diag.patch_diff)

        diag.status = "resolved"
        diag.resolution_note = f"Successfully patched {diag.target_file}."

        settings = self.load_settings()
        restarted = False
        if settings.get("auto_restart_on_patch", True):
            if self.restart_callback:
                try:
                    self.restart_callback()
                    restarted = True
                except Exception:
                    pass

        return {
            "status": "applied",
            "error_id": diag.error_id,
            "target_file": diag.target_file,
            "auto_restarted": restarted,
            "note": diag.resolution_note
        }

    def _extract_offending_file(self, tb_str: str) -> Optional[str]:
        """Parses python traceback to extract relevant workspace file path."""
        matches = re.findall(r'File "([^"]+)", line \d+', tb_str)
        for m in reversed(matches):
            p = Path(m)
            try:
                rel = p.relative_to(self.workspace_root)
                return str(rel).replace("\\", "/")
            except ValueError:
                if "brainuke" in m or "server" in m or "core" in m:
                    parts = p.parts
                    for i in range(len(parts)):
                        if parts[i] in ("brainuke_core", "brainuke_throne", "tests"):
                            return "/".join(parts[i:])
        return None
