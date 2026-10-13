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
