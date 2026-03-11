# ⚠️ URGENT: Video Optimization Required

## Problem
Your videos are loading from Firebase Storage but taking too long because:
1. **MOV files are very large** (often 50-100MB+)
2. **MOV format is not web-optimized** (not designed for streaming)
3. **No compression** - files are in original quality

## Solution: Convert to Optimized MP4

### Quick Fix (Recommended)

Convert your `.mov` files to optimized `.mp4` format:

```bash
# Install ffmpeg first: https://ffmpeg.org/download.html

# Navigate to your video folder
cd "C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main\public\public"

# Convert background video (optimize for web)
ffmpeg -i video_rugby.mov -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart -vf "scale=1920:1080" video_rugby.mp4

# Convert header video
ffmpeg -i video_rugby_ball.mov -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart -vf "scale=1920:1080" video_rugby_ball.mp4

# Convert login video
ffmpeg -i login_video.mov -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart -vf "scale=1920:1080" login_video.mp4
```

**What this does:**
- `libx264`: H.264 codec (universal browser support)
- `crf 23`: Good quality/size balance (lower = better quality but larger file)
- `faststart`: Enables progressive download (starts playing while downloading)
- `scale=1920:1080`: Limits resolution (adjust if needed)
- `aac`: Audio codec
- `b:a 128k`: Audio bitrate

### Expected Results
- **File size reduction**: 70-90% smaller files
- **Faster loading**: 5-10x faster
- **Better streaming**: Progressive download enabled

### After Conversion

1. **Upload MP4 files to Firebase Storage:**
   - Upload `video_rugby.mp4` to `media/video_rugby.mp4`
   - Upload `video_rugby_ball.mp4` to `media/video_rugby_ball.mp4`
   - Upload `login_video.mp4` to `media/login_video.mp4`

2. **Update code to use .mp4:**
   - Change `storageUrls.js` to use `.mp4` instead of `.mov`
   - Or keep both formats and let browser choose

3. **Keep .mov as fallback** (optional):
   - Upload both formats
   - Browser will use MP4 if available

## Alternative: Use Local Files Temporarily

If conversion takes time, temporarily use local files:

1. In `storageUrls.js`, change:
   ```javascript
   const USE_STORAGE = false; // Temporarily use local
   ```

2. Make sure files are in `public/build/` folder

3. Rebuild and deploy

## Why This Matters

- **Current**: 50-100MB MOV files = 30-60 seconds load time
- **Optimized**: 5-15MB MP4 files = 2-5 seconds load time
- **Result**: 10x faster loading, better user experience

## File Size Targets

- Background video: < 10MB
- Header video: < 5MB  
- Login video: < 8MB
- Image: < 500KB (already good)

## Quick Test

After conversion, test file sizes:
```bash
# Check file sizes
ls -lh public/public/*.mp4
```

If files are still > 20MB, use lower CRF (higher quality) or reduce resolution further.

