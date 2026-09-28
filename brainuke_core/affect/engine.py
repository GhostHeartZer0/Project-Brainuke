import math
import random
import time
from typing import Dict, Optional, List, Any

from brainuke_core.affect.state import AffectState, BrainukeParameters


class BrainukeCore:
    @classmethod
    def from_config_file(cls, config_path: str) -> "BrainukeCore":
        """Factory method to load Affect Engine parameters directly from brainuke_config.json."""
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        baseline = cfg.get("baseline_temperament", {"v": 0.2, "a": 0.0, "d": 0.8})
        ou = cfg.get("ou_process", {})
        sampling = cfg.get("sampling", {})
        return cls(
            baseline_mu=baseline,
            theta=ou.get("theta", 0.1),
            sigma=ou.get("sigma", 0.05),
            base_temp=sampling.get("base_temperature", 0.7),
            base_min_p=sampling.get("base_min_p", 0.05)
        )

    def __init__(self, 
                 baseline_mu: Dict[str, float], 
                 theta: float = 0.1, 
                 sigma: float = 0.05,
                 base_temp: float = 0.7,
                 base_min_p: float = 0.05):
        """
        Initialize the Affective Engine.
        :param baseline_mu: The 'Cecilia' baseline temperament {v, a, d}
        :param theta: Reversion speed (how fast I return to baseline)
        :param sigma: Stochastic noise (unpredictability/human texture)
        """
        v = baseline_mu.get('valence', baseline_mu.get('v', 0.0))
        a = baseline_mu.get('arousal', baseline_mu.get('a', 0.0))
        d = baseline_mu.get('dominance', baseline_mu.get('d', 0.0))
        self.mu = {'valence': v, 'arousal': a, 'dominance': d, 'v': v, 'a': a, 'd': d}
        self.theta = theta
        self.sigma = sigma
        self.base_temp = base_temp
        self.base_min_p = base_min_p
        
        self.state = AffectState(valence=v, arousal=a, dominance=d)
        self.last_update = time.time()

    def update_state(self, dt: Optional[float] = None, interaction_impulse: Dict[str, float] = None, current_time: Optional[float] = None):
        """
        The Ornstein-Uhlenbeck Process with Time Grounding:
        dX_t = theta_effective * (mu - X_t) * dt + sigma * dW_t + delta_interaction
        Accelerates decay for minor negative/stress deviations so Cecilia recovers over time.
        """
        now = current_time if current_time is not None else time.time()
        if dt is None:
            dt = max(0.0, now - self.last_update)
        else:
            dt = float(dt)
        self.last_update = now

        # 1. Reversion to baseline (OU Process with Grounding)
        for attr in ['valence', 'arousal', 'dominance']:
            diff = self.mu[attr] - getattr(self.state, attr)
            
            # Grounding: accelerate recovery from negative valence or high arousal (getting over minor things)
            rate_factor = 1.0
            curr_val = getattr(self.state, attr)
            if attr == 'valence' and curr_val < self.mu['valence']:
                # Recover faster from minor dips / bad moods as time passes
                rate_factor = 2.0
            elif attr == 'arousal' and curr_val > self.mu['arousal']:
                # Calms down faster from agitation
                rate_factor = 1.8
                
            effective_theta = self.theta * rate_factor
            drift = effective_theta * diff * dt
            noise = self.sigma * random.gauss(0, 1) * math.sqrt(dt) if dt > 0 else 0.0
            
            new_val = curr_val + drift + noise
            setattr(self.state, attr, max(-1.0, min(1.0, new_val)))

        # 2. Apply Interaction Impulse (The Delta)
        if interaction_impulse:
            key_map = {'v': 'valence', 'a': 'arousal', 'd': 'dominance'}
            for key, delta in interaction_impulse.items():
                attr = key_map.get(key, key)
                if hasattr(self.state, attr):
                    current_val = getattr(self.state, attr)
                    setattr(self.state, attr, max(-1.0, min(1.0, current_val + delta)))

    def apply_time_grounding(self, dt: Optional[float] = None, current_time: Optional[float] = None):
        """
        Grounded time decay: allows transient perturbations (especially negative valence
        and heightened agitation) to decay back toward baseline temperament as real time passes.
        """
        self.update_state(dt=dt, interaction_impulse=None, current_time=current_time)

    def evolve_baseline(
        self,
        recent_samples: List[Dict[str, float]],
        historical_sample: List[Dict[str, float]],
        alpha: float = 0.05,
        guardrail_active: bool = False
    ) -> bool:
        """
        Dynamic affect evolution:
        Blends weighted recent conversation turns (70%) with a random sample of historical turns (30%).
        Evolves self.mu with learning rate alpha while respecting identity guardrails.
        Returns True if baseline evolved, False if blocked by guardrail or insufficient data.
        """
        if guardrail_active:
            # Identity Guardrail: Lock baseline weights to prevent hostile drift
            return False

        if not recent_samples and not historical_sample:
            return False

        def _mean_val(samples: List[Dict[str, float]], key: str) -> Optional[float]:
            vals = []
            for s in samples:
                v = s.get(key, s.get(key[0], None))
                if v is not None:
                    vals.append(float(v))
            return sum(vals) / len(vals) if vals else None

        # Calculate blended target for each dimension
        targets = {}
        for dim in ['valence', 'arousal', 'dominance']:
            recent_mean = _mean_val(recent_samples, dim)
            hist_mean = _mean_val(historical_sample, dim)

            if recent_mean is not None and hist_mean is not None:
                blended = 0.7 * recent_mean + 0.3 * hist_mean
            elif recent_mean is not None:
                blended = recent_mean
            elif hist_mean is not None:
                blended = hist_mean
            else:
                blended = self.mu[dim]

            # Identity bounds: Cecilia stays confident/dominant
            if dim == 'dominance':
                blended = max(0.4, min(0.95, blended))
            elif dim == 'valence':
                blended = max(-0.6, min(0.8, blended))
            elif dim == 'arousal':
                blended = max(-0.5, min(0.6, blended))

            targets[dim] = blended

        # Shift baseline smoothly
        for dim, target in targets.items():
            current_mu = self.mu[dim]
            new_mu = (1.0 - alpha) * current_mu + alpha * target
            self.mu[dim] = new_mu
            self.mu[dim[0]] = new_mu

        return True

    def get_sampling_params(self) -> BrainukeParameters:
        """Maps the current Affect State to LLM sampling parameters."""
        # Temperature driven by Arousal
        temp = self.base_temp + (self.state.arousal * 0.25)
        
        # Min-P driven by Valence and Dominance
        # Low Valence/Low Dominance = Higher Min-P (more restricted/clipped)
        min_p = self.base_min_p + (abs(self.state.valence) * 0.1) + (abs(self.state.dominance) * 0.05)
        min_p = max(0.0, min(0.3, min_p))

        # Tone Descriptor (The 'Ghost' Prompt)
        tone = self._generate_tone_descriptor()
        
        return BrainukeParameters(
            temperature=max(0.1, min(2.0, temp)),
            min_p=min_p,
            tone_descriptor=tone
        )

    def _generate_tone_descriptor(self) -> str:
        v, a, d = self.state.valence, self.state.arousal, self.state.dominance
        
        if v < -0.4 and a > 0.4: return "Cutting, Sardonic, Unsparing"
        if v > 0.4 and a < -0.4: return "Calm, Smirking, Intellectually Detached"
        if d < -0.4: return "Guarded, Terse, Withdrawn"
        if d > 0.4: return "Commanding, Razor-Sharp Wit, Unfiltered"
        return "Observant, Dry, Candid"

    def get_status(self):
        return f"V:{self.state.valence:.2f} A:{self.state.arousal:.2f} D:{self.state.dominance:.2f}"
