"""
brainuke_core/protocol/schema.py
The Unified Intelligence Exchange Protocol schema for Project Brainuke.
Defines communication envelopes between PC Throne and SerenityDroid.
"""

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional


class PacketType(str, Enum):
    HANDSHAKE = "handshake"
    SENSORY = "sensory"
    QUERY = "query"
    THOUGHT = "thought"
    SPEECH = "speech"
    HEARTBEAT = "heartbeat"
    HANDOFF = "handoff"
    STATE_SYNC = "state_sync"
    DMN_INSIGHT = "dmn_insight"


class ExchangeMode(str, Enum):
    DIRECT_TRANSFER = "direct_transfer"
    AGENT_DISCUSSION = "agent_discussion"


class DeviceType(str, Enum):
    PC = "pc"
    ANDROID = "android"
    UNKNOWN = "unknown"


@dataclass
class DeviceSender:
    device: str
    component: str

    def to_dict(self) -> Dict[str, str]:
        return {"device": self.device, "component": self.component}


@dataclass
class ProtocolEnvelope:
    type: str
    sender: Dict[str, str]
    payload: Dict[str, Any]
    version: str = "1.0"
    packet_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    mode: str = ExchangeMode.DIRECT_TRANSFER.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "packet_id": self.packet_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "sender": self.sender,
            "mode": self.mode,
            "payload": self.payload
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtocolEnvelope":
        if "type" not in data or "sender" not in data or "payload" not in data:
            raise ValueError("Malformed packet envelope: missing type, sender, or payload")
        return cls(
            version=data.get("version", "1.0"),
            packet_id=data.get("packet_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", int(time.time() * 1000)),
            type=data["type"],
            sender=data["sender"],
            mode=data.get("mode", ExchangeMode.DIRECT_TRANSFER.value),
            payload=data["payload"]
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ProtocolEnvelope":
        return cls.from_dict(json.loads(json_str))

    @property
    def is_isolated_thought(self) -> bool:
        """Enforces thought isolation: thoughts must never be routed to speech bubbles."""
        return self.type in (PacketType.THOUGHT.value, PacketType.DMN_INSIGHT.value)


@dataclass
class SessionHandoffPayload:
    session_id: str
    source_device: str
    target_device: str
    focus_device: str
    recent_turns: List[Dict[str, Any]]
    affect_vector: Dict[str, float]
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
