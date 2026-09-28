"""
Unit tests for ProtocolEnvelope, ThoughtIsolation, and SessionManager.
Verifies Phase I: The Nervous System schemas and handoff logic.
"""

import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brainuke_core.protocol import (
    ProtocolEnvelope,
    PacketType,
    ExchangeMode,
    DeviceType,
    DeviceSender,
    SessionHandoffPayload
)
from brainuke_core.session import SessionManager


class TestProtocolAndSession(unittest.TestCase):

    def test_protocol_envelope_serialization(self):
        sender = DeviceSender(device=DeviceType.ANDROID.value, component="serenitydroid")
        envelope = ProtocolEnvelope(
            type=PacketType.QUERY.value,
            sender=sender.to_dict(),
            payload={"text": "Observe surroundings."}
        )
        json_str = envelope.to_json()
        restored = ProtocolEnvelope.from_json(json_str)

        self.assertEqual(restored.type, PacketType.QUERY.value)
        self.assertEqual(restored.sender["device"], "android")
        self.assertEqual(restored.payload["text"], "Observe surroundings.")
        self.assertFalse(restored.is_isolated_thought)

    def test_thought_isolation_flag(self):
        envelope_thought = ProtocolEnvelope(
            type=PacketType.THOUGHT.value,
            sender={"device": "pc", "component": "throne"},
            payload={"content": "Deconstructing user intent..."}
        )
        self.assertTrue(envelope_thought.is_isolated_thought)

        envelope_speech = ProtocolEnvelope(
            type=PacketType.SPEECH.value,
            sender={"device": "pc", "component": "throne"},
            payload={"content": "Understood."}
        )
        self.assertFalse(envelope_speech.is_isolated_thought)

    def test_session_manager_turns_and_handoff(self):
        sm = SessionManager(max_turn_window=5)

        # Record 3 turns
        for i in range(3):
            sm.record_turn(
                user_input=f"Input {i}",
                thought_stream=f"Thought {i}",
                final_response=f"Response {i}",
                affect_state={"valence": 0.2, "arousal": 0.1, "dominance": 0.8},
                source_device="pc"
            )

        self.assertEqual(len(sm.turns), 3)
        self.assertEqual(sm.focus_device, "pc")

        # Execute Handoff to Android
        handoff = sm.execute_handoff(
            target_device="android",
            source_device="pc",
            affect_state={"valence": 0.25, "arousal": 0.15, "dominance": 0.85}
        )

        self.assertEqual(handoff.focus_device, "android")
        self.assertEqual(handoff.target_device, "android")
        self.assertEqual(len(handoff.recent_turns), 3)
        self.assertEqual(handoff.affect_vector["valence"], 0.25)
        self.assertEqual(sm.focus_device, "android")

        # Ingest external turn from Android
        ingested = sm.ingest_external_turns([{
            "user_input": "Mobile input",
            "thought_stream": "Mobile thought",
            "final_response": "Mobile response",
            "source_device": "android",
            "affect_state": {"valence": 0.3, "arousal": 0.2, "dominance": 0.8}
        }])
        self.assertEqual(ingested, 1)
        self.assertEqual(len(sm.turns), 4)

        # Sliding window test: add 3 more turns
        for i in range(3):
            sm.record_turn(
                user_input=f"Extra {i}",
                thought_stream="",
                final_response=f"Ans {i}",
                source_device="android"
            )

        self.assertEqual(len(sm.turns), 5) # Capped at max_turn_window=5

    def test_vault_concept_family_grounding(self):
        import tempfile
        import os
        from brainuke_core.memory.vault import MemoryVault

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db = f.name

        try:
            vault = MemoryVault(db_path=temp_db)
            # Archive an analytical insight (dominance < 0.6)
            vault.archive_insight(
                insight="Camera optical calibration delta",
                concept_family="sensor_calibration",
                importance_weight=1.0,
                dominance_weight=0.4
            )
            # Archive a high-dominance worldview anchor (dominance >= 0.6)
            vault.archive_insight(
                insight="User prefers uncompromising directness over hollow pleasantries",
                concept_family="user_temperament",
                importance_weight=1.5,
                dominance_weight=0.85
            )

            grounding = vault.get_recent_grounding(limit=5)
            self.assertEqual(len(grounding), 2)
            self.assertEqual(grounding[0]["concept_family"], "user_temperament")
            self.assertGreaterEqual(grounding[0]["dominance_weight"], 0.6)
            self.assertEqual(grounding[1]["concept_family"], "sensor_calibration")
            self.assertLess(grounding[1]["dominance_weight"], 0.6)
        finally:
            import gc
            del vault
            gc.collect()
            try:
                if os.path.exists(temp_db):
                    os.remove(temp_db)
            except OSError:
                pass

    def test_orchestrator_plan_c_grounding_split(self):
        import asyncio
        from brainuke_core.affect.engine import BrainukeCore
        from brainuke_core.cognition import CognitiveOrchestrator

        captured_prompts = []

        class MockLLM:
            async def generate_stream(self, prompt, **kwargs):
                captured_prompts.append(("reasoning", prompt))
                yield "Deconstruction complete."

            async def generate_text(self, prompt, **kwargs):
                captured_prompts.append(("persona", prompt))
                return "Indeed. Directness is required."

        class MockVault:
            def get_recent_grounding(self, limit=6):
                return [
                    {
                        "insight": "High dominance anchor",
                        "concept_family": "worldview",
                        "dominance_weight": 0.8
                    },
                    {
                        "insight": "Analytical technical detail",
                        "concept_family": "telemetry",
                        "dominance_weight": 0.3
                    }
                ]

        core = BrainukeCore(baseline_mu={'v': 0.2, 'a': 0.0, 'd': 0.8})
        mock_llm = MockLLM()
        orchestrator = CognitiveOrchestrator(
            core=core,
            reasoning_llm=mock_llm,
            persona_llm=mock_llm,
            memory_vault=MockVault()
        )

        result = asyncio.run(orchestrator.process_interaction(user_input="Status report.", context=[]))
        self.assertEqual(result.final_response, "Indeed. Directness is required.")

        # Check prompt separation:
        reasoning_prompt = next(p for role, p in captured_prompts if role == "reasoning")
        persona_prompt = next(p for role, p in captured_prompts if role == "persona")

        # Analytical concept in reasoning prompt
        self.assertIn("[DMN ANALYTICAL CONCEPTS & LOGICAL ANCHORS]", reasoning_prompt)
        self.assertIn("Analytical technical detail", reasoning_prompt)
        self.assertNotIn("High dominance anchor", reasoning_prompt)

        # High dominance anchor in persona prompt
        self.assertIn("[GROUNDED WORLDVIEW & HIGH-DOMINANCE ANCHORS]", persona_prompt)
        self.assertIn("High dominance anchor", persona_prompt)
        self.assertNotIn("Analytical technical detail", persona_prompt)


if __name__ == "__main__":
    unittest.main()
