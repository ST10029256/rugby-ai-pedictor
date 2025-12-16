# Install FFmpeg on Windows

## Method 1: Using Chocolatey (Easiest)

1. **Install Chocolatey** (if not already installed):
   - Open PowerShell as Administrator
   - Run:
   ```powershell
   Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
   ```

2. **Install FFmpeg**:
   ```powershell
   choco install ffmpeg
   ```

3. **Restart PowerShell** and test:
   ```powershell
   ffmpeg -version
   ```

## Method 2: Manual Installation

1. **Download FFmpeg**:
   - Go to: https://www.gyan.dev/ffmpeg/builds/
   - Download: `ffmpeg-release-essentials.zip` (or latest version)

2. **Extract**:
   - Extract to: `C:\ffmpeg`
   - You should have: `C:\ffmpeg\bin\ffmpeg.exe`

3. **Add to PATH**:
   - Press `Win + X` → System → Advanced system settings
   - Click "Environment Variables"
   - Under "System variables", find "Path" → Edit
   - Click "New" → Add: `C:\ffmpeg\bin`
   - Click OK on all dialogs

4. **Restart PowerShell** and test:
   ```powershell
   ffmpeg -version
   ```

## Method 3: Using Winget (Windows 10/11)

```powershell
winget install ffmpeg
```

## After Installation

Navigate to your video folder and convert:

```powershell
cd "C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main\public\public"

# Convert videos
ffmpeg -i video_rugby.mov -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart video_rugby.mp4

ffmpeg -i video_rugby_ball.mov -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart video_rugby_ball.mp4

ffmpeg -i login_video.mov -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart login_video.mp4
```

## Alternative: Online Converter

If you don't want to install ffmpeg, use an online converter:

1. **CloudConvert**: https://cloudconvert.com/mov-to-mp4
2. **FreeConvert**: https://www.freeconvert.com/mov-to-mp4
3. **Zamzar**: https://www.zamzar.com/convert/mov-to-mp4/

**Settings to use:**
- Codec: H.264
- Quality: Medium/High
- Resolution: Keep original (or 1920x1080 max)
- Audio: AAC, 128kbps

## Quick Test After Installation

```powershell
ffmpeg -version
```

If you see version info, you're ready to convert!

