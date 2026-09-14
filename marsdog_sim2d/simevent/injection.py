"""Editable state for manual ROS2 event injection."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class InjectionFormState:
    """Values shared by the left-panel view and injection workflow."""

    tab: str = "Event"
    group: str = "Audio"
    fields: dict[str, str] = field(default_factory=dict)
    payload_preview: str = ""
    payload_preview_dirty: bool = False
    payload_preview_scroll: int = 0
    preview_topics: list[str] = field(default_factory=list)
    selected_scenario: str = "high_hunger"
