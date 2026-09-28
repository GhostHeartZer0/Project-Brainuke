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

if __name__ == '__main__':
    unittest.main()
