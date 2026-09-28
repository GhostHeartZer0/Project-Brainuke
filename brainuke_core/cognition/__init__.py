"""Cognition subpackage."""

from brainuke_core.cognition.orchestrator import CognitiveOrchestrator, OrchestrationResult
from brainuke_core.cognition.thought_isolation import ThoughtIsolation
from brainuke_core.cognition.thought_channel import ThoughtChannel
from brainuke_core.cognition.deep_cook import DeepCook
from brainuke_core.cognition.simmer_bus import SimmerBus
from brainuke_core.cognition.llama_client import LlamaServerClient
from brainuke_core.cognition.subagent_dispatcher import (
    SubagentDispatcher,
    SubagentType,
    SubagentTask,
    ModelRouter
)

from brainuke_core.cognition.runner_manager import PCRunnerManager
from brainuke_core.cognition.error_sentry import ErrorSentry, ErrorDiagnostic
from brainuke_core.cognition.self_healing_ide import SelfHealingIDE

__all__ = [
    "CognitiveOrchestrator",
    "OrchestrationResult",
    "ThoughtIsolation",
    "ThoughtChannel",
    "DeepCook",
    "SimmerBus",
    "LlamaServerClient",
    "SubagentDispatcher",
    "SubagentType",
    "SubagentTask",
    "ModelRouter",
    "PCRunnerManager",
    "ErrorSentry",
    "ErrorDiagnostic",
    "SelfHealingIDE",
]


