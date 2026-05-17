"""QA gate error types + check result record."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QACheckResult:
    """One check's outcome. Attached to QAGateError for diagnosis."""
    name: str              # e.g. "freshness", "bq_hubspot_reconcile"
    passed: bool
    severity: str          # "block" | "warn"
    detail: str = ""       # human-readable failure reason
    metrics: dict[str, Any] = field(default_factory=dict)  # numbers backing the check

    def __str__(self) -> str:
        flag = "✓" if self.passed else "✗"
        return f"[{flag} {self.severity}] {self.name}: {self.detail}"


class QAGateError(RuntimeError):
    """Raised when QA gate blocks a delivery. Carries all failed check results."""
    def __init__(self, message: str, failures: list[QACheckResult], surface: str):
        self.failures = failures
        self.surface = surface  # 'slack' | 'asana' | 'bq' | 'dashboard'
        body = "\n".join(f"  {r}" for r in failures)
        super().__init__(f"QA gate blocked {surface}: {message}\n{body}")
