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

    def test_stage_drawer_flow_and_dual_line_titles(self):
        comp = self.app._build_stage_drawer_component(
            parent_widget=self.app.chat_text,
            thought="Deep internal thoughts",
            raw_response="Unfiltered tactical response",
            speech="Refined authentic speech",
            is_streaming=False
        )

        slaves = comp.pack_slaves()
        self.assertGreaterEqual(len(slaves), 2)
        btn_bar = slaves[0]

        # 1. Left-to-right button flow: Stage 1 Thoughts -> Stage 2 Raw Response -> Stage 3 Refined Response
        btn_slaves = btn_bar.pack_slaves()
        self.assertEqual(len(btn_slaves), 3)
        btn_thought, btn_raw, btn_speech = btn_slaves[0], btn_slaves[1], btn_slaves[2]

        # Verify dual-line titles
        self.assertEqual(btn_thought.cget("text"), "▶ Stage 1\nThoughts")
        self.assertEqual(btn_raw.cget("text"), "▶ Stage 2\nRaw Response")
        self.assertEqual(btn_speech.cget("text"), "▼ Stage 3\nRefined Response")

        # 2. Top-to-bottom text flow:
        # Initially only speech is open
        content_slaves = [s for s in comp.pack_slaves() if s != btn_bar]
        self.assertEqual(len(content_slaves), 1)

        # Toggle thoughts open
        btn_thought.invoke()
        self.assertEqual(btn_thought.cget("text"), "▼ Stage 1\nThoughts")
        content_slaves = [s for s in comp.pack_slaves() if s != btn_bar]
        self.assertEqual(len(content_slaves), 2)
        # Thought is on top, speech is below
        self.assertIn("Deep internal thoughts", str(content_slaves[0].winfo_children()[0].cget("text")))

        # Toggle raw response open
        btn_raw.invoke()
        self.assertEqual(btn_raw.cget("text"), "▼ Stage 2\nRaw Response")
        content_slaves = [s for s in comp.pack_slaves() if s != btn_bar]
        self.assertEqual(len(content_slaves), 3)

        # Strict top-to-bottom order: 0: Thought, 1: Raw Response, 2: Refined Speech
        self.assertIn("Deep internal thoughts", str(content_slaves[0].winfo_children()[0].cget("text")))
        self.assertIn("RAW UNFILTERED", str(content_slaves[1].winfo_children()[0].cget("text")))
        self.assertIn("Refined authentic speech", str(content_slaves[2].winfo_children()[0].cget("text")))

    def test_streaming_turn_flow(self):
        self.app._init_streaming_turn()
        btn_bar = self.app.streaming_btn_bar
        btn_slaves = btn_bar.pack_slaves()
        self.assertEqual(len(btn_slaves), 3)

        # Left-to-right buttons
        self.assertEqual(btn_slaves[0], self.app.streaming_btn_thought)
        self.assertEqual(btn_slaves[1], self.app.streaming_btn_raw)
        self.assertEqual(btn_slaves[2], self.app.streaming_btn_speech)

        # Dual-line button titles
        self.assertEqual(self.app.streaming_btn_thought.cget("text"), "▼ Stage 1\nThoughts")
        self.assertEqual(self.app.streaming_btn_raw.cget("text"), "▶ Stage 2\nRaw Response")
        self.assertEqual(self.app.streaming_btn_speech.cget("text"), "▶ Stage 3\nRefined Response")

        # Stream raw chunk -> auto-minimizes Stage 1, opens Stage 2
        self.app._append_raw_chunk("Raw tactical chunk")
        self.assertEqual(self.app.streaming_btn_thought.cget("text"), "▶ Stage 1\nThoughts")
        self.assertEqual(self.app.streaming_btn_raw.cget("text"), "▼ Stage 2\nRaw Response")

        # Stream speech chunk -> auto-minimizes Stage 2, opens Stage 3
        self.app._append_speech_chunk("Refined dialogue")
        self.assertEqual(self.app.streaming_btn_raw.cget("text"), "▶ Stage 2\nRaw Response")
        self.assertEqual(self.app.streaming_btn_speech.cget("text"), "▼ Stage 3\nRefined Response")

        # Toggle all open and verify top-to-bottom order
        self.app.streaming_btn_thought.invoke()
        self.app.streaming_btn_raw.invoke()
        content_slaves = [s for s in self.app.streaming_drawer_frame.pack_slaves() if s != btn_bar]
        self.assertEqual(len(content_slaves), 3)
        self.assertEqual(content_slaves[0], self.app.streaming_box_thought)
        self.assertEqual(content_slaves[1], self.app.streaming_box_raw)
        self.assertEqual(content_slaves[2], self.app.streaming_box_speech)

        # Finalize turn
        self.app._finalize_streaming_turn(final_thought="Final thought", final_speech="Final speech", final_raw="Final raw")


if __name__ == "__main__":
    unittest.main()
