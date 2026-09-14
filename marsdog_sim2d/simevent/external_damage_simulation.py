"""Rules for UI-only external-damage risk demonstrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DamageStep:
    """One visible action in a local damage-response sequence."""

    label: str
    action: str


@dataclass(frozen=True, slots=True)
class ExternalDamageSpec:
    """Display and sequence metadata for one documented damage event."""

    label: str
    suggested_level: str
    response_name: str
    duration_label: str
    hold_mode: str
    steps: tuple[DamageStep, ...]


EXTERNAL_DAMAGE_SPECS = {
    "EVT_DAMAGE_JOINT_OR_MOTOR_FAILURE": ExternalDamageSpec(
        "关节或电机确认损坏/卡死",
        "D1",
        "Fault Joint Safe Hold",
        "持续保持",
        "manual",
        (
            DamageStep("立即停止动作", "ACT_EMERGENCY_STOP"),
            DamageStep("故障关节安全保持", "ACT_FAULT_JOINT_SAFE_HOLD"),
            DamageStep("连续发出求助提示", "ACT_CONTINUOUS_BARK"),
        ),
    ),
    "EVT_DAMAGE_STRUCTURE_EXPOSED": ExternalDamageSpec(
        "外壳破裂、零件脱落或线束暴露",
        "D1",
        "Structural Damage Hold",
        "持续保持",
        "manual",
        (
            DamageStep("停止或缓慢趴下", "ACT_ACTION_STOP"),
            DamageStep("结构损坏保持", "ACT_STRUCTURAL_DAMAGE_HOLD"),
            DamageStep("提醒主人检查", "ACT_CONTINUOUS_BARK"),
        ),
    ),
    "EVT_DAMAGE_RECOVERY_FAILED": ExternalDamageSpec(
        "无法站立或多次起身失败",
        "D1",
        "Recovery Failed & Call",
        "持续保持",
        "manual",
        (
            DamageStep("停止反复起身", "ACT_ACTION_STOP"),
            DamageStep("调整为低功耗安全姿态", "ACT_ADJUST_SAFE_POSTURE"),
            DamageStep("发送恢复失败求助", "ACT_RECOVERY_FAILED_CALL"),
        ),
    ),
    "EVT_DAMAGE_POWER_RISK": ExternalDamageSpec(
        "电池或电源受外力损坏风险",
        "D1",
        "Power Damage Emergency",
        "立即执行并保持",
        "manual",
        (
            DamageStep("立即停止并趴下", "ACT_EMERGENCY_STOP"),
            DamageStep("电源损坏安全保持", "ACT_POWER_DAMAGE_SAFE_HOLD"),
            DamageStep("发出最高级别警告", "ACT_CONTINUOUS_BARK"),
        ),
    ),
    "EVT_DAMAGE_PERCEPTION_FAILURE": ExternalDamageSpec(
        "关键传感器损坏导致环境不可感知",
        "D1",
        "Perception Fault Safe Stop",
        "持续保持",
        "manual",
        (
            DamageStep("原地停止自主运动", "ACT_EMERGENCY_STOP"),
            DamageStep("感知故障安全停止", "ACT_PERCEPTION_FAULT_SAFE_STOP"),
            DamageStep("通知主人处理", "ACT_CONTINUOUS_BARK"),
        ),
    ),
    "EVT_DAMAGE_JOINT_ANOMALY_AFTER_IMPACT": ExternalDamageSpec(
        "强撞击后疑似关节异常",
        "D2",
        "Crouch & Joint Protect",
        "10~60s",
        "timed",
        (
            DamageStep("迅速伏低保护关节", "ACT_CROUCH_JOINT_PROTECT"),
            DamageStep("停止高功率动作", "ACT_ACTION_STOP"),
            DamageStep("检查异常关节", "ACT_CHECK_ABNORMAL_POSITION"),
        ),
    ),
    "EVT_DAMAGE_SHELL_DISPLACED": ExternalDamageSpec(
        "外壳移位或覆盖件松动",
        "D2",
        "Hold & Request Inspection",
        "持续至检查完成",
        "inspection",
        (
            DamageStep("停止当前行为", "ACT_ACTION_STOP"),
            DamageStep("保持低姿态", "ACT_ADJUST_SAFE_POSTURE"),
            DamageStep("请求人工检查", "ACT_HOLD_REQUEST_INSPECTION"),
        ),
    ),
    "EVT_DAMAGE_SUSTAINED_PRESSURE": ExternalDamageSpec(
        "持续挤压或夹持风险",
        "D2",
        "Release, Guard & Call",
        "5~30s",
        "timed",
        (
            DamageStep("全身收紧并尝试脱困", "ACT_RELEASE_FROM_PRESSURE"),
            DamageStep("护住疑似受伤部位", "ACT_GUARD_INJURY"),
            DamageStep("大声求助", "ACT_CONTINUOUS_BARK"),
        ),
    ),
    "EVT_DAMAGE_FALL_RECOVERY_DIFFICULT": ExternalDamageSpec(
        "跌倒后恢复困难",
        "D2",
        "Lie Down & Reassess",
        "20~120s",
        "timed",
        (
            DamageStep("保持趴卧并观察", "ACT_LIE_DOWN_REASSESS"),
            DamageStep("重新评估起身方向", "ACT_CHECK_ABNORMAL_POSITION"),
        ),
    ),
    "EVT_DAMAGE_LIGHT_IMPACT": ExternalDamageSpec(
        "轻微外部撞击",
        "D3",
        "Flinch, Retreat & Inspect",
        "2~8s",
        "timed",
        (
            DamageStep("身体瞬间缩紧", "ACT_BODY_FLINCH"),
            DamageStep("后退一步", "ACT_STEP_BACK"),
            DamageStep("查看撞击来源", "ACT_CHECK_ABNORMAL_POSITION"),
        ),
    ),
    "EVT_DAMAGE_SHORT_PUSH_PULL": ExternalDamageSpec(
        "短时推挤或拉扯",
        "D3",
        "Yield & Reposition",
        "3~10s",
        "timed",
        (
            DamageStep("顺受力方向小幅让步", "ACT_YIELD_FORCE"),
            DamageStep("重新规划站位", "ACT_REPOSITION"),
        ),
    ),
    "EVT_DAMAGE_SLIP_IMBALANCE": ExternalDamageSpec(
        "单次打滑或轻微失衡",
        "D3",
        "Brace & Test Ground",
        "5~20s",
        "timed",
        (
            DamageStep("展开四肢稳定身体", "ACT_BRACE_BALANCE"),
            DamageStep("缩短速度试探地面", "ACT_TEST_GROUND"),
        ),
    ),
}

_LEVEL_LABELS = {
    "D1": "损伤 L1",
    "D2": "损伤 L2",
    "D3": "损伤 L3",
    "NONE": "低于处置阈值",
}


def resolve_damage_risk(score: float, confirmed: bool) -> str:
    """Resolve a damage code without colliding with abnormal L0-L3."""

    resolved_score = max(0.0, min(100.0, float(score)))
    if confirmed or resolved_score > 90.0:
        return "D1"
    if resolved_score > 70.0:
        return "D2"
    if resolved_score > 40.0:
        return "D3"
    return "NONE"


def build_external_damage_payload(
    event_type: str,
    risk_score: float,
    *,
    confirmed: bool,
) -> dict[str, Any]:
    """Build normalized local metadata for one damage demonstration."""

    spec = EXTERNAL_DAMAGE_SPECS[event_type]
    score = max(0.0, min(100.0, float(risk_score)))
    risk_code = resolve_damage_risk(score, confirmed)
    return {
        "event_type": event_type,
        "label": spec.label,
        "risk_score": score,
        "confirmed": bool(confirmed),
        "risk_code": risk_code,
        "risk_level": _LEVEL_LABELS[risk_code],
        "suggested_risk_code": spec.suggested_level,
        "suggested_risk_level": _LEVEL_LABELS[spec.suggested_level],
        "response_name": spec.response_name,
        "duration_label": spec.duration_label,
        "hold_mode": spec.hold_mode,
        "source": "local_external_damage_demo",
    }


def damage_auto_finishes(event_type: str) -> bool:
    """Return whether the accelerated local demo restores automatically."""

    return EXTERNAL_DAMAGE_SPECS[event_type].hold_mode == "timed"
