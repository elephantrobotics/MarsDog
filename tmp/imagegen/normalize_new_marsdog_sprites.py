from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ASSET_DIR = Path("marsdog_sim2d/assets/dog")
OUTPUT_SIZE = (256, 256)
CONTENT_SIZE = (240, 240)
SPRITES = [
    ("啃咬/叼狗粮", "marsdog_chew_carry_food.png"),
    ("刨拔狗粮", "marsdog_scratch_food.png"),
    ("打嗝", "marsdog_burp.png"),
    ("舔嘴巴/鼻子", "marsdog_lick_lips_nose.png"),
    ("叼狗盆", "marsdog_carry_bowl.png"),
    ("刨地面", "marsdog_scratch_ground.png"),
    ("身体蹭物体", "marsdog_body_rub_object.png"),
    ("后腿挠耳朵", "marsdog_scratch_ear.png"),
    ("伸懒腰", "marsdog_stretch.png"),
    ("打哈欠", "marsdog_yawn.png"),
    ("板鸭趴", "marsdog_sploot.png"),
    ("蹭爬式起床", "marsdog_wake_crawl.png"),
    ("滚醒式起床", "marsdog_wake_roll.png"),
    ("弹起式起床", "marsdog_wake_spring.png"),
    ("伸懒腰式起床", "marsdog_wake_stretch.png"),
    ("坐起式起床", "marsdog_wake_sit_up.png"),
    ("趴下叫", "marsdog_bark_lying.png"),
    ("短促吠叫/哼鸣", "marsdog_tentative_bark_whine.png"),
    ("歪头观察", "marsdog_head_tilt_observe.png"),
]


def normalize(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError(f"{path} has no visible pixels")
    image = image.crop(bbox)
    image.thumbnail(CONTENT_SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", OUTPUT_SIZE, (0, 0, 0, 0))
    position = (
        (OUTPUT_SIZE[0] - image.width) // 2,
        (OUTPUT_SIZE[1] - image.height) // 2,
    )
    canvas.alpha_composite(image, position)
    canvas.save(path, optimize=True)
    return canvas


def checkerboard(size: tuple[int, int], cell: int = 16) -> Image.Image:
    background = Image.new("RGB", size, "#d8d8d8")
    draw = ImageDraw.Draw(background)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill="#eeeeee")
    return background


normalized = [(label, normalize(ASSET_DIR / filename)) for label, filename in SPRITES]

columns = 5
cell_width, cell_height = 280, 300
rows = (len(normalized) + columns - 1) // columns
sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
font = ImageFont.load_default()

for index, (label, sprite) in enumerate(normalized):
    x = (index % columns) * cell_width
    y = (index // columns) * cell_height
    tile = checkerboard(OUTPUT_SIZE)
    tile.paste(sprite, (0, 0), sprite)
    sheet.paste(tile, (x + 12, y + 8))
    ImageDraw.Draw(sheet).text((x + 12, y + 270), f"{index + 1:02d} {label}", fill="black", font=font)

sheet.save("tmp/imagegen/marsdog_new_poses_contact.png", optimize=True)
