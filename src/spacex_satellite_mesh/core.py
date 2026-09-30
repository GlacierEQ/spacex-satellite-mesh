"""Telemetry Processing & Mission Sequencing — Core Module"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import time

class LaunchPhase(Enum):
    PRE_LAUNCH = auto()
    TERMINAL_COUNT = auto()
    IGNITION = auto()
    LIFTOFF = auto()
    MAX_Q = auto()
    MECO = auto()
    STAGE_SEP = auto()
    SES = auto()
    SECO = auto()
    PAYLOAD_DEPLOY = auto()
    ENTRY_BURN = auto()
    LANDING_BURN = auto()
    LANDED = auto()
    ABORT = auto()

    def next_nominal(self) -> Optional['LaunchPhase']:
        order = list(LaunchPhase)
        idx = order.index(self)
        if self == LaunchPhase.ABORT or idx >= len(order) - 2:
            return None
        return order[idx + 1]


@dataclass
class TelemetryFrame:
    """Single telemetry frame from vehicle."""
    timestamp_ms: int
    altitude_m: float
    velocity_ms: float
    acceleration_g: float
    downrange_km: float
    phase: LaunchPhase
    anomaly_flags: list[str] = field(default_factory=list)

    @property
    def mach_number(self) -> float:
        """Approximate Mach at sea level (speed of sound ~343 m/s)."""
        return self.velocity_ms / 343.0

    @property
    def is_supersonic(self) -> bool:
        return self.mach_number > 1.0


class HoldReasonCompiler:
    """Accumulates hold reasons and determines GO/NO-GO."""

    def __init__(self):
        self._holds: list[tuple[str, str]] = []  # (system, reason)

    def add_hold(self, system: str, reason: str) -> None:
        self._holds.append((system, reason))

    def clear_hold(self, system: str) -> None:
        self._holds = [(s, r) for s, r in self._holds if s != system]

    @property
    def is_go(self) -> bool:
        return len(self._holds) == 0

    @property
    def hold_count(self) -> int:
        return len(self._holds)

    def summary(self) -> str:
        if self.is_go:
            return "ALL SYSTEMS GO"
        lines = [f"HOLD — {{len(self._holds)}} issue(s):"]
        for sys, reason in self._holds:
            lines.append(f"  [{sys}] {{reason}}")
        return "\n".join(lines)


class AnomalyDetector:
    """Statistical anomaly detection on telemetry streams."""

    def __init__(self, max_g: float = 6.0, max_velocity_ms: float = 8000.0):
        self.max_g = max_g
        self.max_velocity = max_velocity_ms
        self._history: list[TelemetryFrame] = []

    def ingest(self, frame: TelemetryFrame) -> list[str]:
        anomalies = []
        if abs(frame.acceleration_g) > self.max_g:
            anomalies.append(f"G-load {{frame.acceleration_g:.1f}} exceeds limit {{self.max_g}}")
        if frame.velocity_ms > self.max_velocity:
            anomalies.append(f"Velocity {{frame.velocity_ms:.0f}} m/s exceeds limit")
        if frame.altitude_m < 0:
            anomalies.append("Negative altitude detected")
        if self._history:
            dt = (frame.timestamp_ms - self._history[-1].timestamp_ms) / 1000.0
            if dt > 0:
                dv = abs(frame.velocity_ms - self._history[-1].velocity_ms)
                jerk = dv / dt
                if jerk > 500.0:
                    anomalies.append(f"High jerk {{jerk:.0f}} m/s² detected")
        self._history.append(frame)
        return anomalies

