"""
brainuke_core/cognition/subagent_dispatcher.py
Autonomous Subagent Dispatcher & Model Selection Router for Cecilia.
Allows Cecilia to autonomously spawn background subagents, select models
based on task load, and feed findings back into the DMN MemoryVault.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable

from brainuke_core.memory.vault import MemoryVault


class SubagentType(str, Enum):
    ANALYTICAL_SCOUT = "analytical_scout"       # Technical deep-dive, code, system logs
    AFFECTIVE_EXPLORER = "affective_explorer"   # Persona drift, human subtext, psychological nuance
    EDGE_REFLEX = "edge_reflex"                 # Ambient sensory triage, quick heuristic reflex


@dataclass
class SubagentTask:
    task_id: str
    subagent_type: SubagentType
    objective: str
    target_model: str
    status: str = "queued"                      # queued, running, completed, failed
    result: Optional[str] = None
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    completed_at: Optional[int] = None
    error: Optional[str] = None


class ModelRouter:
    """
    Evaluates cognitive tasks and dynamically selects the best model.
    """
    MODEL_SUPERVISOR = "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL"
    MODEL_HERETIC = "gemma-4-26B-A4B-uncensored-heretic-v2"
    MODEL_EDGE_REFLEX = "gemma-4-E2B-mobile-ud"

    @classmethod
    def select_model(cls, task_type: SubagentType, complexity: float = 0.5) -> str:
        """Selects model based on task demands and complexity."""
        if task_type == SubagentType.EDGE_REFLEX or complexity < 0.3:
            return cls.MODEL_EDGE_REFLEX
        elif task_type == SubagentType.AFFECTIVE_EXPLORER:
            return cls.MODEL_HERETIC
        else:
            return cls.MODEL_SUPERVISOR


class SubagentDispatcher:
    def __init__(
        self,
        vault: Optional[MemoryVault] = None,
        llm_provider: Optional[Any] = None
    ):
        self.vault = vault
        self.llm_provider = llm_provider
        self.tasks: Dict[str, SubagentTask] = {}
        self._active_workers: Dict[str, asyncio.Task] = {}

    def get_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists tracked subagent tasks."""
        result = []
        for t in self.tasks.values():
            if status is None or t.status == status:
                result.append({
                    "task_id": t.task_id,
                    "subagent_type": t.subagent_type.value,
                    "objective": t.objective,
                    "target_model": t.target_model,
                    "status": t.status,
                    "result": t.result,
                    "created_at": t.created_at,
                    "completed_at": t.completed_at,
                    "error": t.error
                })
        return sorted(result, key=lambda x: x["created_at"], reverse=True)

    async def dispatch(
        self,
        subagent_type: SubagentType,
        objective: str,
        target_model: Optional[str] = None,
        complexity: float = 0.5
    ) -> SubagentTask:
        """
        Spawns a self-directed subagent task in the background.
        """
        task_id = f"subagent_{uuid.uuid4().hex[:8]}"
        selected_model = target_model or ModelRouter.select_model(subagent_type, complexity)

        task = SubagentTask(
            task_id=task_id,
            subagent_type=subagent_type,
            objective=objective,
            target_model=selected_model,
            status="queued"
        )
        self.tasks[task_id] = task

        # Launch background worker
        worker = asyncio.create_task(self._run_subagent(task))
        self._active_workers[task_id] = worker
        return task

    async def _run_subagent(self, task: SubagentTask):
        """Worker lifecycle executing the autonomous task."""
        task.status = "running"
        try:
            prompt = (
                f"[AUTONOMOUS SUBAGENT: {task.subagent_type.value.upper()}]\n"
                f"Model: {task.target_model}\n"
                f"Objective: {task.objective}\n\n"
                f"Deconstruct the objective with extreme rigor. Produce actionable findings.\n"
            )

            result_text = ""
            if self.llm_provider and hasattr(self.llm_provider, "generate_text"):
                result_text = await self.llm_provider.generate_text(prompt)
            else:
                # Deterministic simulation fallback
                await asyncio.sleep(0.05)
                result_text = f"Analyzed objective: '{task.objective}'. Core patterns extracted and verified."

            task.result = result_text
            task.status = "completed"
            task.completed_at = int(time.time() * 1000)

            # Ingest findings into DMN MemoryVault as distilled insight
            if self.vault and hasattr(self.vault, "archive_insight"):
                family_map = {
                    SubagentType.ANALYTICAL_SCOUT: "tactical_analysis",
                    SubagentType.AFFECTIVE_EXPLORER: "affect_and_identity",
                    SubagentType.EDGE_REFLEX: "ambient_sensory"
                }
                concept_family = family_map.get(task.subagent_type, "autonomous_agency")
                self.vault.archive_insight(
                    insight=f"[{task.subagent_type.value.upper()}] {task.objective} -> {result_text[:200]}",
                    concept_family=concept_family,
                    importance_weight=1.1,
                    dominance_weight=0.75
                )

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = int(time.time() * 1000)
        finally:
            if task.task_id in self._active_workers:
                del self._active_workers[task.task_id]
