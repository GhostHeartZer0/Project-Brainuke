import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from brainuke_core.cognition.runner_manager import PCRunnerManager


class TestPCRunnerManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "models.json"
        
        # Seed dummy config
        dummy_data = {
            "active_model": PCRunnerManager.NORMAL_MODEL_ID,
            "pc_runner": {
                "engine": "llama-server",
                "host": "127.0.0.1",
                "port": 8081,
                "default_flags": [
                    "-sm", "none",
                    "-fa", "on",
                    "--cache-type-k", "q8_0",
                    "--cache-type-v", "q5_1"
                ],
                "models": {
                    PCRunnerManager.NORMAL_MODEL_ID: {
                        "path": "S:/LLM/gemma-4 QAT/26B-A4B/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
                        "role": "heavy_intellect_supervisor",
                        "gpu_layers": 8,
                        "context_window": 32768,
                        "temperature": 0.8,
                        "min_p": 0.05,
                        "repeat_penalty": 1.1
                    },
                    PCRunnerManager.SECRET_MODEL_ID: {
                        "path": "S:/LLM/gemma-4-unc/26B/gemma-4-26B-A4B-it-qat-q4_0-unquantized-uncensored-heretic-v2.i1-Q4_K_M.gguf",
                        "role": "secret_uncensored",
                        "gpu_layers": 7,
                        "context_window": 32768,
                        "temperature": 0.8,
                        "min_p": 0.05,
                        "repeat_penalty": 1.1
                    }
                }
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(dummy_data, f)
            
        self.manager = PCRunnerManager(config_path=str(self.config_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_active_model_is_normal(self):
        self.assertEqual(self.manager.get_active_alias(), "normal")
        self.assertEqual(self.manager.get_active_model_id(), PCRunnerManager.NORMAL_MODEL_ID)

    def test_select_secret_model(self):
        res = self.manager.select_model("secret")
        self.assertEqual(res["alias"], "secret")
        self.assertEqual(res["active_model"], PCRunnerManager.SECRET_MODEL_ID)
        self.assertEqual(self.manager.get_active_alias(), "secret")

    def test_select_normal_model(self):
        self.manager.select_model("secret")
        res = self.manager.select_model("normal")
        self.assertEqual(res["alias"], "normal")
        self.assertEqual(res["active_model"], PCRunnerManager.NORMAL_MODEL_ID)
        self.assertEqual(self.manager.get_active_alias(), "normal")

    def test_get_status_offline(self):
        mock_client = MagicMock()
        mock_client.is_healthy.return_value = False
        status = self.manager.get_status(llama_client=mock_client)
        self.assertFalse(status["online"])
        self.assertEqual(status["status"], "offline")
        self.assertEqual(status["active_alias"], "normal")
        self.assertEqual(status["port"], 8081)
        self.assertIn("temperature", status["inference_settings"])

    def test_get_status_online(self):
        mock_client = MagicMock()
        mock_client.is_healthy.return_value = True
        status = self.manager.get_status(llama_client=mock_client)
        self.assertTrue(status["online"])
        self.assertEqual(status["status"], "loaded")

    def test_update_inference_settings(self):
        new_settings = {
            "temperature": 0.95,
            "min_p": 0.08,
            "context_window": 16384,
            "gpu_layers": 12,
            "repeat_penalty": 1.15,
            "cache_type_k": "q4_0",
            "cache_type_v": "q4_0",
            "flash_attn": False
        }
        res = self.manager.update_inference_settings(new_settings)
        self.assertEqual(res["status"], "updated")

        status = self.manager.get_status()
        self.assertAlmostEqual(status["inference_settings"]["temperature"], 0.95)
        self.assertAlmostEqual(status["inference_settings"]["min_p"], 0.08)
        self.assertEqual(status["inference_settings"]["context_window"], 16384)
        self.assertEqual(status["inference_settings"]["gpu_layers"], 12)
        self.assertEqual(status["inference_settings"]["cache_type_k"], "q4_0")
        self.assertEqual(status["inference_settings"]["cache_type_v"], "q4_0")
        self.assertFalse(status["inference_settings"]["flash_attn"])

    def test_get_launch_command(self):
        cmd = self.manager.get_launch_command()
        self.assertIn("llama-server", cmd)
        self.assertIn("--port 8081", cmd)
        self.assertIn("-c 32768", cmd)
        self.assertIn("-ngl 8", cmd)

    def test_initiate_load(self):
        res = self.manager.initiate_load()
        self.assertIn(res["status"], ("launched", "ready_command"))
        self.assertIn("command", res)

    def test_reset_model_slot(self):
        mock_client = MagicMock()
        mock_client.reset_slot.return_value = True
        res = self.manager.reset_model_slot(llama_client=mock_client)
        self.assertEqual(res["status"], "reset")
        self.assertTrue(res["kv_cache_erased"])
        self.assertEqual(res["context_window"], 32768)

    def test_orchestrator_reset_command(self):
        import asyncio
        from brainuke_core.affect.engine import BrainukeCore
        from brainuke_core.cognition.orchestrator import CognitiveOrchestrator

        core = BrainukeCore(baseline_mu={'v': 0.2, 'a': 0.0, 'd': 0.8})
        mock_client = MagicMock()
        mock_client.reset_slot.return_value = True
        orchestrator = CognitiveOrchestrator(core=core, llm_provider=mock_client, runner_manager=self.manager)

        res = asyncio.run(orchestrator.process_interaction("/reset", []))
        self.assertIn("cleared", res.final_response.lower())
        self.assertIn("intact", res.final_response.lower())

    def test_stop_runner(self):
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = None
        self.manager._managed_process = mock_proc

        res = self.manager.stop_runner()
        self.assertEqual(res["status"], "stopped")
        self.assertEqual(res["pid"], 9999)
        self.assertTrue(res["stopped"])
        mock_proc.terminate.assert_called_once()
        self.assertIsNone(self.manager._managed_process)


    def test_scan_available_models_and_auto_fallback(self):
        # Create a mock models directory with a fallback .gguf
        mock_models_dir = Path(self.temp_dir.name) / "models"
        mock_models_dir.mkdir(parents=True, exist_ok=True)
        fallback_gguf = mock_models_dir / "fallback_cerebrum.gguf"
        fallback_gguf.write_bytes(b"GGUF_TEST_BYTES")

        # Point workspace root to temp dir
        self.manager.workspace_root = Path(self.temp_dir.name)

        # 1. Test scanning
        discovered = self.manager.scan_available_models()
        self.assertTrue(any(d["name"] == "fallback_cerebrum.gguf" for d in discovered))

        # 2. Test auto-fallback when configured path is missing
        resolved_path, exists = self.manager.resolve_model_path("non_existent_model_id")
        self.assertTrue(exists)
        self.assertEqual(os.path.abspath(resolved_path), os.path.abspath(str(fallback_gguf)))

    def test_set_custom_model_path(self):
        dummy_gguf = Path(self.temp_dir.name) / "custom_model.gguf"
        dummy_gguf.write_bytes(b"MOCK_MODEL")

        res = self.manager.set_custom_model_path(str(dummy_gguf))
        self.assertEqual(res["status"], "updated")
        self.assertEqual(res["path"], str(dummy_gguf))

        # Test invalid path error handling
        err_res = self.manager.set_custom_model_path(r"C:\fake\path\does_not_exist.gguf")
        self.assertEqual(err_res["status"], "error")

    def test_path_containment_and_traversal_rejection(self):
        # 1. Allowed path within workspace/temp dir
        dummy_gguf = Path(self.temp_dir.name) / "allowed.gguf"
        dummy_gguf.write_bytes(b"TEST")
        self.assertTrue(self.manager.is_path_within_allowed_dirs(dummy_gguf))

        # 2. Outside path traversal attempt rejected
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_gguf = Path(outside_dir) / "evil.gguf"
            outside_gguf.write_bytes(b"EXPLOIT")
            self.assertFalse(self.manager.is_path_within_allowed_dirs(outside_gguf))

            err_res = self.manager.set_custom_model_path(str(outside_gguf))
            self.assertEqual(err_res["status"], "error")
            self.assertIn("outside permitted", err_res["error"].lower())


if __name__ == "__main__":
    unittest.main()

