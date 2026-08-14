param(
    [int]$SecondsPerSlide = 5,
    [int]$SecondsPerTitleSlide = 6,
    [string]$OutputPath = 'Fabric_Monitor_Demo.mp4',
    [string]$ImagesPath = 'images'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "Building Fabric Monitor video..."
Write-Host "  Output: $OutputPath"
Write-Host "  Slide duration: $SecondsPerSlide seconds"
Write-Host "  Title slide duration: $SecondsPerTitleSlide seconds"

# Verify images directory exists
if (-not (Test-Path $ImagesPath)) {
    throw "Images directory not found: $ImagesPath"
}

# Install static-ffmpeg if needed
Write-Host "Checking Python dependencies..."
python -m pip install static-ffmpeg pillow --quiet

# Create Python script for video generation
$pythonScript = @"
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import subprocess
import sys
import shutil

# Slide definitions: (image_filename, title, description, is_title_slide)
slides = [
    (None, "Fabric Monitor", "Comprehensive Power BI & Fabric Estate Monitoring\n\nSupports Azure Commercial, GCC, GCC High", True),
    ("admin-portal-settings.png", "Setup: Admin Portal Configuration", "Grant Service Principal permissions in Fabric Admin Portal\nEnable API access for monitoring and data extraction", False),
    ("Service-Principal-API-Permissions.png", "Setup: API Permissions", "Configure Graph API and Power BI permissions\nApplication-level permissions for headless monitoring", False),
    (None, "Monitoring Capabilities", "Real-time visibility into your Power BI and Fabric estate", True),
    ("Workspace_Artifacts.png", "Workspace Inventory", "Complete catalog of all workspaces and artifacts\nTrack reports, datasets, dashboards, and dataflows", False),
    ("Catalog_Governance.png", "Governance & Classification", "Monitor data classification and governance policies\nEnsure compliance across your enterprise", False),
    ("Activity_Operations.png", "Activity & Operations", "Track user activity, refresh operations, and usage patterns\nIdentify trends and monitor platform health", False),
    ("PBI_Audience_Usage.png", "Audience & Usage Analytics", "Understand which audiences are consuming content\nMeasure engagement and adoption metrics", False),
    ("Users_Access.png", "User Access & Security", "Monitor user permissions and access levels\nEnsure proper authorization across workspaces", False),
    ("User_Inactivity.png", "User Inactivity Tracking", "Identify inactive users and unused capacity\nOptimize licensing and capacity allocation", False),
    ("RiskAnomalies.png", "Risk & Anomaly Detection", "Detect unusual patterns and potential security risks\nProactive monitoring for estate health", False),
    ("Semantic_Model_Governance.png", "Semantic Model Governance", "Monitor data models, dependencies, and quality\nTrack lineage and data governance metrics", False),
    ("Audit_Overview.png", "Audit Overview Dashboard", "Comprehensive view of all monitoring activities\nCentralized dashboard for estate oversight", False),
    ("Customer_Audit_Overview.png", "Customer-Facing Audit View", "Present insights to stakeholders and leadership\nTransparent reporting of platform metrics", False),
    ("Drillthrough_Details.png", "Detailed Drill-Through Analysis", "Dive deep into specific items for root cause analysis\nUnderstand the 'why' behind the metrics", False),
    (None, "Multi-Cloud Support", "Azure Commercial • GCC • GCC High\n\nSeamless monitoring across all government and commercial clouds", True),
    (None, "Key Benefits", "✓ Real-time visibility across entire estate\n✓ Governance and compliance monitoring\n✓ Usage and adoption analytics\n✓ Proactive risk detection", True),
    (None, "Get Started Today", "Deploy Fabric Monitor to gain complete visibility\ninto your Power BI and Fabric environment", True),
]

images_dir = Path(r'''$ImagesPath''')
output = Path(r'''$OutputPath''')
title_slide_duration = $SecondsPerTitleSlide
regular_slide_duration = $SecondsPerSlide
width, height = 1920, 1080
fps = 1

# Create temporary directory for expanded frames
frames_dir = Path('.tmp_fabric_monitor_frames')
if frames_dir.exists():
    shutil.rmtree(frames_dir)
frames_dir.mkdir(exist_ok=True)

frame_index = 1
try:
    for idx, slide in enumerate(slides, 1):
        image_filename, title, description, is_title = slide
        print(f"[{idx}/{len(slides)}] Processing: {title}")
        
        if image_filename is None:
            # Create title slide
            img = Image.new('RGB', (width, height), color=(25, 35, 65))
            draw = ImageDraw.Draw(img)
            
            try:
                title_font = ImageFont.truetype("arial.ttf", 80)
                text_font = ImageFont.truetype("arial.ttf", 60)
            except:
                title_font = ImageFont.load_default()
                text_font = ImageFont.load_default()
            
            # Draw title (centered)
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_w = title_bbox[2] - title_bbox[0]
            title_x = (width - title_w) // 2
            title_y = (height // 2) - 100
            draw.text((title_x, title_y), title, fill='white', font=title_font)
            
            # Draw description (centered, multi-line)
            line_y = height // 2 + 100
            for line in description.split('\n'):
                line_bbox = draw.textbbox((0, 0), line, font=text_font)
                line_w = line_bbox[2] - line_bbox[0]
                line_x = (width - line_w) // 2
                draw.text((line_x, line_y), line, fill=(176, 190, 197), font=text_font)
                line_y += 70
            
            duration = title_slide_duration
        else:
            # Load image and create slide with text overlay
            image_path = images_dir / image_filename
            if not image_path.exists():
                print(f"  WARNING: Image not found: {image_path}")
                continue
            
            img = Image.open(image_path).convert('RGB')
            img_w, img_h = img.size
            
            # Resize image to fit slide
            max_img_height = height - 300
            max_img_width = width - 100
            scale = min(max_img_width / img_w, max_img_height / img_h)
            new_size = (int(img_w * scale), int(img_h * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Create background slide
            slide_img = Image.new('RGB', (width, height), color=(245, 245, 245))
            img_x = (width - new_size[0]) // 2
            img_y = 150
            slide_img.paste(img, (img_x, img_y))
            
            # Add text overlay
            draw = ImageDraw.Draw(slide_img)
            try:
                title_font = ImageFont.truetype("arial.ttf", 80)
                text_font = ImageFont.truetype("arial.ttf", 60)
            except:
                title_font = ImageFont.load_default()
                text_font = ImageFont.load_default()
            
            # Draw title
            draw.text((50, 20), title, fill=(25, 35, 65), font=title_font)
            
            # Draw description
            desc_y = img_y + new_size[1] + 30
            for line in description.split('\n'):
                draw.text((50, desc_y), line, fill=(66, 66, 66), font=text_font)
                desc_y += 40
            
            img = slide_img
            duration = regular_slide_duration
        
        # Save frame and repeat for duration
        num_frames = int(duration * fps)
        for _ in range(num_frames):
            frame_path = frames_dir / f'frame_{frame_index:04d}.png'
            img.save(frame_path)
            frame_index += 1
    
    # Find FFmpeg
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass
    
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg = None
    
    if ffmpeg is None:
        from shutil import which
        ffmpeg = which('ffmpeg')
    
    if ffmpeg is None:
        raise SystemExit('FFmpeg not found. Install: python -m pip install static-ffmpeg')
    
    # Build video with FFmpeg
    print(f"\nEncoding video with FFmpeg...")
    cmd = [
        ffmpeg,
        '-y',
        '-framerate', str(fps),
        '-i', str(frames_dir / 'frame_%04d.png'),
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-r', '30',
        str(output)
    ]
    subprocess.check_call(cmd)
    
    print(f"\n[SUCCESS] Video created: {output}")
    
finally:
    # Cleanup temp frames
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
"@

$pythonPath = Join-Path $env:TEMP 'build-fabric-monitor-video.py'
Set-Content -Path $pythonPath -Value $pythonScript -Encoding UTF8

try {
    python $pythonPath
} catch {
    Write-Error "Video generation failed: $_"
    Write-Host "Make sure you have Python and FFmpeg installed:"
    Write-Host "  python -m pip install static-ffmpeg pillow"
    exit 1
}

Write-Host "`n[SUCCESS] Video ready: $OutputPath"
