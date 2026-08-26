"""Shared drawing helpers for consistent CJK-capable text rendering."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import Any

import arcade

from marsdog_sim2d import config


TEXT_CACHE_SIZE = 512

@lru_cache(maxsize=TEXT_CACHE_SIZE)
def _create_text(
    _context_identity: int,
    text: str,
    x: float,
    y: float,
    color: tuple[int, int, int],
    font_size: float,
    width: int | None,
    align: str,
    font_name: str | tuple[str, ...],
    bold: bool | str,
    italic: bool,
    anchor_x: str,
    anchor_y: str,
    multiline: bool,
    rotation: float,
    z: float,
) -> arcade.Text:
    """Create a cached text object scoped by the context identity cache key."""

    return arcade.Text(
        text,
        x,
        y,
        color,
        font_size,
        width,
        align,
        font_name,
        bold,
        italic,
        anchor_x,
        anchor_y,
        multiline,
        rotation,
        z=z,
    )


def draw_text(
    text: Any,
    x: float,
    y: float,
    color: Iterable[int] = (255, 255, 255),
    font_size: float = 12,
    width: int | None = None,
    align: str = "left",
    font_name: str | tuple[str, ...] = config.FONT_NAMES,
    bold: bool | str = False,
    italic: bool = False,
    anchor_x: str = "left",
    anchor_y: str = "baseline",
    multiline: bool = False,
    rotation: float = 0,
    z: float = 0,
    draw: bool = True
) -> arcade.Text:
    """Draw text through bounded reusable Arcade Text objects."""
    # ponytail: Exact-call caching avoids unsafe same-frame Text mutation;
    # replace it with a frame pool only if moving text dominates a profile.
    text_object = _create_text(
        id(arcade.get_window().ctx),
        str(text),
        x,
        y,
        tuple(color),
        font_size,
        width,
        align,
        font_name,
        bold,
        italic,
        anchor_x,
        anchor_y,
        multiline,
        rotation,
        z,
    )
    if draw:
        text_object.draw()
    return text_object


def measure_text(
    text: Any,
    font_size: float = 12,
    width: int | None = None,
    font_name: str | tuple[str, ...] = config.FONT_NAMES,
    bold: bool | str = False,
    multiline: bool = False,
) -> tuple[int, int]:
    """Return the rendered text size reported by Arcade/Pyglet."""

    text_object = _create_text(
        id(arcade.get_window().ctx),
        str(text),
        0,
        0,
        (255, 255, 255),
        font_size,
        width,
        "left",
        font_name,
        bold,
        False,
        "left",
        "top",
        multiline,
        0,
        0,
    )
    return text_object.content_size
