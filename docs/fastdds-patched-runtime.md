# Patched Fast DDS runtime for ROS 2 Humble

The Humble Fast DDS 2.6.12 `StatelessReader` can retain an incomplete
fragmented sample after a remote writer is removed. A reader with a small
history can then exhaust its `CacheChangePool`, so its ROS subscription stops
receiving later images. The project carries a one-file patch that releases
that partial sample as the matched writer record is removed.

This patch is pinned to Fast DDS 2.6.12 to match the ROS 2 Humble ABI and
configuration used by this deployment. It does not claim that other Fast DDS
releases have the same defect or that an upstream release has fixed it.

## Build and install

Run from a source checkout with ROS 2 Humble installed. The script downloads
pinned Fast DDS and Asio source archives, checks their SHA-256 digests, applies
the project patch, and installs to a separate prefix. It does not overwrite
`/opt/ros/humble`.

```bash
source /opt/ros/humble/setup.bash
scripts/build_fastdds.sh
```

The default install prefix is
`$HOME/.local/opt/marsdog-fastdds-2.6.12`. Set
`MARSDOG_FASTDDS_PREFIX` to choose another prefix, `ROS_PREFIX` to choose the
Humble install, or `MARSDOG_FASTDDS_BUILD_JOBS` to control build parallelism
(default 2). Existing source, archive, and CMake outputs are cached under the
ignored `build/fastdds-2.6.12/` directory.

## Load the runtime

The sourceable environment helper prepends the installed library directory to
`LD_LIBRARY_PATH`, preserves existing entries, and keeps the project's Fast
DDS transport profile settings:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
source scripts/fastdds_env.sh
```

`demo/run_demo.sh` and the project's `vision.launch.py` and
`vision_debug.launch.py` load the optional installed overlay automatically.
For an external camera driver or a node from another checkout, source
`scripts/fastdds_env.sh` in that process's terminal before starting it. Direct
`python -m demo.vision_demo_node` launches should also source the helper first.

An explicit `MARSDOG_FASTDDS_PREFIX` that does not contain the expected
`libfastrtps.so.2.6` fails with an error instead of silently falling back. To
roll back, use a fresh terminal and set `MARSDOG_FASTDDS_DISABLE_OVERLAY=1`
before launching nodes. Restart every ROS process after changing the runtime;
already exhausted reader pools do not recover by replacing a library on disk.

## Verify

```bash
tests/native/run_fastdds_fragment_cleanup_regression.sh
```

The regression uses DDS domain 217 and UDP bound to loopback. It checks 100
partial-fragment writer removals with both lease and explicit removal, repeated
and no-fragment removals, continued delivery from a second matched writer, and
cleanup of a completed fragmented sample. The test exits nonzero if a cache
slot is lost.
