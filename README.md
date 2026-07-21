# MarsDog 2D ROS2 Viewer

Lightweight Arcade-based 2D visualization for MarsDog ROS2 event and state
topics. This is not a Gazebo physics simulation; it is a UI bridge for
perception events, internal needs, emotion state, behavior results, personality
state, and a virtual `/execute_behavior` Action execution environment.

## Install

For ROS2 Humble, use the same Python ABI as ROS2, then install Arcade into that
environment:

```bash
python3 -m pip install "arcade>=3.3.3"
```

If this repository is inside a ROS2 workspace:

```bash
colcon build --packages-select marsdog_sim2d
source install/setup.bash
ros2 run marsdog_sim2d arcade_viewer_node
```

For local development outside `ros2 run`, use the Python interpreter from the
sourced ROS2 environment, with Arcade installed for that same interpreter:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python main.py
```

Do not mix a Python 3.12 virtualenv with ROS2 Humble's Python 3.10 `rclpy`
binary extension.

## Subscribed Topics

All subscribed topics are `std_msgs/msg/String` containing a JSON object:

- `/perception/visual_event`
- `/perception/audio_event`
- `/internal_need/state`
- `/internal_need/signal_event`
- `/emotion/state`
- `/emotion/signal_event`
- `/behavior/result_event`
- `/personality/state`

Arcade runs on the main thread. `rclpy.spin()` runs on a background thread and
passes normalized events to the UI through `queue.Queue`.

## Virtual Execution

The current behavior-tree interface executes behavior through the ROS2 Action:

- `/execute_behavior`

When the `ExecuteBehavior` action type is available from `marsdog_interfaces`,
this viewer can act as the virtual Action Server. During execution it also
publishes the debug/visualization topics:

- `/debug/execute_behavior/goal`
- `/debug/execute_behavior/feedback`
- `/debug/execute_behavior/result`

Behavior tree goals are converted into lightweight room motion scripts. The
virtual dog can move toward the user, food bowl, sleep mat, toilet pad, toy,
charger, and grooming mat. Action feedback and debug topic feedback are
published at 10Hz.

Do not run `marsdog_action_executor action_executor_node` or another
`/execute_behavior` server at the same time when using this viewer as the
executor.

If you want to run the real `marsdog_action_executor` and use this viewer only as
a room visualizer, disable the viewer's Action Server:

```bash
MARSDOG_SIM2D_ACTION_SERVER=0 UV_CACHE_DIR=/tmp/uv-cache uv run python main.py
```

Manual Action test:

```bash
ros2 action send_goal /execute_behavior marsdog_interfaces/action/ExecuteBehavior \
  "{goal_id: 'sim_test_001', behavior_name: 'seekFood', priority_level: 4, params_json: '{}', timeout_sec: 4.0}" \
  --feedback
```

The v2 executor uses canonical behavior names such as `eatNormally`,
`eatExcitedly`, `defecate`, `sleepNow`, `cleanSelf`, `recharge`, `exploreRoom`,
`inspectObject`, `seekHumanInteraction`, and `expressJoy`. Older names remain
supported by the viewer's visual alias map.

The viewer always subscribes to the current `/debug/execute_behavior/*` topics
and the deprecated `/execute_behavior/*` mirror topics. Duplicate messages are
filtered automatically. If an external `marsdog_action_executor` is running,
start the viewer with `MARSDOG_SIM2D_ACTION_SERVER=0` so it only visualizes that
executor instead of registering a second Action Server.

Set `MARSDOG_LEGACY_DEBUG_TOPICS=1` only when the viewer itself is the Action
Server and must additionally publish the deprecated no-prefix debug topics.

Local motion self-test inside the Arcade window:

- `T`: exploreRoom
- `F`: seekFood
- `S`: sleepNow
- `C`: seekInteraction
- `W`: fast tail wag
- `P`: spin in circle
- `G`: cleanSelf
- `E`: defecate
- `R`: recharge
- `H`: hideAway

If these keys move the dog but ROS goals do not, the animation path is healthy
and `/execute_behavior` Action goals are not reaching this viewer.

## Runtime Diagnostics

The console follows the debugging flow from left to right:

- The left panel creates manual input.
- The center home scene uses a top-down indoor floor plan with living, feeding,
  care, play, and utility areas. It overlays the robot, targets, path, heading,
  and optional perception field of view without changing scene coordinates.
- The right panel explains the current behavior, decision trace, need state,
  emotion state, and perception summary.
- The top bar summarizes VIS, AUDIO, NEED, EMO, and EXEC health and rate. Hover a
  health item for topic, count, and age details.
- The bottom event stream provides filters, search, pause, clear, auto-scroll,
  repeated-event folding, and raw JSON inspection/copy.

`Current Behavior` combines behavior-tree results, `/execute_behavior` feedback,
and animation state. It shows behavior, current ACT, numbered step strip,
progress, target, mode, interrupt safety, and execution status. Click the card
body to reveal goal, source, priority, raw feedback message, and result context.
Click card headers to collapse them, and scroll the right column to reach lower
cards.

The window is resizable. At small widths the input panel becomes a narrow tab
rail so the situation view and Current Behavior remain visible. Drag the handle
above the event stream to change its height.

The scene dog uses six transparent golden-retriever puppy sprites: stand, walk,
sit, lie, play bow, and raised paw. The renderer selects a pose from the current
ACT while keeping the existing behavior and ROS2 payload logic unchanged. The
source atlas and runtime sprites live in `marsdog_sim2d/assets/dog/`.

The indoor scene uses the hand-painted apartment master image at
`marsdog_sim2d/assets/backgrounds/apartment_floorplan_source.png`. Arcade loads
the optimized runtime copy from the same directory; if that asset is missing,
the renderer falls back to the original programmatic room drawing.

The room user is a stable scene anchor. Moving perception bounding boxes are
drawn as observation markers and do not move the user avatar. A manually placed
and sent human Vision target intentionally updates that anchor. Local interaction
visualization stops the dog at pose-specific contact distances; hand actions
align the raised paw with the user's extended hand, while follow keeps a wider
offset behind the stationary user marker.

## Manual Event Injection

The left input panel contains four tabs:

Field labels and option names are shown in Chinese. Selectable enums use compact
radio groups; the documented ROS2 values remain unchanged and are visible in
tooltips and the Payload preview.

- `Event`: choose Audio, Vision, or Result, edit the dynamic parameters, inspect
  the publish Topic and JSON preview, then send.
- `State`: simulate Need, Emotion, or Personality engine output. Need and
  Emotion accept only the state item and `0-100` value; the documented level,
  range, and signal event are derived automatically.
- `Command`: choose a voice command or use the Sit, Come, Hand, Follow, and Stop
  shortcuts, with shared ASR, speaker, and confidence fields.
- `Scenario`: run High Hunger, Low Energy, Owner Calls Dog, Joy Interaction,
  Fear Response, or Explore Toy as a batch of existing manual injections.

Critical simulated outputs and scenarios require confirmation.

For Vision input, select `Place target on map`, then click the situation view.
For Audio input, `Place sound source` derives the existing wake angle from the
clicked point. The pending object is drawn as a dashed preview with type,
position, and confidence. Sending uses only coordinate fields already present
in the documented payload.

Click a field to focus it, type a value, use `Backspace` / `Delete` to edit,
`Tab` to move to the next field, and `Enter` to send or publish the current form.

- Audio publishes perception-style input on `/perception/audio_event`, including
  editable `event_type`, ASR text, command id, wake angle, speaker id, and
  confidence.
- Vision publishes perception-style input on `/perception/visual_event`,
  including editable event lists, active target identity/pose, and visible
  object label.
- Need publishes simulated need-engine outputs on `/internal_need/state` and
  `/internal_need/signal_event`. Each demand uses its own documented threshold
  and `gt` / `lt` operator to derive `NORMAL`, `TRIGGERED`, or `OVERFLOW`.
- Emotion publishes a simulated `/emotion/state` snapshot and publishes
  `/emotion/signal_event` only when the value belongs to a documented interval.
  Values at `NONE` do not create an undocumented `EMO_*_NONE` event.
- Result publishes behavior result feedback on `/behavior/result_event`, with
  editable `ACTION_*`, demand, result type, and metadata JSON. Leave demand as
  `auto` to use the documented `ACTION_* -> demand_type` mapping.
- Personality publishes `/personality/state` using transient-local QoS, with
  editable profile and A/O/E/C values. This simulates personality-node output;
  persistent changes to `personality_node` must use its ROS2 parameter service.

`/internal_need/state` and `/emotion/state` are output topics, not setters for
the calculation nodes. Manual snapshots can be consumed by subscribers but do
not change the engines' internal values and will be superseded by their regular
1 Hz output. The corresponding `signal_event` is the event-driven behavior-tree
test input.

The viewer ignores its own simulated `/internal_need/state` and
`/emotion/state` echoes when updating the gauges, so the state panels continue
to represent the real need/emotion nodes when those nodes are running.

Use these controls to drive the behavior tree manually, then watch
`/execute_behavior` feedback and the 2D situation view. For interactive tests,
place and send an owner Vision target before voice or social events so the
behavior layer has a current target cached.

This viewer subscribes to ROS2 topics and can host `/execute_behavior` as a
virtual Action Server. It does not call the `/perception/perception_task` service
yet.

If the page opens but state does not change, first confirm messages exist in the
same ROS environment:

```bash
ros2 topic echo /emotion/state --once
ros2 topic echo /internal_need/state --once
ros2 topic echo /perception/audio_event --once
```

If perception changes but the dog never moves:

```bash
ros2 action list
ros2 action info /execute_behavior
ros2 topic echo /debug/execute_behavior/goal
ros2 topic echo /debug/execute_behavior/feedback
ros2 topic echo /debug/execute_behavior/result
```

The viewer should be the only `/execute_behavior` server when used as the virtual
execution environment. If an external `action_executor_node` is running, the
viewer should be started with `MARSDOG_SIM2D_ACTION_SERVER=0` and will only
mirror its debug topics.

When running through `ros2 run`, rebuild and source the workspace after code
changes. For immediate source-tree testing, prefer:

```bash
source /opt/ros/humble/setup.bash
UV_CACHE_DIR=/tmp/uv-cache uv run python main.py
```
