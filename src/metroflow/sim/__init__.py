from importlib import import_module
from typing import Any

from .control import SimulationControl as SimulationControl
from .control import SimulationTelemetry as SimulationTelemetry
from .invariants import InvariantReport as InvariantReport
from .invariants import validate_invariants as validate_invariants
from .scheduler import SchedulerDecision as SchedulerDecision
from .scheduler import TickSchedule as TickSchedule
from .scheduler import scheduler_decision as scheduler_decision
from .state import SimulationClockState as SimulationClockState
from .state import SimulationDynamicRefs as SimulationDynamicRefs
from .state import SimulationState as SimulationState
from .state import SimulationStaticRefs as SimulationStaticRefs

_LAZY_EXPORTS = {
    "FastTickInput": ("metroflow.sim.orchestrator", "FastTickInput"),
    "MediumTickInput": ("metroflow.sim.orchestrator", "MediumTickInput"),
    "RuntimeDiagnosticFrame": (
        "metroflow.sim.runtime_diagnostics",
        "RuntimeDiagnosticFrame",
    ),
    "RuntimeDiagnosticReport": (
        "metroflow.sim.runtime_diagnostics",
        "RuntimeDiagnosticReport",
    ),
    "render_runtime_diagnostic_html": (
        "metroflow.sim.runtime_diagnostics",
        "render_runtime_diagnostic_html",
    ),
    "run_runtime_diagnostic_rollout": (
        "metroflow.sim.runtime_diagnostics",
        "run_runtime_diagnostic_rollout",
    ),
    "step_world_from_inputs": ("metroflow.sim.orchestrator", "step_world_from_inputs"),
    "write_runtime_diagnostic_html": (
        "metroflow.sim.runtime_diagnostics",
        "write_runtime_diagnostic_html",
    ),
}

__all__ = [
    "FastTickInput",
    "InvariantReport",
    "MediumTickInput",
    "RuntimeDiagnosticFrame",
    "RuntimeDiagnosticReport",
    "SchedulerDecision",
    "SimulationClockState",
    "SimulationControl",
    "SimulationDynamicRefs",
    "SimulationState",
    "SimulationStaticRefs",
    "SimulationTelemetry",
    "TickSchedule",
    "render_runtime_diagnostic_html",
    "run_runtime_diagnostic_rollout",
    "scheduler_decision",
    "step_world_from_inputs",
    "validate_invariants",
    "write_runtime_diagnostic_html",
]


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
