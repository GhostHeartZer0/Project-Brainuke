"""
brainuke_core/session/state.py
State Management & Zero-Amnesia Session Handoff Manager.
Maintains active dialogue window, device focus, and cross-platform continuity.
"""

import time
import uuid
from typing import Dict, Any, List, Optional
from brainuke_core.protocol.schema import SessionHandoffPayload, DeviceType


class SessionManager:
    def __init__(self, max_turn_window: int = 20):
        self.session_id: str = str(uuid.uuid4())
        self.focus_device: str = DeviceType.PC.value
        self.max_turn_window = max_turn_window
        self.turns: List[Dict[str, Any]] = []
        self.last_activity: int = int(time.time() * 1000)

    def record_turn(
        self,
        user_input: str,
        thought_stream: str,
        final_response: str,
        affect_state: Optional[Dict[str, float]] = None,
        source_device: str = "pc"
    ) -> Dict[str, Any]:
        """Appends a dialogue turn to the active session sliding window."""
        turn = {
            "turn_id": len(self.turns) + 1,
            "source_device": source_device,
            "user_input": user_input,
            "thought_stream": thought_stream,
            "final_response": final_response,
            "affect_state": affect_state or {},
            "timestamp": int(time.time() * 1000)
        }
        self.turns.append(turn)
        if len(self.turns) > self.max_turn_window:
            self.turns = self.turns[-self.max_turn_window:]
        self.last_activity = turn["timestamp"]
        return turn

    def execute_handoff(self, target_device: str, source_device: str, affect_state: Optional[Dict[str, float]] = None) -> SessionHandoffPayload:
        """Transfers active conversational focus to target device."""
        self.focus_device = target_device
        self.last_activity = int(time.time() * 1000)
        return SessionHandoffPayload(
            session_id=self.session_id,
            source_device=source_device,
            target_device=target_device,
            focus_device=self.focus_device,
            recent_turns=list(self.turns),
            affect_vector=affect_state or {},
            timestamp=self.last_activity
        )

    def get_active_session(self, affect_state: Optional[Dict[str, float]] = None) -> SessionHandoffPayload:
        """Returns the full active session snapshot for zero-amnesia resume."""
        return SessionHandoffPayload(
            session_id=self.session_id,
            source_device=self.focus_device,
            target_device=self.focus_device,
            focus_device=self.focus_device,
            recent_turns=list(self.turns),
            affect_vector=affect_state or {},
            timestamp=self.last_activity
        )

    def ingest_external_turns(self, turns: List[Dict[str, Any]]) -> int:
        """Merges turns arriving from Android or external clients."""
        ingested = 0
        for t in turns:
            turn_entry = {
                "turn_id": len(self.turns) + 1,
                "source_device": t.get("source_device", "android"),
                "user_input": t.get("user_input", ""),
                "thought_stream": t.get("thought_stream", ""),
                "final_response": t.get("final_response", ""),
                "affect_state": t.get("affect_state", {}),
                "timestamp": t.get("timestamp", int(time.time() * 1000))
            }
            self.turns.append(turn_entry)
            ingested += 1

        if len(self.turns) > self.max_turn_window:
            self.turns = self.turns[-self.max_turn_window:]
        self.last_activity = int(time.time() * 1000)
        return ingested
