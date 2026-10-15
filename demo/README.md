# Standalone vision demo

This process replaces the full `vision_interaction` node for the object and
human-target APIs listed below. It does not start the full node or camera
driver. A real camera driver must be started separately and publish the image
topic configured in `config/vision.yaml`.

## Start

Source ROS 2 Humble and the workspace overlay so both `rclpy` and the generated
`VisionTask` service type are available, then run:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
demo/run_demo.sh
```

The launcher uses the repository's existing `.venv` through `uv`. To select a
different vision YAML, pass `--config PATH` to the launcher.

## Interfaces

- Service: `/perception/vision/task` (`marsdog_vision_interaction/srv/VisionTask`)
- Human boxes: `/perception/visual_event` (`std_msgs/msg/String`, JSON)
- Object results: `/perception/vision/object_detections` (`std_msgs/msg/String`, schema v2 JSON)
- Tasks: `detect_objects`, `set_object_detection`,
  `get_object_detection_state`, `query_targets`, and `locate_person_once`.

The demo adds an optional `event_lifecycle[]` array to each
`/perception/visual_event` JSON snapshot. It maps a confirmed `owner` to
`EVT_VISION_MASTER`, a confirmed `family_member_1` through `family_member_4`
to `EVT_VISION_FAMILY_PRESENT`, and `confirmed_unknown` to
`EVT_VISION_STRANGER`. Candidate and unverified identities do not create
presence events. Each item contains `event_name`, `state`, and positive face
`track_id`.

生命周期输入来自最近一次成功推理的全量人脸身份快照，并同时要求相机和推理结果新鲜；
识别推理失败或快照超过 `camera_stale_timeout_sec` 后会按未识别计时，避免沿用旧身份。
这不会改变 `faces[]` 的主目标视图，也不依赖可选 `debug_faces[]`。

Lifecycle timing uses monotonic time and defaults to 1 second stable presence
for `ENTER`, 2 seconds continuously unrecognized for `EXIT`, and a 3 second
same-track cooldown after `EXIT`. While active, each approximately 10 Hz visual
snapshot reports `HOLD`, including the exit grace period. Consumers may trigger
a one-shot direct-drive behavior on `ENTER`; `HOLD` must not repeat it, and
`EXIT` closes the presence state. Configure these durations in the root-level
`face_presence_events` section of `config/vision.yaml`. The existing `events[]`
string array remains unchanged.

Object detection sessions default to 2 Hz, are limited to 5 Hz, and use the
configured lease defaults (normally 3 seconds). `query_targets` returns the
same full `target_id` and normalized bbox used by `locate_person_once`.

## Mock verification

After sourcing the same ROS environment, run:

```bash
uv run --project . python -m demo.mock_smoke_test
```

The validator starts only this demo with `config/vision.mock.yaml` in a
temporary ROS domain. It needs no camera driver or model files.
