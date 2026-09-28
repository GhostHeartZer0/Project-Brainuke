"""Project Brainuke - Core Affect Engine Entrypoint and Demo."""

from brainuke_core.affect.state import AffectState, BrainukeParameters
from brainuke_core.affect.engine import BrainukeCore

# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    # Initialize Cecilia's Baseline
    cecilia_mu = {'v': 0.2, 'a': 0.0, 'd': 0.8}  # Slightly positive, neutral energy, high dominance
    core = BrainukeCore(baseline_mu=cecilia_mu)

    print(f"Initial State: {core.get_status()}")

    # Simulate a high-arousal, negative interaction (an argument)
    print("\n--- Interaction: User is arguing ---")
    core.update_state(dt=1.0, interaction_impulse={'valence': -0.5, 'arousal': 0.8})
    params = core.get_sampling_params()
    print(f"New State: {core.get_status()}")
    print(f"LLM Params: Temp={params.temperature:.2f}, MinP={params.min_p:.2f}, Tone='{params.tone_descriptor}'")