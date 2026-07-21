"""Shared drawing helpers for consistent CJK-capable text rendering."""

from __future__ import annotations

from typing import Any

import arcade

from . import config


def draw_text(*args: Any, **kwargs: Any) -> Any:
    kwargs.setdefault("font_name", config.FONT_NAMES)
    return arcade.draw_text(*args, **kwargs)
