# tests/test_volition_salience.py
import unittest
import math
from brainuke_core.affect.engine import BrainukeCore
from brainuke_core.affect.state import AffectState


class TestVolitionSalience(unittest.TestCase):
    def setUp(self):
        # Cecilia baseline: V: 0.2, A: 0.0, D: 0.8
        self.core = BrainukeCore(baseline_mu={'v': 0.2, 'a': 0.0, 'd': 0.8})

    def test_loud_vs_vital_decay(self):
        """Validates that Loud events decay rapidly while Vital events persist."""
        # 1. Loud Event: High Arousal (A=0.8), Low Memory Resonance (M=0.05)
        self.core.state = AffectState(valence=0.2, arousal=0.8, dominance=0.8)
        loud_initial = self.core.calculate_volition_salience(
            memory_resonance=0.05,
            dt_since_event=0.0
        )
        loud_after_30s = self.core.calculate_volition_salience(
            memory_resonance=0.05,
            dt_since_event=30.0
        )

        self.assertTrue(loud_initial["is_loud"])
        self.assertFalse(loud_initial["is_vital"])
        self.assertGreater(loud_initial["effective_decay_rate"], 0.05)
        # Fast decay: after 30s should have decayed significantly
        self.assertLess(loud_after_30s["salience_score"], loud_initial["salience_score"] * 0.1)

        # 2. Vital Event: Low Arousal (A=0.0), High Memory Resonance (M=0.9)
        self.core.state = AffectState(valence=0.2, arousal=0.0, dominance=0.8)
        vital_initial = self.core.calculate_volition_salience(
            memory_resonance=0.9,
            dt_since_event=0.0
        )
        vital_after_30s = self.core.calculate_volition_salience(
            memory_resonance=0.9,
            dt_since_event=30.0
        )

        self.assertFalse(vital_initial["is_loud"])
        self.assertTrue(vital_initial["is_vital"])
        # Near zero decay rate:
        self.assertAlmostEqual(vital_initial["effective_decay_rate"], 0.001, places=3)
        # After 30s, virtually unchanged (~97% retained)
        self.assertGreater(vital_after_30s["salience_score"], vital_initial["salience_score"] * 0.95)

    def test_thematic_equilibrium_threat(self):
        """Validates that threat to thematic equilibrium (Valence/Dominance shift) drives salience."""
        # Perturb dominance and valence: user challenges Cecilia's core boundaries
        self.core.state = AffectState(valence=-0.4, arousal=0.2, dominance=0.3)
        threat_result = self.core.calculate_volition_salience(
            memory_resonance=0.7,
            dt_since_event=0.0
        )

        self.assertGreater(threat_result["thematic_threat"], 0.5)
        self.assertTrue(threat_result["salience_score"] >= 0.85)
        self.assertTrue(self.core.should_trigger_volition(memory_resonance=0.7, threshold=0.85))

    def test_shouting_without_substance_rejected(self):
        """Validates that pure emotional shouting (high A) without memory depth fails volition threshold."""
        # Only arousal is high; valence and dominance are perfectly at baseline equilibrium
        self.core.state = AffectState(valence=0.2, arousal=0.7, dominance=0.8)
        result = self.core.calculate_volition_salience(
            memory_resonance=0.0,
            sensory_delta=0.0,
            dt_since_event=0.0
        )

        # Shouting without substance must not cross the 0.85 threshold
        self.assertFalse(self.core.should_trigger_volition(memory_resonance=0.0, threshold=0.85))
        self.assertLess(result["salience_score"], 0.85)


if __name__ == "__main__":
    unittest.main()
