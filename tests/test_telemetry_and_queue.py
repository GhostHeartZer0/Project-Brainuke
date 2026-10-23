"""
tests/test_telemetry_and_queue.py
Unit tests for unfinished prompt queue backlog and Option C hardware telemetry.
"""

import unittest
import os
import shutil
import tempfile
import time
from brainuke_core.memory.vault import MemoryVault
from brainuke_core.telemetry.hardware import (
    get_system_ram_stats,
    get_dedicated_vram_stats,
    get_shared_vram_stats,
    get_all_hardware_telemetry
)
from brainuke_core.cognition.llama_client import LlamaServerClient
from brainuke_core.cognition.orchestrator import CognitiveOrchestrator, OrchestrationResult
from brainuke_core.affect.engine import BrainukeCore


class TestTelemetryAndPromptQueue(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_vault.db")
        self.vault = MemoryVault(db_path=self.db_path)
        self.core = BrainukeCore(baseline_mu={"valence": 0.2, "arousal": 0.0, "dominance": 0.8})

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_memory_vault_failed_prompt_buffer(self):
        # 1. Queue is initially empty
        pending = self.vault.get_pending_failed_prompts(target_mode="pc")
        self.assertEqual(len(pending), 0)
        self.assertEqual(self.vault.get_pending_count(target_mode="pc"), 0)

        # 2. Buffer prompts while offline
        pid1 = self.vault.buffer_failed_prompt("Option C telemetry test", failure_reason="model_offline", target_mode="pc")
        pid2 = self.vault.buffer_failed_prompt("Option D memory check", failure_reason="model_offline", target_mode="pc")
        self.assertGreater(pid1, 0)
        self.assertGreater(pid2, pid1)

        # 3. Retrieve pending prompts
        pending = self.vault.get_pending_failed_prompts(target_mode="pc")
        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]["prompt_text"], "Option C telemetry test")
        self.assertEqual(pending[1]["prompt_text"], "Option D memory check")
        self.assertEqual(self.vault.get_pending_count(target_mode="pc"), 2)

        # 4. Mark first prompt flushed
        ok = self.vault.mark_prompt_status(pid1, "flushed")
        self.assertTrue(ok)
        pending_after = self.vault.get_pending_failed_prompts(target_mode="pc")
        self.assertEqual(len(pending_after), 1)
        self.assertEqual(pending_after[0]["id"], pid2)
        self.assertEqual(self.vault.get_pending_count(target_mode="pc"), 1)

        # 5. Flush second prompt
        self.vault.mark_prompt_status(pid2, "flushed")
        self.assertEqual(self.vault.get_pending_count(target_mode="pc"), 0)

    def test_hardware_telemetry_reads(self):
        # System RAM
        ram = get_system_ram_stats()
        self.assertIn("total_mb", ram)
        self.assertIn("used_mb", ram)
        self.assertIn("pct", ram)
        self.assertGreater(ram["total_mb"], 0)

        # Dedicated VRAM
        vram = get_dedicated_vram_stats()
        self.assertIn("total_mb", vram)
        self.assertIn("used_mb", vram)
        self.assertIn("pct", vram)

        # Shared VRAM
        shared = get_shared_vram_stats()
        self.assertIn("used_mb", shared)
        self.assertIn("total_mb", shared)

        # Combined telemetry snapshot
        snapshot = get_all_hardware_telemetry()
        self.assertIn("ram", snapshot)
        self.assertIn("vram_dedicated", snapshot)
        self.assertIn("vram_shared", snapshot)

    def test_llama_client_telemetry_methods(self):
        client = LlamaServerClient(port=8081)
        telem = client.get_telemetry()
        self.assertIn("ttft_ms", telem)
        self.assertIn("tokens_per_sec", telem)
        self.assertIn("prompt_tokens", telem)
        self.assertIn("predicted_tokens", telem)
        self.assertIn("context_tokens", telem)

    def test_orchestrator_context_metrics(self):
        class MockLLM:
            async def generate_stream(self, prompt, **kwargs):
                yield "Test response token"

            async def generate_text(self, prompt, **kwargs):
                return "Mock authentic speech"

        mock_llm = MockLLM()
        orch = CognitiveOrchestrator(
            core=self.core,
            llm_provider=mock_llm,
            reasoning_llm=mock_llm,
            persona_llm=mock_llm,
            memory_vault=self.vault
        )

        ctx_metrics = orch.get_context_metrics()
        self.assertIn("total_tokens", ctx_metrics)
        self.assertIn("context_window", ctx_metrics)


if __name__ == "__main__":
    unittest.main()
