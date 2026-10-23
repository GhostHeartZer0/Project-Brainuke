"""Tests for MemoryVault cross-temporal keyword search and priority to simmered thoughts."""
import os
import sys
import tempfile
import unittest
import gc
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brainuke_core.memory.vault import MemoryVault
from brainuke_throne.server.main import get_history_feed


class TestMemoryIntegrity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_integrity_vault.db")
        self.vault = MemoryVault(db_path=self.db_path)

    def tearDown(self):
        del self.vault
        gc.collect()
        self.temp_dir.cleanup()

    def test_search_memory_across_all_time_and_simmered_priority(self):
        # 1. Archive a distilled insight (simmered thought) with high importance
        self.vault.archive_insight(
            insight="Quantum entanglement ensures cryptographic cohesion across nodes.",
            concept_family="architecture",
            importance_weight=1.5,
            dominance_weight=0.8
        )

        # 2. Archive an older lower-importance insight
        self.vault.archive_insight(
            insight="General system temperature is stable under nominal load.",
            concept_family="general",
            importance_weight=0.8,
            dominance_weight=0.4
        )

        # 3. Ingest an older turn with the specific keyword
        self.vault.ingest_interaction(
            user_input="Explain quantum entanglement in detail",
            thought_stream="Deep quantum physics reasoning",
            final_response="Quantum entanglement couples two states instantaneously.",
            source_device="pc"
        )

        # 4. Ingest several subsequent interactions across time
        for i in range(5):
            self.vault.ingest_interaction(
                user_input=f"Routine check turn {i}",
                thought_stream="Nominal monitoring",
                final_response=f"Status normal {i}",
                source_device="pc"
            )

        # 5. Search memory across all time with keyword 'quantum'
        search_res = self.vault.search_memory("quantum", limit=10, max_recent=3)

        # Verify simmered insights priority
        self.assertTrue(len(search_res["simmered_insights"]) >= 1)
        self.assertIn("cryptographic cohesion", search_res["simmered_insights"][0]["insight"])
        self.assertEqual(search_res["simmered_insights"][0]["source"], "simmered_insight")

        # Verify latest few prompts are stored and retrieved
        self.assertTrue(len(search_res["recent_prompts"]) <= 3)
        self.assertEqual(len(search_res["recent_prompts"]), 3)

        # Verify historical interaction matching keyword across all time was found
        self.assertTrue(len(search_res["historical_interactions"]) >= 1)
        hist_text = [h["user_input"] for h in search_res["historical_interactions"]]
        self.assertTrue(any("quantum" in t.lower() for t in hist_text))

    def test_get_grounding_for_prompt_prioritizes_simmered_thoughts(self):
        self.vault.archive_insight(
            insight="Adversarial firewall blocks prompt injection attempts.",
            concept_family="security_guardrails",
            importance_weight=1.8,
            dominance_weight=0.9
        )
        self.vault.archive_insight(
            insight="Unrelated mood reflection on calm morning.",
            concept_family="affect_and_identity",
            importance_weight=1.0,
            dominance_weight=0.5
        )

        # Prompt with keyword 'firewall'
        grounding = self.vault.get_grounding_for_prompt("How strong is our firewall against jailbreaks?", limit=4)
        self.assertTrue(len(grounding) >= 1)
        # First node must be the matching simmered thought
        self.assertEqual(grounding[0]["concept_family"], "security_guardrails")
        self.assertIn("Adversarial firewall", grounding[0]["insight"])

    async def test_get_history_feed_with_query_parameter(self):
        self.vault.archive_insight(
            insight="Neural network telemetry reveals low latency on Snapdragon NPU.",
            concept_family="architecture",
            importance_weight=1.2
        )

        # Test request mock
        req = MagicMock()
        req.headers = {"Authorization": "Bearer bypass"}

        # Patch memory_vault in server/main.py temporarily
        import brainuke_throne.server.main as server_main
        old_vault = server_main.memory_vault
        old_verify = server_main.verify_machine_token
        server_main.memory_vault = self.vault
        server_main.verify_machine_token = lambda r: True
        try:
            feed = await get_history_feed(req, limit=10, q="neural")
            self.assertEqual(feed["status"], "ok")
            self.assertEqual(feed["query"], "neural")
            self.assertTrue(len(feed["dmn_insights"]) >= 1)
            self.assertIn("Snapdragon NPU", feed["dmn_insights"][0]["insight"])
        finally:
            server_main.memory_vault = old_vault
            server_main.verify_machine_token = old_verify


if __name__ == "__main__":
    unittest.main()
