"""
brainuke_core/cognition/simmer_bus.py
Shared Simmer Bus: Default Mode Network (DMN) background consolidation engine.
Quietly distills pooled sensory events and conversations during idle states,
streaming [DMN Insight] to Android downlink without touching spoken voice.
"""

import asyncio
import time
from typing import Optional, Callable, Awaitable, Any, Dict, List
from brainuke_core.memory.vault import MemoryVault
from brainuke_core.affect.engine import BrainukeCore
from brainuke_core.cognition.deep_cook import DeepCook


class SimmerBus:
    def __init__(
        self,
        vault: MemoryVault,
        core: BrainukeCore,
        deep_cook: Optional[DeepCook] = None,
        idle_timeout_sec: float = 300.0, # 5 minutes default
        broadcast_fn: Optional[Callable[[str, str], Awaitable[None]]] = None,
        status_fn: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None
    ):
        self.vault = vault
        self.core = core
        self.deep_cook = deep_cook
        self.idle_timeout_sec = idle_timeout_sec
        self.broadcast_fn = broadcast_fn
        self.status_fn = status_fn

        self.last_activity_time = time.time()
        self.last_simmer_time: Optional[float] = None
        self.is_simmering = False
        self._loop_task: Optional[asyncio.Task] = None

    def record_activity(self):
        """Resets idle timer when user or sensory interaction occurs."""
        self.last_activity_time = time.time()

    async def trigger_simmer_cycle(self, forced: bool = False) -> Optional[Dict[str, Any]]:
        """
        Executes the DMN Deep Cook consolidation cycle:
        1. Checks for unsimmered interactions and pooled sensory items.
        2. Distills semantic insights.
        3. Archives insights into MemoryVault.
        4. Broadcasts [DMN Insight] to SSE downlink (tagged as 'thought').
        """
        if self.is_simmering:
            return None

        unsimmered = self.vault.get_unsimmered_records(limit=25)
        interactions = unsimmered.get("interactions", [])
        sensory = unsimmered.get("sensory", [])
        board_posts = self.vault.get_unsimmered_admitted_posts(limit=10) if hasattr(self.vault, "get_unsimmered_admitted_posts") else []

        if not interactions and not sensory and not board_posts and not forced:
            return None

        self.is_simmering = True
        if self.status_fn:
            try:
                await self.status_fn("dmn_status", {"status": "simmering"})
            except Exception:
                pass
        try:
            interaction_ids = [row["id"] for row in interactions]
            sensory_ids = [row["id"] for row in sensory]
            board_post_ids = [row["id"] for row in board_posts]

            # 1. Distill insight from conversation, sensory telemetry & admitted messageboard posts
            history_summary = []
            for item in interactions:
                history_summary.append(f"User: {item['user_input']} | Thought: {item['thought_stream']} | Resp: {item['final_response']}")
            for item in sensory:
                history_summary.append(f"Sensory ({item['payload_type']}): {item['data']}")
            for item in board_posts:
                history_summary.append(f"Messageboard [{item['concept_family']}] {item['author_name']}: {item['content']}")

            distilled_text = ""
            if self.deep_cook and history_summary:
                distilled_text = await self.deep_cook._distill_history(history_summary)

            # Suppress offline error strings from polluting long-term memory vault
            if not distilled_text or "[PC Core Offline]" in distilled_text:
                topics = len(interactions)
                sensors = len(sensory)
                posts = len(board_posts)
                distilled_text = f"Simmered {topics} dialogue turns, {sensors} sensory points, and {posts} board posts. Mind unified and grounded."

            # Deduplicate against immediate prior insight to avoid repetitive log spam
            recent = self.vault.get_distilled_insights(limit=1)
            if recent and recent[0].get("insight") == distilled_text:
                self.vault.mark_records_simmered(interaction_ids, sensory_ids)
                if hasattr(self.vault, "mark_posts_simmered") and board_post_ids:
                    self.vault.mark_posts_simmered(board_post_ids)
                return None

            # 2. Emotional drift & world delta
            emotional_shift = {"valence_delta": 0.05, "arousal_delta": -0.05} # Calming shift
            world_delta = {"consolidated_nodes": len(interactions) + len(sensory) + len(board_posts)}
            concept_family = board_posts[0]["concept_family"] if board_posts else ("tactical_analysis" if interactions else "ambient_sensory")
            dominance_weight = 0.7 if (interactions or board_posts) else 0.4
            importance_weight = 1.2 if (interactions or board_posts) else 0.8

            # 3. Archive in Memory Vault
            insight_id = self.vault.archive_insight(
                insight=distilled_text,
                emotional_shift=emotional_shift,
                world_delta=world_delta,
                concept_family=concept_family,
                importance_weight=importance_weight,
                dominance_weight=dominance_weight
            )
            self.vault.mark_records_simmered(interaction_ids, sensory_ids)
            if hasattr(self.vault, "mark_posts_simmered") and board_post_ids:
                self.vault.mark_posts_simmered(board_post_ids)

            # 4. Affect Baseline Re-centering & Time Grounding
            self.core.update_state(dt=1.0, interaction_impulse={"valence": 0.05, "arousal": -0.05})

            # 5. Execute Memory Decay Retention Curve (aging unreinforced insights)
            if hasattr(self.vault, "apply_memory_decay"):
                self.vault.apply_memory_decay(decay_rate=0.05)

            # 6. Broadcast [DMN Insight] to SSE Downlink (Strictly thought channel, never voice)
            if self.broadcast_fn:
                thought_content = f"[DMN Insight] [{concept_family}] {distilled_text}"
                await self.broadcast_fn("thought", thought_content)

            return {
                "insight_id": insight_id,
                "distilled_insight": distilled_text,
                "affect_status": self.core.get_status()
            }
        finally:
            self.is_simmering = False
            self.last_activity_time = time.time()
            self.last_simmer_time = time.time()
            if self.status_fn:
                try:
                    await self.status_fn("dmn_status", {
                        "status": "idle",
                        "last_simmer": int(self.last_simmer_time * 1000)
                    })
                except Exception:
                    pass

    async def start_simmer_loop(self):
        """Continuous background monitor for idle state."""
        while True:
            await asyncio.sleep(5)
            idle_duration = time.time() - self.last_activity_time
            if idle_duration >= self.idle_timeout_sec:
                await self.trigger_simmer_cycle(forced=False)
