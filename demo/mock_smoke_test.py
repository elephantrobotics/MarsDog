"""End-to-end ROS smoke check for the standalone demo using mock providers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from marsdog_vision_interaction.srv import VisionTask


ROOT = Path(__file__).resolve().parents[1]
TOPIC_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class SmokeClient(Node):
    def __init__(self) -> None:
        super().__init__("vision_demo_smoke_client")
        self.client = self.create_client(VisionTask, "/perception/vision/task")
        self.visual_messages: list[dict] = []
        self.object_messages: list[dict] = []
        self.create_subscription(
            String,
            "/perception/visual_event",
            lambda message: self._append(self.visual_messages, message),
            TOPIC_QOS,
        )
        self.create_subscription(
            String,
            "/perception/vision/object_detections",
            lambda message: self._append(self.object_messages, message),
            TOPIC_QOS,
        )

    @staticmethod
    def _append(target: list[dict], message: String) -> None:
        try:
            value = json.loads(message.data)
        except (TypeError, ValueError):
            return
        if isinstance(value, dict):
            target.append(value)

    def spin_until(self, predicate, timeout: float, description: str) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            rclpy.spin_once(self, timeout_sec=0.1)
        raise RuntimeError(f"Timed out waiting for {description}")

    def call_task(
        self,
        task_type: str,
        params: dict,
        *,
        success: bool = True,
        timeout: float = 8.0,
    ) -> dict:
        request = VisionTask.Request()
        request.task_id = uuid.uuid4().hex
        request.task_type = task_type
        request.params_json = json.dumps(params)
        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        response = future.result()
        if response is None:
            raise RuntimeError(f"Timed out calling {task_type}")
        result = json.loads(response.result_json) if response.result_json else {}
        if response.success is not success:
            raise RuntimeError(
                f"{task_type} success={response.success}, expected {success}: "
                f"{result or response.error_message}"
            )
        return result


def _run_smoke() -> None:
    domain_id = 20 + (os.getpid() % 190)
    env = os.environ.copy()
    env["ROS_DOMAIN_ID"] = str(domain_id)
    env["ROS_LOCALHOST_ONLY"] = "1"
    env.setdefault("PYTHONUNBUFFERED", "1")
    command = [
        str(ROOT / "demo" / "run_demo.sh"),
        "--config",
        str(ROOT / "config" / "vision.mock.yaml"),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    os.environ.update({"ROS_DOMAIN_ID": str(domain_id), "ROS_LOCALHOST_ONLY": "1"})
    client: SmokeClient | None = None
    try:
        rclpy.init()
        client = SmokeClient()
        client.spin_until(client.client.service_is_ready, 10.0, "VisionTask service")
        client.spin_until(
            lambda: any(message.get("humans") for message in client.visual_messages),
            5.0,
            "a visual_event with a human bbox",
        )
        event = next(message for message in reversed(client.visual_messages) if message.get("humans"))
        human = event["humans"][0]
        assert int(human["track_id"]) > 0
        assert all(0.0 <= float(human[key]) <= 1.0 for key in ("x", "y", "w", "h"))

        queried = client.call_task("query_targets", {"target_types": ["human"]})
        candidates = queried.get("human_candidates", [])
        assert candidates, f"query_targets returned no human_candidates: {queried}"
        candidate = candidates[0]
        target_id = candidate["target_id"]
        bbox = candidate["bbox"]
        assert target_id.startswith(f"{queried['vision_epoch']}:human:")
        assert len(bbox) == 4
        assert all(0.0 <= float(value) <= 1.0 for value in bbox)
        assert float(bbox[0]) + float(bbox[2]) <= 1.0 + 1e-6
        assert float(bbox[1]) + float(bbox[3]) <= 1.0 + 1e-6
        located = client.call_task("locate_person_once", {"target_id": target_id})
        assert located["target_id"] == target_id
        assert located["target"]["bbox"] == bbox
        missing = client.call_task(
            "locate_person_once",
            {"target_id": f"{queried['vision_epoch']}:human:999999"},
            success=False,
        )
        assert missing.get("error_code") == "person_target_not_found"

        state_before = client.call_task("get_object_detection_state", {})
        assert not state_before["stream"]["active"]
        invalid_rate = client.call_task(
            "set_object_detection",
            {"enabled": True, "session_id": "smoke-rate-check", "rate_hz": 5.1},
            success=False,
        )
        assert "rate_hz" in invalid_rate.get("error", "")
        one_shot = client.call_task(
            "detect_objects",
            {"confidence": 0.3, "target_labels": ["dog toy ball"]},
        )
        assert one_shot.get("objects"), f"No mock objects returned: {one_shot}"
        assert one_shot["objects"][0]["target_id"].endswith(":object:1")
        client.spin_until(
            lambda: any(message.get("source") == "service" for message in client.object_messages),
            2.0,
            "source=service object result",
        )
        service_packet = next(
            message for message in reversed(client.object_messages)
            if message.get("source") == "service"
        )
        assert service_packet["schema_version"] == 2
        assert service_packet["objects"]
        state_after = client.call_task("get_object_detection_state", {})
        assert not state_after["stream"]["active"]

        session_id = "smoke-session-" + uuid.uuid4().hex[:8]
        started = client.call_task(
            "set_object_detection", {"enabled": True, "session_id": session_id}
        )
        assert started["stream"]["active"]
        assert started["stream"]["rate_hz"] == 2.0
        renewed = client.call_task(
            "set_object_detection",
            {"enabled": True, "session_id": session_id, "lease_sec": 4.0},
        )
        assert renewed["stream"]["lease_remaining_sec"] > 3.0
        client.call_task(
            "set_object_detection",
            {"enabled": False, "session_id": "wrong-owner"},
            success=False,
        )
        client.spin_until(
            lambda: any(message.get("source") == "stream" for message in client.object_messages),
            3.0,
            "source=stream result",
        )
        active_state = client.call_task("get_object_detection_state", {})
        assert active_state["stream"]["active"]
        stopped = client.call_task(
            "set_object_detection", {"enabled": False, "session_id": session_id}
        )
        assert stopped["stopped_session_id"] == session_id
        client.spin_until(
            lambda: any(
                message.get("source") == "control"
                and message.get("status") == "stopped"
                and message.get("stop_reason") == "requested"
                for message in client.object_messages
            ),
            2.0,
            "requested-stop control packet",
        )
        final_state = client.call_task("get_object_detection_state", {})
        assert not final_state["stream"]["active"]

        lease_id = "smoke-lease-" + uuid.uuid4().hex[:8]
        client.call_task(
            "set_object_detection",
            {"enabled": True, "session_id": lease_id, "lease_sec": 0.5},
        )
        client.spin_until(
            lambda: any(
                message.get("source") == "control"
                and message.get("status") == "stopped"
                and message.get("stop_reason") == "lease_expired"
                for message in client.object_messages
            ),
            2.0,
            "lease-expiry control packet",
        )
        expired_state = client.call_task("get_object_detection_state", {})
        assert not expired_state["stream"]["active"]
        unsupported = client.call_task("not_a_demo_task", {}, success=False)
        assert "unsupported task_type" in unsupported.get("error", "")

        print("PASS visual_event: normalized human box and positive track_id")
        print("PASS query_targets/locate_person_once: same full target_id and bbox")
        print("PASS locate_person_once: unknown current target fails")
        print("PASS detect_objects: one-shot result mirrors source=service; stream stays inactive")
        print("PASS object session: 2 Hz default, renewal, owner check, stream, requested stop, lease expiry")
    finally:
        if client is not None:
            client.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=4.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2.0)
        if process.returncode not in (0, -15, 143):
            output = process.stdout.read() if process.stdout is not None else ""
            if output:
                print("--- demo process output ---", file=sys.stderr)
                print(output, file=sys.stderr)


def main() -> None:
    if not os.environ.get("ROS_DISTRO"):
        raise SystemExit(
            "Source ROS 2 Humble and this workspace's install/setup.bash first."
        )
    try:
        _run_smoke()
    except Exception as exc:
        raise SystemExit(f"Vision demo mock smoke failed: {exc}") from exc


if __name__ == "__main__":
    main()
