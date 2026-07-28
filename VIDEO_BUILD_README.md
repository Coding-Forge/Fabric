# Fabric Monitor Video Build

This solution creates a professional MP4 video from your screenshot images, based on the approach used in the [Enterprise BI DevOps](https://github.com/microsoft/fabric-bi-devops) project.

## Files

- **Build-FabricMonitorVideo.ps1** — PowerShell script that orchestrates the video generation
- **images/** — Directory containing all screenshot PNG files
- **Fabric_Monitor_Demo.mp4** — Generated video (output)

## How It Works

### 1. PowerShell Script (Build-FabricMonitorVideo.ps1)
- Verifies the images directory exists
- Installs Python dependencies (static-ffmpeg, pillow)
- Generates an embedded Python script
- Calls Python to process slides and encode video

### 2. Python Script (embedded in PowerShell)
- Reads slide definitions (image file, title, description)
- **Title slides**: Creates solid-color background with centered text
- **Image slides**: Loads PNG, resizes to fit, overlays title and description
- **Frame expansion**: Repeats each frame for N seconds to create video timing
- **FFmpeg encoding**: Uses libx264 to encode PNG frames into MP4

### 3. Dependencies

The script installs these automatically:

```powershell
python -m pip install static-ffmpeg pillow
```

- **static-ffmpeg**: Bundles FFmpeg (no separate installation needed)
- **pillow**: Image processing library

## Usage

### Run the video builder:

```powershell
cd C:\Projects\Fabric\monitor
powershell -ExecutionPolicy Bypass -File Build-FabricMonitorVideo.ps1
```

### Customize timing:

```powershell
# Adjust slide durations
Build-FabricMonitorVideo.ps1 -SecondsPerSlide 4 -SecondsPerTitleSlide 5
```

### Parameters:

- **SecondsPerSlide** (default: 5) — Duration for image slides
- **SecondsPerTitleSlide** (default: 6) — Duration for title slides
- **OutputPath** (default: Fabric_Monitor_Demo.mp4) — Output file
- **ImagesPath** (default: images) — Directory containing screenshots

## Output

- **Video format**: H.264 (libx264), 1920x1080, 30 FPS
- **Audio**: None (silent video)
- **File size**: ~1.3 MB for 18 slides (~95 seconds)
- **Codec**: H.264/MPEG-4 AVC

## Slide Layout

Each slide contains:
- **Background**: Dark blue for titles, light gray for content
- **Title**: Large white/bold text
- **Image**: Centered with aspect ratio preserved
- **Description**: Smaller text below image or positioned on slide

## Add Narration

To add voiceover narration:

1. Record audio separately (MP3/WAV format)
2. Use FFmpeg to add audio:
   ```powershell
   ffmpeg -i Fabric_Monitor_Demo.mp4 -i narration.mp3 -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 Fabric_Monitor_Demo_WithNarration.mp4
   ```

3. Or use: `Add-NarrationToVideo.ps1` (see [reference](https://github.com/microsoft/fabric-bi-devops/blob/main/Social%20Media/video/Add-NarrationToVideo.ps1))

## Distribute

- **Teams**: Share directly to Teams channels
- **SharePoint**: Upload to document libraries
- **Email**: Attach or link
- **LinkedIn/Social**: Upload as native video
- **YouTube**: Upload and share

## Customization

### Modify slide content:

Edit the `slides` array in the embedded Python script:

```python
slides = [
    (None, "Title", "Description\nLine 2", True),  # Title slide
    ("image.png", "Title", "Description", False),  # Image slide
    ...
]
```

### Change colors:

Edit RGB values in the Python script:
- `(25, 35, 65)` = Dark blue background
- `(245, 245, 245)` = Light gray background
- `(176, 190, 197)` = Light text color

### Adjust fonts:

Modify font sizes:
- `80` = Title font size
- `60` = Description font size

## Troubleshooting

**Video not created:**
- Ensure images directory exists with PNG files
- Check that all referenced image files are present
- Verify Python is in PATH: `python --version`

**FFmpeg errors:**
- Run: `python -m pip install --upgrade static-ffmpeg`
- Check temp directory is writable

**Conda activation errors:**
- Edit your PowerShell profile to skip conda activation, or run:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File Build-FabricMonitorVideo.ps1
  ```

## Reference

This solution is adapted from:
- [Enterprise BI DevOps - Video Build](https://github.com/microsoft/fabric-bi-devops/blob/main/Social%20Media/video/Build-EnterpriseBIDevOpsVideo.ps1)
- Uses similar techniques for frame expansion and FFmpeg encoding
- Customized for screenshot-based video generation

## License

See [LICENSE](../../LICENSE) in the main repository.
