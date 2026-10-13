"""Focused unit checks for demo-owned object result bookkeeping."""

from __future__ import annotations

from types import SimpleNamespace

from demo import vision_demo_node
from demo.vision_demo_node import VisionDemoNode, _ObjectTargetTracker


def test_object_tracker_keeps_ids_and_ages_lost_targets() -> None:
    tracker = _ObjectTargetTracker(
        vision_epoch="demo-epoch",
        persistence_sec=2.0,
        current_timeout_sec=0.75,
        horizontal_fov_deg=69.0,
    )
    detection = {
        "label": "dog toy ball",
        "x": 0.3,
        "y": 0.45,
        "w": 0.12,
        "h": 0.12,
        "confidence": 0.88,
    }

    first = tracker.update(
        [detection], now=10.0, stamp=100.0, frame_id="camera", sequence=1
    )[0]
    moved = {**detection, "x": 0.305}
    second = tracker.update(
        [moved], now=10.5, stamp=100.5, frame_id="camera", sequence=2
    )[0]

    assert first["target_id"] == "demo-epoch:object:1"
    assert second["target_id"] == first["target_id"]
    assert second["source_sequence"] == 2
    stale = tracker.snapshot(now=11.4)[0]
    assert stale["tracking_state"] == "temporarily_lost"
    assert stale["range_valid"] is False
    assert tracker.snapshot(now=12.6) == []


def test_object_tracker_clears_facts_on_terminal_result() -> None:
    tracker = _ObjectTargetTracker(
        vision_epoch="demo-epoch",
        persistence_sec=2.0,
        current_timeout_sec=0.75,
        horizontal_fov_deg=69.0,
    )
    tracker.update(
        [{"label": "ball", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}],
        now=1.0,
        stamp=1.0,
        frame_id="camera",
        sequence=1,
    )

    tracker.clear()

    assert tracker.snapshot(now=1.1) == []


def test_unavailable_object_provider_logs_error_without_aborting_startup(monkeypatch) -> None:
    messages: list[str] = []
    detector = SimpleNamespace(
        start=lambda: None,
        is_available=lambda: False,
        last_error="model file missing",
    )
    monkeypatch.setattr(vision_demo_node, "ObjectDetectorProvider", lambda config: detector)
    node = SimpleNamespace(
        _providers={},
        get_logger=lambda: SimpleNamespace(error=messages.append),
    )

    VisionDemoNode._init_providers(
        node,
        {"object": {"enabled": True}},
        {"enabled": False},
        {},
    )

    assert node._providers["object"] is detector
    assert messages == ["Object detector is unavailable: model file missing"]
