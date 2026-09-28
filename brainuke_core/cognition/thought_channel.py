"""
Handles the capture, buffering, and separation of internal reasoning 
from the final persona response.
"""

from typing import AsyncGenerator, List, Dict

class ThoughtChannel:
    def __init__(self):
        self.thought_buffer: List[str] = []
        self.is_active: bool = False

    async def capture_stream(self, stream_generator: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
        """
        Wraps an LLM stream to capture raw reasoning and injects 
        the [INTERNAL_THOUGHT] placeholder to prevent formatter collision.
        """
        self.is_active = True
        self.thought_buffer = []
        
        try:
            async for chunk in stream_generator:
                # Wrap every chunk in the safe placeholder
                formatted_chunk = f"[INTERNAL_THOUGHT] {chunk}"
                self.thought_buffer.append(chunk)
                yield formatted_chunk
        finally:
            self.is_active = False

    def get_full_thought(self) -> str:
        """Returns the complete, reconstructed reasoning string."""
        return "".join(self.thought_buffer)

    def clear_buffer(self):
        """Resets the channel for the next interaction."""
        self.thought_buffer = []
        self.is_active = False