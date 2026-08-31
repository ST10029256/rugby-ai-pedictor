/**
 * Device biometric login (Face ID / Touch ID / fingerprint) via WebAuthn.
 * This is a convenience lock on this device — the license key is still verified
 * with the server on every unlock. Expired keys always require renewal.
 */

import { getDeviceId, isLocalDeviceSessionValid, clearLocalAuthState, isLikelyFreshBrowserSession, getDeviceAuthPayload } from './deviceId';

const BIOMETRIC_STORAGE_KEY = 'rugby_ai_biometric_v1';
const DEVICE_SESSION_KEY = 'rugby_ai_device_v1';
const BIOMETRIC_LOGIN_SETUP_DISMISSED_KEY = 'rugby_ai_biometric_login_dismissed_v1';
const RP_NAME = 'Rugby AI Predictor';

function normalizeLicenseKey(key) {
  return String(key || '').replace(/\s/g, '').replace(/-/g, '').toUpperCase();
}

function toBase64Url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64Url(value) {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/');
  const padLen = (4 - (padded.length % 4)) % 4;
  const base64 = padded + '='.repeat(padLen);
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

export function getRpId() {
  if (typeof window === 'undefined') return 'localhost';
  const hostname = String(window.location.hostname || '').toLowerCase();
  if (hostname === 'localhost' || hostname === '127.0.0.1') return 'localhost';
  // Safari/iOS reject IP addresses as rpId — LAN dev URLs won't work for biometrics.
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(hostname)) return null;
  return hostname;
}

export function isSecureBiometricContext() {
  return typeof window !== 'undefined' && window.isSecureContext === true;
}

export function isBiometricSupported() {
  return (
    typeof window !== 'undefined' &&
    typeof window.PublicKeyCredential !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    typeof navigator.credentials !== 'undefined'
  );
}

export async function isPlatformAuthenticatorAvailable() {
  if (!isBiometricSupported()) return false;
  try {
    const PKC = window.PublicKeyCredential;
    if (typeof PKC?.isUserVerifyingPlatformAuthenticatorAvailable === 'function') {
      return await PKC.isUserVerifyingPlatformAuthenticatorAvailable();
    }
  } catch {
    return false;
  }
  return isSecureBiometricContext();
}

/**
 * Full availability check for UI — use this on login/profile screens (especially mobile).
 */
export async function getBiometricAvailability() {
  if (typeof window === 'undefined') {
    return { canUse: false, reason: 'Not running in a browser.' };
  }

  // Check HTTPS / hostname first — on mobile HTTP hides WebAuthn and looks like "unsupported".
  if (!isSecureBiometricContext()) {
    return {
      canUse: false,
      reason:
        'Face ID and fingerprint need HTTPS. On your phone, use the cloudflare tunnel script, ngrok, or the deployed app URL — http://192.168.x.x will not work for biometrics.',
    };
  }

  const rpId = getRpId();
  if (!rpId) {
    return {
      canUse: false,
      reason:
        'Biometric login needs the deployed HTTPS app URL or an ngrok HTTPS link — not a local network IP.',
    };
  }

  if (!isBiometricSupported()) {
    return {
      canUse: false,
      reason: 'This browser does not support Face ID or fingerprint login. Use Safari on iPhone or Chrome on Android.',
    };
  }

  try {
    const platformAvailable = await isPlatformAuthenticatorAvailable();
    if (!platformAvailable) {
      return {
        canUse: false,
        reason: 'No Face ID, Touch ID, or fingerprint is available on this device. Check your phone settings.',
      };
    }
  } catch {
    return {
      canUse: false,
      reason: 'Could not check biometric availability on this device.',
    };
  }

  return { canUse: true, reason: '', rpId };
}

export function getBiometricRegistration() {
  try {
    const raw = localStorage.getItem(BIOMETRIC_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.credentialId || !parsed?.enabled) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearBiometricRegistration() {
  localStorage.removeItem(BIOMETRIC_STORAGE_KEY);
}

/** User skipped biometric setup on the login screen for this license key. */
export function getBiometricLoginSetupDismissed() {
  try {
    const raw = localStorage.getItem(BIOMETRIC_LOGIN_SETUP_DISMISSED_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.licenseKey) return null;
    return { ...parsed, licenseKey: normalizeLicenseKey(parsed.licenseKey) };
  } catch {
    return null;
  }
}

export function dismissBiometricLoginSetup(licenseKey) {
  localStorage.setItem(
    BIOMETRIC_LOGIN_SETUP_DISMISSED_KEY,
    JSON.stringify({
      licenseKey: normalizeLicenseKey(licenseKey),
      dismissedAt: Date.now(),
    }),
  );
}

export function clearBiometricLoginSetupDismissed() {
  localStorage.removeItem(BIOMETRIC_LOGIN_SETUP_DISMISSED_KEY);
}

/**
 * After a license-key login, offer biometric setup unless already registered,
 * user skipped for this key, or biometrics unavailable (checked separately).
 */
export function shouldPromptBiometricSetupAfterLogin(licenseKey) {
  if (getBiometricRegistration()) return false;
  const normalized = normalizeLicenseKey(licenseKey);
  const dismissed = getBiometricLoginSetupDismissed();
  if (dismissed?.licenseKey === normalized) return false;
  return true;
}

/** Reset device biometrics when the subscriber logs in with a different license key. */
export function onLicenseKeyLoginSuccess(licenseKey) {
  const normalized = normalizeLicenseKey(licenseKey);
  const sessionKey = getDeviceSession()?.licenseKey;
  if (sessionKey && sessionKey !== normalized) {
    clearBiometricRegistration();
    clearBiometricLoginSetupDismissed();
  }
}

/** License + subscription snapshot bound to this device for biometric unlock. */
export function saveDeviceSession({ licenseKey, expiresAt, email, subscriptionType, deviceId }) {
  if (!licenseKey) return;
  localStorage.setItem(
    DEVICE_SESSION_KEY,
    JSON.stringify({
      licenseKey: normalizeLicenseKey(licenseKey),
      expiresAt: expiresAt || null,
      email: email || null,
      subscriptionType: subscriptionType || null,
      deviceId: deviceId || getDeviceId(),
      updatedAt: Date.now(),
    }),
  );
}

export function getDeviceSession() {
  try {
    const raw = localStorage.getItem(DEVICE_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.licenseKey) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearDeviceSession() {
  localStorage.removeItem(DEVICE_SESSION_KEY);
}

/** Clear all local login state when server rejects this device. */
export function handleDeviceAuthFailure(resultData) {
  if (resultData?.device_rebind_pending) return 'pending';
  if (!resultData?.device_mismatch) return false;
  clearDeviceSession();
  clearBiometricRegistration();
  clearBiometricLoginSetupDismissed();
  clearLocalAuthState();
  return 'blocked';
}

function readStoredAuth() {
  try {
    const raw = localStorage.getItem('rugby_ai_auth');
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.licenseKey) return null;
    return parsed;
  } catch {
    return null;
  }
}

function readStoredLicenseKey() {
  const raw = localStorage.getItem('rugby_ai_license_key');
  if (!raw) return null;
  return String(raw).replace(/\s/g, '').replace(/-/g, '').toUpperCase();
}

/** Best license key saved on this device (biometric session → auth → legacy key). */
export function getDeviceLicenseKey() {
  const session = getDeviceSession();
  if (session?.licenseKey) return session.licenseKey;
  const auth = readStoredAuth();
  if (auth?.licenseKey) {
    return String(auth.licenseKey).replace(/\s/g, '').replace(/-/g, '').toUpperCase();
  }
  return readStoredLicenseKey() || '';
}

function isSubscriptionExpired(expiresAt) {
  if (!expiresAt) return false;
  return expiresAt * 1000 < Date.now() - 3600000;
}

/**
 * Decide login screen: biometric-only when this device completed setup + sub still valid.
 * Returns { mode: 'biometric' | 'license', ... }
 */
export async function getDeviceLoginMode() {
  // Always probe biometrics + build fingerprint so startup feels like a device check.
  const availability = await getBiometricAvailability();
  await getDeviceAuthPayload();

  const registration = getBiometricRegistration();
  if (!registration) {
    const freshBrowser = isLikelyFreshBrowserSession();
    return {
      mode: 'license',
      reason: freshBrowser ? 'fresh_browser' : 'no_biometric',
      message: freshBrowser
        ? 'No saved session on this browser — if you cleared app data, enter your license key once. We\'ll verify your device profile on the server and re-link automatically when it matches.'
        : '',
    };
  }

  if (!availability.canUse) {
    return {
      mode: 'license',
      reason: availability.reason || 'Biometric login unavailable on this browser.',
      hasBiometricRegistration: true,
    };
  }

  const currentRpId = getRpId();
  if (registration.rpId && currentRpId && registration.rpId !== currentRpId) {
    return {
      mode: 'license',
      reason:
        'Biometrics were set up on a different site URL. Sign in with your license key, then re-enable biometrics in Profile.',
      hasBiometricRegistration: true,
    };
  }

  const licenseKey = getDeviceLicenseKey();
  if (!licenseKey) {
    return {
      mode: 'license',
      reason: 'no_device_key',
      hasBiometricRegistration: true,
    };
  }

  const session = getDeviceSession() || readStoredAuth();
  if (session && !isLocalDeviceSessionValid(session)) {
    // Storage was cleared — new device_id but same physical browser. Keep passkey if OS still has it.
    return {
      mode: 'license',
      reason: 'fresh_browser',
      licenseKey: session.licenseKey || getDeviceLicenseKey(),
      message:
        'App data was cleared on this browser. Enter your license key once — your device profile will be verified and re-linked on the server.',
      hasBiometricRegistration: true,
    };
  }

  if (isSubscriptionExpired(session?.expiresAt)) {
    return {
      mode: 'license',
      reason: 'expired',
      licenseKey,
      hasBiometricRegistration: true,
    };
  }

  return {
    mode: 'biometric',
    licenseKey,
    email: session?.email || null,
    expiresAt: session?.expiresAt || null,
    subscriptionType: session?.subscriptionType || null,
    label: getBiometricLabel(),
  };
}

export function getBiometricLabel() {
  if (typeof navigator === 'undefined') return 'Face ID / Fingerprint';
  const ua = navigator.userAgent || '';
  if (/iPhone|iPad|iPod/i.test(ua)) return 'Face ID / Touch ID';
  if (/Android/i.test(ua)) return 'Face unlock / Fingerprint';
  if (/Mac/i.test(ua)) return 'Touch ID / Face ID';
  if (/Win/i.test(ua)) return 'Windows Hello (Face / Fingerprint)';
  return 'Face ID / Fingerprint';
}

/** Short title for buttons and profile headers */
export function getBiometricLoginTitle() {
  return getBiometricLabel();
}

/**
 * Shown before the OS biometric sheet — phones label WebAuthn as "passkey" even when
 * Face ID / fingerprint is what actually unlocks it on this device.
 */
export function getBiometricSetupHint() {
  if (typeof navigator === 'undefined') {
    return 'Your phone may say "passkey" — tap Continue, then use Face ID or fingerprint when prompted. Choose this device only, not a password manager or QR code.';
  }
  const ua = navigator.userAgent || '';
  if (/iPhone|iPad|iPod/i.test(ua)) {
    return 'Your iPhone will say "Save a passkey" — that is normal. Tap Continue, then scan Face ID / Touch ID. Pick "On this iPhone" (not another device or QR code).';
  }
  if (/Android/i.test(ua)) {
    return 'Your phone may say "passkey" — tap Continue, then use fingerprint or face unlock. Choose "This device" / Google fingerprint, not "Save to Google Account" on another phone.';
  }
  if (/Win/i.test(ua)) {
    return 'Windows may say "passkey" — that is normal. Choose Windows Hello (face, fingerprint, or PIN) on this PC, not a phone QR code or security key.';
  }
  if (/Mac/i.test(ua)) {
    return 'Your Mac may say "passkey" — tap Continue, then use Touch ID. Pick "On this Mac", not iCloud sync to another device.';
  }
  return 'Your browser may say "passkey" — tap Continue, then use Face ID, fingerprint, or Windows Hello on this device.';
}

function buildPlatformPublicKeyOptions(challenge, extra = {}) {
  return {
    challenge,
    timeout: 60000,
    userVerification: 'required',
    // Prefer on-device biometrics; avoid cross-device / QR passkey flows.
    hints: ['client-device'],
    ...extra,
  };
}

export async function registerBiometric({ licenseKey, email }) {
  const availability = await getBiometricAvailability();
  if (!availability.canUse) {
    throw new Error(availability.reason || 'Biometric login is not supported on this device or browser.');
  }

  const rpId = availability.rpId || getRpId();
  const userIdSource = String(licenseKey || email || 'rugby-user')
    .replace(/[^a-zA-Z0-9]/g, '')
    .slice(0, 32)
    .padEnd(8, '0');
  const userId = new TextEncoder().encode(userIdSource);
  const challenge = crypto.getRandomValues(new Uint8Array(32));

  const credential = await navigator.credentials.create({
    publicKey: buildPlatformPublicKeyOptions(challenge, {
      rp: { name: RP_NAME, id: rpId },
      user: {
        id: userId,
        name: email || 'Rugby AI subscriber',
        displayName: email || 'Rugby AI subscriber',
      },
      // ES256 only — platform authenticators (Face ID / fingerprint) on mobile.
      pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
      authenticatorSelection: {
        authenticatorAttachment: 'platform',
        userVerification: 'required',
        residentKey: 'discouraged',
        requireResidentKey: false,
      },
      attestation: 'none',
    }),
  });

  if (!credential || !credential.rawId) {
    throw new Error('Biometric setup was cancelled.');
  }

  if (credential.authenticatorAttachment === 'cross-platform') {
    throw new Error(
      `Please use ${getBiometricLabel()} on this device — not a security key, password manager, or QR code from another device.`,
    );
  }

  const registration = {
    enabled: true,
    credentialId: toBase64Url(credential.rawId),
    registeredAt: Date.now(),
    label: getBiometricLabel(),
    rpId,
  };
  localStorage.setItem(BIOMETRIC_STORAGE_KEY, JSON.stringify(registration));
  clearBiometricLoginSetupDismissed();
  return registration;
}

export async function authenticateWithBiometric() {
  const registration = getBiometricRegistration();
  if (!registration?.credentialId) {
    throw new Error('Biometric login is not set up on this device.');
  }

  const availability = await getBiometricAvailability();
  if (!availability.canUse) {
    throw new Error(availability.reason || 'Biometric login is not supported on this device or browser.');
  }

  const challenge = crypto.getRandomValues(new Uint8Array(32));
  const assertion = await navigator.credentials.get({
    publicKey: buildPlatformPublicKeyOptions(challenge, {
      rpId: registration.rpId || getRpId() || undefined,
      allowCredentials: [
        {
          type: 'public-key',
          id: fromBase64Url(registration.credentialId),
        },
      ],
    }),
  });

  if (!assertion) {
    throw new Error('Biometric login was cancelled.');
  }

  return registration;
}
