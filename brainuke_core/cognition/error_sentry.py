"""
brainuke_core/cognition/error_sentry.py
Error Interception Sentry for Project Brainuke.

Captures, structures, and buffers unhandled runtime failures across
Throne server, sensory pipeline, cognitive orchestrator, and desktop UI.
Flags diagnostics for Cecilia's self-healing studio.
"""

import time
import uuid
import traceback
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any


@dataclass
class ErrorDiagnostic:
    error_id: str = field(default_factory=lambda: f"err_{uuid.uuid4().hex[:8]}")
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    error_type: str = "UnknownError"
    message: str = ""
    traceback_str: str = ""
    subsystem: str = "general"
    context_vars: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    status: str = "flagged"  # flagged, in_progress, pending_confirmation, patched, resolved, failed
    patch_diff: Optional[str] = None
    target_file: Optional[str] = None
    resolution_note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ErrorSentry:
    _instance: Optional["ErrorSentry"] = None

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self._errors: List[ErrorDiagnostic] = []

    @classmethod
    def get_instance(cls) -> "ErrorSentry":
        if cls._instance is None:
            cls._instance = ErrorSentry()
        return cls._instance

    def flag_exception(
        self,
        exc: Exception,
        subsystem: str = "general",
        context_vars: Optional[Dict[str, Any]] = None
    ) -> ErrorDiagnostic:
        """Captures an active exception and converts to an ErrorDiagnostic."""
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        diagnostic = ErrorDiagnostic(
            error_type=type(exc).__name__,
            message=str(exc) or type(exc).__name__,
            traceback_str=tb_str,
            subsystem=subsystem,
            context_vars=context_vars or {}
        )
        self._add_diagnostic(diagnostic)
        return diagnostic

    def flag_manual_error(
        self,
        message: str,
        error_type: str = "ManualDebugTrigger",
        traceback_str: str = "",
        subsystem: str = "manual_debug",
        context_vars: Optional[Dict[str, Any]] = None
    ) -> ErrorDiagnostic:
        """Manually records an error report (e.g. from UI debug trigger)."""
        diagnostic = ErrorDiagnostic(
            error_type=error_type,
            message=message,
            traceback_str=traceback_str or f"Manual error flagged in subsystem: {subsystem}",
            subsystem=subsystem,
            context_vars=context_vars or {}
        )
        self._add_diagnostic(diagnostic)
        return diagnostic

    def _add_diagnostic(self, diagnostic: ErrorDiagnostic):
        self._errors.append(diagnostic)
        if len(self._errors) > self.max_history:
            self._errors.pop(0)

    def get_errors(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            return [e.to_dict() for e in self._errors if e.status == status]
        return [e.to_dict() for e in self._errors]

    def get_latest_error(self) -> Optional[ErrorDiagnostic]:
        if not self._errors:
            return None
        return self._errors[-1]

    def get_error_by_id(self, error_id: str) -> Optional[ErrorDiagnostic]:
        for e in self._errors:
            if e.error_id == error_id:
                return e
        return None

    def clear(self):
        self._errors.clear()
