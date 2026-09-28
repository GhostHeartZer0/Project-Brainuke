"""Tests for Desktop Native Cecilia-UI History Tab and DMN Feed."""
import os
import sys
import unittest
import tkinter as tk
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brainuke_throne.ui_desktop.cecilia_ui import CeciliaThroneDesktopApp


class TestUIHistoryTab(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw() # Hide window during test
        self.app = CeciliaThroneDesktopApp(self.root)

    def tearDown(self):
        self.app.close()

    def test_tab_switching(self):
        self.assertEqual(self.app.active_tab, "stage")
        # Switch to history
        self.app._switch_tab("history")
        self.assertEqual(self.app.active_tab, "history")
        # Switch back to stage
        self.app._switch_tab("stage")
        self.assertEqual(self.app.active_tab, "stage")

    def test_render_history_feed(self):
        sample_data = {
            "status": "ok",
            "interactions": [
                {
                    "user_input": "Hello PC",
                    "thought_stream": "PC Reasoning",
                    "final_response": "PC Speech",
                    "source_device": "pc",
                    "influence_weight": 1.0,
                    "timestamp": 1727390000000
                },
                {
                    "user_input": "Hello Android",
                    "thought_stream": "Mobile Reasoning",
                    "final_response": "Mobile Speech",
                    "source_device": "android",
                    "influence_weight": 0.35,
                    "timestamp": 1727390001000
                }
            ],
            "dmn_insights": [
                {
                    "insight": "DMN Refined Reality Insight",
                    "concept_family": "worldview",
                    "importance_weight": 1.4,
                    "dominance_weight": 0.7,
                    "world_delta": {"consolidated_nodes": 4},
                    "emotional_shift": {"valence_delta": 0.05},
                    "timestamp": 1727390002000
                }
            ]
        }

        self.app._render_history_feed(sample_data)
        content = self.app.hist_text.get("1.0", tk.END)

        # Verify PC Core Master weight 1.0 tag
        self.assertIn("PC CORE MASTER • WEIGHT 1.0", content)
        # Verify Android Companion weight 0.35 tag
        self.assertIn("ANDROID COMPANION • WEIGHT 0.35", content)
        # Verify DMN Refined Insight
        self.assertIn("DMN REFINED INSIGHT", content)
        self.assertIn("DMN Refined Reality Insight", content)
        self.assertIn("#WORLDVIEW", content)


if __name__ == "__main__":
    unittest.main()
