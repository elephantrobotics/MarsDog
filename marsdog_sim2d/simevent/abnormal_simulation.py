"""UI-only abnormal-level sequences used by the local debug console."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from marsdog_sim2d.simevent.external_damage_simulation import (
    EXTERNAL_DAMAGE_SPECS,
    damage_auto_finishes,
)


ABNORMAL_LEVEL_ORDER = ("L0", "L1", "L2", "L3")
ABNORMAL_STEP_DURATION_SEC = 0.8


@dataclass(frozen=True, slots=True)
class AbnormalStep:
    """One visible step in a local abnormal simulation."""

    label: str
    action: str


_LEVEL_STEPS = {
    "L0": (
        AbnormalStep("动作紧急停止", "ACT_EMERGENCY_STOP"),
        AbnormalStep("调整为安全姿态", "ACT_ADJUST_SAFE_POSTURE"),
        AbnormalStep("查看异常位置", "ACT_CHECK_ABNORMAL_POSITION"),
        AbnormalStep("连续大声吠叫", "ACT_CONTINUOUS_BARK"),
    ),
    "L1": (
        AbnormalStep("动作紧急停止", "ACT_EMERGENCY_STOP"),
        AbnormalStep("身体缩一下", "ACT_BODY_FLINCH"),
        AbnormalStep("快速回头查看", "ACT_QUICK_TURN_HEAD"),
        AbnormalStep("后退", "ACT_STEP_BACK"),
        AbnormalStep("耳朵向后", "ACT_EARS_BACKWARD"),
        AbnormalStep("保持警觉", "ACT_ALERT_STATE"),
    ),
    "L2": (
        AbnormalStep("动作停止", "ACT_ACTION_STOP"),
        AbnormalStep("扭头查看原因", "ACT_TURN_HEAD_CHECK_CAUSE"),
        AbnormalStep("换方向尝试", "ACT_CHANGE_DIRECTION_RETRY"),
        AbnormalStep("短促呜咽", "ACT_SHORT_WHIMPER"),
    ),
    "L3": (
        AbnormalStep("停顿一下", "ACT_PAUSE_MOMENT"),
        AbnormalStep("歪头查看目标", "ACT_HEAD_TILT_CHECK_TARGET"),
        AbnormalStep("重新尝试", "ACT_RETRY_ACTION"),
    ),
}

_LEVEL_EMOTION_DELTAS: dict[str, dict[str, int | tuple[int, int]]] = {
    "L0": {"Fear": 40, "Anxiety": 30, "Excite": -30, "Joy": -40},
    "L1": {"Fear": 30, "Anxiety": 20, "Excite": -10, "Joy": -20},
    "L2": {"Anxiety": 10, "Excite": -10, "Joy": -10},
    "L3": {"Anxiety": (5, 10)},
}


def normalize_abnormal_level(level: str) -> str:
    normalized = str(level or "").strip().upper()
    return normalized if normalized in ABNORMAL_LEVEL_ORDER else "L0"


def next_abnormal_level(level: str) -> str:
    """Return the next selectable level, wrapping after L3."""

    normalized = normalize_abnormal_level(level)
    index = ABNORMAL_LEVEL_ORDER.index(normalized)
    return ABNORMAL_LEVEL_ORDER[(index + 1) % len(ABNORMAL_LEVEL_ORDER)]


def abnormal_steps(
    level: str,
    *,
    owner_visible: bool,
) -> tuple[AbnormalStep, ...]:
    """Resolve the local sequence, including L2's visual-context branch."""

    normalized = normalize_abnormal_level(level)
    steps = _LEVEL_STEPS[normalized]
    if normalized != "L2":
        return steps

    final_step = (
        AbnormalStep("坐下看向主人", "ACT_SIT_LOOK_OWNER")
        if owner_visible
        else AbnormalStep("坐下东张西望", "ACT_SIT_LOOK_AROUND")
    )
    return (*steps, final_step)


def abnormal_emotion_delta(
    level: str,
) -> dict[str, int | tuple[int, int]]:
    """Return a copy of the display-only emotion effect for one level."""

    return dict(_LEVEL_EMOTION_DELTAS[normalize_abnormal_level(level)])


def active_abnormal_steps(state: Any) -> tuple[Any, ...]:
    """Resolve generic abnormal steps or an event-specific damage plan."""

    damage = state.ui_external_damage
    if isinstance(damage, dict):
        event_type = str(damage.get("event_type") or "")
        spec = EXTERNAL_DAMAGE_SPECS.get(event_type)
        if spec is not None:
            return spec.steps
    return abnormal_steps(
        state.ui_abnormal_level,
        owner_visible=bool(state.ui_user_visible),
    )


def format_emotion_delta(
    delta: dict[str, int | tuple[int, int]],
    labels: dict[str, str] | None = None,
) -> str:
    """Format signed local effects without applying them to emotion state."""

    display_labels = labels or {}
    parts = []
    for name, amount in delta.items():
        label = display_labels.get(name, name)
        if isinstance(amount, tuple):
            parts.append(f"{label}+{amount[0]}~+{amount[1]}")
        else:
            parts.append(f"{label}{amount:+d}")
    return " ".join(parts) or "-"


def apply_abnormal_step(state: Any, step_index: int, *, now: float | None = None) -> None:
    """Apply one resolved local step to main-thread presentation state."""

    steps = active_abnormal_steps(state)
    index = max(0, min(int(step_index), len(steps) - 1))
    step = steps[index]
    updated_at = time.time() if now is None else now

    state.ui_abnormal_step_index = index
    state.action_current_action = step.action
    state.action_visual_action = step.action
    state.action_progress = (index + 1) / len(steps)
    state.action_visual_progress = state.action_progress
    state.action_visual_progress_start = state.action_progress
    state.action_stage_index = index + 1
    state.action_stage_total = len(steps)
    state.action_stage_label = step.label
    damage = state.ui_external_damage
    if isinstance(damage, dict):
        state.action_message = f"{damage['risk_level']} {step.label}"
        state.action_level = str(damage["risk_level"])
        state.action_params = {
            **damage,
            "source": "UI",
            "intent": "external_damage_simulation",
        }
    else:
        state.action_message = f"{state.ui_abnormal_level} {step.label}"
        state.action_level = state.ui_abnormal_level
        state.action_params = {
            "source": "UI",
            "intent": "abnormal_simulation",
            "abnormal_level": state.ui_abnormal_level,
            "emotion_delta": dict(state.ui_abnormal_emotion_delta),
        }
    state.action_updated_at = updated_at
    state.recent_action_steps.append((updated_at, step.action))


def advance_abnormal_step(
    state: Any,
    *,
    now_monotonic: float | None = None,
    now: float | None = None,
) -> bool:
    """Advance a running local sequence once its current step has elapsed."""

    if not state.ui_abnormal_simulation_active:
        return False

    monotonic_now = time.monotonic() if now_monotonic is None else now_monotonic
    if state.ui_abnormal_step_started_at is None:
        state.ui_abnormal_step_started_at = monotonic_now
        return False
    if monotonic_now - state.ui_abnormal_step_started_at < ABNORMAL_STEP_DURATION_SEC:
        return False

    steps = active_abnormal_steps(state)
    next_index = state.ui_abnormal_step_index + 1
    if next_index >= len(steps):
        return False

    state.ui_abnormal_step_started_at = monotonic_now
    apply_abnormal_step(state, next_index, now=now)
    return True


def should_finish_abnormal_simulation(
    state: Any,
    *,
    now_monotonic: float | None = None,
) -> bool:
    """Return whether a timed damage demo has shown its final step."""

    if not state.ui_abnormal_simulation_active:
        return False
    damage = state.ui_external_damage
    if not isinstance(damage, dict):
        return False
    event_type = str(damage.get("event_type") or "")
    if event_type not in EXTERNAL_DAMAGE_SPECS:
        return False
    if not damage_auto_finishes(event_type):
        return False
    if state.ui_abnormal_step_index < len(active_abnormal_steps(state)) - 1:
        return False
    if state.ui_abnormal_step_started_at is None:
        return False
    current_time = (
        time.monotonic() if now_monotonic is None else now_monotonic
    )
    return (
        current_time - state.ui_abnormal_step_started_at
        >= ABNORMAL_STEP_DURATION_SEC
    )
