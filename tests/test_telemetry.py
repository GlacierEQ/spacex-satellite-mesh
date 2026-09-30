"""Auto-generated tests for Telemetry Processing & Mission Sequencing."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spacex_satellite_mesh.core import LaunchPhase, TelemetryFrame, HoldReasonCompiler, AnomalyDetector

def test_launch_phase_sequence():
    phase = LaunchPhase.PRE_LAUNCH
    assert phase.next_nominal() == LaunchPhase.TERMINAL_COUNT

def test_abort_has_no_next():
    assert LaunchPhase.ABORT.next_nominal() is None

def test_mach_number():
    frame = TelemetryFrame(0, 10000.0, 686.0, 1.5, 50.0, LaunchPhase.LIFTOFF)
    assert abs(frame.mach_number - 2.0) < 0.01

def test_supersonic():
    frame = TelemetryFrame(0, 15000.0, 400.0, 2.0, 80.0, LaunchPhase.MAX_Q)
    assert frame.is_supersonic

def test_hold_compiler_go():
    hrc = HoldReasonCompiler()
    assert hrc.is_go
    assert "GO" in hrc.summary()

def test_hold_compiler_nogo():
    hrc = HoldReasonCompiler()
    hrc.add_hold("WEATHER", "Upper level winds exceed limit")
    assert not hrc.is_go
    assert hrc.hold_count == 1

def test_hold_clear():
    hrc = HoldReasonCompiler()
    hrc.add_hold("RANGE", "Boat in exclusion zone")
    hrc.clear_hold("RANGE")
    assert hrc.is_go

def test_anomaly_detector_nominal():
    det = AnomalyDetector()
    frame = TelemetryFrame(1000, 5000.0, 300.0, 2.0, 10.0, LaunchPhase.LIFTOFF)
    assert len(det.ingest(frame)) == 0

def test_anomaly_detector_g_overload():
    det = AnomalyDetector(max_g=5.0)
    frame = TelemetryFrame(1000, 5000.0, 300.0, 7.0, 10.0, LaunchPhase.MAX_Q)
    anomalies = det.ingest(frame)
    assert any("G-load" in a for a in anomalies)

def test_anomaly_negative_altitude():
    det = AnomalyDetector()
    frame = TelemetryFrame(1000, -100.0, 0.0, 0.0, 0.0, LaunchPhase.PRE_LAUNCH)
    assert any("altitude" in a for a in det.ingest(frame))

