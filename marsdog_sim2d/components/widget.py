import dataclasses
import json
import typing as T

import arcade
import arcade.gui

from marsdog_sim2d import config
from marsdog_sim2d.components.text import measure_text


@dataclasses.dataclass(frozen=True, slots=True)
class BBox:
    x: float
    y: float
    width: float
    height: float


class AButton(arcade.gui.UIFlatButton):
    """Theme-aware native Arcade button with BBox compatibility."""

    def __init__(
        self,
        bbox: BBox,
        text: str,
        *,
        primary: bool = False,
        active: bool = False,
        size_hint: tuple[float | None, float | None] | None = None,
    ) -> None:
        super().__init__(
            x=bbox.x,
            y=bbox.y,
            width=bbox.width,
            height=bbox.height,
            text=text,
            style=arcade_button_style(primary=primary, active=active),
            size_hint=size_hint,
        )

    @property
    def bbox(self) -> BBox:
        """Return the current button bounds."""

        return BBox(self.left, self.bottom, self.width, self.height)

    @bbox.setter
    def bbox(self, bounds: BBox) -> None:
        """Resize and reposition the button."""

        self.width = bounds.width
        self.height = bounds.height
        self.left = bounds.x
        self.bottom = bounds.y


class AMessageBox(
    arcade.gui.UIMouseFilterMixin,
    arcade.gui.UIAnchorLayout,
):
    """Project-themed message box with explicit CJK font support."""

    def __init__(
        self,
        *,
        width: float,
        height: float,
        message_text: str,
        title: str | None = None,
        buttons: tuple[str, ...] = ("确定",),
    ) -> None:
        if not buttons:
            raise ValueError("At least one message-box button is required")

        super().__init__(size_hint=(1, 1))
        self.register_event_type("on_action")
        self.with_background(color=(8, 10, 10, 172))

        title_height = float(config.CONTROL_HEIGHT + config.SPACE_XS)
        title_offset = title_height if title else 0.0
        button_height = float(config.CONTROL_HEIGHT + config.SPACE_XS)
        body_line_width = max(
            (
                measure_text(line, font_size=config.FONT_SIZE_BODY)[0] for line in message_text.split("\n")
            ),
            default=0,
        )
        title_width = (
            measure_text(title, font_size=config.FONT_SIZE_MODULE, bold=True)[0]
            if title
            else 0
        )
        horizontal_chrome = config.SPACE_MD * 2 + config.SPACE_SM * 2
        maximum_width = min(
            width,
            config.WINDOW_WIDTH - config.SPACE_LG * 2,
        )
        minimum_width = min(320.0, maximum_width)
        resolved_width = min(
            maximum_width,
            max(
                minimum_width,
                body_line_width + horizontal_chrome,
                title_width + config.SPACE_LG * 2,
            ),
        )
        message_width = resolved_width - config.SPACE_MD * 2
        content_width = message_width - config.SPACE_SM * 2
        wrapped_message = _wrap_message_text(
            message_text,
            content_width,
            config.FONT_SIZE_BODY,
        )
        _, text_height = measure_text(
            wrapped_message,
            font_size=config.FONT_SIZE_BODY,
            width=int(content_width),
            multiline=True,
        )
        vertical_chrome = (
            title_offset + button_height + config.SPACE_MD * 3
        )
        requested_message_height = max(
            config.CONTROL_HEIGHT,
            text_height + config.SPACE_SM * 2,
        )
        maximum_height = max(
            config.CONTROL_HEIGHT,
            config.WINDOW_HEIGHT - config.SPACE_LG * 2,
        )
        resolved_height = min(
            maximum_height,
            max(height, vertical_chrome + requested_message_height),
        )
        message_height = max(
            config.CONTROL_HEIGHT,
            resolved_height - vertical_chrome,
        )

        frame = arcade.gui.UIAnchorLayout(
            width=resolved_width,
            height=resolved_height,
            size_hint=None,
        )
        frame.with_background(color=_as_color(config.COLORS["surface_raised"]))
        frame.with_border(color=_as_color(config.COLORS["border_strong"]), width=1)
        self.add(child=frame)

        if title:
            title_label = arcade.gui.UILabel(
                text=title,
                height=title_height,
                font_name=config.FONT_NAMES,
                font_size=config.FONT_SIZE_MODULE,
                text_color=_as_rgba(config.COLORS["text"]),
                bold=True,
                align="center",
                size_hint=(1, 0),
            )
            title_label.with_background(
                color=_as_color(config.COLORS["accent_dim"]),
            )
            frame.add(
                child=title_label,
                anchor_y="top",
            )

        message_area = arcade.gui.UITextArea(
            text=wrapped_message,
            width=message_width,
            height=message_height,
            font_name=config.FONT_NAMES,
            font_size=config.FONT_SIZE_BODY,
            text_color=_as_rgba(config.COLORS["text"]),
            multiline=True,
            scroll_speed=float(config.LINE_HEIGHT),
            size_hint=None,
        )
        message_area.with_padding(all=config.SPACE_SM)
        frame.add(
            child=message_area,
            anchor_x="center",
            anchor_y="top",
            align_y=-(title_offset + config.SPACE_MD),
        )

        button_group = arcade.gui.UIBoxLayout(
            vertical=False,
            space_between=config.SPACE_SM,
        )
        for index, button_text in enumerate(buttons):
            button = AButton(
                BBox(0.0, 0.0, 100.0, button_height),
                button_text,
                primary=index == len(buttons) - 1,
            )
            button.on_click = self._on_choice
            button_group.add(button)

        frame.add(
            child=button_group,
            anchor_x="right",
            anchor_y="bottom",
            align_x=-config.SPACE_MD,
            align_y=config.SPACE_MD,
        )

    def _on_choice(self, event: T.Any) -> None:
        if self.parent:
            self.parent.remove(self)
        self.dispatch_event(
            "on_action",
            arcade.gui.UIOnActionEvent(self, event.source.text),
        )

    def on_action(self, event: arcade.gui.UIOnActionEvent) -> None:
        """Handle a message-box action; callers normally register an event."""


class ATopicChip(arcade.gui.UIAnchorLayout):
    """Native Topic health chip with a dedicated status indicator."""

    _DOT_WIDTH = 12.0
    _CONTENT_GAP = 2.0

    def __init__(
        self,
        bbox: BBox,
        text: str,
        status_color: tuple[int, ...],
    ) -> None:
        super().__init__(
            x=bbox.x,
            y=bbox.y,
            width=bbox.width,
            height=bbox.height,
            size_hint=None,
        )
        self.appearance = (text, tuple(status_color))
        self._dot_label = arcade.gui.UILabel(
            width=self._DOT_WIDTH,
            text="●",
            font_name=config.FONT_NAMES,
            font_size=config.FONT_SIZE_AUX,
            text_color=_as_rgba(status_color),
            bold=True,
            align="center",
            size_hint=None,
        )
        self._text_label = arcade.gui.UILabel(
            width=self._text_width(bbox.width),
            text=text,
            font_name=config.FONT_NAMES,
            font_size=config.FONT_SIZE_AUX,
            text_color=_as_rgba(config.COLORS["text"]),
            bold=True,
            align="center",
            size_hint=None,
        )
        self.add(
            child=self._dot_label,
            anchor_x="left",
            anchor_y="center",
            align_x=config.SPACE_SM,
        )
        self.add(
            child=self._text_label,
            anchor_x="left",
            anchor_y="center",
            align_x=(
                config.SPACE_SM + self._DOT_WIDTH + self._CONTENT_GAP
            ),
        )
        self.with_background(color=_as_color(config.COLORS["surface"]))
        self.with_border(color=_as_color(status_color), width=1)

    @property
    def bbox(self) -> BBox:
        """Return the current chip bounds."""

        return BBox(self.left, self.bottom, self.width, self.height)

    @bbox.setter
    def bbox(self, bounds: BBox) -> None:
        """Resize and reposition the chip."""

        self.width = bounds.width
        self.height = bounds.height
        self.left = bounds.x
        self.bottom = bounds.y
        self._text_label.width = self._text_width(bounds.width)

    @classmethod
    def _text_width(cls, chip_width: float) -> float:
        horizontal_inset = (
            config.SPACE_SM * 2 + cls._DOT_WIDTH + cls._CONTENT_GAP
        )
        return max(1.0, chip_width - horizontal_inset)


class AJsonPreviewer(arcade.gui.UITextArea):
    """Scrollable, read-only JSON preview managed by Arcade's UIManager."""

    def __init__(
        self,
        bbox: BBox,
        value: T.Any = "",
        *,
        max_chars: int = config.MAX_PAYLOAD_PREVIEW_CHARS,
        font_size: float = config.FONT_SIZE_AUX,
        size_hint: tuple[float | None, float | None] | None = None,
    ) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")

        self._max_chars = max_chars
        super().__init__(
            x=bbox.x,
            y=bbox.y,
            width=bbox.width,
            height=bbox.height,
            text=_format_json(value, max_chars),
            font_name=config.FONT_NAMES,
            font_size=font_size,
            text_color=(*config.COLORS["subtle_text"], 255),
            multiline=True,
            scroll_speed=24.0,
            size_hint=size_hint,
        )
        self.with_background(color=_as_color((*config.COLORS["preview_background"], 255)))
        self.with_border(color=_as_color((*config.COLORS["border_strong"], 255)), width=1)
        self.with_padding(all=config.SPACE_SM)

    @property
    def bbox(self) -> BBox:
        """Return the current widget bounds."""

        return BBox(self.left, self.bottom, self.width, self.height)

    @bbox.setter
    def bbox(self, bounds: BBox) -> None:
        """Resize and reposition the previewer."""

        self.width = bounds.width
        self.height = bounds.height
        self.left = bounds.x
        self.bottom = bounds.y

    def set_value(self, value: T.Any) -> bool:
        """Format and display a value, returning whether the text changed."""

        formatted = _format_json(value, self._max_chars)
        if self.text == formatted:
            return False

        self.text = formatted
        return True


class AJsonEditor(arcade.gui.UIInputText):
    """Editable multiline JSON text using Arcade's native input behavior."""

    def __init__(
        self,
        bbox: BBox,
        value: str = "",
        *,
        font_size: float = config.FONT_SIZE_AUX,
        size_hint: tuple[float | None, float | None] | None = None,
    ) -> None:
        super().__init__(
            x=bbox.x,
            y=bbox.y,
            width=bbox.width,
            height=bbox.height,
            text=value,
            font_name=config.FONT_NAMES,
            font_size=font_size,
            text_color=_as_rgba(config.COLORS["text"]),
            caret_color=_as_rgba(config.COLORS["accent"]),
            border_color=_as_color(config.COLORS["border_strong"]),
            border_width=1,
            multiline=True,
            size_hint=size_hint,
        )
        self.with_background(
            color=_as_color(config.COLORS["preview_background"]),
        )

    @property
    def bbox(self) -> BBox:
        """Return the current editor bounds."""

        return BBox(self.left, self.bottom, self.width, self.height)

    @bbox.setter
    def bbox(self, bounds: BBox) -> None:
        """Resize and reposition the editor."""

        self.width = bounds.width
        self.height = bounds.height
        self.left = bounds.x
        self.bottom = bounds.y


def _format_json(value: T.Any, max_chars: int) -> str:
    """Format JSON-like values while retaining diagnostic plain text."""

    normalized = value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""

        try:
            normalized = json.loads(stripped)
        except json.JSONDecodeError:
            return _limit_preview(value, max_chars)

    try:
        formatted = json.dumps(
            normalized,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except (TypeError, ValueError) as exc:
        formatted = f"JSON preview unavailable: {exc}"

    return _limit_preview(formatted, max_chars)


def _limit_preview(text: str, max_chars: int) -> str:
    """Bound expensive glyph layout while clearly marking truncated text."""

    if len(text) <= max_chars:
        return text

    marker = "\n…（内容已截断）"
    if max_chars <= len(marker):
        return marker[-max_chars:]
    return f"{text[:max_chars - len(marker)]}{marker}"


def _wrap_message_text(
    text: str,
    maximum_width: float,
    font_size: float,
) -> str:
    """Wrap mixed CJK text using the active Arcade font metrics."""

    wrapped_lines: list[str] = []
    for paragraph in text.split("\n"):
        current_line = ""
        for character in paragraph:
            candidate = f"{current_line}{character}"
            candidate_width, _ = measure_text(
                candidate,
                font_size=font_size,
            )
            if current_line and candidate_width > maximum_width:
                wrapped_lines.append(current_line)
                current_line = character
                continue
            current_line = candidate
        wrapped_lines.append(current_line)

    return "\n".join(wrapped_lines)


def arcade_button_style(primary: bool = False, active: bool = False) -> dict[str, T.Any]:
    """Return the shared theme for native Arcade flat buttons."""

    normal_background = (
        config.COLORS["accent_dim"]
        if primary
        else config.COLORS["surface_hover"]
        if active
        else config.COLORS["surface_raised"]
    )
    normal_border = config.COLORS["accent"] if primary or active else config.COLORS["border"]

    style_type = arcade.gui.UIFlatButton.UIStyle
    common = {
        "font_name": config.FONT_NAMES,
        "font_size": config.FONT_SIZE_AUX,
        "font_color": _as_rgba(config.COLORS["text"]),
        "border_width": 1,
    }
    return {
        "normal": style_type(
            bg=_as_rgba(normal_background),
            border=_as_rgba(normal_border),
            **common,
        ),
        "hover": style_type(
            bg=_as_rgba(config.COLORS["surface_hover"]),
            border=_as_rgba(config.COLORS["accent"]),
            **common,
        ),
        "press": style_type(
            bg=_as_rgba(config.COLORS["accent_dim"]),
            border=_as_rgba(config.COLORS["accent"]),
            **common,
        ),
        "disabled": style_type(
            bg=_as_rgba(config.COLORS["surface"]),
            border=_as_rgba(config.COLORS["border"]),
            **common,
        ),
    }


def _as_rgba(color: tuple[int, ...]) -> tuple[int, int, int, int]:
    return int(color[0]), int(color[1]), int(color[2]), 255


def _as_color(color: tuple[int, ...]) -> arcade.color.Color:
    alpha = color[3] if len(color) >= 4 else 255
    return arcade.color.Color(color[0], color[1], color[2], alpha)
