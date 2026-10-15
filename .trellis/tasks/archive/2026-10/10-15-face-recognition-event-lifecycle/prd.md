# 视觉人脸识别事件生命周期发布

## Goal

让独立视觉 demo 按稳定的人脸身份识别结果发布带生命周期语义的主人、家人、陌生人在场事件，避免把 10 Hz 状态包重复解释成多次直驱触发。

## Background

- 当前独立 demo 按约 10 Hz 发布 `/perception/visual_event` JSON，提供 `faces[]` 身份字段，但不产生身份业务事件。
- 完整视觉节点已有历史 `events[]` 规则；它是兼容性敏感的字符串数组，当前状态事件会在连续包中重复。其契约和重复语义记载于 `docs/ROS2_CONTRACT.md:176-225`。
- 人脸识别状态机输出 `candidate_known`、`confirmed_known`、`unknown_candidate` 和 `confirmed_unknown`。已登记身份固定为 `owner` 与 `family_member_1`～`family_member_4`；跟踪 ID 仅表示几何轨迹，可在目标消失后复用。
- 项目已有统一 `/perception/visual_event` normalizer `marsdog_vision_interaction/messages/visual_event.py`；新字段必须明确规范化，不能被默认结构丢弃。

## Requirements

1. 本任务只为独立视觉 demo 增加三类人脸在场生命周期事件；招手、跌倒、停止手势等瞬时动作保持现状。
2. 事件名映射为：已确认 `owner` → `EVT_VISION_MASTER`；已确认 `family_member_1`～`family_member_4` → `EVT_VISION_FAMILY_PRESENT`；`confirmed_unknown` → `EVT_VISION_STRANGER`。候选、未验证、无有效正 `track_id` 的人脸不产生在场事件。置信度沿用人脸算法已有门限，不新增阈值。
3. 使用初始时序参数 `T_enter=1.0s`、`T_exit=2.0s`、`T_retrigger=3.0s`，采用单调时钟计时；以各 `(event_name, track_id)` 独立维护生命周期。
4. 在 `/perception/visual_event` 同一 JSON 新增顶层 `event_lifecycle[]`。每项含 `event_name`、`state`（`ENTER`、`HOLD` 或 `EXIT`）和 `track_id`。现有 `events[]` 字符串数组保持原样。
5. 达到 `T_enter` 后只发布一次 `ENTER`；持续在场时，在每个 10 Hz 视觉状态包中发布 `HOLD`；目标未被识别的缺失宽限期内生命周期保持 `HOLD`，连续缺失达到 `T_exit` 后只发布一次 `EXIT`。两秒内恢复同一事件和轨迹则续接原生命周期。只接受最近一次成功推理且单调年龄未超过相机 stale timeout 的人脸快照；推理失败时不得无限沿用缓存身份。
6. 某生命周期发出 `EXIT` 后，只有经过 `T_retrigger` 才允许相同 `(event_name, track_id)` 再次发出 `ENTER`。重现目标的稳定计时仍从其本次连续有效识别开始。
7. 人脸身份识别、跟踪状态机、Face API、人脸库和 `VisionTask` 接口保持不变；允许在 `VisionObservationProvider` 增加只读 accessor，供 demo 获取最新成功推理的全量人脸身份行及单调完成时间，不改变现有 `faces[]` 对外投影、debug 设置或识别结果。其它变更限于 demo 事件输出、公共 JSON normalization、相关配置和契约文档。

## Acceptance Criteria

- [x] 未连续满足 `T_enter=1.0s` 的确认身份不会输出 `ENTER`；连续满足后首次输出一个 `ENTER`。
- [x] 活跃生命周期在后续每个视觉快照输出 `HOLD`；消费者能区分它与可触发一次直驱的 `ENTER`。
- [x] 短于 `T_exit=2.0s` 的未识别间隔保持原生命周期；连续缺失达到 2 秒时输出一次 `EXIT`。
- [x] `EXIT` 后 3 秒内同一 `(event_name, track_id)` 不会重新 `ENTER`；冷却时间和新一轮 `T_enter` 均满足后才输出 `ENTER`。
- [x] 主人、任一已登记家人和确认陌生人的事件名分别符合映射；候选/未验证状态、无效 track 不生成事件。
- [x] 多张脸按独立正 `track_id` 维护生命周期；一个目标的缺失、退出或重触发计时不影响其它目标。
- [x] `event_lifecycle[]` 经统一 normalizer 后保留；原 `events[]` 继续是字符串数组且其内容不受新字段影响。
- [x] demo 之外的完整视觉节点、Face API 和既有任务输出不因本任务出现行为回归。
- [x] ROS2 视觉契约和 demo 使用说明描述字段、状态、事件映射及 1/2/3 秒初始时序参数。

## Out of Scope

- 招手、跌倒、Stop 手势及其它姿态/手势 `TRIGGER` 生命周期改造。
- 修改完整 `VisionInteractionNode` 既有 `events[]` 生成策略或现有下游消费者。
- 修改检测/识别/跟踪模型、身份确认次数、人脸库、Face API、导航或动作执行逻辑。

## Open Questions

- 无。范围、payload、HOLD 发布频率和初始时间参数已确认。
