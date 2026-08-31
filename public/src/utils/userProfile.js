const PROFILE_STORAGE_KEY = 'rugby_ai_profile_v1';
const MAX_AVATAR_DATA_URL_LEN = 200000;
const AVATAR_IMAGE_MAX_DIM = 256;

export const AVATAR_EMOJI_OPTIONS = ['🏉', '👤', '🦁', '🐯', '⚡', '🏆', '🎯', '🔥'];

export function getUserProfile() {
  try {
    const raw = localStorage.getItem(PROFILE_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed ? parsed : {};
  } catch {
    return {};
  }
}

export function saveUserProfile(updates) {
  const current = getUserProfile();
  const next = {
    ...current,
    ...updates,
    updatedAt: Date.now(),
  };
  localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(next));
  return next;
}

export function getDefaultDisplayName(authData) {
  const profile = getUserProfile();
  if (profile.displayName && String(profile.displayName).trim()) {
    return String(profile.displayName).trim();
  }
  const email = authData?.email;
  if (email && String(email).includes('@')) {
    return String(email).split('@')[0];
  }
  return 'Rugby Fan';
}

export function getAvatarEmoji(profile = getUserProfile()) {
  const emoji = profile?.avatarEmoji;
  if (emoji && AVATAR_EMOJI_OPTIONS.includes(emoji)) return emoji;
  return '🏉';
}

export function getAvatarImage(profile = getUserProfile()) {
  const img = profile?.avatarImage;
  if (img && typeof img === 'string' && img.startsWith('data:image/')) return img;
  return null;
}

export function hasCustomAvatar(profile = getUserProfile()) {
  return Boolean(getAvatarImage(profile));
}

function loadImageFromFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('Could not load image.'));
      img.src = event.target.result;
    };
    reader.onerror = () => reject(new Error('Could not read file.'));
    reader.readAsDataURL(file);
  });
}

function imageToDataUrl(img, maxDim, quality) {
  const canvas = document.createElement('canvas');
  let { width, height } = img;
  const scale = Math.min(1, maxDim / Math.max(width, height, 1));
  width = Math.max(1, Math.round(width * scale));
  height = Math.max(1, Math.round(height * scale));
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, width, height);
  return canvas.toDataURL('image/jpeg', quality);
}

async function compressAvatarImage(file) {
  const img = await loadImageFromFile(file);
  let maxDim = AVATAR_IMAGE_MAX_DIM;
  let quality = 0.88;
  let dataUrl = imageToDataUrl(img, maxDim, quality);

  while (dataUrl.length > MAX_AVATAR_DATA_URL_LEN && quality > 0.45) {
    quality -= 0.08;
    dataUrl = imageToDataUrl(img, maxDim, quality);
  }
  while (dataUrl.length > MAX_AVATAR_DATA_URL_LEN && maxDim > 96) {
    maxDim -= 32;
    dataUrl = imageToDataUrl(img, maxDim, Math.max(quality, 0.55));
  }

  if (dataUrl.length > MAX_AVATAR_DATA_URL_LEN) {
    throw new Error('Image is too large. Try a smaller photo.');
  }
  return dataUrl;
}

export async function importAvatarFromFile(file) {
  const allowed = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
  if (!file || !allowed.includes(file.type)) {
    throw new Error('Use a JPG, PNG, WebP, or GIF image.');
  }
  if (file.size > 8 * 1024 * 1024) {
    throw new Error('Image must be under 8 MB.');
  }

  const avatarImage = await compressAvatarImage(file);
  return saveUserProfile({ avatarImage, avatarType: 'image' });
}

export function clearCustomAvatar() {
  return saveUserProfile({ avatarImage: null, avatarType: 'emoji' });
}

export function saveAvatarEmoji(emoji) {
  return saveUserProfile({ avatarEmoji: emoji, avatarImage: null, avatarType: 'emoji' });
}

export function ensureProfileFromAuth(authData) {
  if (!authData) return getUserProfile();
  const current = getUserProfile();
  if (current.displayName) return current;
  return saveUserProfile({ displayName: getDefaultDisplayName(authData) });
}
