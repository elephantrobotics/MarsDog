# Implementation plan

## Ordered checklist

1. [x] Add the `EVT_VISION_FAMILY_PRESENT` constant and implement a focused, ROS-independent `FacePresenceEventTracker` in `marsdog_vision_interaction/core/`. It maps only confirmed states, uses monotonic time, separates `(event_name, track_id)` state, and emits deterministic `ENTER`/`HOLD`/`EXIT` rows using the approved 1/2/3-second defaults.
2. [x] Add the approved `face_presence_events` default block to `config/vision.yaml`; implement safe defaults and bounded/validated durations for omitted or invalid config values.
3. [x] Extend `normalize_visual_event()` in `marsdog_vision_interaction/messages/visual_event.py` to normalize the optional `event_lifecycle[]` field: allow only the three supported event names and lifecycle states, require a positive integer `track_id`, and leave legacy `events[]` processing unchanged.
4. [x] Add `VisionObservationProvider.get_face_presence_snapshot()` as a read-only accessor for all detected faces' identity fields and the latest successful inference's monotonic completion time. Preserve the current public `faces[]` projection, debug settings, and identity state machine.
5. [x] Wire the tracker into `VisionDemoNode` in `demo/vision_demo_node.py`. At each visual publication, require fresh camera input and a face snapshot no older than the camera stale timeout (the explicit mock provider uses its current mock observation); attach lifecycle rows before caching and serialization. Do not change `VisionInteractionNode` or its event generation.
6. [x] Update `docs/ROS2_CONTRACT.md`, `docs/integration/ROS2_INTERFACES.md`, `docs/integration/interface_manifest.yaml`, and `demo/README.md` with the new demo field, mapping, initial timing, per-track behavior, state cadence, and consumer rules. Explicitly retain the existing `events[]` compatibility description.
7. [x] Review all touched files against the PRD, check the workspace diff for unrelated changes, and perform the repository's available non-test static checks for Python/config/document consistency.

## Validation record

- `python3 -m py_compile` passed for the lifecycle tracker, visual-event normalizer/types, and demo node.
- Python YAML parsing passed for `config/vision.yaml` and `docs/integration/interface_manifest.yaml`.
- `git diff --check` passed.
- Runtime and test-suite checks were not run in this implementation pass.
- Lifecycle now consumes the timestamped full-face provider snapshot; stale cached output and primary-target-only `faces[]` cannot sustain or suppress another face's lifecycle.

## Review gates

- The `T_exit` grace preserves `HOLD`; a valid same-key observation before expiry resumes the same lifecycle.
- Pending identities never publish an event before both confirmation and `T_enter`.
- `T_retrigger` is measured from `EXIT`; when the target returns during cooldown, its fresh `T_enter` and the remaining cooldown must both be satisfied.
- Two faces with the same event name remain independent by `track_id`; one face's lifecycle does not suppress another's.
- `event_lifecycle[]` is attached by the demo only. The shared normalizer does not inject it into unrelated producers that omit it.
- Existing `events[]` values and string item type remain unchanged.
- Existing user edits in README/config/docs/demo files are shared workspace changes; preserve them and make only scoped edits needed for this feature.

## Risk and rollback

- Risk: the 10 Hz publisher reads a cached latest observation while model inference can run at a different rate. Use the provider's monotonic successful-inference timestamp as well as the fresh-camera gate; do not count stale camera or inference snapshots as presence.
- Risk: `track_id` expresses geometric continuity and can be reused. Keep cooldown and lifecycle scoped to the requested `(event_name, track_id)`, and rely only on current confirmed identity rows.
- Rollback: remove the demo lifecycle tracker attachment/config and the optional normalizer field handling. Preserve the legacy event string list and existing provider pipeline.

## Static validation commands

After implementation, use the project Python environment to lint/compile only the changed Python modules and parse the edited YAML. Do not invoke ROS hardware/model inference as part of this contract change.
