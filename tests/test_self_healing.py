import unittest
import os
import json
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from brainuke_core.cognition.error_sentry import ErrorSentry, ErrorDiagnostic
from brainuke_core.cognition.self_healing_ide import SelfHealingIDE
from brainuke_core.cognition.runner_manager import PCRunnerManager


class TestErrorSentry(unittest.TestCase):
    def setUp(self):
        self.sentry = ErrorSentry(max_history=5)

    def test_flag_exception(self):
        try:
            raise ValueError("Invalid dimension index")
        except ValueError as exc:
            diag = self.sentry.flag_exception(exc, subsystem="throne_server", context_vars={"req_id": 42})

        self.assertEqual(diag.error_type, "ValueError")
        self.assertEqual(diag.message, "Invalid dimension index")
        self.assertEqual(diag.subsystem, "throne_server")
        self.assertEqual(diag.context_vars.get("req_id"), 42)
        self.assertIn("ValueError: Invalid dimension index", diag.traceback_str)
        self.assertEqual(diag.status, "flagged")

    def test_flag_manual_error(self):
        diag = self.sentry.flag_manual_error("Manual button test", subsystem="ui_desktop")
        self.assertEqual(diag.error_type, "ManualDebugTrigger")
        self.assertEqual(diag.message, "Manual button test")
        self.assertEqual(diag.subsystem, "ui_desktop")
        self.assertEqual(self.sentry.get_latest_error().error_id, diag.error_id)

    def test_sentry_eviction(self):
        for i in range(10):
            self.sentry.flag_manual_error(f"Err {i}")
        errors = self.sentry.get_errors()
        self.assertEqual(len(errors), 5)
        self.assertEqual(errors[-1]["message"], "Err 9")

    def test_get_by_id_and_clear(self):
        diag = self.sentry.flag_manual_error("Look me up")
        found = self.sentry.get_error_by_id(diag.error_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.message, "Look me up")

        self.sentry.clear()
        self.assertEqual(len(self.sentry.get_errors()), 0)


class TestSelfHealingIDE(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.config_path = self.workspace / "config" / "self_healing.json"
        
        # Create dummy module file to patch
        self.test_src_dir = self.workspace / "brainuke_core"
        self.test_src_dir.mkdir(parents=True, exist_ok=True)
        self.dummy_file = self.test_src_dir / "calculator.py"
        with open(self.dummy_file, "w", encoding="utf-8") as f:
            f.write("def compute(x):\n    return x + 1\n")

        self.mock_llm = MagicMock()
        self.mock_llm.is_healthy.return_value = True
        self.mock_runner = MagicMock()
        self.mock_runner.get_status.return_value = {
            "online": True,
            "status": "loaded",
            "active_model": PCRunnerManager.NORMAL_MODEL_ID,
            "active_alias": "normal",
            "port": 8081
        }
        self.restart_called = False

        def on_restart():
            self.restart_called = True

        self.ide = SelfHealingIDE(
            config_path=str(self.config_path),
            workspace_root=str(self.workspace),
            llm_client=self.mock_llm,
            runner_manager=self.mock_runner,
            restart_callback=on_restart
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_settings_persistence(self):
        settings = self.ide.load_settings()
        self.assertFalse(settings.get("auto_heal_enabled"))

        self.ide.save_settings({"auto_heal_enabled": True, "max_healing_attempts": 5})
        reloaded = self.ide.load_settings()
        self.assertTrue(reloaded.get("auto_heal_enabled"))
        self.assertEqual(reloaded.get("max_healing_attempts"), 5)

    def test_check_green_lights(self):
        green, details = self.ide.check_green_lights()
        self.assertTrue(green)
        self.assertTrue(details["runner_healthy"])
        self.assertTrue(details["model_loaded"])

        # Offline case
        self.mock_llm.is_healthy.return_value = False
        self.mock_runner.get_status.return_value = {"online": False}
        green2, details2 = self.ide.check_green_lights()
        self.assertFalse(green2)
        self.assertFalse(details2["runner_healthy"])

    def test_sandbox_tools(self):
        # read_code_file
        code = self.ide.read_code_file("brainuke_core/calculator.py")
        self.assertIn("def compute(x):", code)

        # Path traversal guard
        invalid = self.ide.read_code_file("../../etc/passwd")
        self.assertIn("not found", invalid.lower())

        # search_workspace
        search_res = self.ide.search_workspace("compute")
        self.assertIn("calculator.py", search_res)

        # test_syntax_sandbox
        valid_ok, _ = self.ide.test_syntax_sandbox("def valid(a):\n    return a * 2\n")
        self.assertTrue(valid_ok)

        invalid_ok, msg = self.ide.test_syntax_sandbox("def broken(\n")
        self.assertFalse(invalid_ok)
        self.assertIn("Syntax Error", msg)

    def test_diagnose_and_heal_pipeline(self):
        # Seed an error into sentry
        diag = self.ide.sentry.flag_manual_error(
            message="ZeroDivisionError in compute",
            error_type="ZeroDivisionError",
            traceback_str=f'File "{self.dummy_file}", line 2, in compute\n  return 1 / 0\nZeroDivisionError: division by zero',
            subsystem="cognition"
        )

        patch_code = "def compute(x):\n    return x if x != 0 else 0\n"
        llm_reply = (
            "<thought>Let us fix division by zero.</thought>\n"
            f"[PATCH: brainuke_core/calculator.py]\n"
            f"```python\n{patch_code}```\n[/PATCH]"
        )
        self.mock_llm.generate_text = AsyncMock(return_value=llm_reply)

        # Run diagnosis (with force=True to bypass auto_heal_enabled=False)
        result = asyncio.run(self.ide.diagnose_and_heal(diag, force=True))
        self.assertEqual(result["status"], "pending_confirmation")
        self.assertEqual(result["error_id"], diag.error_id)
        self.assertEqual(diag.target_file, "brainuke_core/calculator.py")

        # Now apply staged patch
        apply_res = self.ide.apply_staged_patch(diag.error_id)
        self.assertEqual(apply_res["status"], "applied")
        self.assertTrue(self.restart_called)

        # Verify target file has updated content
        with open(self.dummy_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, patch_code.strip())

        # Verify backup exists
        backup_file = self.ide.sandbox_dir / "calculator.py.bak"
        self.assertTrue(backup_file.exists())


if __name__ == "__main__":
    unittest.main()
