"""
Create a demo video from Fabric Monitor PBIP screenshots.
Generates an MP4 with descriptive slides for each image.
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

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
        "Comprehensive Power BI & Fabric Estate Monitoring\nSupports Azure Commercial, GCC, GCC High"
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
        "Azure Commercial • GCC • GCC High\nSeamless monitoring across all government and commercial clouds"
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
    
    # Draw title
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_x = (width - title_w) // 2
    draw.text((title_x, height // 2 - 150), title, fill='white', font=title_font, anchor="lm")
    
    # Draw subtitle
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    subtitle_w = subtitle_bbox[2] - subtitle_bbox[0]
    subtitle_x = (width - subtitle_w) // 2
    draw.text((subtitle_x, height // 2 + 150), subtitle, fill=(176, 190, 197), font=subtitle_font, anchor="lm")
    
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
    draw.text((50, desc_y), description, fill=(66, 66, 66), font=text_font)
    
    return slide


def save_frames_to_file(frames_list, temp_dir):
    """Save frames to temp directory for ffmpeg."""
    frame_files = []
    for idx, img in enumerate(frames_list):
        frame_path = temp_dir / f"frame_{idx:04d}.png"
        img.save(frame_path)
        # Repeat frame for duration
        frame_files.append(frame_path)
    return frame_files


def create_video():
    """Create the final video."""
    print("Creating Fabric Monitor demo video...")
    print(f"Output: {OUTPUT_VIDEO}")
    
    # Create temporary directory for frames
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        frame_list_file = temp_dir / "frames.txt"
        frame_count = 0
        
        # Generate all slides
        with open(frame_list_file, 'w') as f:
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
                
                # Save frame and repeat for duration
                frame_path = temp_dir / f"frame_{frame_count:04d}.png"
                img.save(frame_path)
                
                # Add to FFmpeg concat file
                # Each frame repeated for (duration * fps) times
                num_repeats = int(duration * FPS)
                for _ in range(num_repeats):
                    f.write(f"file '{frame_path}'\n")
                    frame_count += 1
        
        # Use FFmpeg to create video
        print("\nEncoding video with FFmpeg...")
        
        # Find ffmpeg in PATH or common installation locations
        ffmpeg_path = shutil.which('ffmpeg')
        
        if not ffmpeg_path:
            # Try common installation paths
            username = os.getenv('USERNAME', '')
            common_paths = [
                f"C:\\Users\\{username}\\AppData\\Local\\Programs\\ffmpeg\\bin\\ffmpeg.exe",
                "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
                "C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe",
            ]
            for path in common_paths:
                if Path(path).exists():
                    ffmpeg_path = path
                    print(f"Found FFmpeg at: {ffmpeg_path}")
                    break
        
        if not ffmpeg_path:
            print("Error: FFmpeg not found in PATH or common locations.")
            print("Please ensure FFmpeg is installed:")
            print("  Windows: winget install ffmpeg")
            print("  macOS: brew install ffmpeg")
            print("  Linux: sudo apt-get install ffmpeg")
            print("\nAfter installation, restart your terminal and try again.")
            raise FileNotFoundError("ffmpeg executable not found")
        
        cmd = [
            ffmpeg_path,
            '-f', 'concat',
            '-safe', '0',
            '-i', str(frame_list_file),
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-y',  # Overwrite output file
            str(OUTPUT_VIDEO)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"\n✓ Video created successfully: {OUTPUT_VIDEO}")
        except subprocess.CalledProcessError as e:
            print(f"Error encoding video:\n{e.stderr}")
            raise
        except FileNotFoundError:
            print("Error: FFmpeg not found. Please install FFmpeg:")
            print("  - Windows: winget install ffmpeg  (or download from ffmpeg.org)")
            print("  - macOS: brew install ffmpeg")
            print("  - Linux: sudo apt-get install ffmpeg")
            raise


if __name__ == "__main__":
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
