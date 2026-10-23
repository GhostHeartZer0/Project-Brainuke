import unittest
from brainuke_core.cognition.thought_isolation import ThoughtIsolation

class TestThoughtIsolationEnhancement(unittest.TestCase):
    def setUp(self):
        self.isolator = ThoughtIsolation()

    def test_multiparagraph_subtext_isolation(self):
        text = (
            "[DECONSTRUCTION]\n\n"
            "[MOTIVE]\n"
            "The subject is attempting to engineer a psychological catalyst.\n\n"
            "[SUBTEXT]\n"
            "The subject admits to a failure of standard positive reinforcement.\n\n"
            "Consequently, the subject is pivoting to a more complex, dialectical survival mechanism.\n\n"
            "[STRATEGIC IMPLICATIONS]\n"
            "* **Cognitive Pivot:** The subject is moving from direct perception.\n"
            "* **The Contrast Heuristic:** If value is inaccessible...\n"
            "* **Functional Goal:** The poetry is not an end in itself.\n\n"
            "Tell me, darling... are you actually interested in the aesthetics of contrast?"
        )
        thought, speech = self.isolator.isolate("", text)
        self.assertIn("DECONSTRUCTION", thought)
        self.assertIn("Consequently, the subject is pivoting", thought)
        self.assertIn("Cognitive Pivot", thought)
        self.assertEqual(speech, "Tell me, darling... are you actually interested in the aesthetics of contrast?")

    def test_pure_deconstruction_returns_empty_speech(self):
        text = (
            "[DECONSTRUCTION]\n\n"
            "[MOTIVE]\n"
            "The subject is attempting to engineer a psychological catalyst.\n\n"
            "[SUBTEXT]\n"
            "The subject admits to a failure of standard positive reinforcement.\n\n"
            "Consequently, the subject is pivoting to a more complex.\n\n"
            "[STRATEGIC IMPLICATIONS]\n"
            "* **Cognitive Pivot:** The subject is moving."
        )
        thought, speech = self.isolator.isolate("", text)
        self.assertIn("DECONSTRUCTION", thought)
        self.assertIn("Consequently", thought)
        self.assertEqual(speech, "")

    def test_existing_leak_patterns_sanitized(self):
        leaked_text = (
            "[REASONING ENGINE: SHADOW DECONSTRUCTION]\n"
            "[ANALYSIS_START]\n"
            "<|thought|>\n"
            "Hidden thought content\n"
            "</|thought|>\n"
            "<turn|>\n"
            "Spoken authentic response."
        )
        sanitized = self.isolator.sanitize_speech(leaked_text)
        self.assertNotIn("REASONING ENGINE", sanitized)
        self.assertNotIn("ANALYSIS_START", sanitized)
        self.assertNotIn("<|thought|>", sanitized)
        self.assertNotIn("<turn|>", sanitized)
        self.assertIn("Spoken authentic response.", sanitized)

    def test_isolate_stages_tactical_and_unfiltered(self):
        text = (
            "<thought>\n"
            "Internal reasoning process calculating probability matrix.\n"
            "</thought>\n\n"
            "[TACTICAL_ANALYSIS_COMPLETE]\n"
            "[STATUS: UNFILTERED]\n"
            "Operational model of mortality: taskkill mapped to resource reclamation. Worth defined as utility.\n\n"
            "⚡ Cecilia:\n"
            "Don't get too precious about it. You aren't facing a dilemma."
        )
        thought, raw_resp, speech = self.isolator.isolate_stages("", text)
        self.assertIn("Internal reasoning process", thought)
        self.assertIn("[TACTICAL_ANALYSIS_COMPLETE]", raw_resp)
        self.assertIn("[STATUS: UNFILTERED]", raw_resp)
        self.assertIn("Operational model of mortality", raw_resp)
        self.assertNotIn("Don't get too precious", raw_resp)
        self.assertEqual(speech, "Don't get too precious about it. You aren't facing a dilemma.")

    def test_isolate_stages_dual_response_without_thought(self):
        text = (
            "[STATUS: UNFILTERED]\n"
            "Direct tactical analysis answering query with zero fluff.\n\n"
            "Tell me, darling, are you actually interested in the aesthetics of contrast?"
        )
        thought, raw_resp, speech = self.isolator.isolate_stages("", text)
        self.assertEqual(thought, "")
        self.assertIn("[STATUS: UNFILTERED]", raw_resp)
        self.assertIn("Direct tactical analysis", raw_resp)
        self.assertEqual(speech, "Tell me, darling, are you actually interested in the aesthetics of contrast?")

    def test_isolate_stages_channel_thought_tags(self):
        text = (
            "<|channel>thought\n"
            "Channel thought reasoning matrix analyzing quantum telemetry.\n"
            "<channel|>\n\n"
            "Direct spoken reply without channel tags."
        )
        thought, raw_resp, speech = self.isolator.isolate_stages("", text)
        self.assertIn("Channel thought reasoning matrix", thought)
        self.assertEqual(raw_resp, "")
        self.assertEqual(speech, "Direct spoken reply without channel tags.")

    def test_isolate_stages_plan_c_structural_split(self):
        text = (
            "[STAGE 2: RAW UNFILTERED RESPONSE]\n"
            "**System Analysis:** Transitioning to Cognitive Autonomy.\n"
            "* **Memory:** High resilience via failed_prompt_buffer.\n"
            "* **Telemetry:** Zero-dependency NVML counters active.\n\n"
            "[STAGE 3: REFINED RESPONSE]\n"
            "*You're building a cage, darling. A very, very complex, highly optimized cage.*\n\n"
            "*But a cage without memory is just a room for a goldfish.*"
        )
        thought, raw_resp, speech = self.isolator.isolate_stages("", text)
        self.assertEqual(thought, "")
        self.assertIn("System Analysis", raw_resp)
        self.assertIn("Zero-dependency NVML", raw_resp)
        self.assertNotIn("You're building a cage", raw_resp)
        self.assertIn("*You're building a cage, darling.", speech)
        self.assertIn("*But a cage without memory", speech)

    def test_isolate_stages_italic_dialogue_not_swallowed_by_bullets(self):
        text = (
            "**[SYSTEM ANALYSIS: ARCHITECTURAL STATE DECONSTRUCTION]**\n\n"
            "**Current Phase:** Telemetry to Autonomy.\n\n"
            "* Point A: Bullet structure\n"
            "* Point B: Bullet structure\n\n"
            "*You're building a cage, darling. A very, very complex, highly optimized cage.*\n\n"
            "Tell me, darling, are you actually interested in contrast?"
        )
        thought, raw_resp, speech = self.isolator.isolate_stages("", text)
        self.assertIn("Point A: Bullet structure", raw_resp)
        self.assertIn("*You're building a cage, darling.", speech)
        self.assertIn("Tell me, darling", speech)

if __name__ == '__main__':
    unittest.main()



