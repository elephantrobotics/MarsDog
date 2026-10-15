# Journal - foo (Part 1)

> AI development session journal
> Started: 2026-09-15

---



## Session 1: Configurable face enrollment quality
<!-- trellis-session: v=2 fp=9791a8d437cadf8d -->

**Date**: 2026-09-16
**Task**: Configurable face enrollment quality
**Branch**: `VisionInteraction`

### Summary

Unified upload and continuous enrollment quality configuration and diagnostics. Full suite 169 passed; final focused suite 76 passed. Device image validation pending. Existing .gitattributes excluded.

### Git Commits

| Hash | Message |
|------|---------|
| `ec7e582` | feat: 支持人脸录入质量阈值配置及失败诊断 |

### Status

[OK] **Completed**


## Session 2: 人脸样本去重与 API 调用信息完善
<!-- trellis-session: v=2 fp=d0aaaead57c0188d -->

**Date**: 2026-09-16
**Task**: 人脸样本去重与 API 调用信息完善
**Branch**: `VisionInteraction`

### Summary

为同一身份的规范化人脸 JPG 增加精确去重，覆盖 REST API、ROS/Web UI 连续录入和样本替换；重复返回 face_sample_duplicate 与已有样本编号。Face API 增加 X-Request-ID、结构化请求日志和兼容的错误响应字段；同步接口文档与 181 项测试。

### Git Commits

| Hash | Message |
|------|---------|
| `78ac4e6` | fix: 增加人脸样本去重与请求关联 |
| `bc24663` | docs: 完善人脸样本接口调用说明 |

### Status

[OK] **Completed**


## Session 3: 修复人脸 track 重现继承旧身份
<!-- trellis-session: v=2 fp=e5bea8e42e104640 -->

**Date**: 2026-09-16
**Task**: 修复人脸 track 重现继承旧身份
**Branch**: `VisionInteraction`

### Summary

新增 face track 缺失/重现生命周期；重现时清除旧身份并立即触发 SFace；陌生人结果清除 confirmed known 状态；新增 5 个回归测试。全量 pytest 186 passed，compileall 与 diff check 通过。任务已归档；.trellis 因项目 gitignore 未自动提交。

### Git Commits

| Hash | Message |
|------|---------|
| `eabb849` | fix: prevent stale face identity on track reentry |

### Status

[OK] **Completed**


## Session 4: RKNN FP16 face model adaptation
<!-- trellis-session: v=2 fp=32d38d6e403c1391 -->

**Date**: 2026-09-17
**Task**: RKNN FP16 face model adaptation
**Branch**: `VisionInteraction`

### Summary

Implemented suffix-selected YuNet/SFace FP16 adapters, provider integration, runtime compatibility and safe failure handling. Final review passed; production defaults in commit remain ONNX. Later local RKNN path switches preserved uncommitted.

### Main Changes

- Automatic .onnx/.rknn selection, verified profiles, shared runtime, enrollment and independent recognition integration.

### Git Commits

| Hash | Message |
|------|---------|
| `9f352d4` | feat: 支持按模型格式自动适配人脸 RKNN FP16 |

### Testing

- [OK] 213 pytest cases, compileall and diff checks passed; six-image hardware parity and 50-round concurrent pipeline smoke passed.

### Status

[OK] **Completed**

### Next Steps

- Live-video accuracy and long-duration validation before production rollout; local config switches remain uncommitted.


## Session 5: Complete hand RKNN FP16 and RGA migration
<!-- trellis-session: v=2 fp=88c67b7a127f5098 -->

**Date**: 2026-09-21
**Task**: Complete hand RKNN FP16 and RGA migration
**Branch**: `VisionInteraction`

### Summary

Migrated hand detection and landmarks from CPU MediaPipe to verified RKNN FP16 with RGA preprocessing, retained .task rollback, added Provider lifecycle and geometry coverage, and validated 236 tests with 3 skips plus native RGA build. Real continuous hand-motion video remains unavailable; unrelated .gitignore change was left untouched.

### Git Commits

| Hash | Message |
|------|---------|
| `7603975` | feat: migrate hand inference to RKNN FP16 with RGA |
| `fa8aeb0` | test: add hand backend and provider validation |

### Status

[OK] **Completed**


## Session 6: Migrate pose inference to RKNN YOLOv8
<!-- trellis-session: v=2 fp=8c30c4aba881f737 -->

**Date**: 2026-09-21
**Task**: Migrate pose inference to RKNN YOLOv8
**Branch**: `VisionInteraction`

### Summary

Added config-selectable RKNN YOLOv8 Pose and MediaPipe rollback, native COCO 17 public keypoints with format-aware business consumers, board smoke tooling, docs, and tests (252 passed, 3 skipped).

### Git Commits

| Hash | Message |
|------|---------|
| `83ff467` | feat: migrate pose inference to RKNN YOLOv8 |

### Status

[OK] **Completed**


## Session 7: Validate Hand DMA-BUF RGA RKNN zero-copy baseline
<!-- trellis-session: v=2 fp=51ed8111dec67475 -->

**Date**: 2026-09-22
**Task**: Validate Hand DMA-BUF RGA RKNN zero-copy baseline
**Branch**: `VisionInteraction`

### Summary

Added an opt-in native Hand DMA-BUF → RGA → RKNN detector probe. Verified explicit model hash, RGA FD import/letterbox, same destination FD passed through rknn_create_mem_from_fd, UINT8/NHWC with native pass_through=false for the FP16 model, and finite detector outputs. Board result: 35/35 iterations plus 10 fresh-process smokes passed; focused Hand tests: 21 passed, 3 skipped. Production Provider and camera transport remain unchanged.

### Git Commits

| Hash | Message |
|------|---------|
| `226f70b` | test: add Hand DMA-BUF RGA RKNN baseline probe |

### Status

[OK] **Completed**


## Session 8: Live CPU/NPU vision performance benchmark
<!-- trellis-session: v=2 fp=13b61b7ab824e3c7 -->

**Date**: 2026-09-22
**Task**: Live CPU/NPU vision performance benchmark
**Branch**: `VisionInteraction`

### Summary

Added a live-camera observer and tests, ran matched CPU/NPU Face/Pose/Hand pipelines on C922 640x480@30, recorded latency/resource/NPU telemetry, and archived the benchmark task. CPU/NPU core A/B: event mean 298.73ms -> 220.09ms, P95 450.66ms -> 275.14ms; vision CPU 231.47% -> 76.36%; vision RSS 681.18MiB -> 408.43MiB.

### Git Commits

| Hash | Message |
|------|---------|
| `5d5e1d7` | test: add live CPU NPU vision benchmark |

### Status

[OK] **Completed**


## Session 9: Configurable all-target debug OSD
<!-- trellis-session: v=2 fp=f407f5f39daa4547 -->

**Date**: 2026-09-22
**Task**: Configurable all-target debug OSD
**Branch**: `VisionInteraction`

### Summary

Implemented config-controlled debug OSD and all current human/face detection overlays. Active target behavior remains unchanged; non-active targets render dashed boxes. Added event, viewer, dashboard, and regression-test coverage. Focused tests passed; 217 tests passed with two unrelated environment/test exclusions.

### Git Commits

| Hash | Message |
|------|---------|
| `df89957` | feat: show all debug vision detections |

### Status

[OK] **Completed**


## Session 10: Preserve original OSD colors
<!-- trellis-session: v=2 fp=f4b9e2bdef330823 -->

**Date**: 2026-09-22
**Task**: Preserve original OSD colors
**Branch**: `VisionInteraction`

### Summary

Restored original human box/detail colors while keeping non-active human and face boxes dashed in all-detection debug OSD. Added a regression test; 35 focused tests passed.

### Git Commits

| Hash | Message |
|------|---------|
| `79bbdf0` | fix: preserve debug OSD colors |

### Status

[OK] **Completed**


## Session 11: 接入 SLAM 单次人体定位
<!-- trellis-session: v=2 fp=a35101c88928f81c -->

**Date**: 2026-09-23
**Task**: 接入 SLAM 单次人体定位
**Branch**: `VisionInteraction`

### Summary

完成 VisionTask locate_person_once 单次 SLAM 定位接入，保留 bbox 对应的精确图像 Header 和目标来源元数据；新增结构化结果、超时与服务不可用处理、配置及接口文档和测试。全量 pytest 279 passed/3 skipped，ROS 包构建通过；真实 SLAM wire 联调因接口包未安装未执行。提交 cacf191。

### Git Commits

| Hash | Message |
|------|---------|
| `cacf191` | feat: 接入 SLAM 单次人体定位 |

### Status

[OK] **Completed**


## Session 12: Separate face and pose detection thresholds
<!-- trellis-session: v=2 fp=9b08941d0888a5d5 -->

**Date**: 2026-09-24
**Task**: Separate face and pose detection thresholds
**Branch**: `VisionInteraction`

### Summary

Separated face and pose detection thresholds, removed the legacy det_threshold fallback from VisionObservationProvider, updated regression coverage, and verified the full pytest suite (280 passed, 3 skipped).

### Git Commits

| Hash | Message |
|------|---------|
| `a05dbf4` | fix: separate face and pose detection thresholds |

### Status

[OK] **Completed**


## Session 13: Make locate_person_once visual-only
<!-- trellis-session: v=2 fp=d056c461aac33bab -->

**Date**: 2026-09-24
**Task**: Make locate_person_once visual-only
**Branch**: `VisionInteraction`

### Summary

Removed the optional SLAM client and localization provenance path. locate_person_once now returns the requested current visual human candidate, with updated docs/config/spec. Tests were not run per instruction; syntax/YAML/diff checks passed, lint/type-check tools unavailable.

### Git Commits

| Hash | Message |
|------|---------|
| `1904258` | refactor: make locate_person_once visual-only |

### Status

[OK] **Completed**


## Session 14: Report confirmed stranger pose events
<!-- trellis-session: v=2 fp=39a7c911e06185c5 -->

**Date**: 2026-10-05
**Task**: Report confirmed stranger pose events
**Branch**: `VisionInteraction`

### Summary

Allowed formal pose and hand events for tracked confirmed strangers using existing event names. Synchronized publisher, viewer, dashboard, interface docs, and recorded the identity gate in the local pose model spec. No test suite run.

### Git Commits

| Hash | Message |
|------|---------|
| `c8f73d2` | feat: 上报确认陌生人的姿态事件 |

### Status

[OK] **Completed**


## Session 15: 优化掩面持续识别与结束判定
<!-- trellis-session: v=2 fp=08a0668df8099438 -->

**Date**: 2026-10-05
**Task**: 优化掩面持续识别与结束判定
**Branch**: `VisionInteraction`

### Summary

按用户确认实现掩面3秒触发、两类结束迹象1秒解除、0.5秒未知容忍；融合脸部范围和双侧手/腕肘证据，并补齐无手坐标时的正式事件路由。

### Main Changes

- 修复遮挡时鼻尖漂移、短暂漏检清票、未知超时恢复及缓存跨时间流问题；保存诊断并同步测试/对接文档与本地规范。

### Git Commits

| Hash | Message |
|------|---------|
| `c959b67` | fix: 优化掩面持续识别与结束判定 |

### Testing

- [OK] 全量测试307通过3跳过；相关测试146通过；编译及git diff --check通过。
- [OK] 隔离原模型视频回放：掩面8.95秒触发、10.35秒解除；抱头100次观测无掩面误触发。

### Status

[OK] **Completed**

### Next Steps

- 现有运行进程尚未重启；模型几何是可见性代理，后续扩大真实视频样本验证。


## Session 16: 优化抱头动作触发
<!-- trellis-session: v=2 fp=a073a3c87e753e09 -->

**Date**: 2026-10-06
**Task**: 优化抱头动作触发
**Branch**: `VisionInteraction`

### Summary

放开抱头历史对 HandLandmarker 漏检的硬清除门槛，保留双侧 Pose 判定、可靠头肩锚点清除和原有对外映射；补充单测，83 项通过，MP4 回放稳定输出 hands_on_head。

### Git Commits

| Hash | Message |
|------|---------|
| `0ada0c1` | fix: 优化抱头触发 |

### Status

[OK] **Completed**


## Session 17: 优化驼背方向与躺卧判定
<!-- trellis-session: v=2 fp=08b294716a81c7e9 -->

**Date**: 2026-10-06
**Task**: 优化驼背方向与躺卧判定
**Branch**: `VisionInteraction`

### Summary

基于 COCO RKNN 对 hunchback01.mp4 全 424 帧回放，补充单耳方向判断，确认前倾区间稳定识别、回直时退出，躺卧与跌倒未误触发；98 项专项及 360 项完整测试通过。提交 4719cfc。

### Git Commits

| Hash | Message |
|------|---------|
| `4719cfc` | fix: 优化驼背方向与躺卧判定 |

### Status

[OK] **Completed**


## Session 18: RK3588 emotion RKNN benchmark
<!-- trellis-session: v=2 fp=0b8315a270152653 -->

**Date**: 2026-10-07
**Task**: RK3588 emotion RKNN benchmark
**Branch**: `VisionInteraction`

### Summary

Added the RK3588 emotion RKNN benchmark harness and completed the JAFFE/KDEF board run for eight models. Saved reproducible metrics and per-sample records under data/benchmark/results/emotion_rknn/20261007T150828+0800/. Fixed label validation and warm-up metadata bookkeeping, validated script compilation and Trellis context, and locally archived the task.

### Git Commits

| Hash | Message |
|------|---------|
| `a39980e` | feat: add RK3588 emotion benchmark harness |

### Status

[OK] **Completed**


## Session 19: Implement standalone vision demo
<!-- trellis-session: v=2 fp=6bce025ade96229d -->

**Date**: 2026-10-13
**Task**: Implement standalone vision demo
**Branch**: `VisionInteraction`

### Summary

Added and committed the standalone ROS 2 vision demo; verified its Mock and live camera/API paths.

### Main Changes

- Added standalone demo node, launcher, README, focused checks, and Mock smoke validation.

### Git Commits

| Hash | Message |
|------|---------|
| `c7f08de` | feat: add standalone vision demo |

### Testing

- [OK] Focused demo checks: 3 passed; Mock ROS smoke passed.
- [OK] Live C922/RKNN check: camera 30 Hz, visual events 10 Hz, human query/locate and object one-shot/session passed.

### Status

[OK] **Completed**

### Next Steps

- Consider fixing shared ObjectDetectionSessionManager expiry visibility so a state query cannot suppress the lease-expiry terminal packet.


## Session 20: 视觉人脸识别事件生命周期
<!-- trellis-session: v=2 fp=9b8197b5cf96b3a5 -->

**Date**: 2026-10-15
**Task**: 视觉人脸识别事件生命周期
**Branch**: `VisionInteraction`

### Summary

独立 demo 增加人脸 presence 的 ENTER/HOLD/EXIT 发布及全量新鲜推理快照。

### Main Changes

- 按确认身份映射主人、家人、陌生人事件，按轨迹独立管理进入、保持、退出与 3 秒重触发冷却。
- 兼容保留旧 events[]；生命周期读取 provider 全量人脸并拒绝过期推理快照。

### Git Commits

| Hash | Message |
|------|---------|
| `4c70429` | feat: add face presence lifecycle events |

### Testing

- [OK] py_compile、YAML 解析、Trellis context 校验和 git diff --check 通过；未运行测试套件。

### Status

[OK] **Completed**
