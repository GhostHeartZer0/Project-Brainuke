from dataclasses import dataclass

@dataclass
class AffectState:
    """Represents the 3D Continuous Affect Space (V, A, D)."""
    valence: float = 0.0     # Pleasure/Displeasure [-1.0, 1.0]
    arousal: float = 0.0     # Excitement/Calm [-1.0, 1.0]
    dominance: float = 0.0    # Power/Complexity [-1.0, 1.0]

@dataclass
class BrainukeParameters:
    """The modulations injected into the LLM sampling."""
    temperature: float
    min_p: float
    tone_descriptor: str