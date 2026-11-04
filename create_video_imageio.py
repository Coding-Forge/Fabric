"""
Create an MP4 video from Fabric Monitor screenshots using imageio.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import imageio
import os

# Configuration
IMAGE_DIR = Path(__file__).parent / "images"
OUTPUT_VIDEO = Path(__file__).parent / "Fabric_Monitor_Demo.mp4"
SLIDE_DURATION = 5  # seconds per slide
TITLE_DURATION = 6  # seconds for title slides
FONT_SIZE = 80
SUBTITLE_FONT_SIZE = 60
WIDTH, HEIGHT = 1920, 1080
FPS = 30

# Define slide content: (image_filename, title, description)
SLIDES = [
    (
        None,
        "Fabric Monitor",
        "Comprehensive Power BI & Fabric Estate Monitoring\n\nSupports Azure Commercial, GCC, GCC High"
    ),
    (
        "admin-portal-settings.png",
        "Setup: Admin Portal Configuration",
        "Grant Service Principal permissions in Fabric Admin Portal\nEnable API access for monitoring and data extraction"
    ),
    (
        "Service-Principal-API-Permissions.png",
        "Setup: API Permissions",
        "Configure Graph API and Power BI permissions\nApplication-level permissions for headless monitoring"
    ),
    (
        None,
        "Monitoring Capabilities",
        "Real-time visibility into your Power BI and Fabric estate"
    ),
    (
        "Workspace_Artifacts.png",
        "Workspace Inventory",
        "Complete catalog of all workspaces and artifacts\nTrack reports, datasets, dashboards, and dataflows"
    ),
    (
        "Catalog_Governance.png",
        "Governance & Classification",
        "Monitor data classification and governance policies\nEnsure compliance across your enterprise"
    ),
    (
        "Activity_Operations.png",
        "Activity & Operations",
        "Track user activity, refresh operations, and usage patterns\nIdentify trends and monitor platform health"
    ),
    (
        "PBI_Audience_Usage.png",
        "Audience & Usage Analytics",
        "Understand which audiences are consuming content\nMeasure engagement and adoption metrics"
    ),
    (
        "Users_Access.png",
        "User Access & Security",
        "Monitor user permissions and access levels\nEnsure proper authorization across workspaces"
    ),
    (
        "User_Inactivity.png",
        "User Inactivity Tracking",
        "Identify inactive users and unused capacity\nOptimize licensing and capacity allocation"
    ),
    (
        "RiskAnomalies.png",
        "Risk & Anomaly Detection",
        "Detect unusual patterns and potential security risks\nProactive monitoring for estate health"
    ),
    (
        "Semantic_Model_Governance.png",
        "Semantic Model Governance",
        "Monitor data models, dependencies, and quality\nTrack lineage and data governance metrics"
    ),
    (
        "Audit_Overview.png",
        "Audit Overview Dashboard",
        "Comprehensive view of all monitoring activities\nCentralized dashboard for estate oversight"
    ),
    (
        "Customer_Audit_Overview.png",
        "Customer-Facing Audit View",
        "Present insights to stakeholders and leadership\nTransparent reporting of platform metrics"
    ),
    (
        "Drillthrough_Details.png",
        "Detailed Drill-Through Analysis",
        "Dive deep into specific items for root cause analysis\nUnderstand the 'why' behind the metrics"
    ),
    (
        None,
        "Multi-Cloud Support",
        "Azure Commercial • GCC • GCC High\n\nSeamless monitoring across all government and commercial clouds"
    ),
    (
        None,
        "Key Benefits",
        "✓ Real-time visibility across entire estate\n✓ Governance and compliance monitoring\n✓ Usage and adoption analytics\n✓ Proactive risk detection"
    ),
    (
        None,
        "Get Started Today",
        "Deploy Fabric Monitor to gain complete visibility\ninto your Power BI and Fabric environment"
    ),
]


def create_title_slide(title, subtitle, width=WIDTH, height=HEIGHT):
    """Create a title slide with background and text."""
    img = Image.new('RGB', (width, height), color=(25, 35, 65))
    draw = ImageDraw.Draw(img)
    
    # Try to use a nice font, fallback to default
    try:
        title_font = ImageFont.truetype("arial.ttf", FONT_SIZE)
        subtitle_font = ImageFont.truetype("arial.ttf", SUBTITLE_FONT_SIZE)
    except:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
    
    # Draw title (centered)
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    title_x = (width - title_w) // 2
    title_y = (height // 2) - title_h - 50
    draw.text((title_x, title_y), title, fill='white', font=title_font)
    
    # Draw subtitle (centered)
    for line_idx, line in enumerate(subtitle.split('\n')):
        line_bbox = draw.textbbox((0, 0), line, font=subtitle_font)
        line_w = line_bbox[2] - line_bbox[0]
        line_x = (width - line_w) // 2
        line_y = height // 2 + 100 + (line_idx * 80)
        draw.text((line_x, line_y), line, fill=(176, 190, 197), font=subtitle_font)
    
    return img


def create_image_slide(image_path, title, description, width=WIDTH, height=HEIGHT):
    """Create a slide with an image and text overlay."""
    # Create light background
    slide = Image.new('RGB', (width, height), color=(245, 245, 245))
    
    # Load and resize image
    img = Image.open(image_path)
    img_w, img_h = img.size
    
    max_img_height = height - 300
    max_img_width = width - 100
    scale = min(max_img_width / img_w, max_img_height / img_h)
    new_size = (int(img_w * scale), int(img_h * scale))
    img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    # Paste image centered
    img_x = (width - new_size[0]) // 2
    img_y = 150
    slide.paste(img, (img_x, img_y))
    
    # Add text
    draw = ImageDraw.Draw(slide)
    try:
        title_font = ImageFont.truetype("arial.ttf", FONT_SIZE)
        text_font = ImageFont.truetype("arial.ttf", SUBTITLE_FONT_SIZE)
    except:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
    
    # Draw title
    draw.text((50, 20), title, fill=(25, 35, 65), font=title_font)
    
    # Draw description
    desc_y = img_y + new_size[1] + 30
    for line_idx, line in enumerate(description.split('\n')):
        draw.text((50, desc_y + (line_idx * 40)), line, fill=(66, 66, 66), font=text_font)
    
    return slide


def create_video():
    """Create the final video."""
    print("Creating Fabric Monitor demo video...")
    print(f"Output: {OUTPUT_VIDEO}")
    
    frames = []
    frame_counts = []
    
    # Generate all slides
    for idx, slide_data in enumerate(SLIDES, 1):
        image_filename, title, description = slide_data
        print(f"[{idx}/{len(SLIDES)}] Creating slide: {title}")
        
        if image_filename is None:
            # Title slide
            img = create_title_slide(title, description)
            duration = TITLE_DURATION
        else:
            # Image slide
            image_path = IMAGE_DIR / image_filename
            if not image_path.exists():
                print(f"  ⚠️  Warning: Image not found: {image_path}")
                continue
            img = create_image_slide(image_path, title, description)
            duration = SLIDE_DURATION
        
        # Convert PIL image to numpy array
        img_array = np.array(img)
        
        # Repeat frame for duration
        num_frames = int(duration * FPS)
        for _ in range(num_frames):
            frames.append(img_array)
    
    # Write video
    print("\nEncoding video...")
    imageio.mimwrite(str(OUTPUT_VIDEO), frames, fps=FPS, codec='libx264')
    
    print(f"\n✓ Video created successfully: {OUTPUT_VIDEO}")
    print(f"  Total frames: {len(frames)}")
    print(f"  Duration: {len(frames) / FPS:.1f} seconds")
    print(f"  Resolution: {WIDTH}x{HEIGHT} @ {FPS} FPS")


if __name__ == "__main__":
    import numpy as np
    
    if not IMAGE_DIR.exists():
        print(f"Error: Image directory not found: {IMAGE_DIR}")
        exit(1)
    
    try:
        create_video()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
