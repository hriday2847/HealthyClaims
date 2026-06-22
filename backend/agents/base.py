"""Base agent class with built-in tracing, timing, and error handling."""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from typing import Any

from backend.models.decision import CheckResult, TraceStep, TraceStepStatus


class AgentResult:
    """Container for an agent's output."""

    def __init__(
        self,
        success: bool = True,
        data: dict[str, Any] | None = None,
        checks: list[CheckResult] | None = None,
        error: str | None = None,
        warnings: list[str] | None = None,
    ):
        self.success = success
        self.data = data or {}
        self.checks = checks or []
        self.error = error
        self.warnings = warnings or []


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents.

    Provides:
    - Automatic timing
    - Structured trace output
    - Exception catching for graceful degradation
    """

    name: str = "BaseAgent"
    critical: bool = False  # If True, pipeline stops on failure

    def run(self, context: dict[str, Any]) -> tuple[AgentResult, TraceStep]:
        """Execute the agent with full instrumentation.

        Returns (result, trace_step) — even if the agent throws,
        the trace_step will capture the error.
        """
        start = time.perf_counter()
        try:
            result = self.execute(context)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status = (
                TraceStepStatus.SUCCESS
                if result.success
                else TraceStepStatus.FAILED
            )
            if result.warnings:
                status = TraceStepStatus.DEGRADED

            trace = TraceStep(
                agent_name=self.name,
                status=status,
                duration_ms=elapsed_ms,
                input_summary=self._summarize_input(context),
                output_summary=self._summarize_output(result),
                checks=result.checks,
                error=result.error,
                warnings=result.warnings,
            )
            return result, trace

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            error_msg = f"{type(exc).__name__}: {exc}"
            trace = TraceStep(
                agent_name=self.name,
                status=TraceStepStatus.FAILED,
                duration_ms=elapsed_ms,
                input_summary=self._summarize_input(context),
                output_summary=None,
                checks=[],
                error=error_msg,
                warnings=[traceback.format_exc()],
            )
            result = AgentResult(
                success=False,
                error=error_msg,
                warnings=["Agent crashed — returning degraded result"],
            )
            return result, trace

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> AgentResult:
        """Implement the agent's core logic. Override in subclasses."""
        ...

    def _summarize_input(self, context: dict[str, Any]) -> str:
        """Create a brief summary of the input context."""
        parts = []
        if "submission" in context:
            sub = context["submission"]
            parts.append(f"member={sub.member_id}")
            parts.append(f"category={sub.claim_category.value}")
            parts.append(f"amount=₹{sub.claimed_amount:,.0f}")
        return ", ".join(parts) if parts else "—"

    def _summarize_output(self, result: AgentResult) -> str:
        """Create a brief summary of the agent's output."""
        if result.error:
            return f"ERROR: {result.error}"
        parts = []
        passed = sum(1 for c in result.checks if c.passed)
        failed = sum(1 for c in result.checks if not c.passed)
        if result.checks:
            parts.append(f"{passed} passed, {failed} failed")
        if result.warnings:
            parts.append(f"{len(result.warnings)} warnings")
        return ", ".join(parts) if parts else "OK"
