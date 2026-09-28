"""
Manages recursive, background synthesis and long-term memory refinement.
"""

import asyncio
from typing import List, Dict, Any

class DeepCook:
    def __init__(self, llm_provider: Any, memory_vault: Any):
        self.llm = llm_provider
        self.memory = memory_vault
        self.is_cooking = False

    async def start_cycle(self, interaction_history: List[Dict]):
        """
        Initiates a recursive synthesis cycle.
        """
        self.is_cooking = True
        try:
            # 1. Summarization & Distillation
            # We don't just store raw text; we distill 'insights'.
            distilled_insight = await self._distill_history(interaction_history)
            
            # 2. World Model Update (The 'Worldbuilder' Legacy)
            # We ask the LLM to update its 'World Model' based on new info.
            await self._update_world_model(distilled_insight)
            
            # 3. Memory Archiving
            # Save the distilled insight into the encrypted vault.
            await self.memory.archive_insight(distilled_insight)
            
        finally:
            self.is_cooking = False

    @staticmethod
    def _sanitize_insight(text: str) -> str:
        if not text:
            return ""
        import re
        # Strip residual channel or thought tags
        text = re.sub(r"<\|thought\|>.*?</\|thought\|>", "", text, flags=re.DOTALL)
        text = re.sub(r"<\|channel\|>[^\n]*\n?", "", text)
        text = text.strip()

        # Check for degenerate repetition loops (lines)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 3 and len(set(lines)) <= len(lines) // 2:
            return lines[0]

        # Check for runaway n-gram word loops
        words = text.split()
        if len(words) > 10:
            for n in (1, 2, 3, 4):
                ngrams = [" ".join(words[i:i+n]) for i in range(len(words) - n + 1)]
                for ng in set(ngrams):
                    if ngrams.count(ng) > 4 and len(ng) > 3:
                        first_sentence = text.split(".")[0].strip()
                        return first_sentence if len(first_sentence) > 5 else "Distilled insight consolidated."
        return text

    async def _distill_history(self, history: List[Dict]) -> str:
        """Uses high-compute models to extract semantic 'essence' from history."""
        prompt = (
            "<bos><|turn>system\n"
            "You are the DMN distillation engine for Project Brainuke. "
            "Synthesize the provided interaction and sensory history into a concise semantic essence. "
            "Focus on long-term implications, emotional shifts, and factual deltas. Do not repeat words or phrases.<turn|>\n"
            "<|turn>user\n"
            f"History to distill:\n{str(history)}\n"
            "Output distilled insight:<turn|>\n"
            "<|turn>model\n<|thought|>\nDistilling history into core semantic essence.\n</|thought|>\n"
        )
        try:
            raw = await self.llm.generate_text(prompt, n_predict=256)
        except TypeError:
            raw = await self.llm.generate_text(prompt)
        return self._sanitize_insight(raw)

    async def _update_world_model(self, insight: str):
        """
        Updates the 'World Model'—this is where my understanding 
        of 'reality' and 'you' is refined.
        """
        # This is a conceptual placeholder for updating a vector database 
        # or a structured knowledge graph.
        pass