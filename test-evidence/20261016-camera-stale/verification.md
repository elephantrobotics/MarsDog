# Camera stale fix verification — 2026-10-16

## Result

The Fast DDS fragment-cache ownership fix was built, installed, and loaded by
both live receivers. The deterministic regression fails on the original runtime
and passes on the patched runtime. Both receivers stayed fresh during a
120.019-second live observation (121 samples).

| Measurement | vision_demo | vision_debug_viewer |
|---|---:|---:|
| Before fix: last-frame age | 49,842,447.2 ms | 55,562,756.7 ms |
| After fix: median last-frame age | 20.6 ms | 19.3 ms |
| After fix: maximum last-frame age | 40.1 ms | 38.4 ms |
| Demo camera available | 121 / 121 samples | — |
| Median incoming FPS | — | 30.0 |

The demo's image source timestamp advanced by 120.002 seconds and advanced on
every sample. Its visual sequence advanced by 1,199. The stale threshold is
500 ms. This records the observed interval, not an indefinite stability claim.

## Root fix and build

Fast DDS 2.6.12 `StatelessReader::matched_writer_remove()` erased a writer's
incomplete `fragmented_change` without returning its payload and cache slot.
The project patch calls `releaseCache`, clears the pointer, then erases the
writer record. The sample has not entered ReaderHistory, so history cleanup
cannot reclaim it. With depth 1, two orphaned samples exhausted both cache slots.

- Patch: [0001-release-partial-change-on-writer-removal.patch](../../patches/fastdds/0001-release-partial-change-on-writer-removal.patch).
- Build/install command: `scripts/build_fastdds.sh`.
- Installed library:
  `/home/marsdog/.local/opt/marsdog-fastdds-2.6.12/lib/libfastrtps.so.2.6.12`.
- Patched library SHA-256:
  `3a1939d1249ecea32783754db6753d540c6c2dfe31897952aed98457418e1cbb`.
- System library SHA-256:
  `afe6588b08febeffce4c1fc6ad705726ef6c87a02c1adc9bdac22b9065c70258`.
- The generated `fastrtps/config.h` matches the installed Humble configuration
  byte-for-byte, including security, TLS and SQLite support. The SONAME remains
  `libfastrtps.so.2.6`; no public structure or signature changed.
- The system ROS installation was not replaced.

The build script was executed against the already-patched cached source and
completed, exercising patch reuse and incremental compilation. The project was
also reinstalled with:

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths . --packages-select marsdog_vision_interaction --symlink-install
```

Result: one package finished successfully.

## Native comparison

The same native regression uses domain 217 and UDP loopback only. It does not
publish anything to the live camera topic.

Original system runtime:

```bash
MARSDOG_FASTDDS_PREFIX=/opt/ros/humble tests/native/run_fastdds_fragment_cleanup_regression.sh
```

Expected failure, exit code 1:

```text
FAIL: cache pool exhausted after partial writer removal at cycle 2 (removed_by_lease=1)
```

Patched runtime:

```bash
tests/native/run_fastdds_fragment_cleanup_regression.sh
```

Exit code 0:

```text
PASS: 100 incomplete fragmented samples reclaimed across lease and explicit removals
PASS: repeated removal and no-fragment writer removals preserve cache availability
PASS: surviving writer delivered a complete sample after peer writer removal
```

The original three-cycle diagnostic program also changed from allocation
failure on cycles 2 and 3 to successful allocation on every cycle when loading
the patched library.

## Startup checks

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/python3 -m pytest -q -rs \
  tests/test_fastdds_overlay.py tests/test_fastdds_config.py tests/test_ros_entrypoint.py
```

Result: **14 passed**, no skipped launch tests. The project virtual environment
lacks `lark`, so the ROS launch tests were explicitly run with system ROS Python.

Coverage includes library precedence, missing or dangling SONAME, explicit
missing prefix, absent/incomplete default prefix, rollback, source and installed
environment helpers from an external working directory without PYTHONPATH, and
both launch actions. Ruff, helper mypy, shell syntax, strict native C++ syntax,
Python compilation and diff whitespace checks passed.

The actual installed environment helper was also sourced from `/tmp`, followed
by `ctypes.CDLL('libfastrtps.so.2.6')`; process maps resolved to the patched library.

## Live rollout and evidence

- `vision_demo`: PID 1330018 → **1680122**.
- `vision_debug_viewer`: PID 1296683 → **1680195**.
- Both were stopped with SIGINT and restarted with their existing Python,
  working directory, arguments and configuration plus the patched library path.
  `/proc/<pid>/maps` confirms the patched library in both processes.
- The local camera driver, PID **1327430**, was not restarted. An independent
  read-only C++ subscriber subsequently received 120 images in four seconds
  from local publisher GID `010f724d4641042900000000000011030000000000000000`.
  A Python subscriber received 121 valid 640×480 BGR8 images in four seconds.
- [Before state](before-fix-state.json), [live summary](live-after-fix-summary.json),
  and [all 121 live samples](live-after-fix-samples.jsonl) retain only freshness,
  sequence and timing facts; no image or biometric content is recorded.

The viewer runs from a separate Platform checkout. Its current process has the
patched environment. For future launches from that older checkout, source the
current repository's `scripts/fastdds_env.sh` before starting it; the updated
launch files in this repository and `demo/run_demo.sh` select the installed
overlay automatically. See [runtime deployment guide](../../docs/fastdds-patched-runtime.md).

The enrollment-event RELIABILITY warning remains a separate compatibility
issue. Image QoS and vision inference logic were not changed by this fix.
