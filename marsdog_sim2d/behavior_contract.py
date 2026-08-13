"""Load the behavior-tree action contract shipped with the viewer.

The upstream YAML intentionally remains the single source of truth for direct
behavior names, ordered stages, and exact ``ACT_*`` candidates.  The file uses
a deliberately small YAML subset, so a strict standard-library parser keeps
the viewer independent of PyYAML while still rejecting malformed rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import random
import re
from typing import Any


CONTRACT_PATH = (
    Path(__file__).with_name("assets")
    / "config"
    / "behavior_tree_actions.yaml"
)

_BEHAVIOR_RE = re.compile(r"^  ([A-Za-z0-9_]+):\s*$")
_STAGE_RE = re.compile(r"^      - stage_id:\s*([A-Za-z0-9_]+)\s*$")
_ORDER_RE = re.compile(r"^        order:\s*(\d+)\s*$")
_REQUIRED_RE = re.compile(r"^        required:\s*(true|false)\s*$", re.IGNORECASE)
_ACTION_RE = re.compile(
    r"^          - \{unit_id:\s*(ACT_[A-Za-z0-9_]+)\}\s*$"
)


@dataclass(frozen=True, slots=True)
class ContractStage:
    stage_id: str
    order: int
    required: bool
    candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BehaviorContract:
    behavior_name: str
    stages: tuple[ContractStage, ...]


@dataclass(frozen=True, slots=True)
class SelectedStage:
    stage_id: str
    order: int
    action_id: str


@lru_cache(maxsize=1)
def load_behavior_contract() -> dict[str, BehaviorContract]:
    """Return all direct behaviors keyed by their case-sensitive name."""

    lines = CONTRACT_PATH.read_text(encoding="utf-8").splitlines()
    behaviors: dict[str, BehaviorContract] = {}
    behavior_name: str | None = None
    stages: list[ContractStage] = []
    stage_id: str | None = None
    stage_order = 0
    stage_required = True
    candidates: list[str] = []

    def finish_stage() -> None:
        nonlocal stage_id, stage_order, stage_required, candidates
        if stage_id is None:
            return
        if not candidates:
            raise ValueError(
                f"{CONTRACT_PATH}: stage {stage_id!r} has no ACT candidates"
            )
        stages.append(
            ContractStage(
                stage_id=stage_id,
                order=stage_order or len(stages) + 1,
                required=stage_required,
                candidates=tuple(candidates),
            )
        )
        stage_id = None
        stage_order = 0
        stage_required = True
        candidates = []

    def finish_behavior() -> None:
        nonlocal behavior_name, stages
        finish_stage()
        if behavior_name is None:
            return
        ordered = tuple(sorted(stages, key=lambda item: item.order))
        if not ordered:
            raise ValueError(
                f"{CONTRACT_PATH}: behavior {behavior_name!r} has no stages"
            )
        behaviors[behavior_name] = BehaviorContract(
            behavior_name=behavior_name,
            stages=ordered,
        )
        behavior_name = None
        stages = []

    for line_number, line in enumerate(lines, start=1):
        behavior_match = _BEHAVIOR_RE.match(line)
        if behavior_match:
            finish_behavior()
            behavior_name = behavior_match.group(1)
            continue

        stage_match = _STAGE_RE.match(line)
        if stage_match:
            if behavior_name is None:
                raise ValueError(
                    f"{CONTRACT_PATH}:{line_number}: stage before behavior"
                )
            finish_stage()
            stage_id = stage_match.group(1)
            continue

        order_match = _ORDER_RE.match(line)
        if order_match and stage_id is not None:
            stage_order = int(order_match.group(1))
            continue

        required_match = _REQUIRED_RE.match(line)
        if required_match and stage_id is not None:
            stage_required = required_match.group(1).lower() == "true"
            continue

        action_match = _ACTION_RE.match(line)
        if action_match:
            if stage_id is None:
                raise ValueError(
                    f"{CONTRACT_PATH}:{line_number}: action before stage"
                )
            candidates.append(action_match.group(1))

    finish_behavior()
    if len(behaviors) != 53:
        raise ValueError(
            f"{CONTRACT_PATH}: expected 53 behaviors, found {len(behaviors)}"
        )
    return behaviors


def select_behavior_stages(
    behavior_name: str,
    *,
    rng: Any = None,
) -> tuple[SelectedStage, ...]:
    """Select one exact ACT candidate for every ordered stage."""

    contract = load_behavior_contract().get(behavior_name)
    if contract is None:
        return ()
    generator = rng or random
    return tuple(
        SelectedStage(
            stage_id=stage.stage_id,
            order=stage.order,
            action_id=generator.choice(stage.candidates),
        )
        for stage in contract.stages
        if stage.required or stage.candidates
    )


def direct_behavior_names() -> tuple[str, ...]:
    return tuple(load_behavior_contract())


def contract_action_ids() -> frozenset[str]:
    return frozenset(
        action_id
        for behavior in load_behavior_contract().values()
        for stage in behavior.stages
        for action_id in stage.candidates
    )


def stage_position(
    behavior_name: str | None,
    stage_id: str | None,
) -> tuple[int, int] | None:
    """Return the one-based Stage position declared by the contract."""

    behavior = load_behavior_contract().get(str(behavior_name or ""))
    if behavior is None or not stage_id:
        return None
    for index, stage in enumerate(behavior.stages, start=1):
        if stage.stage_id == stage_id:
            return index, len(behavior.stages)
    return None
