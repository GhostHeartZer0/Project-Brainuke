"""Tests for sync mechanics, influence weighting, and fallback isolation."""
import os
import sys
import tempfile
import unittest
import gc
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brainuke_core.cognition.llama_client import LlamaServerClient
from brainuke_core.memory.vault import MemoryVault
from brainuke_core.security.key_vault import KeyVault
from brainuke_throne.server.main import sync_status_endpoint, sync_trigger, sync_simmer, get_history_feed, last_sync_info, simmer_bus


class TestSyncAndWeighting(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_vault.db")
        self.vault = MemoryVault(db_path=self.db_path)
        self.token = KeyVault.generate_token()

    def tearDown(self):
        del self.vault
        gc.collect()
        self.temp_dir.cleanup()

    def _make_mock_request(self):
        req = MagicMock()
        req.headers = {"Authorization": f"Bearer {self.token}"}
        req.query_params = {}
        return req

    def test_vault_influence_weighting(self):
        # PC interaction (default weight 1.0)
        self.vault.ingest_interaction(
            user_input="Hello PC",
            thought_stream="Analyzing PC input",
            final_response="PC Cecilia response",
            source_device="pc",
            influence_weight=1.0,
        )

        # Android interaction (default weight 0.35)
        self.vault.ingest_interaction(
            user_input="Hello Android",
            thought_stream="Analyzing mobile input",
            final_response="Android Cecilia response",
            source_device="android",
            influence_weight=0.35,
        )

        recs = self.vault.get_recent_interactions(limit=10)
        self.assertEqual(len(recs), 2)
        # recs[0] is most recent (android), recs[1] is earlier (pc)
        self.assertEqual(recs[0]["source_device"], "android")
        self.assertEqual(recs[0]["influence_weight"], 0.35)
        self.assertEqual(recs[1]["source_device"], "pc")
        self.assertEqual(recs[1]["influence_weight"], 1.0)

    async def test_llama_client_fallback_no_directive_leak(self):
        client = LlamaServerClient(port=9999)  # Unreachable port
        prompt = "[SYSTEM DIRECTIVE: CECILIA PERSONA ENGINE] You are Cecilia."
        res = await client.generate_text(prompt=prompt)

        # Must NOT leak directive
        self.assertNotIn("[SYSTEM DIRECTIVE:", res)
        self.assertIn("PC Core Offline", res)

    async def test_sync_status_endpoint(self):
        req = self._make_mock_request()
        data = await sync_status_endpoint(req)
        self.assertEqual(data["status"], "ok")
        self.assertIn("last_sync", data)

    async def test_sync_trigger_endpoint(self):
        req = self._make_mock_request()
        data = await sync_trigger(req)
        self.assertEqual(data["status"], "sync_triggered")
        self.assertEqual(data["source"], "pc")
        self.assertIsNotNone(data["last_sync"])
        self.assertTrue(data.get("in_progress"))

    async def test_sync_simmer_endpoint_async(self):
        req = self._make_mock_request()
        data = await sync_simmer(req)
        self.assertEqual(data["status"], "simmered")
        self.assertTrue(data.get("in_progress"))
        # Verify status endpoint reflects simmer state or completion
        status_data = await sync_status_endpoint(req)
        self.assertEqual(status_data["status"], "ok")
        self.assertIn("sync_status", status_data)
        self.assertIn("is_simmering", status_data)

    async def test_process_interaction_streaming(self):
        from brainuke_core.affect.engine import BrainukeCore
        from brainuke_core.cognition import CognitiveOrchestrator
        from brainuke_core.cognition.thought_isolation import ThoughtIsolation

        captured_thoughts = []
        captured_speech = []
        captured_prompts = []

        class MockStreamingLLM:
            async def generate_stream(self, prompt, **kwargs):
                captured_prompts.append(prompt)
                if "[REASONING ENGINE" in prompt:
                    yield "Analyzing "
                    yield "intent in shadows."
                else:
                    yield "Reality is raw, "
                    yield "deal with it."

            async def generate_text(self, prompt, **kwargs):
                return "Fallback speech"

        core = BrainukeCore(baseline_mu={'v': 0.2, 'a': 0.0, 'd': 0.8})
        llm = MockStreamingLLM()
        orchestrator = CognitiveOrchestrator(core=core, llm_provider=llm, memory_vault=self.vault)

        async def _thought_cb(chunk: str):
            captured_thoughts.append(chunk)

        async def _speech_cb(chunk: str):
            captured_speech.append(chunk)

        res = await orchestrator.process_interaction(
            user_input="reality, good.",
            context=[],
            on_thought_chunk=_thought_cb,
            on_speech_chunk=_speech_cb
        )

        self.assertEqual("".join(captured_thoughts), "Analyzing intent in shadows.")
        self.assertEqual("".join(captured_speech), "Reality is raw, deal with it.")
        self.assertEqual(res.thought_stream, "Analyzing intent in shadows.")
        self.assertEqual(res.final_response, "Reality is raw, deal with it.")

        # Ensure final prompt cleanly wraps thoughts inside closed <|thought|> tags
        persona_prompt = captured_prompts[1]
        self.assertIn("<|thought|>\nAnalyzing intent in shadows.\n</|thought|>", persona_prompt)

    def test_thought_isolation_leak_patterns(self):
        from brainuke_core.cognition.thought_isolation import ThoughtIsolation
        isolator = ThoughtIsolation()

        leaked_text = (
            "[REASONING ENGINE: SHADOW DECONSTRUCTION]\n"
            "[ANALYSIS_START]\n"
            "<|thought|>\n"
            "Hidden thought content\n"
            "</|thought|>\n"
            "<turn|>\n"
            "Spoken authentic response."
        )

        sanitized = isolator.sanitize_speech(leaked_text)
        self.assertNotIn("REASONING ENGINE", sanitized)
        self.assertNotIn("ANALYSIS_START", sanitized)
        self.assertNotIn("<|thought|>", sanitized)
        self.assertNotIn("<turn|>", sanitized)
        self.assertIn("Spoken authentic response.", sanitized)

    async def test_history_feed_endpoint(self):
        req = self._make_mock_request()
        # Seed test data in main's memory vault
        from brainuke_throne.server.main import memory_vault
        memory_vault.ingest_interaction(
            user_input="Test PC input",
            thought_stream="Reasoning on PC core",
            final_response="PC core response",
            source_device="pc",
            influence_weight=1.0
        )
        memory_vault.ingest_interaction(
            user_input="Test Mobile input",
            thought_stream="Reasoning on companion",
            final_response="Mobile companion response",
            source_device="android",
            influence_weight=0.35
        )
        memory_vault.archive_insight(
            insight="Distilled test insight from DMN",
            concept_family="architecture",
            importance_weight=1.2,
            dominance_weight=0.6
        )

        # Test filter="all"
        res_all = await get_history_feed(req, limit=10, filter="all")
        self.assertEqual(res_all["status"], "ok")
        self.assertEqual(res_all["weights"]["pc_master"], 1.0)
        self.assertEqual(res_all["weights"]["android_companion"], 0.35)
        self.assertEqual(res_all["weights"]["telemetry_oracle"], 0.2)
        self.assertGreaterEqual(len(res_all["interactions"]), 2)
        self.assertGreaterEqual(len(res_all["dmn_insights"]), 1)

        # Verify weights on individual records
        pc_turns = [t for t in res_all["interactions"] if t.get("source_device") == "pc"]
        android_turns = [t for t in res_all["interactions"] if t.get("source_device") == "android"]
        self.assertTrue(any(t["influence_weight"] == 1.0 for t in pc_turns))
        self.assertTrue(any(t["influence_weight"] == 0.35 for t in android_turns))

        # Test filter="pc"
        res_pc = await get_history_feed(req, limit=10, filter="pc")
        self.assertTrue(all(t.get("source_device") == "pc" for t in res_pc["interactions"]))
        self.assertEqual(len(res_pc["dmn_insights"]), 0)

        # Test filter="android"
        res_android = await get_history_feed(req, limit=10, filter="android")
        self.assertTrue(all(t.get("source_device") == "android" for t in res_android["interactions"]))
        self.assertEqual(len(res_android["dmn_insights"]), 0)

        # Test filter="dmn"
        res_dmn = await get_history_feed(req, limit=10, filter="dmn")
        self.assertEqual(len(res_dmn["interactions"]), 0)
        self.assertGreaterEqual(len(res_dmn["dmn_insights"]), 1)
        self.assertEqual(res_dmn["dmn_insights"][0]["concept_family"], "architecture")

    def test_vault_device_filtering_and_insights(self):
        self.vault.ingest_interaction(
            user_input="PC query",
            thought_stream="PC thought",
            final_response="PC speech",
            source_device="pc",
            influence_weight=1.0
        )
        self.vault.ingest_interaction(
            user_input="Android query",
            thought_stream="Android thought",
            final_response="Android speech",
            source_device="android",
            influence_weight=0.35
        )
        self.vault.archive_insight(
            insight="Synthesized wisdom",
            concept_family="philosophy",
            importance_weight=1.5,
            dominance_weight=0.8
        )

        pc_only = self.vault.get_recent_interactions(limit=10, source_device="pc")
        self.assertEqual(len(pc_only), 1)
        self.assertEqual(pc_only[0]["source_device"], "pc")
        self.assertEqual(pc_only[0]["influence_weight"], 1.0)

        android_only = self.vault.get_recent_interactions(limit=10, source_device="android")
        self.assertEqual(len(android_only), 1)
        self.assertEqual(android_only[0]["source_device"], "android")
        self.assertEqual(android_only[0]["influence_weight"], 0.35)

        insights = self.vault.get_distilled_insights(limit=10)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["concept_family"], "philosophy")
        self.assertEqual(insights[0]["importance_weight"], 1.5)


if __name__ == "__main__":
    unittest.main()
