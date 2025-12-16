/**
 * Firebase Storage URL helper functions
 * These URLs point to media files stored in Firebase Storage for faster CDN delivery
 * 
 * IMPORTANT: After uploading files to Firebase Storage, these URLs will work automatically.
 * Until then, the app will fallback to local files.
 */

const STORAGE_BASE_URL = 'https://firebasestorage.googleapis.com/v0/b/rugby-ai-61fd0.firebasestorage.app/o';
const USE_STORAGE = true; // Using optimized MP4 files - ready for Storage!

// Performance: Test Storage availability and fallback to local if slow
let storageTested = false;
let storageAvailable = true;

/**
 * Test if Storage is fast enough (timeout after 3 seconds)
 */
const testStorageSpeed = async () => {
  if (storageTested) return storageAvailable;
  
  storageTested = true;
  const testUrl = `${STORAGE_BASE_URL}/${encodeURIComponent('media/image_rugby.jpeg')}?alt=media`;
  
  try {
    const startTime = performance.now();
    const response = await fetch(testUrl, { method: 'HEAD', signal: AbortSignal.timeout(3000) });
    const loadTime = performance.now() - startTime;
    
    if (response.ok && loadTime < 2000) {
      console.log(`✅ [Storage] Storage is fast (${Math.round(loadTime)}ms)`);
      storageAvailable = true;
      return true;
    } else {
      console.warn(`⚠️ [Storage] Storage is slow (${Math.round(loadTime)}ms), using local files`);
      storageAvailable = false;
      return false;
    }
  } catch (error) {
    console.warn(`⚠️ [Storage] Storage test failed, using local files:`, error.message);
    storageAvailable = false;
    return false;
  }
};

/**
 * Get Firebase Storage URL for a media file
 * @param {string} fileName - Name of the file in the media folder
 * @returns {string} Public URL to the file
 */
export const getStorageUrl = (fileName) => {
  // Encode the path (media/filename)
  const encodedPath = encodeURIComponent(`media/${fileName}`);
  const url = `${STORAGE_BASE_URL}/${encodedPath}?alt=media`;
  console.log(`📦 [Storage] Generated Storage URL for ${fileName}:`, url);
  return url;
};

/**
 * Get Storage URL with token (if needed for private files)
 * @param {string} fileName - Name of the file
 * @param {string} token - Access token (optional)
 * @returns {string} URL with token
 */
export const getStorageUrlWithToken = (fileName, token) => {
  const encodedPath = encodeURIComponent(`media/${fileName}`);
  return `${STORAGE_BASE_URL}/${encodedPath}?alt=media&token=${token}`;
};

/**
 * Get media URL with fallback to local
 * @param {string} fileName - Name of the file
 * @param {boolean} preferStorage - Whether to prefer Storage over local
 * @returns {string} URL (Storage or local)
 */
export const getMediaUrl = (fileName, preferStorage = USE_STORAGE) => {
  if (preferStorage) {
    return getStorageUrl(fileName);
  }
  // Fallback to local path
  return `/${fileName}`;
};

// Pre-defined URLs for all media files
// These will use Storage URLs if USE_STORAGE is true, otherwise local paths
const getMediaUrlWithLogging = (fileName, fileType) => {
  if (USE_STORAGE && storageAvailable) {
    const url = getStorageUrl(fileName);
    console.log(`✅ [Storage] Using Firebase Storage for ${fileType} (${fileName})`);
    return url;
  } else {
    const url = `/${fileName}`;
    console.log(`📁 [Local] Using local file for ${fileType} (${fileName})`);
    return url;
  }
};

// Initialize with Storage URLs, but will fallback if slow
export const MEDIA_URLS = {
  // Videos (using optimized MP4 format)
  videoRugby: getMediaUrlWithLogging('video_rugby.mp4', 'Background Video'),
  videoRugbyBall: getMediaUrlWithLogging('video_rugby_ball.mp4', 'Header Video'),
  loginVideo: getMediaUrlWithLogging('login_video.mp4', 'Login Video'),
  
  // Images
  imageRugby: getMediaUrlWithLogging('image_rugby.jpeg', 'Rugby Image'),
};

// Test Storage speed on module load (non-blocking)
testStorageSpeed().then(isFast => {
  if (!isFast && USE_STORAGE) {
    console.warn('⚠️ [Storage] Storage is slow, consider using local files or optimizing videos');
    // Update URLs to use local if Storage is slow
    Object.keys(MEDIA_URLS).forEach(key => {
      const fileName = key === 'videoRugby' ? 'video_rugby.mp4' :
                       key === 'videoRugbyBall' ? 'video_rugby_ball.mp4' :
                       key === 'loginVideo' ? 'login_video.mp4' :
                       'image_rugby.jpeg';
      MEDIA_URLS[key] = `/${fileName}`;
    });
  }
});

