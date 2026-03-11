# Media Optimization Guide for Rugby AI Predictor

## Current Media Files
- `video_rugby.mov` - Background video
- `video_rugby_ball.mov` - Header video  
- `login_video.mov` - Login page video
- `image_rugby.jpeg` - Prediction cards background

## Optimizations Applied

### 1. Caching Headers ✅
Added aggressive caching for videos and images in `firebase.json`:
- Videos: `Cache-Control: public, max-age=31536000, immutable`
- Images: `Cache-Control: public, max-age=31536000, immutable`
- Added `Accept-Ranges: bytes` for video streaming

### 2. Preloading ✅
Added `preload="auto"` to all video elements for faster loading.

### 3. Programmatic Preloading ✅
Added preload links in `index.js` to preload critical assets on app start.

## Recommended Further Optimizations

### Option 1: Convert Videos to Optimized Formats (RECOMMENDED)

**Convert .mov files to optimized MP4/WebM:**

```bash
# Install ffmpeg first, then:

# Convert to optimized MP4 (H.264)
ffmpeg -i video_rugby.mov -c:v libx264 -preset slow -crf 22 -c:a aac -b:a 128k -movflags +faststart video_rugby.mp4

ffmpeg -i video_rugby_ball.mov -c:v libx264 -preset slow -crf 22 -c:a aac -b:a 128k -movflags +faststart video_rugby_ball.mp4

ffmpeg -i login_video.mov -c:v libx264 -preset slow -crf 22 -c:a aac -b:a 128k -movflags +faststart login_video.mp4

# Optional: Also create WebM for better compression
ffmpeg -i video_rugby.mov -c:v libvpx-vp9 -crf 30 -b:v 0 -c:a libopus video_rugby.webm
```

**Benefits:**
- Smaller file sizes (often 50-70% reduction)
- Faster loading
- Better browser compatibility
- `faststart` flag enables progressive download

### Option 2: Use Firebase Storage with CDN

**Upload to Firebase Storage:**
1. Upload videos/images to Firebase Storage
2. Get public URLs
3. Update code to use Storage URLs
4. Benefits: Global CDN, automatic optimization, faster delivery

**Steps:**
```bash
# Install Firebase CLI tools
npm install -g firebase-tools

# Login
firebase login

# Upload files
firebase storage:upload public/video_rugby.mov media/video_rugby.mov
firebase storage:upload public/video_rugby_ball.mov media/video_rugby_ball.mov
firebase storage:upload public/login_video.mov media/login_video.mov
firebase storage:upload public/image_rugby.jpeg media/image_rugby.jpeg
```

Then update URLs in code to:
- `https://firebasestorage.googleapis.com/v0/b/rugby-ai-61fd0.appspot.com/o/media%2Fvideo_rugby.mov?alt=media`

### Option 3: Convert Images to WebP

**Convert JPEG to WebP:**
```bash
# Using cwebp (install via: npm install -g webp)
cwebp -q 80 image_rugby.jpeg -o image_rugby.webp
```

**Benefits:**
- 25-35% smaller file sizes
- Better quality at same size
- Modern browser support

### Option 4: Lazy Loading (For Non-Critical Assets)

For images that aren't immediately visible, use lazy loading:
```jsx
<img src="/image_rugby.jpeg" loading="lazy" alt="Rugby" />
```

## Current Implementation Status

✅ **Completed:**
- Added video caching headers
- Added image caching headers  
- Added `preload="auto"` to all videos
- Added programmatic preloading in index.js

⏳ **Recommended Next Steps:**
1. Convert .mov files to optimized .mp4 format
2. Consider using Firebase Storage for CDN delivery
3. Convert images to WebP format
4. Test loading times after optimizations

## Testing Performance

Use browser DevTools:
1. Open Network tab
2. Check "Disable cache"
3. Reload page
4. Check load times for media files
5. Look for "from disk cache" on subsequent loads

## Expected Results

After optimizations:
- **First Load:** 2-5 seconds (depending on connection)
- **Cached Load:** < 100ms (instant from cache)
- **Video Start:** Immediate (preloaded and cached)

