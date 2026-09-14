"""Thread-safe event values passed from ROS callbacks to the UI thread."""

from __future__ import annotations

import dataclasses
import time
import typing as T


@dataclasses.dataclass(slots=True)
class SimEvent:
    """Normalized event passed from ROS callbacks to the Arcade thread."""

    kind: str
    topic: str
    payload: dict[str, T.Any]
    summary: str
    received_at: float = dataclasses.field(default_factory=time.time)
    format_hint: str | None = None
