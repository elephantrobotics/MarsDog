# Design: Face presence event lifecycle in standalone demo

## Scope and boundaries

Add the lifecycle reducer at the standalone demo's visual publication boundary. Reuse the existing `VisionObservationProvider` face observations and confirmation state machine. Do not change the full `VisionInteractionNode`, face models, recognition throttle, target manager, enrollment manager, service definitions, or legacy `events[]` behavior.

## Data flow

```text
VisionObservationProvider latest successful inference
  -> read-only all-face identity snapshot + monotonic completion time
  -> demo freshness gate (camera and observation)
  -> confirmed identity + positive face track_id filter
  -> FacePresenceEventTracker (monotonic time, per event_name/track_id)
  -> event_lifecycle[] on standalone demo visual_event JSON
  -> existing ROS publisher and cached Web status snapshot
```

The provider's new read-only accessor preserves every face row from the latest successful inference for lifecycle use; the existing public `faces[]` projection remains primary-target-only where it is today, and debug overlays do not become a business-data dependency. The accessor includes a monotonic completion timestamp because `get_observation()` retains its previous cache after failed inference. The demo rejects snapshots older than `camera_stale_timeout_sec`, even when camera frames continue arriving. The shared visual-event normalizer will accept and validate `event_lifecycle[]` entries when present. Producers that do not implement this feature may omit the field; legacy `events[]` remains a list of strings and is not rewritten.

## Eligibility and mapping

- Require `track_id > 0`.
- Map `identity_state=confirmed_known` plus `recognized_user=owner` to `EVT_VISION_MASTER`.
- Map `identity_state=confirmed_known` plus a fixed `family_member_1` through `family_member_4` identity to `EVT_VISION_FAMILY_PRESENT`.
- Map `identity_state=confirmed_unknown` to `EVT_VISION_STRANGER`; the provider represents confirmed unknown with an empty `recognized_user`, so map from `identity_state`, not the user string.
- Ignore candidate, unverified and other identity states. Do not introduce a second confidence threshold; YuNet/SFace quality and identity thresholds remain authoritative.

Maintain independent state keyed by `(event_name, track_id)`, so multiple faces do not share timers. Use every face row in the provider snapshot, not the primary-only public `faces[]` or optional `debug_faces[]`. A geometric track ID is not treated as a person's immutable identity. If its confirmed event classification changes, the old event becomes absent and follows its exit grace while the new event begins its own enter dwell.

## Lifecycle timing

Use `time.monotonic()` and initial configurable values `t_enter=1.0s`, `t_exit=2.0s`, `t_retrigger=3.0s`.

- An eligible key starts an enter dwell. A loss or identity-state ineligibility before entry resets that pending dwell.
- When an eligible key has remained continuous for `t_enter`, emit `ENTER` once.
- For every subsequent 10 Hz visual snapshot while active, emit `HOLD`. During the `t_exit` grace, continue `HOLD`; if the same key returns before expiry, clear its missing timer and continue the existing lifecycle.
- Once the key has been absent/ineligible for `t_exit`, emit `EXIT` once and begin that key's `t_retrigger` cooldown.
- If the key reappears before cooldown expiry, begin a fresh enter dwell but emit no lifecycle item until both the dwell and cooldown have completed. This means the earliest next `ENTER` satisfies both minimum durations.
- On camera staleness or when the latest successful inference snapshot is older than the camera stale timeout, pass no eligible faces to the tracker. The normal exit grace then applies.

The producer sends state declarations; downstream behavior must use `ENTER` for one-shot direct-drive triggering and must not treat `HOLD` as a repeated direct-drive command. `EXIT` closes the current presence state. Instantaneous action `TRIGGER` events are outside this task.

## Payload

Each lifecycle item has the minimal confirmed contract:

```json
{"event_name":"EVT_VISION_MASTER","state":"ENTER","track_id":12}
```

`event_lifecycle[]` contains the new `ENTER`/`EXIT` transition plus `HOLD` declarations for active keys in deterministic order. No lifecycle record is emitted for a pending enter, a key in cooldown, or an event after its one `EXIT`. Existing `events[]` values remain exactly as the current producer provides them.

## Configuration and files

Add a small root-level `face_presence_events` config block in `config/vision.yaml`; missing keys use the approved defaults. Keep the reducer configurable for deployment-specific time calibration while preserving the user's `1/2/3s` starting values. Add `VisionObservationProvider.get_face_presence_snapshot() -> tuple[list[dict[str, Any]], float]`, returning all latest successful face identity rows and their monotonic completion time without changing the existing public observation shape. Update `visual_event.py` to normalize optional lifecycle rows without changing the existing schema version or event string normalization. Add the lifecycle reducer under `marsdog_vision_interaction/core/` and wire it in `demo/vision_demo_node.py`.

Document the optional field and its timing/consumer semantics in `docs/ROS2_CONTRACT.md`, the ROS interface reference/manifest, and standalone demo documentation. The contract must clearly distinguish the new demo lifecycle array from the legacy repeated `events[]` string array used by existing producers.

## Compatibility and failure behavior

- Keep `events[]` a string list and preserve its contents.
- Keep `schema_version=1`; the field is additive and consumers should ignore it if unknown.
- A face without a valid geometric track ID or with an unconfirmed identity cannot start a lifecycle.
- A model or camera outage cannot create an identity. Existing active lifecycle entries close only through the configured exit grace after observations cease.
- Restarting the demo resets in-memory lifecycle timers; the next qualified stable observation begins a new enter dwell.

## Rollback

The demo can stop attaching `event_lifecycle[]` and the lifecycle reducer/config can be removed without touching existing `events[]`, model providers, or task interfaces. The shared normalizer will remain backward compatible with payloads lacking the new field.
