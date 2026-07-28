"""
Build a hosted-friendly Fabric Monitor demo video from solution screenshots.

Outputs:
  docs/demo/fabric-monitor-demo.mp4
  docs/demo/fabric-monitor-demo-poster.png
  docs/demo/index.html
"""

from __future__ import annotations

import html
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import static_ffmpeg
except ImportError:
    static_ffmpeg = None


ROOT = Path(__file__).parent
IMAGE_DIR = ROOT / "images"
OUTPUT_DIR = ROOT / "docs" / "demo"
VIDEO_PATH = OUTPUT_DIR / "fabric-monitor-demo.mp4"
POSTER_PATH = OUTPUT_DIR / "fabric-monitor-demo-poster.png"
HTML_PATH = OUTPUT_DIR / "index.html"

WIDTH = 1920
HEIGHT = 1080
FPS = 24

NAVY = (18, 31, 55)
BLUE = (41, 98, 255)
CYAN = (55, 184, 220)
INK = (31, 41, 55)
MUTED = (86, 98, 115)
PAGE = (244, 247, 251)
CARD = (255, 255, 255)
LINE = (214, 224, 236)


@dataclass(frozen=True)
class Slide:
    kind: str
    title: str
    body: str
    image: str | None = None
    eyebrow: str = "Fabric Monitor"
    duration: float = 4.5


DESCRIPTION = (
    "Fabric Monitor is a Python-based monitoring accelerator for Microsoft Fabric and Power BI. "
    "It uses a service principal or managed identity pattern to collect tenant, catalog, activity, "
    "refresh, gateway, capacity, app, role, and Microsoft Graph signals, then writes raw output to "
    "local files, Blob Storage, ADLS Gen2, or Fabric Lakehouse paths for downstream curation. The "
    "included PBIP starter project turns that telemetry into audit and governance reporting pages "
    "for activity trends, workspace and artifact inventory, users and access, semantic model "
    "governance, risk anomalies, and drill-through investigation."
)

SLIDES = [
    Slide(
        "title",
        "Fabric Monitor",
        "A practical monitoring accelerator for Power BI and Microsoft Fabric estates.",
        duration=5.0,
    ),
    Slide(
        "architecture",
        "How the solution works",
        "Collect tenant signals with scheduled Python modules. Store raw outputs in local, Blob, ADLS Gen2, or Lakehouse paths. Curate the data, then report from PBIP dashboards.",
        duration=6.0,
    ),
    Slide(
        "image",
        "Enable admin API access",
        "A dedicated service principal is granted Fabric Admin Portal access so collection can run unattended and consistently.",
        "admin-portal-settings.png",
        eyebrow="Setup",
    ),
    Slide(
        "image",
        "Grant the required API permissions",
        "Power BI and Microsoft Graph permissions unlock tenant metadata, activity logs, users, groups, and governance signals.",
        "Service-Principal-API-Permissions.png",
        eyebrow="Setup",
    ),
    Slide(
        "image",
        "Collect activity and catalog data",
        "The monitor separates high-volume activity events from slower-moving catalog metadata so each workload can run on the right cadence.",
        "Silver Activity.png",
        eyebrow="Data pipeline",
    ),
    Slide(
        "image",
        "Standardize catalog outputs",
        "Workspace, artifact, model, datasource, lineage, and user metadata can be shaped into reusable silver-layer tables.",
        "Silver Catalog.png",
        eyebrow="Data pipeline",
    ),
    Slide(
        "image",
        "Audit overview",
        "Executive KPIs summarize activity volume, active users, workspace footprint, artifacts, success rate, and recent platform activity.",
        "Audit_Overview.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "image",
        "Activity and operations",
        "Operational pages expose the actions, workloads, refresh patterns, failures, and trends that need administrator attention.",
        "Activity_Operations.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "image",
        "Users and access",
        "Access views help identify who is active, where activity originates, and which users or IP addresses merit investigation.",
        "Users_Access.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "image",
        "Workspace and artifact inventory",
        "Catalog reporting gives admins a searchable view of reports, semantic models, dataflows, dashboards, capacities, and ownership context.",
        "Workspace_Artifacts.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "image",
        "Audience usage",
        "Audience and consumption pages help teams understand which content is being used and where adoption is growing or stale.",
        "PBI_Audience_Usage.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "image",
        "Catalog governance",
        "Governance pages connect catalog metadata with classifications, workspace posture, and artifacts that need lifecycle attention.",
        "Catalog_Governance.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "image",
        "Semantic model governance",
        "Model-focused views surface dataset activity, dependencies, and governance signals so teams can manage shared semantic assets.",
        "Semantic_Model_Governance.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "image",
        "Risk and anomalies",
        "Risk pages highlight failed activity, unusual client IPs, high-volume users, suspicious operations, and other investigation triggers.",
        "RiskAnomalies.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "image",
        "Drill-through investigation",
        "Administrators can move from a KPI or chart into row-level context: user, workspace, activity, artifact, request, and success state.",
        "Drillthrough_Details.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "image",
        "Customer-facing audit story",
        "A curated audit view provides a cleaner stakeholder narrative while keeping operational details available for administrators.",
        "Customer_Audit_Overview.png",
        eyebrow="PBIP dashboard",
    ),
    Slide(
        "closing",
        "From API telemetry to governed reporting",
        "Run it locally, as a container, through notebooks, or as an Azure Function. Use the PBIP starter as the reporting layer for Git-backed Power BI development.",
        duration=5.5,
    ),
]


def font_path(name: str) -> str | None:
    candidates = [
        Path("C:/Windows/Fonts") / name,
        Path("C:/Windows/Fonts") / name.lower(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for name in names:
        path = font_path(name)
        if path:
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT_EYEBROW = load_font(28, bold=True)
FONT_TITLE = load_font(62, bold=True)
FONT_TITLE_LARGE = load_font(90, bold=True)
FONT_BODY = load_font(34)
FONT_BODY_LARGE = load_font(40)
FONT_SMALL = load_font(24)


def measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if measure(draw, candidate, font)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_gap: int = 12,
    align: str = "left",
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width)
    _, line_height = measure(draw, "Ag", font)
    for line in lines:
        line_width, _ = measure(draw, line, font)
        if align == "center":
            line_x = x + (max_width - line_width) // 2
        else:
            line_x = x
        draw.text((line_x, y), line, font=font, fill=fill)
        y += line_height + line_gap
    return y


def rounded_shadow(base: Image.Image, rect: tuple[int, int, int, int], radius: int = 28) -> None:
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(rect, radius=radius, fill=(0, 0, 0, 80))
    shadow.alpha_composite(layer.filter(ImageFilter.GaussianBlur(20)), (0, 14))
    base.alpha_composite(shadow)


def paste_contained(
    base: Image.Image,
    source: Image.Image,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int] = CARD,
) -> None:
    x1, y1, x2, y2 = box
    target_w = x2 - x1
    target_h = y2 - y1
    src = source.convert("RGB")
    scale = min(target_w / src.width, target_h / src.height)
    new_size = (max(1, int(src.width * scale)), max(1, int(src.height * scale)))
    resized = src.resize(new_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), fill)
    paste_x = (target_w - resized.width) // 2
    paste_y = (target_h - resized.height) // 2
    canvas.paste(resized, (paste_x, paste_y))
    base.alpha_composite(canvas.convert("RGBA"), (x1, y1))


def gradient_background(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), top)
    px = image.load()
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        color = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        for x in range(WIDTH):
            px[x, y] = color
    return image.convert("RGBA")


def add_header(draw: ImageDraw.ImageDraw, slide: Slide) -> None:
    draw.text((110, 54), slide.eyebrow.upper(), font=FONT_EYEBROW, fill=BLUE)
    draw.text((110, 94), slide.title, font=FONT_TITLE, fill=INK)
    draw.line((110, 184, WIDTH - 110, 184), fill=LINE, width=2)


def render_title(slide: Slide) -> Image.Image:
    frame = gradient_background((16, 30, 58), (25, 55, 96))
    draw = ImageDraw.Draw(frame)
    draw.rounded_rectangle((120, 110, 1800, 970), radius=48, outline=(78, 110, 170), width=2)
    draw.text((180, 220), "MICROSOFT FABRIC + POWER BI", font=FONT_EYEBROW, fill=CYAN)
    draw_wrapped(draw, slide.title, (180, 310), FONT_TITLE_LARGE, (255, 255, 255), 1200, 22)
    draw_wrapped(draw, slide.body, (185, 530), FONT_BODY_LARGE, (214, 225, 240), 1120, 18)

    steps = ["Collect", "Store", "Curate", "Report"]
    left = 190
    top = 730
    for i, step in enumerate(steps):
        x = left + i * 360
        draw.rounded_rectangle(
            (x, top, x + 250, top + 92),
            radius=28,
            fill=(34, 82, 140),
            outline=(116, 171, 232),
            width=2,
        )
        step_width, step_height = measure(draw, step, FONT_BODY)
        draw.text(
            (x + (250 - step_width) // 2, top + (92 - step_height) // 2 - 3),
            step,
            font=FONT_BODY,
            fill=(255, 255, 255),
        )
        if i < len(steps) - 1:
            draw.line((x + 270, top + 46, x + 330, top + 46), fill=CYAN, width=5)
            draw.polygon([(x + 330, top + 46), (x + 312, top + 34), (x + 312, top + 58)], fill=CYAN)
    return frame.convert("RGB")


def render_architecture(slide: Slide) -> Image.Image:
    frame = Image.new("RGBA", (WIDTH, HEIGHT), PAGE + (255,))
    draw = ImageDraw.Draw(frame)
    add_header(draw, slide)
    draw_wrapped(draw, slide.body, (110, 215), FONT_BODY, MUTED, WIDTH - 220, 14)

    cards = [
        ("Scheduled modules", "Activity, Catalog, Tenant, Apps, Capacity, Gateways, Refresh, Roles, Graph"),
        ("Flexible storage", "Local files, Blob Storage, ADLS Gen2, or Fabric Lakehouse paths"),
        ("Cloud profiles", "Commercial, GCC, GCC High, and DoD endpoint selection"),
        ("PBIP reporting", "Audit, usage, governance, risk, and drill-through pages"),
    ]
    x = 120
    y = 400
    for idx, (title, body) in enumerate(cards):
        rect = (x + idx * 440, y, x + idx * 440 + 380, y + 340)
        rounded_shadow(frame, rect, radius=34)
        draw.rounded_rectangle(rect, radius=34, fill=CARD, outline=LINE, width=2)
        draw.ellipse((rect[0] + 34, rect[1] + 34, rect[0] + 94, rect[1] + 94), fill=BLUE)
        draw.text((rect[0] + 54, rect[1] + 46), str(idx + 1), font=FONT_SMALL, fill=(255, 255, 255))
        draw_wrapped(draw, title, (rect[0] + 34, rect[1] + 125), FONT_BODY, INK, 310, 12)
        draw_wrapped(draw, body, (rect[0] + 34, rect[1] + 205), FONT_SMALL, MUTED, 310, 8)
        if idx < len(cards) - 1:
            arrow_x = rect[2] + 18
            draw.line((arrow_x, y + 170, arrow_x + 40, y + 170), fill=CYAN, width=5)
            draw.polygon([(arrow_x + 40, y + 170), (arrow_x + 24, y + 160), (arrow_x + 24, y + 180)], fill=CYAN)
    return frame.convert("RGB")


def render_image_slide(slide: Slide) -> Image.Image:
    frame = Image.new("RGBA", (WIDTH, HEIGHT), PAGE + (255,))
    draw = ImageDraw.Draw(frame)
    add_header(draw, slide)

    image_path = IMAGE_DIR / str(slide.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Missing screenshot: {image_path}")

    screenshot_box = (110, 220, WIDTH - 110, 850)
    if slide.image in {"Silver Activity.png", "Silver Catalog.png", "Customer_Audit_Overview.png"}:
        screenshot_box = (110, 220, 1010, 880)
        info_box = (1060, 260, 1810, 800)
    else:
        info_box = (110, 878, WIDTH - 110, 1018)

    rounded_shadow(frame, screenshot_box, radius=24)
    draw.rounded_rectangle(screenshot_box, radius=24, fill=CARD, outline=LINE, width=2)
    clip_box = (
        screenshot_box[0] + 18,
        screenshot_box[1] + 18,
        screenshot_box[2] - 18,
        screenshot_box[3] - 18,
    )
    with Image.open(image_path) as source:
        paste_contained(frame, source, clip_box)

    draw.rounded_rectangle(info_box, radius=26, fill=(255, 255, 255), outline=LINE, width=2)
    draw_wrapped(draw, slide.body, (info_box[0] + 34, info_box[1] + 30), FONT_BODY, INK, info_box[2] - info_box[0] - 68, 14)
    return frame.convert("RGB")


def render_closing(slide: Slide) -> Image.Image:
    frame = gradient_background((17, 33, 62), (24, 67, 105))
    draw = ImageDraw.Draw(frame)
    draw.text((140, 150), "HOSTED DEMO READY", font=FONT_EYEBROW, fill=CYAN)
    draw_wrapped(draw, slide.title, (140, 240), FONT_TITLE_LARGE, (255, 255, 255), 1340, 20)
    draw_wrapped(draw, slide.body, (145, 500), FONT_BODY_LARGE, (220, 232, 246), 1320, 18)
    draw.rounded_rectangle(
        (140, 760, 1780, 895),
        radius=36,
        fill=(34, 82, 140),
        outline=(116, 171, 232),
        width=2,
    )
    draw_wrapped(
        draw,
        "Use the generated MP4 and HTML page from docs/demo with GitHub Pages, Azure Static Web Apps, SharePoint, or any static host.",
        (190, 800),
        FONT_BODY,
        (255, 255, 255),
        1540,
        12,
    )
    return frame.convert("RGB")


def render_slide(slide: Slide) -> Image.Image:
    if slide.kind == "title":
        return render_title(slide)
    if slide.kind == "architecture":
        return render_architecture(slide)
    if slide.kind == "closing":
        return render_closing(slide)
    return render_image_slide(slide)


def interpolate_zoom(frame: Image.Image, frame_index: int, total_frames: int, intensity: float = 0.018) -> Image.Image:
    if total_frames <= 1:
        return frame
    progress = frame_index / (total_frames - 1)
    eased = 0.5 - 0.5 * math.cos(progress * math.pi)
    scale = 1.0 + intensity * eased
    crop_w = int(WIDTH / scale)
    crop_h = int(HEIGHT / scale)
    left = (WIDTH - crop_w) // 2
    top = (HEIGHT - crop_h) // 2
    return frame.crop((left, top, left + crop_w, top + crop_h)).resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def fade_factor(frame_index: int, total_frames: int, fade_frames: int = 10) -> float:
    if frame_index < fade_frames:
        return frame_index / fade_frames
    if frame_index >= total_frames - fade_frames:
        return max(0.0, (total_frames - frame_index - 1) / fade_frames)
    return 1.0


def apply_fade(frame: Image.Image, factor: float) -> Image.Image:
    if factor >= 0.999:
        return frame
    black = Image.new("RGB", frame.size, (0, 0, 0))
    return Image.blend(black, frame, factor)


def write_video() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rendered = [render_slide(slide) for slide in SLIDES]
    rendered[0].save(POSTER_PATH, quality=95)

    if shutil.which("ffmpeg") is None and static_ffmpeg is not None:
        static_ffmpeg.add_paths()

    with imageio.get_writer(
        VIDEO_PATH,
        fps=FPS,
        codec="libx264",
        quality=8,
        pixelformat="yuv420p",
        macro_block_size=1,
        ffmpeg_log_level="error",
        output_params=["-movflags", "+faststart"],
    ) as writer:
        for slide, base_frame in zip(SLIDES, rendered):
            total = int(slide.duration * FPS)
            for idx in range(total):
                frame = interpolate_zoom(base_frame, idx, total)
                frame = apply_fade(frame, fade_factor(idx, total))
                writer.append_data(np.asarray(frame))


def write_html() -> None:
    description = html.escape(DESCRIPTION)
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fabric Monitor Demo</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f7fb;
      --ink: #172033;
      --muted: #566273;
      --card: #ffffff;
      --line: #d6e0ec;
      --blue: #2962ff;
      --navy: #121f37;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: linear-gradient(180deg, #f8fbff 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    main {{
      width: min(1120px, calc(100% - 40px));
      margin: 0 auto;
      padding: 56px 0 72px;
    }}
    .hero {{
      display: grid;
      gap: 24px;
    }}
    .eyebrow {{
      color: var(--blue);
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2.25rem, 5vw, 4.5rem);
      line-height: 1;
      letter-spacing: -0.04em;
    }}
    p {{
      color: var(--muted);
      font-size: 1.1rem;
      line-height: 1.65;
      max-width: 920px;
    }}
    .video-card {{
      margin-top: 20px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 28px;
      background: var(--card);
      box-shadow: 0 24px 70px rgba(18, 31, 55, 0.16);
    }}
    video {{
      display: block;
      width: 100%;
      border-radius: 18px;
      background: var(--navy);
      aspect-ratio: 16 / 9;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 16px;
      margin-top: 28px;
    }}
    .tile {{
      padding: 22px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.78);
    }}
    .tile strong {{
      display: block;
      margin-bottom: 8px;
      color: var(--ink);
    }}
    .tile span {{
      color: var(--muted);
      line-height: 1.5;
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="eyebrow">Microsoft Fabric + Power BI monitoring</div>
      <h1>Fabric Monitor Demo</h1>
      <p>{description}</p>
      <div class="video-card">
        <video controls preload="metadata" poster="fabric-monitor-demo-poster.png">
          <source src="fabric-monitor-demo.mp4" type="video/mp4">
          Your browser does not support the video tag.
        </video>
      </div>
    </section>
    <section class="grid" aria-label="Solution highlights">
      <div class="tile"><strong>Collect</strong><span>Scheduled modules gather Power BI, Fabric, and Graph signals with service-principal authentication.</span></div>
      <div class="tile"><strong>Store</strong><span>Raw outputs can land in local files, Blob Storage, ADLS Gen2, or Fabric Lakehouse paths.</span></div>
      <div class="tile"><strong>Curate</strong><span>Activity and catalog data can be shaped into reporting-ready silver-layer datasets.</span></div>
      <div class="tile"><strong>Report</strong><span>The PBIP starter supplies audit, governance, usage, risk, and drill-through pages.</span></div>
    </section>
  </main>
</body>
</html>
"""
    HTML_PATH.write_text(html_doc, encoding="utf-8")


def main() -> None:
    missing = [slide.image for slide in SLIDES if slide.image and not (IMAGE_DIR / slide.image).exists()]
    if missing:
        raise FileNotFoundError(f"Missing screenshots: {', '.join(missing)}")
    write_video()
    write_html()
    print(f"Video: {VIDEO_PATH}")
    print(f"Poster: {POSTER_PATH}")
    print(f"Page: {HTML_PATH}")


if __name__ == "__main__":
    main()
