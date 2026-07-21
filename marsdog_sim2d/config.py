"""Configuration for the MarsDog 2D simulation viewer."""

from __future__ import annotations

WINDOW_WIDTH = 1470
WINDOW_HEIGHT = 820
WINDOW_TITLE = "MarsDog 2D ROS2 Viewer"

MIN_WINDOW_WIDTH = 1060
MIN_WINDOW_HEIGHT = 680
TOP_BAR_HEIGHT = 44
DEFAULT_LEFT_PANEL_WIDTH = 280
COLLAPSED_LEFT_PANEL_WIDTH = 48
DEFAULT_RIGHT_PANEL_WIDTH = 420
DEFAULT_LOG_HEIGHT = 156
MIN_LOG_HEIGHT = 112
MAX_LOG_HEIGHT = 280
MIN_WORLD_WIDTH = 500
AUTO_COMPACT_WIDTH = 1180

# The virtual executor and ROS payloads use the original scene coordinate space.
# Rendering maps this stable space into the responsive center viewport.
SCENE_LOGICAL_LEFT = 0.0
SCENE_LOGICAL_RIGHT = 890.0
SCENE_LOGICAL_BOTTOM = 120.0
SCENE_LOGICAL_TOP = 720.0

LEFT_PANEL_LEFT = 0.0
LEFT_PANEL_RIGHT = float(DEFAULT_LEFT_PANEL_WIDTH)
LEFT_PANEL_WIDTH = float(DEFAULT_LEFT_PANEL_WIDTH)
RIGHT_PANEL_WIDTH = float(DEFAULT_RIGHT_PANEL_WIDTH)
RIGHT_PANEL_LEFT = float(WINDOW_WIDTH - DEFAULT_RIGHT_PANEL_WIDTH)
RIGHT_PANEL_RIGHT = float(WINDOW_WIDTH)
BOTTOM_LOG_HEIGHT = float(DEFAULT_LOG_HEIGHT)
TOP_BAR_BOTTOM = float(WINDOW_HEIGHT - TOP_BAR_HEIGHT)
TOP_BAR_TOP = float(WINDOW_HEIGHT)
WORLD_LEFT = LEFT_PANEL_RIGHT
WORLD_RIGHT = RIGHT_PANEL_LEFT
WORLD_BOTTOM = BOTTOM_LOG_HEIGHT
WORLD_TOP = TOP_BAR_BOTTOM
WORLD_WIDTH = WORLD_RIGHT - WORLD_LEFT
WORLD_HEIGHT = WORLD_TOP - WORLD_BOTTOM

# Legacy aliases retained for the old injector layout helpers. The active UI
# uses LEFT_PANEL_* directly.
EVENT_PANEL_LEFT = LEFT_PANEL_LEFT
EVENT_PANEL_RIGHT = LEFT_PANEL_RIGHT
EVENT_PANEL_WIDTH = LEFT_PANEL_WIDTH
SIDE_PANEL_WIDTH = LEFT_PANEL_WIDTH + RIGHT_PANEL_WIDTH

DEFAULT_DOG_X = 430.0
DEFAULT_DOG_Y = 420.0
DEFAULT_DOG_HEADING = 0.0
DEFAULT_USER_X = 680.0
DEFAULT_USER_Y = 405.0

# Logical scene anchors matched to apartment_floorplan_source.png. Keep these
# separate from responsive screen coordinates used by the Arcade layout.
DEFAULT_ROOM_OBJECTS = {
    "bowl": {"label": "food bowl", "x": 158.0, "y": 198.0, "kind": "food"},
    "bed": {"label": "sleep mat", "x": 140.0, "y": 453.0, "kind": "rest"},
    "pad": {"label": "toilet pad", "x": 760.0, "y": 475.0, "kind": "need"},
    "toy": {"label": "toy ball", "x": 742.0, "y": 570.0, "kind": "toy"},
    "charger": {"label": "charger", "x": 82.0, "y": 330.0, "kind": "power"},
    "groom": {"label": "groom mat", "x": 465.0, "y": 207.0, "kind": "clean"},
}

MAX_EVENT_LOG = 80
MAX_STRUCTURED_EVENTS = 240
MAX_VISIBLE_LOG_LINES = 8
MAX_BEHAVIOR_RESULTS = 8
QUEUE_DRAIN_LIMIT = 200

FONT_SIZE_PAGE = 19
FONT_SIZE_MODULE = 14
FONT_SIZE_KEY = 17
FONT_SIZE_BODY = 12
FONT_SIZE_AUX = 10
FONT_SIZE_SMALL = FONT_SIZE_AUX
FONT_SIZE = FONT_SIZE_BODY
FONT_SIZE_TITLE = FONT_SIZE_MODULE
FONT_NAMES = ("Noto Sans CJK SC", "Droid Sans Fallback", "Arial")
LINE_HEIGHT = 17
SECTION_GAP = 8

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
CARD_PADDING = 12
CARD_GAP = 8
CONTROL_HEIGHT = 30
BUTTON_HEIGHT = 30
TAB_HEIGHT = 32
FORM_LABEL_HEIGHT = 24
FORM_ROW_GAP = 8
RADIO_OPTION_HEIGHT = 22
RADIO_ROW_GAP = 5
STATUS_GRID_ROW_HEIGHT = 36
STATUS_GRID_VALUE_OFFSET = 17
STATUS_METER_ROW_HEIGHT = 22
STATUS_COMPACT_ROW_HEIGHT = 20
PANEL_BORDER_WIDTH = 1

TOPICS = {
    "visual_event": "/perception/visual_event",
    "audio_event": "/perception/audio_event",
    "internal_need_state": "/internal_need/state",
    "internal_need_signal_event": "/internal_need/signal_event",
    "emotion_state": "/emotion/state",
    "emotion_signal_event": "/emotion/signal_event",
    "behavior_result_event": "/behavior/result_event",
    "personality_state": "/personality/state",
}

ACTION_NAME = "/execute_behavior"
ACTION_DEBUG_PREFIX = "/debug/execute_behavior"
ACTION_GOAL_TOPIC = f"{ACTION_DEBUG_PREFIX}/goal"
ACTION_FEEDBACK_TOPIC = f"{ACTION_DEBUG_PREFIX}/feedback"
ACTION_RESULT_TOPIC = f"{ACTION_DEBUG_PREFIX}/result"
LEGACY_ACTION_GOAL_TOPIC = f"{ACTION_NAME}/goal"
LEGACY_ACTION_FEEDBACK_TOPIC = f"{ACTION_NAME}/feedback"
LEGACY_ACTION_RESULT_TOPIC = f"{ACTION_NAME}/result"
ACTION_FEEDBACK_PERIOD_SEC = 0.1
VIEWER_SOURCE = "marsdog_sim2d_virtual_executor"

VISUAL_TOPIC_DEPTH = 5
STATE_TOPIC_DEPTH = 10
EVENT_TOPIC_DEPTH = 10
PERSONALITY_TOPIC_DEPTH = 1

DEMAND_NAMES = (
    "Hunger",
    "Bladder",
    "Sleepiness",
    "Cleanliness",
    "Energy",
    "Social",
    "Exploration",
)

EMOTION_NAMES = (
    "Joy",
    "Excite",
    "Anxiety",
    "Fear",
    "Curious",
    "Calm",
)

RESULT_TYPE_MAPPING = {
    "COMPLETED": "DemandSatisfied",
    "FAILED": "DemandUnsatisfied",
    "TIMEOUT": "DemandUnsatisfied",
    "INTERRUPTED": "ActionInterrupted",
    "CANCELLED": "ActionInterrupted",
    "CANCELED": "ActionInterrupted",
    "STARTED": "No emotion effect",
}

COLORS = {
    "background": (18, 19, 19),
    "world_background": (42, 42, 39),
    "world_floor": (194, 169, 132),
    "world_floor_alt": (202, 178, 141),
    "world_grid": (171, 144, 108),
    "world_plank_soft": (216, 190, 151),
    "world_wall": (232, 225, 207),
    "world_wall_dark": (75, 73, 68),
    "world_tile": (202, 207, 197),
    "world_tile_line": (177, 184, 176),
    "world_rug": (139, 158, 145),
    "world_rug_border": (102, 124, 113),
    "world_text": (57, 54, 47),
    "world_muted": (103, 92, 76),
    "furniture_wood": (116, 84, 62),
    "furniture_wood_light": (160, 119, 85),
    "furniture_fabric": (150, 161, 146),
    "furniture_fabric_dark": (105, 120, 109),
    "furniture_cream": (235, 229, 211),
    "plant": (73, 119, 82),
    "panel_background": (27, 28, 27),
    "surface": (34, 35, 34),
    "surface_raised": (40, 42, 41),
    "surface_hover": (47, 50, 48),
    "top_bar": (22, 23, 23),
    "preview_background": (23, 24, 24),
    "progress_track": (49, 52, 50),
    "meter_track": (47, 50, 49),
    "table_header": (30, 31, 30),
    "table_alt": (24, 25, 25),
    "detail_background": (31, 32, 31),
    "modal_background": (38, 38, 36),
    "popover_background": (45, 47, 45),
    "tooltip_background": (47, 49, 47),
    "chip_idle": (31, 32, 31),
    "log_background": (21, 22, 22),
    "separator": (62, 65, 62),
    "border": (59, 63, 61),
    "border_strong": (81, 88, 84),
    "text": (232, 232, 225),
    "muted_text": (158, 163, 157),
    "subtle_text": (113, 121, 116),
    "title": (158, 197, 183),
    "accent": (94, 174, 154),
    "accent_dim": (54, 101, 90),
    "need": (99, 143, 173),
    "emotion": (157, 122, 151),
    "dog_body": (181, 117, 73),
    "dog_dark": (91, 62, 45),
    "dog_accent": (224, 176, 107),
    "shadow": (53, 48, 41),
    "target": (83, 151, 112),
    "audio": (91, 154, 166),
    "visual": (103, 145, 169),
    "object": (151, 121, 149),
    "warning": (213, 151, 78),
    "error": (199, 88, 92),
    "success": (94, 163, 116),
    "waiting": (111, 117, 113),
    "panel_rule": (53, 56, 54),
}


def update_layout(
    width: float,
    height: float,
    left_collapsed: bool = False,
    log_height: float | None = None,
) -> None:
    """Update shared responsive UI bounds without touching simulation data."""

    global WINDOW_WIDTH, WINDOW_HEIGHT
    global LEFT_PANEL_LEFT, LEFT_PANEL_RIGHT, LEFT_PANEL_WIDTH
    global RIGHT_PANEL_LEFT, RIGHT_PANEL_RIGHT, RIGHT_PANEL_WIDTH
    global BOTTOM_LOG_HEIGHT, TOP_BAR_BOTTOM, TOP_BAR_TOP
    global WORLD_LEFT, WORLD_RIGHT, WORLD_BOTTOM, WORLD_TOP, WORLD_WIDTH, WORLD_HEIGHT
    global EVENT_PANEL_LEFT, EVENT_PANEL_RIGHT, EVENT_PANEL_WIDTH, SIDE_PANEL_WIDTH

    WINDOW_WIDTH = max(MIN_WINDOW_WIDTH, int(width))
    WINDOW_HEIGHT = max(MIN_WINDOW_HEIGHT, int(height))

    compact = left_collapsed or WINDOW_WIDTH < AUTO_COMPACT_WIDTH
    left_width = COLLAPSED_LEFT_PANEL_WIDTH if compact else _clamp(
        WINDOW_WIDTH * 0.19,
        260.0,
        300.0,
    )
    right_width = _clamp(WINDOW_WIDTH * 0.30, 340.0, 440.0)
    available = WINDOW_WIDTH - left_width - right_width
    if available < MIN_WORLD_WIDTH:
        right_width = max(320.0, right_width - (MIN_WORLD_WIDTH - available))

    desired_log = WINDOW_HEIGHT * 0.20 if log_height is None else log_height
    resolved_log = _clamp(desired_log, MIN_LOG_HEIGHT, min(MAX_LOG_HEIGHT, WINDOW_HEIGHT * 0.34))

    LEFT_PANEL_LEFT = 0.0
    LEFT_PANEL_WIDTH = float(left_width)
    LEFT_PANEL_RIGHT = LEFT_PANEL_WIDTH
    RIGHT_PANEL_WIDTH = float(right_width)
    RIGHT_PANEL_RIGHT = float(WINDOW_WIDTH)
    RIGHT_PANEL_LEFT = RIGHT_PANEL_RIGHT - RIGHT_PANEL_WIDTH
    BOTTOM_LOG_HEIGHT = float(resolved_log)
    TOP_BAR_TOP = float(WINDOW_HEIGHT)
    TOP_BAR_BOTTOM = TOP_BAR_TOP - TOP_BAR_HEIGHT
    WORLD_LEFT = LEFT_PANEL_RIGHT
    WORLD_RIGHT = RIGHT_PANEL_LEFT
    WORLD_BOTTOM = BOTTOM_LOG_HEIGHT
    WORLD_TOP = TOP_BAR_BOTTOM
    WORLD_WIDTH = max(1.0, WORLD_RIGHT - WORLD_LEFT)
    WORLD_HEIGHT = max(1.0, WORLD_TOP - WORLD_BOTTOM)

    EVENT_PANEL_LEFT = LEFT_PANEL_LEFT
    EVENT_PANEL_RIGHT = LEFT_PANEL_RIGHT
    EVENT_PANEL_WIDTH = LEFT_PANEL_WIDTH
    SIDE_PANEL_WIDTH = LEFT_PANEL_WIDTH + RIGHT_PANEL_WIDTH


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
