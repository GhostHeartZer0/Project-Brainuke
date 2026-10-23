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
from brainuke_throne.server.main import (
    sync_status_endpoint, sync_trigger, sync_simmer, get_history_feed,
    stop_model_endpoint, last_sync_info, simmer_bus, pc_runner_manager,
    sync_push, sync_pull
)
import brainuke_throne.server.main as main_server
from unittest.mock import AsyncMock


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

    def _make_mock_request(self, body=None, query_params=None):
        req = MagicMock()
        req.headers = {"Authorization": f"Bearer {self.token}"}
        req.query_params = query_params or {}
        if body is not None:
            req.json = AsyncMock(return_value=body)
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

    async def test_stop_model_endpoint(self):
        req = self._make_mock_request()
        orig_managed = pc_runner_manager._managed_process
        mock_proc = MagicMock()
        mock_proc.pid = 8888
        mock_proc.poll.return_value = None
        pc_runner_manager._managed_process = mock_proc
        try:
            res = await stop_model_endpoint(req)
            self.assertEqual(res["status"], "stopped")
            self.assertEqual(res["pid"], 8888)
            mock_proc.terminate.assert_called_once()
        finally:
            pc_runner_manager._managed_process = orig_managed

    def test_turn_uuid_deduplication(self):
        """Ensures identical turn_uuid calls are deduplicated and idempotent."""
        id1 = self.vault.ingest_interaction(
            user_input="Test input",
            thought_stream="Test thought",
            final_response="Test response",
            source_device="android",
            turn_uuid="unique-turn-uuid-001"
        )
        id2 = self.vault.ingest_interaction(
            user_input="Test input duplicate",
            thought_stream="Test thought duplicate",
            final_response="Test response duplicate",
            source_device="android",
            turn_uuid="unique-turn-uuid-001"
        )
        self.assertEqual(id1, id2)
        interactions = self.vault.get_recent_interactions(limit=10)
        self.assertEqual(len(interactions), 1)
        self.assertEqual(interactions[0]["user_input"], "Test input")

    def test_get_delta_pack_symmetric_pc_turns(self):
        """Ensures get_delta_pack symmetrically returns PC turns and distilled insights."""
        self.vault.ingest_interaction(
            user_input="Hello from PC",
            thought_stream="Thinking on PC",
            final_response="Response from PC",
            source_device="pc",
            turn_uuid="pc-turn-001"
        )
        self.vault.ingest_interaction(
            user_input="Hello from Mobile",
            thought_stream="Thinking on Mobile",
            final_response="Response from Mobile",
            source_device="android",
            turn_uuid="android-turn-001"
        )
        self.vault.archive_insight(insight="Consolidated DMN worldview test.")

        delta = self.vault.get_delta_pack(since_timestamp=0)
        self.assertEqual(len(delta["insights"]), 1)
        self.assertEqual(delta["insights"][0]["insight"], "Consolidated DMN worldview test.")

        # Symmetric pull: only PC turns returned to mobile
        self.assertEqual(len(delta["pc_turns"]), 1)
        self.assertEqual(delta["pc_turns"][0]["source_device"], "pc")
        self.assertEqual(delta["pc_turns"][0]["user_input"], "Hello from PC")
        self.assertEqual(delta["pc_turns"][0]["turn_uuid"], "pc-turn-001")

        # High-water mark query: since_turn_id suppresses previously synced turns
        max_turn_id = delta["max_turn_id"]
        next_delta = self.vault.get_delta_pack(since_turn_id=max_turn_id)
        self.assertEqual(len(next_delta["pc_turns"]), 0)

    async def test_sync_push_endpoint_validation(self):
        """Validates /api/v1/sync/push endpoint ingests telemetry & turns with deduplication."""
        orig_vault = main_server.memory_vault
        main_server.memory_vault = self.vault
        try:
            body = {
                "sync_id": "test_sync_001",
                "items": [
                    {"type": "telemetry", "battery": 85, "timestamp": 1000}
                ],
                "conversation_turns": [
                    {
                        "turn_uuid": "mobile-turn-abc",
                        "user_input": "Mobile prompt",
                        "thought_stream": "Mobile thinking",
                        "final_response": "Mobile reply",
                        "affect_state": {"v": 0.5, "a": 0.2, "d": 0.7}
                    }
                ]
            }
            req = self._make_mock_request(body=body)
            res = await sync_push(req)
            self.assertEqual(res["status"], "queued")
            self.assertEqual(res["count"], 1)
            self.assertEqual(res["conversation_count"], 1)

            # Verify in vault
            turns = self.vault.get_recent_interactions(limit=10)
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0]["turn_uuid"], "mobile-turn-abc")
            self.assertEqual(turns[0]["source_device"], "android")
            self.assertEqual(turns[0]["influence_weight"], 0.35)

            # Re-pushing identical turn_uuid must be deduplicated
            res_dup = await sync_push(req)
            self.assertEqual(res_dup["status"], "queued")
            turns_after = self.vault.get_recent_interactions(limit=10)
            self.assertEqual(len(turns_after), 1)
        finally:
            main_server.memory_vault = orig_vault

    async def test_sync_pull_endpoint_validation(self):
        """Validates /api/v1/sync/pull endpoint returns symmetric PC turns & DMN insights."""
        orig_vault = main_server.memory_vault
        main_server.memory_vault = self.vault
        try:
            self.vault.ingest_interaction(
                user_input="PC query",
                thought_stream="PC thoughts",
                final_response="PC speech",
                source_device="pc",
                turn_uuid="pc-uuid-101"
            )
            self.vault.ingest_interaction(
                user_input="Mobile query",
                thought_stream="Mobile thoughts",
                final_response="Mobile speech",
                source_device="android",
                turn_uuid="mobile-uuid-101"
            )
            self.vault.archive_insight(
                insight="Unified cognitive anchor.",
                concept_family="core_telemetry"
            )

            req = self._make_mock_request()
            res = await sync_pull(req, since=0, since_insight_id=0, since_turn_id=0)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(len(res["insights"]), 1)
            self.assertEqual(res["insights"][0]["insight"], "Unified cognitive anchor.")

            # Symmetrical: only PC turns sent down to mobile
            self.assertEqual(len(res["pc_turns"]), 1)
            self.assertEqual(res["pc_turns"][0]["source_device"], "pc")
            self.assertEqual(res["pc_turns"][0]["turn_uuid"], "pc-uuid-101")

            # High-water mark suppresses re-pull
            next_req = self._make_mock_request(query_params={
                "since_turn_id": str(res["max_turn_id"]),
                "since_insight_id": str(res["max_insight_id"])
            })
            res_next = await sync_pull(next_req)
            self.assertEqual(len(res_next["pc_turns"]), 0)
            self.assertEqual(len(res_next["insights"]), 0)
        finally:
            main_server.memory_vault = orig_vault

    async def test_sync_full_four_step_cycle_e2e(self):
        """Validates end-to-end 4-step sync cycle: Push -> Simmer -> Pull -> Status."""
        orig_vault = main_server.memory_vault
        main_server.memory_vault = self.vault
        try:
            # 1. Step 1: Android pushes unsynced conversation turn
            push_body = {
                "sync_id": "e2e_sync_test",
                "items": [{"type": "battery", "level": 90}],
                "conversation_turns": [
                    {
                        "turn_uuid": "e2e-turn-001",
                        "user_input": "User on Android",
                        "thought_stream": "Reflex processing",
                        "final_response": "Reflex reply"
                    }
                ]
            }
            push_req = self._make_mock_request(body=push_body)
            push_res = await sync_push(push_req)
            self.assertEqual(push_res["status"], "queued")

            # 2. Step 2: PC Throne registers a local turn
            self.vault.ingest_interaction(
                user_input="User on PC Throne",
                thought_stream="Throne cognitive deliberation",
                final_response="Throne authoritative reply",
                source_device="pc",
                turn_uuid="e2e-turn-002"
            )

            # 3. Step 3: DMN Simmer consolidates memory pool
            self.vault.archive_insight(
                insight="Consolidated dual-device coherence.",
                concept_family="synthesis"
            )

            # 4. Step 4: Android pulls delta pack
            pull_req = self._make_mock_request()
            pull_res = await sync_pull(pull_req, since_turn_id=0, since_insight_id=0)
            self.assertEqual(pull_res["status"], "ok")
            self.assertTrue(any(i["insight"] == "Consolidated dual-device coherence." for i in pull_res["insights"]))
            self.assertTrue(any(t["turn_uuid"] == "e2e-turn-002" for t in pull_res["pc_turns"]))
            # Android's own turn must NOT be sent back to Android
            self.assertFalse(any(t["turn_uuid"] == "e2e-turn-001" for t in pull_res["pc_turns"]))

            # Verify status reflects active sync
            status_req = self._make_mock_request()
            status_res = await sync_status_endpoint(status_req)
            self.assertEqual(status_res["status"], "ok")
            self.assertIn("last_sync", status_res)
        finally:
            main_server.memory_vault = orig_vault

    async def test_simmer_bus_volition_trigger_dispatch(self):
        """Validates that SimmerBus dispatches volition_trigger status event on high salience."""
        from brainuke_core.cognition.simmer_bus import SimmerBus
        from brainuke_core.affect.engine import BrainukeCore

        dispatched_events = []
        async def mock_status_fn(event_type: str, data: dict):
            dispatched_events.append((event_type, data))

        core = BrainukeCore(baseline_mu={'v': 0.2, 'a': 0.0, 'd': 0.8})
        # Set core in state that generates salience >= 0.85 (perturbation in dominance)
        core.state.dominance = -0.5
        mock_cook = MagicMock()
        mock_cook._distill_history = AsyncMock(return_value="High importance thematic insight.")

        # Seed unsimmered interaction
        self.vault.ingest_interaction(
            user_input="Core query",
            thought_stream="Core thinking",
            final_response="Core speech",
            source_device="pc"
        )

        bus = SimmerBus(
            vault=self.vault,
            core=core,
            deep_cook=mock_cook,
            broadcast_fn=AsyncMock(),
            status_fn=mock_status_fn
        )

        res = await bus.trigger_simmer_cycle(forced=True)
        self.assertIsNotNone(res)
        self.assertIn("salience_data", res)
        # Verify volition_trigger event was dispatched
        volition_events = [e for e in dispatched_events if e[0] == "volition_trigger"]
        self.assertEqual(len(volition_events), 1)
        v_data = volition_events[0][1]
        self.assertGreaterEqual(v_data["salience"], 0.85)
        self.assertIn("proactive_prompt", v_data)
        self.assertIn("thematic insight", v_data["insight"])


if __name__ == "__main__":
    unittest.main()


