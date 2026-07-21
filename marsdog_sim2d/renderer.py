"""Arcade drawing code for the 2D MarsDog world area."""

from __future__ import annotations

from copy import copy
import math
from pathlib import Path
import time
from typing import Any

import arcade
from arcade.texture_atlas import DefaultTextureAtlas

from . import config
from .drawing import draw_text
from .sim_state import SimState


class WorldRenderer:
    """Draw the center 2D situation view."""

    def __init__(self) -> None:
        asset_root = Path(__file__).with_name("assets")
        dog_asset_dir = asset_root / "dog"
        self._dog_textures: dict[str, Any] = {}
        self._dog_texture_atlases: dict[str, Any] = {}
        self._room_background_texture: Any | None = None
        self._texture_atlas_ready = False
        try:
            self._dog_textures = {
                pose: arcade.load_texture(dog_asset_dir / f"marsdog_{pose}.png")
                for pose in ("stand", "walk", "sit", "lie", "play_bow", "paw")
            }
        except (FileNotFoundError, OSError, RuntimeError):
            self._dog_textures = {}
        try:
            self._room_background_texture = arcade.load_texture(
                asset_root / "backgrounds" / "apartment_floorplan_runtime.png"
            )
        except (FileNotFoundError, OSError, RuntimeError):
            self._room_background_texture = None

    def draw(self, state: SimState) -> None:
        now = time.time()
        view_state = self._screen_state(state)
        self._prepare_texture_atlas()
        old_scissor = arcade.get_window().ctx.scissor
        arcade.get_window().ctx.scissor = (
            int(config.WORLD_LEFT),
            int(config.WORLD_BOTTOM),
            int(config.WORLD_WIDTH),
            int(config.WORLD_HEIGHT),
        )
        try:
            self._draw_world_background()
            if not self._draw_room_background_image():
                self._draw_room_layout(view_state)
            self._draw_perception_range(view_state)
            self._draw_action_path(view_state, now)
            self._draw_room_objects(view_state, now)
            self._draw_tracked_objects(view_state)
            self._draw_user_or_target(view_state)
            self._draw_audio_direction(view_state)
            self._draw_visual_markers(view_state)
            self._draw_pending_placement(state)
            self._draw_action_effects(view_state, now)
            self._draw_interaction_links(view_state, now)
            self._draw_dog(view_state, now)
            self._draw_heading_arrow(view_state)
            self._draw_robot_status_plate(view_state)
            self._draw_interrupt_overlay(view_state, now)
            self._draw_recent_action_steps(view_state, now)
            self._draw_scene_status(view_state)
            self._draw_world_labels(view_state)
        finally:
            arcade.get_window().ctx.scissor = old_scissor

    def _prepare_texture_atlas(self) -> None:
        if self._texture_atlas_ready:
            return
        ctx = arcade.get_window().ctx
        if self._room_background_texture is not None:
            ctx.default_atlas.add(self._room_background_texture)
        self._dog_texture_atlases = {
            pose: DefaultTextureAtlas((512, 512), textures=[texture], ctx=ctx)
            for pose, texture in self._dog_textures.items()
        }
        self._texture_atlas_ready = True

    def scene_to_screen(self, x: float, y: float) -> tuple[float, float]:
        scale_x = config.WORLD_WIDTH / max(
            1.0,
            config.SCENE_LOGICAL_RIGHT - config.SCENE_LOGICAL_LEFT,
        )
        scale_y = config.WORLD_HEIGHT / max(
            1.0,
            config.SCENE_LOGICAL_TOP - config.SCENE_LOGICAL_BOTTOM,
        )
        return (
            config.WORLD_LEFT + (x - config.SCENE_LOGICAL_LEFT) * scale_x,
            config.WORLD_BOTTOM + (y - config.SCENE_LOGICAL_BOTTOM) * scale_y,
        )

    def hit_test(self, state: SimState, x: float, y: float) -> str | None:
        dog_x, dog_y = self.scene_to_screen(state.dog_x, state.dog_y)
        if math.hypot(x - dog_x, y - dog_y) <= 48:
            return "dog"
        view_state = self._screen_state(state)
        user_x, user_y = view_state.user_x, view_state.user_y
        if math.hypot(x - user_x, y - user_y) <= 42:
            return "user"
        for name, item in state.room_objects.items():
            object_x = _float_or_none(item.get("x"))
            object_y = _float_or_none(item.get("y"))
            if object_x is None or object_y is None:
                continue
            screen_x, screen_y = self.scene_to_screen(object_x, object_y)
            if math.hypot(x - screen_x, y - screen_y) <= 30:
                return str(name)
        latest = state.latest_visual_event or {}
        tracked = latest.get("tracked_objects")
        if isinstance(tracked, list):
            for index, item in enumerate(tracked):
                if not isinstance(item, dict):
                    continue
                object_x, object_y = _object_position(item)
                if math.hypot(x - object_x, y - object_y) <= 24:
                    return f"tracked:{index}"
        return None

    def _screen_state(self, state: SimState) -> SimState:
        view_state = copy(state)
        view_state.dog_x, view_state.dog_y = self.scene_to_screen(state.dog_x, state.dog_y)
        view_state.user_x, view_state.user_y = self.scene_to_screen(state.user_x, state.user_y)
        view_state.room_objects = {}
        for name, item in state.room_objects.items():
            copied = dict(item)
            x = _float_or_none(copied.get("x"))
            y = _float_or_none(copied.get("y"))
            if x is not None and y is not None:
                copied["x"], copied["y"] = self.scene_to_screen(x, y)
            view_state.room_objects[str(name)] = copied
        if isinstance(state.active_target, dict):
            target = dict(state.active_target)
            x = _float_or_none(target.get("x"))
            y = _float_or_none(target.get("y"))
            if x is not None and y is not None and not (0 <= x <= 1 and 0 <= y <= 1):
                target["x"], target["y"] = self.scene_to_screen(x, y)
            view_state.active_target = target
        return view_state

    def _draw_world_background(self) -> None:
        arcade.draw_lrbt_rectangle_filled(
            config.WORLD_LEFT,
            config.WORLD_RIGHT,
            config.WORLD_BOTTOM,
            config.WORLD_TOP,
            config.COLORS["world_background"],
        )
        room_left = config.WORLD_LEFT + 10
        room_right = config.WORLD_RIGHT - 10
        room_bottom = config.WORLD_BOTTOM + 10
        room_top = config.WORLD_TOP - 10
        arcade.draw_lrbt_rectangle_filled(
            room_left + 4,
            room_right + 4,
            room_bottom - 4,
            room_top - 4,
            (*config.COLORS["shadow"], 110),
        )
        arcade.draw_lrbt_rectangle_filled(
            room_left,
            room_right,
            room_bottom,
            room_top,
            config.COLORS["world_floor"],
        )
        arcade.draw_lrbt_rectangle_outline(
            room_left,
            room_right,
            room_bottom,
            room_top,
            config.COLORS["world_wall_dark"],
            6,
        )

    def _draw_room_background_image(self) -> bool:
        if self._room_background_texture is None:
            return False
        room_left = config.WORLD_LEFT + 10
        room_bottom = config.WORLD_BOTTOM + 10
        room_width = max(1.0, config.WORLD_WIDTH - 20)
        room_height = max(1.0, config.WORLD_HEIGHT - 20)
        background_rect = arcade.LBWH(room_left, room_bottom, room_width, room_height)
        arcade.draw_texture_rect(self._room_background_texture, background_rect)
        arcade.draw_lrbt_rectangle_outline(
            room_left,
            room_left + room_width,
            room_bottom,
            room_bottom + room_height,
            config.COLORS["world_wall_dark"],
            2,
        )
        return True

    def _draw_room_layout(self, state: SimState) -> None:
        del state
        room_left = config.WORLD_LEFT + 10
        room_right = config.WORLD_RIGHT - 10
        room_bottom = config.WORLD_BOTTOM + 10
        room_top = config.WORLD_TOP - 10
        scale = self._scene_scale()

        plank_height = max(28.0, 42.0 * scale)
        plank_width = max(92.0, 154.0 * scale)
        row = 0
        y = room_bottom + plank_height
        while y < room_top:
            if row % 2:
                arcade.draw_lrbt_rectangle_filled(
                    room_left,
                    room_right,
                    y - plank_height,
                    y,
                    (*config.COLORS["world_floor_alt"], 62),
                )
            arcade.draw_line(room_left, y, room_right, y, config.COLORS["world_grid"], 1)
            seam_x = room_left + (-0.5 if row % 2 else 0.2) * plank_width
            while seam_x < room_right:
                arcade.draw_line(
                    seam_x,
                    y - plank_height,
                    seam_x,
                    y,
                    config.COLORS["world_plank_soft"],
                    1,
                )
                seam_x += plank_width
            y += plank_height
            row += 1

        self._draw_tiled_area(35, 125, 300, 305, "厨房 / 喂食区")
        self._draw_tiled_area(650, 125, 855, 300, "生活设施区")
        self._draw_rug(60, 325, 445, 590, config.COLORS["world_rug"], "客厅 / 休息区")
        self._draw_oval_rug(690, 530, 205, 142, _mix(config.COLORS["emotion"], config.COLORS["world_floor"], 0.52), "玩耍区")
        self._draw_oval_rug(505, 190, 150, 86, (151, 139, 121), "护理区")

        wall_color = config.COLORS["world_wall"]
        self._draw_wall_segment(35, 305, 300, 305, wall_color)
        self._draw_wall_segment(650, 300, 855, 300, wall_color)
        self._draw_wall_segment(650, 125, 650, 238, wall_color)
        self._draw_wall_segment(650, 275, 650, 300, wall_color)

        sofa_x, sofa_y = self.scene_to_screen(70, 540)
        self._draw_sofa(sofa_x, sofa_y, scale)
        table_x, table_y = self.scene_to_screen(255, 455)
        self._draw_low_table(table_x, table_y, scale)
        storage_x, storage_y = self.scene_to_screen(660, 620)
        self._draw_storage(storage_x, storage_y, scale)
        kitchen_x, kitchen_y = self.scene_to_screen(48, 155)
        self._draw_kitchen_counter(kitchen_x, kitchen_y, scale)
        utility_x, utility_y = self.scene_to_screen(812, 148)
        self._draw_utility_cabinet(utility_x, utility_y, scale)

        window_x, window_y = self.scene_to_screen(350, 686)
        self._draw_window(window_x, window_y, scale)
        second_window_x, second_window_y = self.scene_to_screen(760, 686)
        self._draw_window(second_window_x, second_window_y, scale * 0.78)
        plant_x, plant_y = self.scene_to_screen(825, 575)
        self._draw_plant(plant_x, plant_y, scale)
        small_plant_x, small_plant_y = self.scene_to_screen(610, 165)
        self._draw_plant(small_plant_x, small_plant_y, scale * 0.72)
        door_x, door_y = self.scene_to_screen(370, 125)
        self._draw_door(door_x, door_y, scale)

    def _scene_scale(self) -> float:
        scale_x = config.WORLD_WIDTH / max(1.0, config.SCENE_LOGICAL_RIGHT - config.SCENE_LOGICAL_LEFT)
        scale_y = config.WORLD_HEIGHT / max(1.0, config.SCENE_LOGICAL_TOP - config.SCENE_LOGICAL_BOTTOM)
        return max(0.58, min(scale_x, scale_y))

    def _logical_rect(self, left: float, bottom: float, right: float, top: float) -> tuple[float, float, float, float]:
        screen_left, screen_bottom = self.scene_to_screen(left, bottom)
        screen_right, screen_top = self.scene_to_screen(right, top)
        return screen_left, screen_bottom, screen_right, screen_top

    def _draw_tiled_area(self, left: float, bottom: float, right: float, top: float, label: str) -> None:
        screen_left, screen_bottom, screen_right, screen_top = self._logical_rect(left, bottom, right, top)
        arcade.draw_lrbt_rectangle_filled(screen_left, screen_right, screen_bottom, screen_top, config.COLORS["world_tile"])
        tile = max(32.0, 54.0 * self._scene_scale())
        y = screen_bottom + tile
        while y < screen_top:
            arcade.draw_line(screen_left, y, screen_right, y, config.COLORS["world_tile_line"], 1)
            y += tile
        x = screen_left + tile
        while x < screen_right:
            arcade.draw_line(x, screen_bottom, x, screen_top, config.COLORS["world_tile_line"], 1)
            x += tile
        draw_text(label, screen_left + 10, screen_top - 10, config.COLORS["world_muted"], config.FONT_SIZE_AUX, bold=True, anchor_y="top")

    def _draw_rug(
        self,
        left: float,
        bottom: float,
        right: float,
        top: float,
        color: tuple[int, int, int],
        label: str,
    ) -> None:
        screen_left, screen_bottom, screen_right, screen_top = self._logical_rect(left, bottom, right, top)
        arcade.draw_lrbt_rectangle_filled(screen_left + 4, screen_right + 4, screen_bottom - 4, screen_top - 4, (*config.COLORS["shadow"], 70))
        arcade.draw_lrbt_rectangle_filled(screen_left, screen_right, screen_bottom, screen_top, color)
        arcade.draw_lrbt_rectangle_outline(screen_left + 7, screen_right - 7, screen_bottom + 7, screen_top - 7, _mix(color, config.COLORS["world_text"], 0.32), 2)
        draw_text(label, screen_left + 12, screen_top - 12, _mix(config.COLORS["world_text"], color, 0.3), config.FONT_SIZE_AUX, bold=True, anchor_y="top")

    def _draw_oval_rug(
        self,
        center_x: float,
        center_y: float,
        width: float,
        height: float,
        color: tuple[int, int, int],
        label: str,
    ) -> None:
        x, y = self.scene_to_screen(center_x, center_y)
        scale_x = config.WORLD_WIDTH / max(1.0, config.SCENE_LOGICAL_RIGHT - config.SCENE_LOGICAL_LEFT)
        scale_y = config.WORLD_HEIGHT / max(1.0, config.SCENE_LOGICAL_TOP - config.SCENE_LOGICAL_BOTTOM)
        screen_width = width * scale_x
        screen_height = height * scale_y
        arcade.draw_ellipse_filled(x + 4, y - 4, screen_width, screen_height, (*config.COLORS["shadow"], 75))
        arcade.draw_ellipse_filled(x, y, screen_width, screen_height, color)
        arcade.draw_ellipse_outline(x, y, screen_width - 12, screen_height - 12, _mix(color, config.COLORS["world_text"], 0.34), 2)
        draw_text(label, x - screen_width / 2 + 22, y + screen_height / 2 - 15, _mix(config.COLORS["world_text"], color, 0.3), config.FONT_SIZE_AUX, bold=True, anchor_y="top")

    def _draw_wall_segment(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        color: tuple[int, int, int],
    ) -> None:
        x1, y1 = self.scene_to_screen(start_x, start_y)
        x2, y2 = self.scene_to_screen(end_x, end_y)
        arcade.draw_line(x1 + 2, y1 - 3, x2 + 2, y2 - 3, (*config.COLORS["shadow"], 90), 7)
        arcade.draw_line(x1, y1, x2, y2, color, 6)

    def _draw_window(self, x: float, y: float, scale: float) -> None:
        width = 112 * scale
        height = 20 * scale
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, config.COLORS["world_wall_dark"])
        arcade.draw_lbwh_rectangle_filled(x + 5, y + 4, width - 10, height - 8, (133, 169, 174))
        arcade.draw_line(x + width / 2, y + 4, x + width / 2, y + height - 4, config.COLORS["world_wall"], 2)

    def _draw_door(self, x: float, y: float, scale: float) -> None:
        width = 88 * scale
        height = 56 * scale
        arcade.draw_line(x, y, x + width, y, config.COLORS["world_wall_dark"], 6)
        arcade.draw_line(x, y, x + width, y + height, config.COLORS["furniture_wood"], 3)
        arcade.draw_arc_outline(x, y, width * 2, height * 2, config.COLORS["world_muted"], 0, 46, 1)

    def _draw_sofa(self, x: float, y: float, scale: float) -> None:
        width = 250 * scale
        height = 70 * scale
        arcade.draw_lbwh_rectangle_filled(x + 5, y - 5, width, height, (*config.COLORS["shadow"], 95))
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, config.COLORS["furniture_fabric_dark"])
        arcade.draw_lbwh_rectangle_filled(x + 10 * scale, y + 13 * scale, width - 20 * scale, height - 23 * scale, config.COLORS["furniture_fabric"])
        cushion_gap = 6 * scale
        cushion_width = (width - 34 * scale) / 2
        for index in range(2):
            cushion_x = x + 14 * scale + index * (cushion_width + cushion_gap)
            arcade.draw_lbwh_rectangle_outline(cushion_x, y + 18 * scale, cushion_width, 35 * scale, _mix(config.COLORS["furniture_fabric"], config.COLORS["world_wall"], 0.22), 1)
        arcade.draw_circle_filled(x + 13 * scale, y + 20 * scale, 12 * scale, config.COLORS["furniture_fabric_dark"])
        arcade.draw_circle_filled(x + width - 13 * scale, y + 20 * scale, 12 * scale, config.COLORS["furniture_fabric_dark"])

    def _draw_low_table(self, x: float, y: float, scale: float) -> None:
        width = 148 * scale
        height = 62 * scale
        arcade.draw_ellipse_filled(x + 5, y - 5, width, height, (*config.COLORS["shadow"], 90))
        arcade.draw_ellipse_filled(x, y, width, height, config.COLORS["furniture_wood_light"])
        arcade.draw_ellipse_outline(x, y, width, height, config.COLORS["furniture_wood"], 3)
        arcade.draw_circle_outline(x, y, 10 * scale, config.COLORS["furniture_cream"], 3)

    def _draw_storage(self, x: float, y: float, scale: float) -> None:
        width = 142 * scale
        height = 48 * scale
        arcade.draw_lbwh_rectangle_filled(x + 4, y - 4, width, height, (*config.COLORS["shadow"], 85))
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, config.COLORS["furniture_wood"])
        arcade.draw_lbwh_rectangle_outline(x, y, width, height, config.COLORS["world_wall_dark"], 2)
        for index in range(1, 3):
            divider = x + width * index / 3
            arcade.draw_line(divider, y + 5, divider, y + height - 5, config.COLORS["furniture_wood_light"], 1)
        for index in range(3):
            arcade.draw_circle_filled(x + width * (index + 0.5) / 3, y + height / 2, 2.5 * scale, config.COLORS["furniture_cream"])

    def _draw_kitchen_counter(self, x: float, y: float, scale: float) -> None:
        width = 42 * scale
        height = 126 * scale
        arcade.draw_lbwh_rectangle_filled(x + 4, y - 4, width, height, (*config.COLORS["shadow"], 80))
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, config.COLORS["furniture_cream"])
        arcade.draw_lbwh_rectangle_outline(x, y, width, height, config.COLORS["world_wall_dark"], 2)
        arcade.draw_line(x + 7 * scale, y + height * 0.55, x + width - 7 * scale, y + height * 0.55, config.COLORS["world_tile_line"], 1)
        arcade.draw_circle_filled(x + width / 2, y + height * 0.78, 8 * scale, config.COLORS["world_tile"])

    def _draw_utility_cabinet(self, x: float, y: float, scale: float) -> None:
        width = 42 * scale
        height = 102 * scale
        arcade.draw_lbwh_rectangle_filled(x + 4, y - 4, width, height, (*config.COLORS["shadow"], 80))
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, config.COLORS["furniture_cream"])
        arcade.draw_lbwh_rectangle_outline(x, y, width, height, config.COLORS["world_wall_dark"], 2)
        arcade.draw_line(x, y + height * 0.45, x + width, y + height * 0.45, config.COLORS["world_tile_line"], 1)
        arcade.draw_circle_filled(x + width - 8 * scale, y + height * 0.7, 2 * scale, config.COLORS["furniture_wood_light"])

    def _draw_plant(self, x: float, y: float, scale: float) -> None:
        arcade.draw_ellipse_filled(x, y - 4 * scale, 34 * scale, 14 * scale, (*config.COLORS["shadow"], 80))
        arcade.draw_ellipse_filled(x, y, 30 * scale, 18 * scale, config.COLORS["furniture_wood_light"])
        for angle in (-1.05, -0.55, 0.0, 0.55, 1.05):
            end_x = x + math.sin(angle) * 24 * scale
            end_y = y + math.cos(angle) * 34 * scale
            arcade.draw_line(x, y + 5 * scale, end_x, end_y, config.COLORS["plant"], 5 * scale)

    def _draw_perception_range(self, state: SimState) -> None:
        if not state.ui_show_fov:
            return
        heading = math.radians(state.dog_heading)
        radius = min(145.0, config.WORLD_WIDTH * 0.20)
        spread = math.radians(34)
        left_x = state.dog_x + math.cos(heading + spread) * radius
        left_y = state.dog_y + math.sin(heading + spread) * radius
        right_x = state.dog_x + math.cos(heading - spread) * radius
        right_y = state.dog_y + math.sin(heading - spread) * radius
        arcade.draw_triangle_filled(
            state.dog_x,
            state.dog_y,
            left_x,
            left_y,
            right_x,
            right_y,
            (*config.COLORS["visual"], 13),
        )
        arcade.draw_line(state.dog_x, state.dog_y, left_x, left_y, (*config.COLORS["visual"], 72), 1)
        arcade.draw_line(state.dog_x, state.dog_y, right_x, right_y, (*config.COLORS["visual"], 72), 1)
        arcade.draw_arc_outline(
            state.dog_x,
            state.dog_y,
            radius * 2,
            radius * 2,
            (*config.COLORS["visual"], 46),
            math.degrees(heading - spread),
            math.degrees(heading + spread),
            1,
        )

    def _draw_pending_placement(self, state: SimState) -> None:
        pending = state.ui_pending_placement
        if not pending or pending.get("x") is None or pending.get("y") is None:
            return
        x = float(pending["x"])
        y = float(pending["y"])
        color = config.COLORS["warning"] if pending.get("group") == "Audio" else config.COLORS["accent"]
        self._draw_dashed_ring(x, y, 28, color)
        arcade.draw_circle_filled(x, y, 6, (*color, 130))
        arcade.draw_line(x - 10, y, x + 10, y, color, 1)
        arcade.draw_line(x, y - 10, x, y + 10, color, 1)
        if pending.get("group") == "Audio":
            dog_x, dog_y = self.scene_to_screen(state.dog_x, state.dog_y)
            arcade.draw_line(dog_x, dog_y, x, y, (*color, 150), 2)
        kind = str(pending.get("kind") or "target")
        identity = (
            state.event_injector_fields.get("vision_object")
            if kind == "object"
            else state.event_injector_fields.get("vision_identity")
        ) or kind
        confidence = pending.get("confidence")
        _draw_tag(
            min(x + 18, config.WORLD_RIGHT - 190),
            min(y + 38, config.WORLD_TOP - 26),
            _truncate(f"preview {identity}  conf={confidence}  ({x:.0f},{y:.0f})", 42),
            color,
        )

    def _draw_dashed_ring(
        self,
        x: float,
        y: float,
        radius: float,
        color: tuple[int, int, int],
    ) -> None:
        segments = 18
        for index in range(0, segments, 2):
            start = math.tau * index / segments
            end = math.tau * (index + 1) / segments
            arcade.draw_line(
                x + math.cos(start) * radius,
                y + math.sin(start) * radius,
                x + math.cos(end) * radius,
                y + math.sin(end) * radius,
                color,
                2,
            )

    def _draw_heading_arrow(self, state: SimState) -> None:
        heading = math.radians(state.dog_heading)
        start_x = state.dog_x + math.cos(heading) * 42
        start_y = state.dog_y + math.sin(heading) * 42
        end_x = state.dog_x + math.cos(heading) * 72
        end_y = state.dog_y + math.sin(heading) * 72
        arcade.draw_line(start_x, start_y, end_x, end_y, config.COLORS["dog_accent"], 3)
        self._draw_arrow_head(end_x, end_y, heading, config.COLORS["dog_accent"])

    def _draw_robot_status_plate(self, state: SimState) -> None:
        if not state.active_behavior and state.action_status == "waiting":
            return
        width = min(248.0, max(205.0, config.WORLD_WIDTH * 0.34))
        height = 70
        target = _action_target_position(state)
        target_is_right = target is None or target[0] >= state.dog_x
        x = state.dog_x - width - 72 if target_is_right else state.dog_x + 72
        if x < config.WORLD_LEFT + 12 or x + width > config.WORLD_RIGHT - 12:
            x = state.dog_x + 72 if target_is_right else state.dog_x - width - 72
        x = max(config.WORLD_LEFT + 12, min(config.WORLD_RIGHT - width - 12, x))
        top = min(config.WORLD_TOP - 56, max(config.WORLD_BOTTOM + height + 12, state.dog_y + 82))
        bottom = top - height
        status_color = _status_color(state)
        arcade.draw_lbwh_rectangle_filled(x, bottom, width, height, (*config.COLORS["surface"], 232))
        arcade.draw_lbwh_rectangle_outline(x, bottom, width, height, status_color, 1)
        arcade.draw_lbwh_rectangle_filled(x, bottom, 3, height, status_color)
        lines = (
            ("行为", state.active_behavior or "-", config.COLORS["text"]),
            ("阶段", f"{state.action_stage_index or '-'}/{state.action_stage_total or '-'} {state.action_stage_label}", config.COLORS["muted_text"]),
            ("动作", state.action_current_action, config.COLORS["accent"]),
            ("目标", _display_scene_label(state.action_target_label), config.COLORS["muted_text"]),
        )
        y = top - 9
        value_x = x + 72
        max_value_chars = max(18, int((width - 84) / 6.2))
        for label, value, color in lines:
            draw_text(label, x + 10, y, config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_y="top")
            draw_text(_truncate(value, max_value_chars), value_x, y, color, config.FONT_SIZE_AUX, bold=label in {"行为", "动作"}, anchor_y="top")
            y -= 16

    def _draw_dog(self, state: SimState, now: float) -> None:
        if self._dog_textures:
            self._draw_dog_sprite(state, now)
            return

        action = _action_key(state)
        x = state.dog_x
        y = state.dog_y
        heading_deg = state.dog_heading

        if _action_matches(action, "TREMBLE", "ANXIETY"):
            x += math.sin(now * 38.0) * 2.4
            y += math.cos(now * 31.0) * 1.6

        lift = 0.0
        if _action_matches(action, "HOP", "JUMP", "POUNCE", "EXCITE"):
            lift = abs(math.sin(now * 8.5)) * 14.0
            y += lift

        body_w = 84.0
        body_h = 46.0
        body_angle = heading_deg
        head_forward = 48.0
        label_offset = -62.0

        if _action_matches(action, "SLEEP", "REST", "CALM", "LYING", "LIE_DOWN", "CURLED", "ROLL_OVER"):
            body_w = 92.0
            body_h = 34.0
            body_angle = heading_deg + 14.0
            head_forward = 40.0
        elif _action_matches(action, "SIT", "OWNER_ATTENTION"):
            body_w = 64.0
            body_h = 56.0
            head_forward = 38.0
        elif _action_matches(action, "PLAY_BOW"):
            body_angle = heading_deg - 7.0
            head_forward = 54.0
        elif _action_matches(action, "STRETCH"):
            body_w = 104.0
            body_h = 38.0
            head_forward = 58.0

        if _action_matches(action, "ZOOMIES", "FLEE", "PACE", "MATCH_OWNER"):
            self._draw_motion_trail(x, y - lift, math.radians(heading_deg), now)

        shadow_w = max(70.0, body_w + 30.0 - lift * 2.0)
        arcade.draw_ellipse_filled(x, state.dog_y - 34, shadow_w, 22, config.COLORS["shadow"])

        heading = math.radians(heading_deg)
        back_x, back_y = _rotated_point(x, y, heading, -body_w / 2 + 3, 0)
        tail_speed = 18.0 if _action_matches(action, "WAG_FAST", "SOCIAL_WAG", "EXCITE") else 7.5
        wag = math.sin(now * tail_speed) * (0.72 if _action_matches(action, "WAG", "SOCIAL", "JOY") else 0.22)
        tail_angle = heading + math.pi + wag
        if _action_matches(action, "TAIL_UP"):
            tail_angle += 0.35
        if _action_matches(action, "SLEEP", "REST", "CALM", "CURLED"):
            tail_angle = heading + math.pi - 0.2
        tail_len = 35.0 if _action_matches(action, "WAG", "SOCIAL", "JOY", "HOP") else 27.0
        arcade.draw_line(
            back_x,
            back_y,
            back_x + math.cos(tail_angle) * tail_len,
            back_y + math.sin(tail_angle) * tail_len,
            config.COLORS["dog_dark"],
            5,
        )
        arcade.draw_circle_filled(
            back_x + math.cos(tail_angle) * tail_len,
            back_y + math.sin(tail_angle) * tail_len,
            5,
            config.COLORS["dog_dark"],
        )

        self._draw_dog_legs(x, y, heading, action, now, body_h)

        if _action_matches(action, "FREEZE", "HOLD_POSITION", "SAFE_DISTANCE"):
            arcade.draw_circle_outline(x, y, 58, config.COLORS["warning"], 2)
            arcade.draw_circle_outline(x, y, 66, (101, 55, 59), 1)

        body_color = config.COLORS["dog_body"]
        if _action_matches(action, "CHARGER", "RECHARGE", "DOCKED"):
            body_color = (78, 188, 176)
        elif _action_matches(action, "FEAR", "FLEE", "TREMBLE", "FREEZE"):
            body_color = (104, 152, 207)
        elif _action_matches(action, "SLEEP", "REST", "CALM", "CURLED"):
            body_color = (95, 135, 168)

        arcade.draw_ellipse_filled(x, y, body_w, body_h, body_color, tilt_angle=body_angle)
        arcade.draw_ellipse_outline(
            x,
            y,
            body_w + 5,
            body_h + 5,
            config.COLORS["furniture_cream"],
            2,
            tilt_angle=body_angle,
        )

        head_side = 0.0
        head_angle = heading
        if _action_matches(action, "HEAD_TILT"):
            head_side = math.sin(now * 3.0) * 8.0
            head_angle += 0.22
        elif _action_matches(action, "LOOK_AROUND", "CURIOUS"):
            head_angle += math.sin(now * 2.8) * 0.75
        elif _action_matches(action, "SNIFF"):
            head_forward += 8.0

        head_x, head_y = _rotated_point(x, y, heading, head_forward, head_side)
        nose_x = head_x + math.cos(head_angle) * 17.0
        nose_y = head_y + math.sin(head_angle) * 17.0
        left_ear = _rotated_point(head_x, head_y, head_angle, -8.0, 15.0)
        right_ear = _rotated_point(head_x, head_y, head_angle, -8.0, -15.0)
        ear_tip_left = _rotated_point(head_x, head_y, head_angle, 3.0, 25.0)
        ear_tip_right = _rotated_point(head_x, head_y, head_angle, 3.0, -25.0)

        arcade.draw_triangle_filled(
            left_ear[0],
            left_ear[1],
            ear_tip_left[0],
            ear_tip_left[1],
            head_x + math.cos(head_angle) * 7.0,
            head_y + math.sin(head_angle) * 7.0,
            config.COLORS["dog_dark"],
        )
        arcade.draw_triangle_filled(
            right_ear[0],
            right_ear[1],
            ear_tip_right[0],
            ear_tip_right[1],
            head_x + math.cos(head_angle) * 7.0,
            head_y + math.sin(head_angle) * 7.0,
            config.COLORS["dog_dark"],
        )
        arcade.draw_ellipse_filled(
            head_x,
            head_y,
            34,
            29,
            config.COLORS["dog_accent"],
            tilt_angle=math.degrees(head_angle),
        )
        arcade.draw_circle_filled(nose_x, nose_y, 4, (19, 24, 28))

        if _action_matches(action, "SLEEP", "REST", "CALM", "CURLED"):
            eye_left = _rotated_point(head_x, head_y, head_angle, 5.0, 7.0)
            eye_right = _rotated_point(head_x, head_y, head_angle, 5.0, -7.0)
            arcade.draw_line(eye_left[0] - 3, eye_left[1], eye_left[0] + 3, eye_left[1], (20, 27, 32), 2)
            arcade.draw_line(eye_right[0] - 3, eye_right[1], eye_right[0] + 3, eye_right[1], (20, 27, 32), 2)
        else:
            eye_left = _rotated_point(head_x, head_y, head_angle, 5.0, 7.0)
            eye_right = _rotated_point(head_x, head_y, head_angle, 5.0, -7.0)
            arcade.draw_circle_filled(eye_left[0], eye_left[1], 3, (20, 27, 32))
            arcade.draw_circle_filled(eye_right[0], eye_right[1], 3, (20, 27, 32))

        if _action_matches(action, "PAW"):
            paw_x, paw_y = _rotated_point(x, y, heading, 50.0, -22.0)
            arcade.draw_line(x, y - 3, paw_x, paw_y, config.COLORS["dog_accent"], 4)
            arcade.draw_circle_filled(paw_x, paw_y, 6, config.COLORS["dog_accent"])

        draw_text(
            "MarsDog",
            x - 28,
            state.dog_y + label_offset,
            config.COLORS["world_text"],
            config.FONT_SIZE,
            bold=True,
        )

    def _draw_dog_sprite(self, state: SimState, now: float) -> None:
        action = _action_key(state)
        pose = _dog_pose_for_action(action)
        texture = self._dog_textures.get(pose) or self._dog_textures["stand"]
        x = state.dog_x
        y = state.dog_y

        if _action_matches(action, "TREMBLE", "ANXIETY"):
            x += math.sin(now * 38.0) * 2.4
            y += math.cos(now * 31.0) * 1.6

        lift = 0.0
        if _action_matches(action, "HOP", "JUMP", "BOUNCE", "EXCITE"):
            lift = abs(math.sin(now * 8.5)) * 13.0
            y += lift
        elif pose == "walk" and state.action_status == "running":
            y += abs(math.sin(now * 8.0)) * 2.5

        if pose == "walk" and state.action_status == "running":
            self._draw_motion_trail(x, state.dog_y, math.radians(state.dog_heading), now)

        size = 148.0 if pose in {"stand", "walk", "play_bow", "lie"} else 142.0
        shadow_width = 104.0 if pose not in {"sit", "paw"} else 76.0
        shadow_height = 20.0 if pose != "lie" else 16.0
        arcade.draw_ellipse_filled(
            x,
            state.dog_y - 36,
            max(58.0, shadow_width - lift * 1.8),
            shadow_height,
            (*config.COLORS["shadow"], 105),
        )
        angle = state.dog_heading % 360.0
        arcade.draw_texture_rect(
            texture,
            arcade.LBWH(x - size / 2, y - size / 2, size, size),
            angle=angle,
            atlas=self._dog_texture_atlases.get(pose),
        )
        draw_text(
            "MarsDog",
            x,
            state.dog_y - 61,
            config.COLORS["world_text"],
            config.FONT_SIZE,
            bold=True,
            anchor_x="center",
        )

    def _draw_motion_trail(
        self,
        x: float,
        y: float,
        heading: float,
        now: float,
    ) -> None:
        for index, distance in enumerate((36.0, 62.0, 88.0)):
            pulse = 1.0 + math.sin(now * 8.0 + index) * 0.18
            px = x - math.cos(heading) * distance
            py = y - math.sin(heading) * distance
            arcade.draw_ellipse_filled(
                px,
                py - 6,
                (36 - index * 6) * pulse,
                9,
                (50, 62, 61),
                tilt_angle=math.degrees(heading),
            )

    def _draw_dog_legs(
        self,
        x: float,
        y: float,
        heading: float,
        action: str,
        now: float,
        body_h: float,
    ) -> None:
        if _action_matches(action, "SLEEP", "REST", "CALM", "LYING", "LIE_DOWN", "CURLED", "ROLL_OVER"):
            for forward, side in ((-18.0, -14.0), (8.0, -16.0), (-10.0, 15.0), (18.0, 14.0)):
                start = _rotated_point(x, y, heading, forward, side)
                end = _rotated_point(x, y, heading, forward + 8.0, side + (8.0 if side > 0 else -8.0))
                arcade.draw_line(start[0], start[1], end[0], end[1], config.COLORS["dog_dark"], 4)
            return

        speed = 13.0 if _action_matches(action, "ZOOMIES", "FLEE", "RUN") else 7.5
        stride = math.sin(now * speed)
        if _action_matches(action, "FREEZE", "SIT", "HOLD_POSITION", "OWNER_ATTENTION"):
            stride = 0.0
        leg_color = config.COLORS["dog_dark"]
        side_extent = body_h / 2 + 8.0
        leg_specs = (
            (-26.0, -1.0),
            (-4.0, 1.0),
            (10.0, -1.0),
            (30.0, 1.0),
        )
        for index, (forward, phase_sign) in enumerate(leg_specs):
            side = -side_extent if index % 2 == 0 else side_extent
            stride_offset = stride * phase_sign * 8.0
            hip = _rotated_point(x, y, heading, forward, side * 0.68)
            foot = _rotated_point(x, y, heading, forward + stride_offset, side)
            arcade.draw_line(hip[0], hip[1], foot[0], foot[1], leg_color, 4)
            arcade.draw_circle_filled(foot[0], foot[1], 5, config.COLORS["dog_dark"])

    def _draw_user_or_target(self, state: SimState) -> None:
        target = state.active_target or {}
        x, y = state.user_x, state.user_y
        identity = target.get("identity") or "user"
        speaker_id = target.get("speaker_id")
        action = _action_key(state)
        social_active = state.action_status == "running" and _action_matches(
            action,
            "OWNER",
            "SOCIAL",
            "CUDDLE",
            "PERSON",
            "NUDGE",
            "HAND",
            "FOLLOW",
            "PLAY_BOW",
        )

        target_active = bool(state.active_target) or social_active
        arcade.draw_ellipse_filled(x, y - 30, 58, 14, (*config.COLORS["shadow"], 105))
        if target_active:
            pulse = 1.0 + math.sin(time.time() * 5.5) * 0.1
            arcade.draw_circle_outline(x, y, 42 * pulse, config.COLORS["target"], 2)
            arcade.draw_circle_outline(x, y, 52 * pulse, (*config.COLORS["target"], 90), 1)

        clothing = config.COLORS["furniture_fabric_dark"]
        skin = (207, 166, 126)
        hair = (76, 57, 45)
        pose_action = str(target.get("pose_action") or "").lower()
        latest_events = (state.latest_visual_event or {}).get("events") or []
        fallen = pose_action == "fallen_down" or any("FALL" in str(event) for event in latest_events)
        if fallen:
            arcade.draw_ellipse_filled(x, y - 4, 72, 26, clothing, tilt_angle=-16)
            arcade.draw_circle_filled(x + 38, y - 14, 18, hair)
            arcade.draw_circle_filled(x + 34, y - 11, 14, skin)
            arcade.draw_line(x - 25, y - 4, x - 49, y + 10, clothing, 6)
            arcade.draw_line(x - 22, y - 10, x - 47, y - 24, clothing, 6)
            draw_text(
                _truncate(_display_scene_label(str(identity)), 18),
                x + 46,
                y + 22,
                config.COLORS["world_text"],
                config.FONT_SIZE,
                bold=True,
            )
            return

        arcade.draw_line(x - 10, y - 26, x - 20, y - 43, clothing, 6)
        arcade.draw_line(x + 10, y - 26, x + 20, y - 43, clothing, 6)
        arcade.draw_ellipse_filled(x, y - 12, 38, 48, clothing)
        hand_interaction = state.action_status == "running" and _action_matches(
            action,
            "HAND",
            "HIGH_FIVE",
            "PAW_AT",
            "CUDDLE",
            "NUDGE",
        )
        stop_gesture = pose_action == "stop_gesture" or any("STOP_GESTURE" in str(event) for event in latest_events)
        if hand_interaction:
            dx = state.dog_x - x
            dy = state.dog_y - y
            distance = max(1.0, math.hypot(dx, dy))
            hand_x = x + dx / distance * 39.0
            hand_y = y + dy / distance * 39.0
            arcade.draw_line(x - 11, y - 7, hand_x, hand_y, skin, 7)
            arcade.draw_circle_filled(hand_x, hand_y, 5, skin)
            arcade.draw_line(x + 16, y - 8, x + 31, y - 24, skin, 6)
        elif stop_gesture:
            arcade.draw_line(x - 14, y - 8, x - 22, y + 30, skin, 7)
            arcade.draw_circle_filled(x - 22, y + 34, 6, skin)
            arcade.draw_line(x + 16, y - 8, x + 31, y - 24, skin, 6)
        else:
            arcade.draw_line(x - 16, y - 8, x - 31, y - 24, skin, 6)
            arcade.draw_line(x + 16, y - 8, x + 31, y - 24, skin, 6)
        arcade.draw_circle_filled(x, y + 17, 20, hair)
        arcade.draw_circle_filled(x + 2, y + 13, 16, skin)
        arcade.draw_circle_filled(x + 9, y + 13, 2, config.COLORS["world_text"])
        draw_text(
            _truncate(_display_scene_label(str(identity)), 18),
            x + 28,
            y + 31,
            config.COLORS["world_text"],
            config.FONT_SIZE,
            bold=True,
        )
        if speaker_id:
            draw_text(
                _truncate(f"说话人：{speaker_id}", 22),
                x - 48,
                y - 63,
                config.COLORS["world_muted"],
                config.FONT_SIZE_SMALL,
            )

    def _draw_audio_direction(self, state: SimState) -> None:
        if state.audio_wake_angle is None:
            return

        angle = math.radians(state.dog_heading + state.audio_wake_angle)
        start_x = state.dog_x
        start_y = state.dog_y
        end_x = start_x + math.cos(angle) * 145
        end_y = start_y + math.sin(angle) * 145

        left = angle + math.radians(12)
        right = angle - math.radians(12)
        arcade.draw_line(
            start_x,
            start_y,
            start_x + math.cos(left) * 115,
            start_y + math.sin(left) * 115,
            (109, 76, 58),
            2,
        )
        arcade.draw_line(
            start_x,
            start_y,
            start_x + math.cos(right) * 115,
            start_y + math.sin(right) * 115,
            (109, 76, 58),
            2,
        )
        arcade.draw_line(
            start_x,
            start_y,
            end_x,
            end_y,
            config.COLORS["audio"],
            4,
        )
        self._draw_arrow_head(end_x, end_y, angle, config.COLORS["audio"])
        draw_text(
            f"DOA {state.audio_wake_angle:g} deg",
            end_x + 8,
            end_y + 4,
            config.COLORS["audio"],
            config.FONT_SIZE,
        )

    def _draw_arrow_head(
        self,
        x: float,
        y: float,
        angle: float,
        color: tuple[int, int, int],
    ) -> None:
        size = 14
        left = angle + math.radians(150)
        right = angle - math.radians(150)
        arcade.draw_triangle_filled(
            x,
            y,
            x + math.cos(left) * size,
            y + math.sin(left) * size,
            x + math.cos(right) * size,
            y + math.sin(right) * size,
            color,
        )

    def _draw_visual_markers(self, state: SimState) -> None:
        event = state.latest_visual_event
        if not event:
            return

        events = event.get("events") or []
        target_x = state.user_x
        target_y = state.user_y
        if state.active_target:
            target_x, target_y = _target_position(state.active_target, state)

        marker_color = config.COLORS["visual"]
        arcade.draw_circle_outline(target_x, target_y, 48, marker_color, 3)
        arcade.draw_circle_outline(target_x, target_y, 58, (68, 93, 127), 1)

        if any("FALL" in str(item) for item in events):
            arcade.draw_line(
                target_x - 28,
                target_y + 28,
                target_x + 28,
                target_y - 28,
                config.COLORS["warning"],
                4,
            )
            arcade.draw_line(
                target_x - 28,
                target_y - 28,
                target_x + 28,
                target_y + 28,
                config.COLORS["warning"],
                4,
            )

        if events:
            _draw_tag(
                target_x - 96,
                target_y + 58,
                _truncate(", ".join(str(item) for item in events), 34),
                marker_color,
            )

    def _draw_action_path(self, state: SimState, now: float) -> None:
        if state.action_status != "running":
            return
        target = _action_target_position(state)
        if target is None:
            return
        target_x, target_y, label = target
        color = _action_color(state)
        start_x = state.dog_x
        start_y = state.dog_y
        distance = math.hypot(target_x - start_x, target_y - start_y)
        if distance < 18.0:
            return

        arcade.draw_line(start_x, start_y, target_x, target_y, _mix(color, (38, 38, 38), 0.38), 2)
        steps = max(5, min(18, int(distance / 38)))
        for index in range(1, steps):
            phase = (index / steps + now * 0.32) % 1.0
            px = _lerp(start_x, target_x, phase)
            py = _lerp(start_y, target_y, phase)
            radius = 2.0 + (index % 3) * 0.7
            arcade.draw_circle_filled(px, py, radius, color)

        pulse = 1.0 + math.sin(now * 6.0) * 0.12
        arcade.draw_circle_outline(target_x, target_y, 34 * pulse, color, 2)
        arcade.draw_circle_outline(target_x, target_y, 46 * pulse, (76, 84, 78), 1)
        draw_text(
            _truncate(_display_scene_label(label), 18),
            target_x + 20,
            target_y + 30,
            color,
            config.FONT_SIZE_SMALL,
            anchor_y="top",
        )
        if state.action_safe_to_interrupt is not None:
            _draw_tag(
                target_x + 20,
                target_y + 12,
                "可中断" if state.action_safe_to_interrupt else "已锁定",
                config.COLORS["success"] if state.action_safe_to_interrupt else config.COLORS["warning"],
            )

    def _draw_execution_ribbon(self, state: SimState, now: float) -> None:
        if state.action_status in {"waiting", ""} and not state.active_behavior:
            return

        left = config.WORLD_LEFT + 26
        top = config.WORLD_TOP - 104
        width = min(520, config.WORLD_WIDTH - 52)
        height = 46
        status_color = _status_color(state)
        arcade.draw_lbwh_rectangle_filled(left, top - height, width, height, (24, 30, 31))
        arcade.draw_lbwh_rectangle_outline(left, top - height, width, height, status_color, 1)
        arcade.draw_circle_filled(left + 11, top - 13, 4, status_color)
        draw_text(
            _truncate(f"{state.active_behavior or '-'}  {state.action_phase}", 54),
            left + 22,
            top - 5,
            config.COLORS["text"],
            config.FONT_SIZE_SMALL,
            bold=True,
            anchor_y="top",
        )
        draw_text(
            _truncate(f"原因={state.action_trigger_reason} 目标={_display_scene_label(state.action_target_label)}", 62),
            left + 22,
            top - 19,
            config.COLORS["muted_text"],
            config.FONT_SIZE_SMALL,
            anchor_y="top",
        )

        total = max(1, state.action_stage_total or 3)
        active = max(1, min(total, state.action_stage_index or 1))
        strip_left = left + 230
        strip_top = top - 28
        strip_w = width - 246
        gap = 4
        seg_w = (strip_w - gap * (total - 1)) / total
        for index in range(total):
            sx = strip_left + index * (seg_w + gap)
            filled = index + 1 <= active
            seg_color = status_color if filled else (57, 63, 64)
            pulse = 1.0 + math.sin(now * 6.0) * 0.1 if filled and index + 1 == active else 1.0
            arcade.draw_lbwh_rectangle_filled(sx, strip_top - 8, seg_w, 7 * pulse, _mix(seg_color, (20, 24, 24), 0.35))
            arcade.draw_lbwh_rectangle_outline(sx, strip_top - 8, seg_w, 7 * pulse, seg_color, 1)
        draw_text(
            _truncate(("~" if state.action_stage_estimated else "") + (state.action_stage_label or "-"), 28),
            strip_left,
            strip_top - 11,
            config.COLORS["muted_text"],
            config.FONT_SIZE_SMALL,
            anchor_y="top",
        )

    def _draw_interaction_links(self, state: SimState, now: float) -> None:
        if state.action_status != "running":
            return
        target = _action_target_position(state)
        if target is None:
            return
        target_x, target_y, _label = target
        action = _action_key(state)
        if not _action_matches(action, "EAT", "FOOD", "BOWL", "MOUTH", "PAW", "GROOM", "CLEAN", "LICK", "CHARGER", "RECHARGE", "HAND", "NUDGE", "CUDDLE", "TOY", "FETCH", "PRESENT"):
            return
        color = _action_color(state)

        heading = math.radians(state.dog_heading)
        target_angle = math.atan2(target_y - state.dog_y, target_x - state.dog_x)
        dog_reach = 48.0 if _action_matches(action, "HAND", "PAW", "NUDGE", "MOUTH") else 38.0
        target_reach = 24.0 if _action_matches(action, "HAND", "PAW", "NUDGE", "CUDDLE") else 12.0
        start_x = state.dog_x + math.cos(heading) * dog_reach
        start_y = state.dog_y + math.sin(heading) * dog_reach
        end_x = target_x - math.cos(target_angle) * target_reach
        end_y = target_y - math.sin(target_angle) * target_reach
        wobble = math.sin(now * 8.0) * 2.0
        arcade.draw_line(start_x, start_y + wobble, end_x, end_y, _mix(color, (240, 240, 240), 0.22), 3)
        arcade.draw_circle_filled(_lerp(start_x, end_x, 0.52), _lerp(start_y, end_y, 0.52), 4, color)

    def _draw_interrupt_overlay(self, state: SimState, now: float) -> None:
        if not state.action_result_at:
            return
        age = now - state.action_result_at
        if age > 3.2:
            return
        phase = state.action_phase
        if phase not in {"canceled", "interrupted", "timeout", "failed"}:
            return
        color = config.COLORS["warning"]
        pulse = 1.0 + math.sin(now * 9.0) * 0.12
        arcade.draw_circle_outline(state.dog_x, state.dog_y, 72 * pulse, color, 3)
        arcade.draw_line(state.dog_x - 42, state.dog_y + 54, state.dog_x + 42, state.dog_y + 54, color, 4)
        _draw_tag(
            min(state.dog_x + 48, config.WORLD_RIGHT - 180),
            min(state.dog_y + 96, config.WORLD_TOP - 130),
            _truncate(f"{phase}: {state.action_reason}", 34),
            color,
        )

    def _draw_action_effects(self, state: SimState, now: float) -> None:
        action = _action_key(state)
        if state.action_status != "running" and not action:
            return

        x = state.dog_x
        y = state.dog_y
        heading = math.radians(state.dog_heading)
        color = _action_color(state)

        if state.action_unit_type in {"policy", "modifier"}:
            _draw_tag(
                min(x + 48, config.WORLD_RIGHT - 170),
                min(y + 86, config.WORLD_TOP - 132),
                f"{state.action_unit_type}: no motion",
                color,
            )

        if _action_matches(action, "SPIN"):
            for index, radius in enumerate((52, 66, 80)):
                angle = now * (2.6 + index * 0.3)
                px = x + math.cos(angle) * radius
                py = y + math.sin(angle) * radius * 0.58
                arcade.draw_circle_filled(px, py, 3, color)

        if _action_matches(action, "EAT", "BOWL"):
            for offset in (-14, -5, 7, 18):
                arcade.draw_circle_filled(x + offset, y + 36 + math.sin(now * 5 + offset) * 3, 2, (225, 169, 94))

        if _action_matches(action, "SLEEP", "REST", "CALM", "CURLED"):
            for index, letter in enumerate(("Z", "z", "z")):
                draw_text(
                    letter,
                    x + 42 + index * 15,
                    y + 32 + index * 14 + math.sin(now * 2 + index) * 3,
                    (199, 221, 212),
                    config.FONT_SIZE_TITLE - index,
                    bold=True,
                )

        if _action_matches(action, "SNIFF", "HEAD_TILT", "LOOK_AROUND", "CURIOUS"):
            for index in range(4):
                distance = 38 + index * 18
                side = math.sin(now * 3.0 + index) * 10
                px, py = _rotated_point(x, y, heading, distance, side)
                arcade.draw_circle_outline(px, py, 6 + index, color, 1)

        if _action_matches(action, "GROOM", "CLEAN", "LICK_PAWS"):
            for index in range(4):
                y_offset = -18 + index * 12
                arcade.draw_line(
                    x - 42,
                    y + y_offset,
                    x + 42,
                    y + y_offset + math.sin(now * 8 + index) * 6,
                    (218, 196, 240),
                    2,
                )

        if _action_matches(action, "CHARGER", "RECHARGE", "DOCKED"):
            charger = _room_object_xy(state, "charger")
            if charger is not None:
                arcade.draw_line(charger[0], charger[1], x, y, (111, 212, 196), 3)
                for index in range(4):
                    t = (now * 0.7 + index * 0.23) % 1.0
                    arcade.draw_circle_filled(_lerp(charger[0], x, t), _lerp(charger[1], y, t), 3, config.COLORS["dog_accent"])

        if _action_matches(action, "WAG", "JOY", "CUDDLE", "SOCIAL", "OWNER_ATTENTION", "NUDGE"):
            self._draw_affection_mark(x + 48, y + 52 + math.sin(now * 3.0) * 4, color)

        if _action_matches(action, "FREEZE", "HOLD_POSITION", "AVOID", "DANGER"):
            arcade.draw_line(x - 46, y + 58, x + 46, y + 58, config.COLORS["warning"], 3)
            arcade.draw_line(x - 46, y + 58, x - 28, y + 72, config.COLORS["warning"], 3)
            arcade.draw_line(x + 46, y + 58, x + 28, y + 72, config.COLORS["warning"], 3)

    def _draw_affection_mark(self, x: float, y: float, color: tuple[int, int, int]) -> None:
        arcade.draw_circle_filled(x - 5, y + 4, 6, color)
        arcade.draw_circle_filled(x + 5, y + 4, 6, color)
        arcade.draw_triangle_filled(x - 11, y + 4, x + 11, y + 4, x, y - 10, color)

    def _draw_recent_action_steps(self, state: SimState, now: float) -> None:
        recent = [
            (timestamp, action)
            for timestamp, action in state.recent_action_steps
            if now - timestamp <= 1.8
        ]
        if not recent:
            return

        x = min(config.WORLD_RIGHT - 250.0, state.dog_x + 56.0)
        y = min(config.WORLD_TOP - 118.0, state.dog_y + 78.0)
        for index, (timestamp, action) in enumerate(reversed(recent[-4:])):
            age = now - timestamp
            color = _mix(_action_color_for_text(action), (62, 67, 66), min(0.75, age / 1.8))
            text = _compact_action_label(action)
            width = min(230, max(86, len(text) * 6 + 18))
            chip_y = y - index * 20
            arcade.draw_lbwh_rectangle_filled(x, chip_y - 15, width, 16, (28, 33, 33))
            arcade.draw_lbwh_rectangle_outline(x, chip_y - 15, width, 16, color, 1)
            arcade.draw_circle_filled(x + 8, chip_y - 7, 3, color)
            draw_text(
                text,
                x + 16,
                chip_y - 2,
                config.COLORS["text"],
                config.FONT_SIZE_SMALL,
                anchor_y="top",
            )

    def _draw_tracked_objects(self, state: SimState) -> None:
        latest_visual = state.latest_visual_event or {}
        tracked_objects = latest_visual.get("tracked_objects")
        if not isinstance(tracked_objects, list):
            return

        for item in tracked_objects[:6]:
            if not isinstance(item, dict):
                continue
            x, y = _object_position(item)
            arcade.draw_circle_filled(x, y, 7, _mix(config.COLORS["object"], config.COLORS["world_floor"], 0.18))
            arcade.draw_circle_outline(x, y, 14, config.COLORS["object"], 1)
            label = item.get("label") or "object"
            draw_text(
                _truncate(str(label), 16),
                x + 14,
                y - 4,
                config.COLORS["world_text"],
                config.FONT_SIZE_SMALL,
            )

    def _draw_room_objects(self, state: SimState, now: float) -> None:
        for name, item in state.room_objects.items():
            x = _float_or_none(item.get("x"))
            y = _float_or_none(item.get("y"))
            if x is None or y is None:
                continue
            active = bool(item.get("active"))
            label = str(item.get("label") or name)
            kind = str(item.get("kind") or name)
            color = _object_color(kind)
            pulse = 1.0 + (math.sin(now * 8.0) * 0.12 if active else 0.0)

            if name == "bowl" or kind == "food":
                self._draw_food_bowl(x, y, active, pulse)
            elif name == "bed" or kind == "rest":
                self._draw_bed(x, y, active, pulse)
            elif name == "pad" or kind == "need":
                self._draw_toilet_pad(x, y, active, pulse)
            elif name == "toy" or kind == "toy":
                self._draw_toy_ball(x, y, active, pulse)
            elif name == "charger" or kind == "power":
                self._draw_charger(x, y, active, pulse)
            elif name == "groom" or kind == "clean":
                self._draw_groom_mat(x, y, active, pulse)
            else:
                arcade.draw_circle_filled(x, y, 10 * pulse, _mix(color, config.COLORS["world_floor"], 0.45 if not active else 0.0))

            if active:
                arcade.draw_circle_outline(x, y, 27 * pulse, config.COLORS["accent"], 2)
                arcade.draw_circle_outline(x, y, 37 * pulse, _mix(color, config.COLORS["world_floor"], 0.3), 1)
            if not active:
                draw_text(
                    _truncate(_display_scene_label(label), 15),
                    x + 16,
                    y - 5,
                    config.COLORS["world_muted"],
                    config.FONT_SIZE_SMALL,
                )

    def _draw_food_bowl(self, x: float, y: float, active: bool, pulse: float) -> None:
        body = config.COLORS["need"] if active else _mix(config.COLORS["need"], config.COLORS["world_tile"], 0.28)
        arcade.draw_ellipse_filled(x + 2, y - 3, 32 * pulse, 15 * pulse, (*config.COLORS["shadow"], 80))
        arcade.draw_ellipse_filled(x, y, 30 * pulse, 16 * pulse, body)
        arcade.draw_arc_outline(x, y + 3, 30 * pulse, 16 * pulse, config.COLORS["furniture_cream"], 0, 180, 1)
        for dx, dy in ((-6, 3), (2, 4), (7, 2)):
            arcade.draw_circle_filled(x + dx, y + dy, 2, config.COLORS["furniture_wood"])

    def _draw_bed(self, x: float, y: float, active: bool, pulse: float) -> None:
        edge = config.COLORS["success"] if active else config.COLORS["furniture_wood"]
        width = 48 * pulse
        height = 30 * pulse
        arcade.draw_ellipse_filled(x + 2, y - 3, width + 5, height + 4, (*config.COLORS["shadow"], 75))
        arcade.draw_ellipse_filled(x, y, width, height, edge)
        arcade.draw_ellipse_filled(x, y + 2, width - 9, height - 9, config.COLORS["furniture_cream"])
        arcade.draw_arc_outline(x, y + 1, width - 15, height - 14, _mix(edge, config.COLORS["furniture_cream"], 0.55), 0, 180, 1)

    def _draw_toilet_pad(self, x: float, y: float, active: bool, pulse: float) -> None:
        color = config.COLORS["error"] if active else config.COLORS["world_wall_dark"]
        width = 34 * pulse
        height = 22 * pulse
        arcade.draw_lbwh_rectangle_filled(x - width / 2, y - height / 2, width, height, config.COLORS["furniture_cream"])
        arcade.draw_lbwh_rectangle_outline(x - width / 2, y - height / 2, width, height, color, 1)
        arcade.draw_line(x - width / 2 + 5, y, x + width / 2 - 5, y, color, 1)
        arcade.draw_line(x, y - height / 2 + 4, x, y + height / 2 - 4, color, 1)

    def _draw_toy_ball(self, x: float, y: float, active: bool, pulse: float) -> None:
        radius = 11 * pulse
        color = config.COLORS["emotion"] if active else _mix(config.COLORS["emotion"], config.COLORS["world_floor"], 0.28)
        arcade.draw_circle_filled(x, y, radius, color)
        arcade.draw_circle_outline(x, y, radius, config.COLORS["furniture_cream"], 1)
        arcade.draw_arc_outline(x, y, radius * 1.4, radius * 1.8, config.COLORS["furniture_cream"], 90, 270, 1)
        if active:
            arcade.draw_circle_filled(x + 10, y + 9, 3, config.COLORS["title"])

    def _draw_charger(self, x: float, y: float, active: bool, pulse: float) -> None:
        width = 30 * pulse
        height = 18 * pulse
        color = config.COLORS["success"] if active else config.COLORS["world_wall_dark"]
        arcade.draw_lbwh_rectangle_filled(x - width / 2, y - height / 2, width, height, config.COLORS["surface_raised"])
        arcade.draw_lbwh_rectangle_outline(x - width / 2, y - height / 2, width, height, color, 2)
        arcade.draw_line(x - 8, y + 8, x + 3, y - 2, config.COLORS["dog_accent"], 3)
        arcade.draw_line(x + 3, y - 2, x - 2, y - 2, config.COLORS["dog_accent"], 3)
        arcade.draw_line(x - 2, y - 2, x + 9, y - 10, config.COLORS["dog_accent"], 3)
        if active:
            arcade.draw_circle_outline(x, y, 30 * pulse, (145, 220, 199), 2)

    def _draw_groom_mat(self, x: float, y: float, active: bool, pulse: float) -> None:
        width = 36 * pulse
        height = 20 * pulse
        color = config.COLORS["emotion"] if active else config.COLORS["world_wall_dark"]
        arcade.draw_lbwh_rectangle_filled(x - width / 2, y - height / 2, width, height, (178, 163, 143))
        arcade.draw_lbwh_rectangle_outline(x - width / 2, y - height / 2, width, height, color, 1)
        for offset in (-10, 0, 10):
            arcade.draw_line(x + offset - 4, y - 7, x + offset + 4, y + 7, color, 1)

    def _draw_scene_status(self, state: SimState) -> None:
        recent_topics = sum(1 for stats in state.topic_stats.values() if stats.count)
        endpoint_count = max(1, len(state.topic_stats))
        if state.processed_events == 0:
            status = "等待 ROS2 Topic 消息"
            color = config.COLORS["muted_text"]
        else:
            status = f"已接收 {recent_topics}/{endpoint_count} 个端点"
            color = config.COLORS["success"]
        status_x = config.WORLD_LEFT + 18
        _draw_tag(status_x, config.WORLD_TOP - 76, status, color)
        if state.action_status == "running":
            _draw_tag(
                status_x,
                config.WORLD_TOP - 100,
                f"动作 {state.action_progress * 100:.0f}% {state.action_current_action}",
                config.COLORS["audio"],
            )

    def _draw_world_labels(self, state: SimState) -> None:
        latest_audio = state.latest_audio_event or {}
        latest_visual = state.latest_visual_event or {}
        visual_events = latest_visual.get("events") or []

        left = config.WORLD_LEFT + 16
        top = config.WORLD_TOP - 10
        width = min(330.0, max(230.0, config.WORLD_WIDTH * 0.38))
        arcade.draw_lbwh_rectangle_filled(left, top - 46, width, 46, (*config.COLORS["surface"], 224))
        arcade.draw_lbwh_rectangle_filled(left, top - 46, 4, 46, config.COLORS["accent"])
        draw_text(
            "MarsDog 室内调试场景",
            left + 14,
            top - 6,
            config.COLORS["text"],
            config.FONT_SIZE_TITLE,
            bold=True,
            anchor_y="top",
        )
        draw_text(
            _truncate(
                f"声音={latest_audio.get('event_type') or '-'}  "
                f"视觉={','.join(visual_events) if visual_events else '-'}",
                80,
            ),
            left + 14,
            top - 27,
            config.COLORS["muted_text"],
            config.FONT_SIZE_AUX,
            anchor_y="top",
        )


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_scene_label(value: Any) -> str:
    text = str(value or "-")
    return {
        "owner": "主人",
        "user": "用户",
        "human": "人类",
        "animal": "动物",
        "food bowl": "食盆",
        "sleep mat": "休息垫",
        "toilet pad": "如厕垫",
        "toy ball": "玩具球",
        "charger": "充电座",
        "groom mat": "护理垫",
    }.get(text.lower(), text)


def _target_position(target: dict[str, Any], state: SimState) -> tuple[float, float]:
    x = _float_or_none(target.get("x"))
    y = _float_or_none(target.get("y"))
    if x is not None and y is not None:
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            return _normalized_to_world(x, y)
        return x, y

    for key in ("body_center", "face_center"):
        point = target.get(key)
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            point_x = _float_or_none(point[0])
            point_y = _float_or_none(point[1])
            if point_x is not None and point_y is not None:
                return _normalized_to_world(point_x, point_y)

    for key in ("bbox", "face_bbox"):
        bbox = target.get(key)
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            box_x = _float_or_none(bbox[0])
            box_y = _float_or_none(bbox[1])
            box_w = _float_or_none(bbox[2])
            box_h = _float_or_none(bbox[3])
            if None not in (box_x, box_y, box_w, box_h):
                return _normalized_to_world(box_x + box_w / 2, box_y + box_h / 2)

    return state.user_x, state.user_y


def _object_position(item: dict[str, Any]) -> tuple[float, float]:
    x = _float_or_none(item.get("center_x"))
    y = _float_or_none(item.get("center_y"))
    if x is not None and y is not None:
        return _normalized_to_world(x, y)

    box_x = _float_or_none(item.get("x"))
    box_y = _float_or_none(item.get("y"))
    box_w = _float_or_none(item.get("w"))
    box_h = _float_or_none(item.get("h"))
    if None not in (box_x, box_y, box_w, box_h):
        return _normalized_to_world(box_x + box_w / 2, box_y + box_h / 2)

    return config.DEFAULT_USER_X, config.DEFAULT_USER_Y


def _object_color(kind: str) -> tuple[int, int, int]:
    kind = kind.lower()
    if kind in {"food", "need"}:
        return config.COLORS["audio"]
    if kind in {"toy", "clean"}:
        return config.COLORS["object"]
    if kind in {"rest", "power"}:
        return config.COLORS["success"]
    return config.COLORS["visual"]


def _room_object_xy(state: SimState, name: str) -> tuple[float, float] | None:
    item = state.room_objects.get(name)
    if not isinstance(item, dict):
        return None
    x = _float_or_none(item.get("x"))
    y = _float_or_none(item.get("y"))
    if x is None or y is None:
        return None
    return x, y


def _action_target_position(state: SimState) -> tuple[float, float, str] | None:
    for name, item in state.room_objects.items():
        if not isinstance(item, dict) or not item.get("active"):
            continue
        x = _float_or_none(item.get("x"))
        y = _float_or_none(item.get("y"))
        if x is not None and y is not None:
            return x, y, str(item.get("label") or name)

    explicit_target = str(state.action_target_label or "").strip().lower()
    target_object = {
        "food bowl": "bowl",
        "sleep mat": "bed",
        "toilet pad": "pad",
        "toy ball": "toy",
        "charger": "charger",
        "groom mat": "groom",
    }.get(explicit_target)
    if target_object:
        point = _room_object_xy(state, target_object)
        if point is not None:
            return point[0], point[1], explicit_target
    if explicit_target in {"owner", "user", "human", "animal"}:
        return state.user_x, state.user_y, explicit_target

    action = _action_key(state)
    behavior = str(state.active_behavior or "").upper()
    object_by_action = (
        ("BOWL", "bowl"),
        ("FOOD", "bowl"),
        ("PAD", "pad"),
        ("TOILET", "pad"),
        ("BED", "bed"),
        ("SLEEP", "bed"),
        ("TOY", "toy"),
        ("POUNCE", "toy"),
        ("OBJECT", "toy"),
        ("INSPECT", "toy"),
        ("CHARGER", "charger"),
        ("RECHARGE", "charger"),
        ("GROOM", "groom"),
        ("CLEAN", "groom"),
        ("LICK_PAWS", "groom"),
    )
    for needle, name in object_by_action:
        if needle in action or needle in behavior:
            point = _room_object_xy(state, name)
            if point is not None:
                return point[0], point[1], name

    if _action_matches(
        action,
        "OWNER",
        "SOCIAL",
        "CUDDLE",
        "PERSON",
        "HUMAN",
        "ANIMAL",
        "INTERACTION",
        "RESOURCE",
        "GREET",
        "INVITE",
        "NUDGE",
        "HAND",
        "FOLLOW",
        "COME",
        "PLAY_BOW",
    ):
        return state.user_x, state.user_y, "user"

    if state.action_status == "running":
        return state.dog_x + math.cos(math.radians(state.dog_heading)) * 90.0, state.dog_y + math.sin(math.radians(state.dog_heading)) * 90.0, "heading"
    return None


def _action_key(state: SimState) -> str:
    action = str(state.action_current_action or "")
    behavior = str(state.active_behavior or "")
    return f"{action} {behavior}".upper().replace("-", "_")


def _dog_pose_for_action(action: str) -> str:
    if _action_matches(action, "PLAY_BOW", "INVITE_HUMAN_TO_PLAY", "INVITE_ANIMAL_TO_PLAY"):
        return "play_bow"
    if _action_matches(action, "HAND_INTERACTION", "HIGH_FIVE", "PAW_AT", "PAW_POUNCE"):
        return "paw"
    if _action_matches(action, "SLEEP", "LIE_DOWN", "LYING", "CURLED", "PLAY_DEAD", "REST_IN_PLACE"):
        return "lie"
    if _action_matches(action, "SIT", "CUDDLE", "OWNER_ATTENTION", "USE_TOILET"):
        return "sit"
    if _action_matches(
        action,
        "LOCO_",
        "WALK",
        "TROT",
        "RUN",
        "APPROACH",
        "FOLLOW",
        "MATCH_OWNER",
        "FLEE",
        "HIDE_AWAY",
        "ZOOMIES",
    ) and not _action_matches(action, "HOP_IN_PLACE", "DOCKED"):
        return "walk"
    return "stand"


def _action_matches(action: str, *needles: str) -> bool:
    return any(needle.upper() in action for needle in needles)


def _action_color(state: SimState) -> tuple[int, int, int]:
    action = _action_key(state)
    return _action_color_for_text(action)


def _action_color_for_text(action: str) -> tuple[int, int, int]:
    if _action_matches(action, "FEAR", "FLEE", "FREEZE", "DANGER", "STOP"):
        return config.COLORS["warning"]
    if _action_matches(action, "SLEEP", "REST", "CALM"):
        return config.COLORS["success"]
    if _action_matches(action, "FOOD", "BOWL", "PAD", "GROOM"):
        return config.COLORS["audio"]
    if _action_matches(action, "TOY", "POUNCE", "ZOOMIES", "PLAY", "HOP"):
        return config.COLORS["object"]
    if _action_matches(action, "CHARGER", "RECHARGE", "DOCKED"):
        return (111, 212, 196)
    return config.COLORS["target"]


def _status_color(state: SimState) -> tuple[int, int, int]:
    status = str(state.action_status or "").lower()
    phase = str(state.action_phase or "").lower()
    result = str(state.action_result or "").lower()
    if status == "running":
        if state.action_safe_to_interrupt is False:
            return config.COLORS["audio"]
        return config.COLORS["visual"]
    if status == "success" or phase == "completed" or result == "completed":
        return config.COLORS["success"]
    if phase in {"canceled", "interrupted", "timeout", "failed"} or status == "failed":
        return config.COLORS["warning"]
    return config.COLORS["muted_text"]


def _compact_action_label(action: str) -> str:
    label = action
    for prefix in ("ACT_POSTURE_", "ACT_LOCO_", "ACT_HEAD_", "ACT_TAIL_", "ACT_MOUTH_", "ACT_PAW_", "ACT_NAV_", "ACT_"):
        if label.startswith(prefix):
            label = label[len(prefix):]
            break
    return _truncate(label.lower(), 34)


def _rotated_point(
    origin_x: float,
    origin_y: float,
    angle: float,
    forward: float,
    side: float,
) -> tuple[float, float]:
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return (
        origin_x + cos_a * forward - sin_a * side,
        origin_y + sin_a * forward + cos_a * side,
    )


def _lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


def _mix(
    color: tuple[int, int, int],
    other: tuple[int, int, int],
    amount: float,
) -> tuple[int, int, int]:
    amount = _clamp01(amount)
    return (
        int(color[0] * (1.0 - amount) + other[0] * amount),
        int(color[1] * (1.0 - amount) + other[1] * amount),
        int(color[2] * (1.0 - amount) + other[2] * amount),
    )


def _normalized_to_world(x: float, y: float) -> tuple[float, float]:
    screen_x = config.WORLD_LEFT + _clamp01(x) * config.WORLD_WIDTH
    screen_y = config.WORLD_BOTTOM + (1.0 - _clamp01(y)) * config.WORLD_HEIGHT
    return screen_x, screen_y


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _draw_tag(x: float, y: float, text: str, color: tuple[int, int, int]) -> None:
    width = min(320, max(88, len(text) * 6 + 18))
    height = 18
    arcade.draw_lbwh_rectangle_filled(x, y - height, width, height, (26, 32, 38))
    arcade.draw_lbwh_rectangle_outline(x, y - height, width, height, color, 1)
    arcade.draw_circle_filled(x + 9, y - 9, 3, color)
    draw_text(
        text,
        x + 18,
        y - 4,
        config.COLORS["text"],
        config.FONT_SIZE_SMALL,
        anchor_y="top",
    )


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return "." * max(0, max_chars)
    return value[: max_chars - 3] + "..."
