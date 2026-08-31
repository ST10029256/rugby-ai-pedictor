/**
 * Device identity for server-side license binding.
 * - device_id: random UUID in localStorage (changes if site data is cleared)
 * - device_fingerprint: stable hash of high-trust browser/device traits
 * - device_fingerprint_profile: bucketed trait breakdown for similarity scoring
 */

const DEVICE_ID_KEY = 'rugby_ai_device_id_v1';
let fingerprintCache = null;
let profileCache = null;

export const DEVICE_BINDING_NOTICE =
  'Your license is bound to your registered browser/device profile. If your device changes, browser changes, or system settings change significantly, re-approval may be required.';

export function getDeviceId() {
  if (typeof window === 'undefined') return '';
  try {
    let id = localStorage.getItem(DEVICE_ID_KEY);
    if (id && id.length >= 16) return id;
    id = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `dev-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
    localStorage.setItem(DEVICE_ID_KEY, id);
    return id;
  } catch {
    return '';
  }
}

/** True when this browser has a device id but no saved login (cache cleared or first visit). */
export function isLikelyFreshBrowserSession() {
  if (typeof window === 'undefined') return false;
  try {
    const hasSavedLogin =
      localStorage.getItem('rugby_ai_auth') ||
      localStorage.getItem('rugby_ai_device_v1') ||
      localStorage.getItem('rugby_ai_license_key') ||
      localStorage.getItem('rugby_ai_biometric_v1');
    return Boolean(localStorage.getItem(DEVICE_ID_KEY) || getDeviceId()) && !hasSavedLogin;
  } catch {
    return false;
  }
}

export function getDeviceLabel() {
  if (typeof navigator === 'undefined') return 'Unknown device';
  const ua = navigator.userAgent || '';
  if (/iPhone/i.test(ua)) return 'iPhone';
  if (/iPad/i.test(ua)) return 'iPad';
  if (/Android/i.test(ua)) return 'Android';
  if (/Win/i.test(ua)) return 'Windows';
  if (/Mac/i.test(ua)) return 'Mac';
  return 'Browser';
}

function parseBrowserFamily(ua) {
  if (/Edg\//i.test(ua)) return 'edge';
  if (/Chrome/i.test(ua) && !/Edg/i.test(ua)) return 'chrome';
  if (/Firefox/i.test(ua)) return 'firefox';
  if (/Safari/i.test(ua) && !/Chrome/i.test(ua)) return 'safari';
  return 'other';
}

function parseOsFamily(ua, platform) {
  if (/iPhone|iPad/i.test(ua)) return 'ios';
  if (/Android/i.test(ua)) return 'android';
  if (/Win/i.test(ua) || /Win/i.test(platform || '')) return 'windows';
  if (/Mac/i.test(ua) || /Mac/i.test(platform || '')) return 'macos';
  if (/Linux/i.test(ua)) return 'linux';
  return (platform || 'unknown').toLowerCase().slice(0, 32);
}

function getPlatformClass(ua) {
  if (/iPhone|Android.*Mobile|Mobile/i.test(ua)) return 'mobile';
  if (/iPad|Tablet/i.test(ua)) return 'tablet';
  if (/Android/i.test(ua)) return 'tablet';
  return 'desktop';
}

function bucketHardwareConcurrency(cores) {
  const n = Number(cores) || 0;
  if (n <= 0) return 'unknown';
  if (n <= 2) return '1-2';
  if (n <= 4) return '3-4';
  if (n <= 8) return '5-8';
  return '9+';
}

function bucketDeviceMemory(gb) {
  const n = Number(gb) || 0;
  if (n <= 0) return 'unknown';
  if (n <= 2) return '1-2';
  if (n <= 4) return '3-4';
  if (n <= 8) return '5-8';
  return '9+';
}

function getScreenClass(width, height) {
  const w = Number(width) || 0;
  const h = Number(height) || 0;
  const max = Math.max(w, h);
  if (max <= 0) return 'unknown';
  if (max <= 768) return 'small';
  if (max <= 1024) return 'medium';
  if (max <= 1440) return 'large';
  if (max <= 1920) return 'xl';
  return 'xxl';
}

export function getDeviceFingerprintProfile() {
  if (typeof window === 'undefined') return {};
  if (profileCache) return profileCache;

  const ua = navigator.userAgent || '';
  const screenW = window.screen?.width || 0;
  const screenH = window.screen?.height || 0;
  const lang = (navigator.language || '').split('-')[0].toLowerCase();

  profileCache = {
    os_family: parseOsFamily(ua, navigator.platform),
    browser_family: parseBrowserFamily(ua),
    platform_class: getPlatformClass(ua),
    platform: (navigator.platform || '').slice(0, 64),
    screen_class: getScreenClass(screenW, screenH),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
    language: lang.slice(0, 16),
    hardware_concurrency_bucket: bucketHardwareConcurrency(navigator.hardwareConcurrency),
    device_memory_bucket: bucketDeviceMemory(navigator.deviceMemory),
    touch_support: String(
      'ontouchstart' in window || (navigator.maxTouchPoints || 0) > 0,
    ),
  };
  return profileCache;
}

async function computeDeviceFingerprint() {
  if (typeof window === 'undefined') return '';
  if (fingerprintCache) return fingerprintCache;

  const profile = getDeviceFingerprintProfile();
  const parts = [
    profile.os_family,
    profile.browser_family,
    profile.platform_class,
    profile.platform,
    profile.screen_class,
    profile.timezone,
    profile.language,
    profile.hardware_concurrency_bucket,
    profile.device_memory_bucket,
  ].join('|||');

  try {
    if (crypto?.subtle) {
      const data = new TextEncoder().encode(parts);
      const hash = await crypto.subtle.digest('SHA-256', data);
      fingerprintCache = Array.from(new Uint8Array(hash))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
      return fingerprintCache;
    }
  } catch {
    // fall through to simple hash
  }

  let h = 2166136261;
  for (let i = 0; i < parts.length; i += 1) {
    h ^= parts.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  fingerprintCache = `fb-${(h >>> 0).toString(16)}`;
  return fingerprintCache;
}

export async function getDeviceAuthPayload() {
  const profile = getDeviceFingerprintProfile();
  return {
    device_id: getDeviceId(),
    device_fingerprint: await computeDeviceFingerprint(),
    device_fingerprint_profile: profile,
    device_fingerprint_profile_json: JSON.stringify(profile),
    device_label: getDeviceLabel(),
  };
}

export function isLocalDeviceSessionValid(session) {
  if (!session?.deviceId) return true;
  const current = getDeviceId();
  return !current || session.deviceId === current;
}

export function clearLocalAuthState() {
  localStorage.removeItem('rugby_ai_auth');
  localStorage.removeItem('rugby_ai_license_key');
  localStorage.removeItem('rugby_ai_device_v1');
}
