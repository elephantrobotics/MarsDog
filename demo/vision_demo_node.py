"""Focused ROS 2 node for object detection and current human targets."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import threading
import time
from typing import Any

import numpy as np
import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String

try:
    from marsdog_vision_interaction.srv import VisionTask
except ImportError as exc:  # pragma: no cover - requires sourced ROS overlay
    raise RuntimeError(
        "Cannot import marsdog_vision_interaction.srv.VisionTask. Source ROS 2 "
        "Humble and this workspace's install/setup.bash before starting the demo."
    ) from exc

from marsdog_vision_interaction.core.object_detection_session import (
    ObjectDetectionSessionManager,
)
from marsdog_vision_interaction.fusion.stereo_fusion import get_target_manager
from marsdog_vision_interaction.messages.visual_event import normalize_visual_event
from marsdog_vision_interaction.providers.base import BaseProvider
from marsdog_vision_interaction.providers.object_detector import (
    ObjectDetectorProvider,
)
from marsdog_vision_interaction.utils.config_loader import load_config
from marsdog_vision_interaction.utils.stereo_view import select_camera_view


_VISUAL_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)
_CAMERA_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
_INVALID_POSE_3D = {
    "valid": False,
    "frame_id": "",
    "x": None,
    "y": None,
    "z": None,
}
_ANIMAL_LABELS = {"cat", "dog"}
_TOY_LABELS = {"dog toy ball", "dog frisbee toy", "dog tug ring toy"}


class _ObjectTargetTracker:
    """Small 2D fact tracker for the object schema consumed by ROS clients."""

    def __init__(
        self,
        *,
        vision_epoch: str,
        persistence_sec: float,
        current_timeout_sec: float,
        horizontal_fov_deg: float,
    ) -> None:
        self.vision_epoch = vision_epoch
        self.persistence_sec = persistence_sec
        self.current_timeout_sec = current_timeout_sec
        self.horizontal_fov_deg = horizontal_fov_deg
        self.tracks: dict[int, dict[str, Any]] = {}
        self.next_track_id = 1

    @staticmethod
    def _iou(
        first: tuple[float, float, float, float],
        second: tuple[float, float, float, float],
    ) -> float:
        if min(first[2], first[3], second[2], second[3]) <= 0:
            return 0.0
        ix1, iy1 = max(first[0], second[0]), max(first[1], second[1])
        ix2 = min(first[0] + first[2], second[0] + second[2])
        iy2 = min(first[1] + first[3], second[1] + second[3])
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        intersection = (ix2 - ix1) * (iy2 - iy1)
        union = first[2] * first[3] + second[2] * second[3] - intersection
        return intersection / union if union > 0 else 0.0

    def update(
        self,
        detections: list[dict[str, Any]],
        *,
        now: float,
        stamp: float,
        frame_id: str,
        sequence: int,
    ) -> list[dict[str, Any]]:
        self.tracks = {
            track_id: track
            for track_id, track in self.tracks.items()
            if now - track["last_seen_monotonic"] <= self.persistence_sec
        }
        normalized: list[dict[str, Any]] = []
        for item in detections:
            if not isinstance(item, dict):
                continue
            try:
                label = " ".join(str(item.get("label", "")).strip().lower().split())
                bbox = tuple(float(item.get(key, 0.0)) for key in ("x", "y", "w", "h"))
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue
            if (
                not label
                or not all(math.isfinite(value) for value in (*bbox, confidence))
                or bbox[2] <= 0.0
                or bbox[3] <= 0.0
            ):
                continue
            normalized.append({
                "label": label,
                "display_label": str(item.get("label", label)),
                "bbox": bbox,
                "confidence": min(1.0, max(0.0, confidence)),
            })

        matches: list[tuple[float, int, int]] = []
        for index, detection in enumerate(normalized):
            for track_id, track in self.tracks.items():
                if track["label"] == detection["label"]:
                    score = self._iou(track["bbox"], detection["bbox"])
                    if score >= 0.15:
                        matches.append((score, index, track_id))
        assigned: dict[int, int] = {}
        used: set[int] = set()
        for _, index, track_id in sorted(matches, reverse=True):
            if index not in assigned and track_id not in used:
                assigned[index] = track_id
                used.add(track_id)

        for index, detection in enumerate(normalized):
            track_id = assigned.get(index)
            if track_id is None:
                track_id = self.next_track_id
                self.next_track_id += 1
            label = detection["label"]
            x, y, width, height = detection["bbox"]
            self.tracks[track_id] = {
                **detection,
                "track_id": track_id,
                "vision_epoch": self.vision_epoch,
                "target_id": f"{self.vision_epoch}:object:{track_id}",
                "target_type": "animal" if label in _ANIMAL_LABELS else "object",
                "object_kind": "toy" if label in _TOY_LABELS else "generic",
                "last_seen_monotonic": now,
                "header": {"stamp": stamp, "frame_id": frame_id},
                "source_sequence": sequence,
                "source_snapshot_id": f"{self.vision_epoch}:object-result:{sequence}",
                "center_x": x + width / 2.0,
                "center_y": y + height / 2.0,
            }
        return self.snapshot(now=now)

    def clear(self) -> None:
        self.tracks.clear()

    def snapshot(self, *, now: float) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        expired = [
            track_id for track_id, track in self.tracks.items()
            if now - track["last_seen_monotonic"] > self.persistence_sec
        ]
        for track_id in expired:
            del self.tracks[track_id]
        for track_id, track in sorted(self.tracks.items()):
            age = max(0.0, now - track["last_seen_monotonic"])
            x, y, width, height = track["bbox"]
            center_x, center_y = track["center_x"], track["center_y"]
            values.append({
                "vision_epoch": self.vision_epoch,
                "target_id": track["target_id"],
                "target_type": track["target_type"],
                "track_id": track_id,
                "object_track_id": track_id,
                "label": track["label"],
                "display_label": track["display_label"],
                "object_kind": track["object_kind"],
                "x": round(x, 4),
                "y": round(y, 4),
                "w": round(width, 4),
                "h": round(height, 4),
                "bbox": [round(value, 4) for value in track["bbox"]],
                "center_x": round(center_x, 4),
                "center_y": round(center_y, 4),
                "center": [round(center_x, 4), round(center_y, 4)],
                "confidence": round(track["confidence"], 4),
                "detection_confidence": round(track["confidence"], 4),
                "tracking_state": (
                    "tracking" if age <= self.current_timeout_sec
                    else "temporarily_lost"
                ),
                "last_seen_age_ms": round(age * 1000.0, 1),
                "bearing_deg": round((center_x - 0.5) * self.horizontal_fov_deg, 3),
                "bearing_valid": True,
                "bearing_source": "configured_hfov",
                "range_valid": False,
                "distance_m": None,
                "range_source": "none",
                "pose_3d": copy.deepcopy(_INVALID_POSE_3D),
                "header": copy.deepcopy(track["header"]),
                "source_sequence": track["source_sequence"],
                "source_snapshot_id": track["source_snapshot_id"],
            })
        return values


class VisionDemoNode(Node):
    """Serve only the object and human-target functions listed in the demo."""

    def __init__(self, config_path: str | Path) -> None:
        super().__init__("vision_demo")
        self._config = load_config(config_path)
        providers = self._config.get("providers", {})
        vision_cfg = providers.get("vision", {})
        vision_runtime = vision_cfg.get("config", {})
        if not isinstance(vision_runtime, dict):
            vision_runtime = {}
        self._vision_is_mock = vision_cfg.get("type") == "mock"
        self._target_manager = get_target_manager()
        self._target_manager.configure(
            horizontal_fov_deg=float(vision_runtime.get("horizontal_fov_deg", 69.0))
        )
        self._vision_epoch = self._target_manager.vision_epoch
        self._stereo_enabled = bool(vision_runtime.get("stereo_enabled", False))
        self._stereo_view = str(vision_runtime.get("stereo_view", "left")).lower()
        self._stereo_min_aspect_ratio = max(
            1.0, float(vision_runtime.get("stereo_min_aspect_ratio", 2.2))
        )

        self._state_lock = threading.RLock()
        self._object_inference_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._latest_camera_stamp = 0.0
        self._latest_camera_frame_id = "camera_link"
        self._latest_camera_monotonic = 0.0
        self._visual_sequence = 0
        self._visual_snapshot: dict[str, Any] = {}
        self._visual_snapshot_monotonic = 0.0
        self._object_sequence = 0

        self._camera_group = MutuallyExclusiveCallbackGroup()
        self._visual_group = MutuallyExclusiveCallbackGroup()
        self._object_group = MutuallyExclusiveCallbackGroup()
        self._service_group = MutuallyExclusiveCallbackGroup()

        self._providers: dict[str, BaseProvider] = {}
        self._init_providers(providers, vision_cfg, vision_runtime)

        topics = self._config.get("topics", {})
        self._camera_topic = str(topics.get("camera_image", "/camera/camera/color/image_raw"))
        self._visual_topic = str(topics.get("visual_event", "/perception/visual_event"))
        self._object_topic = str(topics.get(
            "object_detections", "/perception/vision/object_detections"
        ))
        self._service_name = str(topics.get("vision_task", "/perception/vision/task"))
        self._camera_stale_timeout_sec = max(
            0.1, float(topics.get("camera_stale_timeout_sec", 0.5))
        )
        depth_config = self._config.get("depth_fusion", {})
        if not isinstance(depth_config, dict):
            depth_config = {}
        self._target_current_timeout_sec = max(
            0.05, float(depth_config.get("target_current_timeout_sec", 0.35))
        )
        self._observation_rate_hz = max(
            0.1, float(topics.get("observation_rate_hz", 10.0))
        )

        object_cfg = providers.get("object", {}).get("config", {})
        if not isinstance(object_cfg, dict):
            object_cfg = {}
        self._object_default_confidence = min(
            1.0, max(0.0, float(object_cfg.get("det_threshold", 0.2)))
        )
        max_rate = min(5.0, max(0.1, float(object_cfg.get("max_inference_rate_hz", 5.0))))
        self._object_stream = ObjectDetectionSessionManager(
            startup_rate_hz=0.0,
            default_rate_hz=min(2.0, max_rate),
            max_rate_hz=max_rate,
            default_confidence=self._object_default_confidence,
            default_lease_sec=float(object_cfg.get("default_lease_sec", 3.0)),
            max_lease_sec=float(object_cfg.get("max_lease_sec", 30.0)),
        )
        self._object_tracker = _ObjectTargetTracker(
            vision_epoch=self._vision_epoch,
            persistence_sec=max(
                0.75,
                float(object_cfg.get("target_persistence_sec", 2.0)),
            ),
            current_timeout_sec=max(
                0.1,
                float(object_cfg.get("target_current_timeout_sec", 0.75)),
            ),
            horizontal_fov_deg=max(
                1.0, float(vision_runtime.get("horizontal_fov_deg", 69.0))
            ),
        )

        self._visual_pub = self.create_publisher(String, self._visual_topic, _VISUAL_QOS)
        self._object_pub = self.create_publisher(String, self._object_topic, _VISUAL_QOS)
        self._camera_sub = self.create_subscription(
            Image,
            self._camera_topic,
            self._on_camera,
            _CAMERA_QOS,
            callback_group=self._camera_group,
        )
        self._service = self.create_service(
            VisionTask,
            self._service_name,
            self._handle_task,
            callback_group=self._service_group,
        )

        scheduler_hz = max(1.0, float(object_cfg.get("scheduler_rate_hz", 20.0)))
        self._visual_timer = self.create_timer(
            1.0 / self._observation_rate_hz,
            self._publish_visual,
            callback_group=self._visual_group,
        )
        self._object_timer = self.create_timer(
            1.0 / scheduler_hz,
            self._poll_objects,
            callback_group=self._object_group,
        )
        self.get_logger().info(
            f"Vision demo ready: camera={self._camera_topic} "
            f"visual={self._visual_topic} objects={self._object_topic} "
            f"service={self._service_name} mock={self._vision_is_mock}"
        )

    def _init_providers(
        self,
        providers: dict[str, Any],
        vision_cfg: dict[str, Any],
        vision_runtime: dict[str, Any],
    ) -> None:
        if vision_cfg.get("enabled", True):
            provider_config = copy.deepcopy(vision_runtime)
            provider_config.update({
                "face_detect_model": "",
                "face_recogn_model": "",
                "hand_landmark_model": "",
                "hand_detect_model": "",
                "show_all_detections": False,
                "face_tracking": {"use_bytetrack": False},
            })
            if vision_cfg.get("type", "observation") == "mock":
                from marsdog_vision_interaction.providers.mock_vision import MockVisionProvider

                vision: BaseProvider = MockVisionProvider(provider_config)
            else:
                from marsdog_vision_interaction.providers.vision_observation import (
                    VisionObservationProvider,
                )

                vision = VisionObservationProvider(provider_config)
                vision.task_face_enabled = False
                vision.task_hand_enabled = False
            vision.start()
            self._providers["vision"] = vision
            if not vision.is_available():
                self.get_logger().error(
                    "Human pose provider is unavailable; the demo will publish "
                    "empty human observations until its configured pose model loads."
                )

        object_cfg = providers.get("object", {})
        if object_cfg.get("enabled", True):
            config = copy.deepcopy(object_cfg.get("config", {}))
            if not isinstance(config, dict):
                config = {}
            if object_cfg.get("type") == "mock":
                config["mock_mode"] = True
            detector = ObjectDetectorProvider(config)
            detector.start()
            self._providers["object"] = detector
            if not detector.is_available():
                self.get_logger().error(
                    f"Object detector is unavailable: {detector.last_error}"
                )

    @staticmethod
    def _stamp(message: Image) -> float:
        stamp = getattr(getattr(message, "header", None), "stamp", None)
        try:
            value = float(getattr(stamp, "sec", 0)) + float(
                getattr(stamp, "nanosec", 0)
            ) * 1e-9
        except (TypeError, ValueError):
            return 0.0
        return value if math.isfinite(value) and value > 0.0 else 0.0

    @staticmethod
    def _decode_image(message: Image) -> np.ndarray | None:
        try:
            import cv2

            encoding = str(getattr(message, "encoding", "bgr8")).lower()
            channels = 1 if encoding in ("mono8", "8uc1") else 3
            width, height = int(message.width), int(message.height)
            step = int(message.step) or width * channels
            if width <= 0 or height <= 0 or step < width * channels:
                return None
            if len(message.data) < height * step:
                return None
            raw = np.frombuffer(message.data, dtype=np.uint8).reshape(height, step)
            if channels == 1:
                return cv2.cvtColor(raw[:, :width], cv2.COLOR_GRAY2BGR)
            frame = raw[:, : width * 3].reshape(height, width, 3)
            if encoding == "rgb8":
                return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            if encoding not in ("bgr8", "8uc3"):
                return None
            return frame.copy()
        except (AttributeError, TypeError, ValueError):
            return None

    def _on_camera(self, message: Image) -> None:
        frame = self._decode_image(message)
        if frame is None:
            self.get_logger().debug("Rejected unsupported or malformed camera image")
            return
        stamp = self._stamp(message) or time.time()
        frame_id = str(getattr(getattr(message, "header", None), "frame_id", "") or "camera_link")
        with self._state_lock:
            self._latest_frame = frame
            self._latest_camera_stamp = stamp
            self._latest_camera_frame_id = frame_id
            self._latest_camera_monotonic = time.monotonic()
        vision = self._providers.get("vision")
        if vision is not None and hasattr(vision, "process_frame"):
            vision.process_frame(frame, stamp=stamp, frame_id=frame_id)  # type: ignore[attr-defined]

    def _camera_state(self) -> tuple[np.ndarray | None, float, str, bool]:
        with self._state_lock:
            frame = self._latest_frame
            stamp = self._latest_camera_stamp
            frame_id = self._latest_camera_frame_id
            received = self._latest_camera_monotonic
        fresh = (
            self._vision_is_mock
            or (
                frame is not None
                and received > 0.0
                and time.monotonic() - received <= self._camera_stale_timeout_sec
            )
        )
        return frame, stamp, frame_id, fresh

    def _publish_visual(self) -> None:
        vision = self._providers.get("vision")
        _, camera_stamp, frame_id, camera_fresh = self._camera_state()
        raw: dict[str, Any] = {}
        if camera_fresh and vision is not None and vision.is_available():
            try:
                observation = vision.get_observation()  # type: ignore[attr-defined]
                if isinstance(observation, dict):
                    raw = observation
            except Exception as exc:
                self.get_logger().error(f"Human observation failed: {exc}")

        event = normalize_visual_event(raw)
        target_snapshot = self._target_manager.get_snapshot()
        vision_epoch = str(target_snapshot.get("vision_epoch", self._vision_epoch))
        candidates = [
            item.to_dict() if hasattr(item, "to_dict") else copy.deepcopy(item)
            for item in target_snapshot.get("human_candidates", [])
            if isinstance(item, dict) or hasattr(item, "to_dict")
        ]
        raw_candidates = {
            str(item.get("target_id", "")): item
            for item in raw.get("human_candidates", [])
            if isinstance(item, dict) and item.get("target_id")
        }
        for candidate in candidates:
            source = raw_candidates.get(str(candidate.get("target_id", "")), {})
            candidate["pose_action"] = str(source.get("pose_action", ""))
            candidate["pose_action_label"] = str(source.get("pose_action_label", ""))
        active_value = target_snapshot.get("active_target")
        active = active_value.to_dict() if hasattr(active_value, "to_dict") else {}
        active["vision_epoch"] = vision_epoch
        raw_active = raw.get("active_target", {})
        if (
            isinstance(raw_active, dict)
            and raw_active.get("target_id") == active.get("target_id")
            and active.get("tracking_state") == "tracking"
        ):
            active["pose_action"] = str(raw_active.get("pose_action", ""))
            active["pose_action_label"] = str(raw_active.get("pose_action_label", ""))
        else:
            active["pose_action"] = ""
            active["pose_action_label"] = ""

        candidate_by_track = {
            int(item.get("track_id", -1)): item
            for item in candidates
            if int(item.get("track_id", -1) or -1) > 0
        }
        visible_humans: list[dict[str, Any]] = []
        normalized_humans = event.get("humans", [])
        if camera_fresh and isinstance(normalized_humans, list):
            for item in normalized_humans:
                if not isinstance(item, dict):
                    continue
                try:
                    track_id = int(item.get("track_id", 0) or 0)
                except (TypeError, ValueError):
                    track_id = 0
                if track_id <= 0:
                    try:
                        box = tuple(
                            float(item.get(key, 0.0))
                            for key in ("x", "y", "w", "h")
                        )
                    except (TypeError, ValueError):
                        continue
                    candidate = max(
                        candidates,
                        key=lambda row: _ObjectTargetTracker._iou(
                            tuple(row.get("bbox", (0.0, 0.0, 0.0, 0.0))), box
                        ),
                        default={},
                    )
                    track_id = int(candidate.get("track_id", 0) or 0)
                candidate = candidate_by_track.get(track_id)
                if candidate is None or candidate.get("tracking_state") != "tracking":
                    continue
                human = copy.deepcopy(item)
                human["track_id"] = track_id
                visible_humans.append(human)
        with self._state_lock:
            self._visual_sequence += 1
            sequence = self._visual_sequence
            event_stamp = camera_stamp if camera_stamp > 0.0 else time.time()
            event["header"] = {"stamp": event_stamp, "frame_id": frame_id or "camera_link"}
            event["vision_epoch"] = vision_epoch
            event["sequence"] = sequence
            event["snapshot_id"] = f"{vision_epoch}:{sequence}"
            event["active_target"] = active
            event["human_candidates"] = candidates
            event["humans"] = visible_humans
            self._visual_snapshot = copy.deepcopy(event)
            self._visual_snapshot_monotonic = time.monotonic()
        message = String()
        message.data = json.dumps(event, ensure_ascii=False)
        self._visual_pub.publish(message)

    @staticmethod
    def _finite(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _query_targets(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock:
            snapshot = copy.deepcopy(self._visual_snapshot)
            cached_at = self._visual_snapshot_monotonic
        if not snapshot or snapshot.get("sequence", 0) <= 0 or cached_at <= 0.0:
            return {"ok": False, "error": "visual snapshot unavailable"}
        snapshot_age_ms = max(0.0, time.monotonic() - cached_at) * 1000.0
        current_timeout_ms = self._target_current_timeout_sec * 1000.0
        for item in [snapshot.get("active_target", {}), *snapshot.get("human_candidates", [])]:
            if not isinstance(item, dict):
                continue
            age = self._finite(item.get("last_seen_age_ms"))
            if age is None or age < 0:
                item["tracking_state"] = "lost"
                item["range_valid"] = False
                item["distance_m"] = None
                continue
            age += snapshot_age_ms
            item["last_seen_age_ms"] = round(age, 1)
            if age > current_timeout_ms:
                item["tracking_state"] = "temporarily_lost"
                item["range_valid"] = False
                item["distance_m"] = None
                pose_3d = item.get("pose_3d")
                if isinstance(pose_3d, dict):
                    pose_3d.update({"valid": False, "x": None, "y": None, "z": None})

        requested = params.get("target_types", ["human"])
        if isinstance(requested, str):
            requested = [requested]
        allowed = {
            str(value).strip().lower()
            for value in requested if str(value).strip()
        } if isinstance(requested, list) else {"human"}
        minimum_confidence = self._finite(params.get("min_confidence", 0.0))
        if minimum_confidence is None:
            minimum_confidence = 0.0
        maximum_age = self._finite(params.get("max_age_ms"))
        humans: list[dict[str, Any]] = []
        if "human" in allowed or "person" in allowed:
            for candidate in snapshot.get("human_candidates", []):
                confidence = self._finite(candidate.get(
                    "detection_confidence", candidate.get("confidence", 0.0)
                )) or 0.0
                age = self._finite(candidate.get("last_seen_age_ms"))
                if confidence < max(0.0, min(1.0, minimum_confidence)):
                    continue
                if maximum_age is not None and (age is None or age > maximum_age):
                    continue
                humans.append(candidate)
        return {
            "ok": True,
            "schema_version": int(snapshot.get("schema_version", 1)),
            "header": snapshot.get("header", {}),
            "vision_epoch": str(snapshot.get("vision_epoch", "")),
            "sequence": int(snapshot.get("sequence", 0)),
            "snapshot_id": str(snapshot.get("snapshot_id", "")),
            "snapshot_age_ms": round(snapshot_age_ms, 1),
            "targets": copy.deepcopy(humans),
            "human_candidates": copy.deepcopy(humans),
            "animal_candidates": [],
            "object_candidates": [],
            "active_target": copy.deepcopy(snapshot.get("active_target", {})),
        }

    def _locate_person_once(self, params: dict[str, Any]) -> dict[str, Any]:
        target_id = str(params.get("target_id", "") or "").strip()
        if not target_id:
            return {
                "ok": False,
                "error_code": "person_target_not_found",
                "error": "target_id is required",
                "target_id": target_id,
            }
        target = self._target_manager.get_current_target(
            target_id=target_id,
            current_timeout=self._target_current_timeout_sec,
        )
        if target is None:
            return {
                "ok": False,
                "error_code": "person_target_not_found",
                "error": "target is missing or no longer current",
                "target_id": target_id,
            }
        return {"ok": True, "target_id": target_id, "target": target}

    def _detection_params(self, params: dict[str, Any]) -> dict[str, Any]:
        labels = ObjectDetectionSessionManager.normalize_target_labels(
            params.get("target_labels")
        )
        confidence = self._finite(params.get("confidence", self._object_default_confidence))
        if confidence is None or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        return {"confidence": confidence, "target_labels": labels}

    def _frame_for_detection(self) -> tuple[np.ndarray | None, float, str, bool]:
        frame, stamp, frame_id, fresh = self._camera_state()
        if not fresh or frame is None:
            return None, stamp, frame_id, False
        selected, _ = select_camera_view(
            frame,
            stereo_enabled=self._stereo_enabled,
            view=self._stereo_view,
            min_aspect_ratio=self._stereo_min_aspect_ratio,
        )
        return selected, stamp, frame_id, True

    def _run_object_detection(
        self,
        params: dict[str, Any],
        *,
        source: str,
        wait_for_slot: bool,
        stream: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        detector = self._providers.get("object")
        if detector is None or not detector.is_available():
            return {"ok": False, "error": "object detector unavailable"}
        acquired = self._object_inference_lock.acquire(blocking=wait_for_slot)
        if not acquired:
            return {"ok": False, "busy": True, "error": "object detector busy"}
        started = time.perf_counter()
        try:
            if source == "stream":
                current = self._object_stream.snapshot()
                if (
                    not current.get("active")
                    or current.get("session_id") != (stream or {}).get("session_id")
                ):
                    return {"ok": False, "error": "object detection session is no longer active"}
            frame, stamp, frame_id, fresh = self._frame_for_detection()
            if not self._vision_is_mock and not fresh:
                error = "camera frame unavailable or stale"
                latency = (time.perf_counter() - started) * 1000.0
                self._record_object_result(
                    [], source=source, status="error", latency_ms=latency,
                    error=error, observation_stamp=stamp, frame_id=frame_id,
                    stream=stream, request=self._object_request_metadata(params),
                )
                return {"ok": False, "error": error}
            detections = detector.detect_objects(frame, params)  # type: ignore[attr-defined]
            latency = (time.perf_counter() - started) * 1000.0
            error = str(getattr(detector, "last_error", ""))
            if error:
                self._record_object_result(
                    [], source=source, status="error", latency_ms=latency,
                    error=error, observation_stamp=stamp, frame_id=frame_id,
                    stream=stream, request=self._object_request_metadata(params),
                )
                return {"ok": False, "error": error}
            objects = self._record_object_result(
                [dict(item) for item in detections if isinstance(item, dict)],
                source=source,
                status="ok",
                latency_ms=latency,
                observation_stamp=stamp,
                frame_id=frame_id,
                stream=stream,
                request=self._object_request_metadata(params),
            )
            return {"ok": True, "objects": objects}
        except Exception as exc:
            latency = (time.perf_counter() - started) * 1000.0
            self._record_object_result(
                [], source=source, status="error", latency_ms=latency,
                error=str(exc), stream=stream,
                request=self._object_request_metadata(params),
            )
            return {"ok": False, "error": str(exc)}
        finally:
            self._object_inference_lock.release()

    @staticmethod
    def _object_request_metadata(params: dict[str, Any]) -> dict[str, Any]:
        try:
            labels = ObjectDetectionSessionManager.normalize_target_labels(
                params.get("target_labels")
            )
        except ValueError:
            labels = []
        confidence = VisionDemoNode._finite(params.get("confidence"))
        return {"target_labels": labels, "confidence": confidence}

    def _record_object_result(
        self,
        detections: list[dict[str, Any]],
        *,
        source: str,
        status: str,
        latency_ms: float,
        error: str = "",
        observation_stamp: float | None = None,
        frame_id: str | None = None,
        stream: dict[str, Any] | None = None,
        request: dict[str, Any] | None = None,
        stop_reason: str = "",
    ) -> list[dict[str, Any]]:
        now_monotonic = time.monotonic()
        published_at = time.time()
        with self._state_lock:
            self._object_sequence += 1
            sequence = self._object_sequence
            resolved_stamp = (
                observation_stamp
                if observation_stamp is not None and observation_stamp > 0.0
                else published_at
            )
            resolved_frame_id = frame_id or self._latest_camera_frame_id or "camera_link"
            if status == "ok":
                objects = self._object_tracker.update(
                    detections,
                    now=now_monotonic,
                    stamp=resolved_stamp,
                    frame_id=resolved_frame_id,
                    sequence=sequence,
                )
            else:
                self._object_tracker.clear()
                objects = []
        if stream is None:
            stream = self._object_stream.snapshot()
        payload = {
            "schema_version": 2,
            "header": {"stamp": resolved_stamp, "frame_id": resolved_frame_id},
            "published_at": published_at,
            "sequence": sequence,
            "source": source,
            "status": status,
            "stream": dict(stream),
            "request": dict(request or {}),
            "stop_reason": stop_reason,
            "inference_latency_ms": round(float(latency_ms), 3),
            "objects": objects,
            "error": error,
        }
        message = String()
        message.data = json.dumps(payload, ensure_ascii=False)
        self._object_pub.publish(message)
        return copy.deepcopy(objects)

    def _set_object_detection(self, params: dict[str, Any]) -> dict[str, Any]:
        enabled = params.get("enabled")
        detector = self._providers.get("object")
        if enabled is True and (detector is None or not detector.is_available()):
            return {
                "ok": False,
                "error": "object detector unavailable",
                "stream": self._object_stream.snapshot(),
            }
        before = self._object_stream.snapshot()
        if enabled is False:
            with self._object_inference_lock:
                result = self._object_stream.configure(params)
                if result.get("ok") and before.get("active"):
                    terminal = dict(before)
                    terminal.update({"active": False, "lease_remaining_sec": 0.0})
                    self._record_object_result(
                        [], source="control", status="stopped", latency_ms=0.0,
                        stream=terminal, stop_reason="requested",
                    )
                return result
        return self._object_stream.configure(params)

    def _poll_objects(self) -> None:
        decision = self._object_stream.poll()
        state = str(decision.get("state", "inactive"))
        if state == "expired":
            self._record_object_result(
                [], source="control", status="stopped", latency_ms=0.0,
                stream=decision.get("stream"),
                stop_reason=str(decision.get("stop_reason", "lease_expired")),
            )
            return
        if state != "due":
            return
        self._run_object_detection(
            dict(decision.get("params", {})),
            source="stream",
            wait_for_slot=False,
            stream=decision.get("stream"),
        )

    def _run_task(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        if task_type == "query_targets":
            return self._query_targets(params)
        if task_type == "locate_person_once":
            return self._locate_person_once(params)
        if task_type == "detect_objects":
            try:
                detection_params = self._detection_params(params)
            except (TypeError, ValueError) as exc:
                return {"ok": False, "error": str(exc)}
            return self._run_object_detection(
                detection_params,
                source="service",
                wait_for_slot=True,
                stream=self._object_stream.snapshot(),
            )
        if task_type == "set_object_detection":
            return self._set_object_detection(params)
        if task_type == "get_object_detection_state":
            return {
                "ok": True,
                "stream": self._object_stream.snapshot(),
                "automatic_stream": {
                    "active": False,
                    "session_id": "",
                    "rate_hz": 0.0,
                    "confidence": None,
                    "target_labels": [],
                    "lease_remaining_sec": None,
                },
            }
        return {"ok": False, "error": f"unsupported task_type: {task_type}"}

    def _handle_task(self, request: Any, response: Any) -> Any:
        started = time.perf_counter()
        response.task_id = request.task_id
        response.task_type = request.task_type
        response.success = False
        response.result_json = ""
        response.error_message = ""
        try:
            params: Any = json.loads(request.params_json or "{}")
            if isinstance(params, list):
                params = {
                    str(item.get("key", "")): item.get("value")
                    for item in params if isinstance(item, dict)
                }
            if not isinstance(params, dict):
                params = {}
            result = self._run_task(str(request.task_type), params)
            response.success = bool(result.get("ok", True))
            response.result_json = json.dumps(result, ensure_ascii=False)
            if not response.success:
                response.error_message = str(result.get("error", "task failed"))
        except Exception as exc:
            response.error_message = str(exc)
        response.latency_ms = (time.perf_counter() - started) * 1000.0
        return response

    def close(self) -> None:
        before = self._object_stream.snapshot()
        if before.get("active"):
            with self._object_inference_lock:
                stopped = self._object_stream.configure({
                    "enabled": False,
                    "session_id": str(before.get("session_id", "")),
                })
                if stopped.get("ok"):
                    terminal = dict(before)
                    terminal.update({"active": False, "lease_remaining_sec": 0.0})
                    self._record_object_result(
                        [], source="control", status="stopped", latency_ms=0.0,
                        stream=terminal, stop_reason="requested",
                    )
        for provider in self._providers.values():
            try:
                provider.stop()
            except Exception as exc:
                self.get_logger().warning(f"Provider shutdown failed: {exc}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the standalone vision demo node")
    parser.add_argument(
        "--config",
        default="config/vision.yaml",
        help="Vision YAML config (default: config/vision.yaml)",
    )
    args = parser.parse_args(argv)
    rclpy.init()
    node: VisionDemoNode | None = None
    executor: MultiThreadedExecutor | None = None
    try:
        node = VisionDemoNode(args.config)
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
