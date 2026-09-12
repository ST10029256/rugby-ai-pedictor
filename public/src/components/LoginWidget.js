import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  TextField,
  Button,
  Typography,
  Alert,
  CircularProgress,
  Paper,
  Fade,
  Zoom,
  Snackbar,
  Slide,
} from '@mui/material';
import { verifyLicenseKey, requestEmailLoginCode, verifyEmailLoginCode } from '../firebase';
import { MEDIA_URLS } from '../utils/storageUrls';
import {
  authenticateWithBiometric,
  dismissBiometricLoginSetup,
  getBiometricAvailability,
  getBiometricLoginTitle,
  getBiometricRegistration,
  getBiometricSetupHint,
  getDeviceLoginMode,
  handleDeviceAuthFailure,
  onLicenseKeyLoginSuccess,
  registerBiometric,
  saveDeviceSession,
  shouldPromptBiometricSetupAfterLogin,
} from '../utils/biometricAuth';
import { getDeviceId, DEVICE_BINDING_NOTICE } from '../utils/deviceId';
import RugbyBallLoader from './RugbyBallLoader';
import FaceRetouchingNaturalIcon from '@mui/icons-material/FaceRetouchingNatural';
import FingerprintIcon from '@mui/icons-material/Fingerprint';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';

const SlideUp = (props) => <Slide {...props} direction="up" />;

const loginErrorAlertSx = {
  mb: 2,
  borderRadius: 2,
  backgroundColor: 'rgba(127,29,29,0.98)',
  color: '#fee2e2',
  border: '1.5px solid rgba(248,113,113,0.7)',
  fontSize: '0.875rem',
  textAlign: 'left',
  fontWeight: 500,
  boxShadow: '0 4px 12px rgba(127,29,29,0.5), inset 0 1px 0 rgba(255,255,255,0.1)',
  '& .MuiAlert-icon': { color: '#fca5a5' },
};

const credentialInputSx = {
  mb: 2.5,
  mt: 0.5,
  '& .MuiOutlinedInput-root': {
    backgroundColor: 'rgba(2,6,23,0.9)',
    color: '#f9fafb',
    borderRadius: 2.5,
    px: 2.5,
    minHeight: 56,
    overflow: 'visible',
    transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
    border: '1.5px solid transparent',
    '& fieldset': {
      borderColor: 'rgba(75,85,99,0.6)',
      borderWidth: '1.5px',
      overflow: 'visible',
    },
    '&:hover': {
      backgroundColor: 'rgba(2,6,23,0.95)',
      '& fieldset': { borderColor: 'rgba(34,197,94,0.7)' },
    },
    '&.Mui-focused': {
      backgroundColor: 'rgba(2,6,23,1)',
      boxShadow: 'none',
      '& fieldset': { borderColor: '#22c55e', borderWidth: '1.5px' },
    },
  },
  '& .MuiOutlinedInput-input': {
    minHeight: 24,
    fontSize: '1rem',
    py: 1.25,
  },
  '& .MuiInputLabel-root': {
    color: '#9ca3af',
    fontWeight: 500,
    zIndex: 1,
    '&.Mui-focused': { color: '#86efac', fontWeight: 600 },
    '&.MuiInputLabel-shrink': {
      backgroundColor: 'rgba(2,6,23,1)',
      px: 0.75,
      ml: -0.25,
    },
  },
};

const LoginWidget = ({ onLoginSuccess, onShowSubscription }) => {
  const [licenseKey, setLicenseKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [biometricLoading, setBiometricLoading] = useState(false);
  const [loginMode, setLoginMode] = useState('loading'); // loading | biometric | license | biometric-setup
  const [loginCheckDone, setLoginCheckDone] = useState(false);
  const [biometricUnavailableReason, setBiometricUnavailableReason] = useState('');
  const [pendingAuth, setPendingAuth] = useState(null);
  const [deviceSession, setDeviceSession] = useState(null);
  const [canReturnToBiometric, setCanReturnToBiometric] = useState(false);
  const [deviceCheckMessage, setDeviceCheckMessage] = useState('');
  const [credentialPanel, setCredentialPanel] = useState('license'); // license | email
  const [email, setEmail] = useState('');
  const [loginCode, setLoginCode] = useState('');
  const [emailStep, setEmailStep] = useState('email'); // email | code
  const [codeSentMessage, setCodeSentMessage] = useState('');
  const [toast, setToast] = useState({ open: false, message: '', severity: 'info' });
  const videoRef = useRef(null);
  const otpRefs = useRef([]);

  const showToast = (message, severity = 'info') => {
    setToast({ open: true, message, severity });
  };

  const closeToast = () => {
    setToast((prev) => ({ ...prev, open: false }));
  };

  const maskEmail = (value) => {
    const trimmed = String(value || '').trim();
    const at = trimmed.indexOf('@');
    if (at < 1) return trimmed;
    const name = trimmed.slice(0, at);
    const domain = trimmed.slice(at);
    const visible = name.slice(0, Math.min(2, name.length));
    return `${visible}${'•'.repeat(Math.max(1, name.length - visible.length))}${domain}`;
  };

  const openPurchase = () => {
    if (onShowSubscription) {
      onShowSubscription();
      return;
    }
    window.open('https://rugby-ai-61fd0.web.app/subscribe.html', '_blank', 'noopener,noreferrer');
  };

  useEffect(() => {
    if (emailStep === 'code') {
      const t = setTimeout(() => otpRefs.current[0]?.focus(), 180);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [emailStep]);

  const minLoadingMs = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });

  // Auto-format license key as user types
  const formatLicenseKey = (value) => {
    // Allow both lower/upper while typing; normalize to uppercase for display/storage
    const cleaned = value.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
    const formatted = cleaned.match(/.{1,4}/g)?.join('-') || cleaned;
    return formatted;
  };

  const handleKeyChange = (e) => {
    const formatted = formatLicenseKey(e.target.value);
    setLicenseKey(formatted);
    setError('');
  };

  // Detect device login mode: biometric-only vs license key.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
      const storedKey = localStorage.getItem('rugby_ai_license_key');
      if (storedKey) {
        setLicenseKey(formatLicenseKey(storedKey));
      }

      const deviceMode = await Promise.all([
        getDeviceLoginMode(),
        minLoadingMs(800),
      ]).then(([mode]) => mode);
      if (cancelled) return;

      if (deviceMode.message) {
        setDeviceCheckMessage(deviceMode.message);
      }

      if (deviceMode.mode === 'biometric') {
        try {
          const authData = await verifyAndBuildAuth(deviceMode.licenseKey);
          if (cancelled) return;
          saveDeviceSession(authData);
          setDeviceSession(authData);
          setCanReturnToBiometric(true);
          setLoginMode('biometric');
        } catch (err) {
          if (cancelled) return;
          setLoginMode('license');
          if (deviceMode.licenseKey) {
            setLicenseKey(formatLicenseKey(deviceMode.licenseKey));
          }
          setError(
            err.message || 'Could not verify your subscription. Check your connection and try again.',
          );
        }
      } else {
        setLoginMode('license');
        if (deviceMode.licenseKey) {
          setLicenseKey(formatLicenseKey(deviceMode.licenseKey));
        }
        if (deviceMode.reason === 'expired') {
          setError('Your subscription has expired. Enter a renewed license key to continue.');
        } else if (deviceMode.hasBiometricRegistration && deviceMode.reason && deviceMode.reason !== 'no_biometric' && deviceMode.reason !== 'no_device_key') {
          setBiometricUnavailableReason(deviceMode.reason);
        }
      }
      } catch (err) {
        if (cancelled) return;
        setLoginMode('license');
        setError(err.message || 'Something went wrong loading login. Refresh and try again.');
      } finally {
        if (!cancelled) {
          setLoginCheckDone(true);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const completeLogin = (authData) => {
    localStorage.setItem('rugby_ai_auth', JSON.stringify(authData));
    localStorage.removeItem('rugby_ai_license_key');
    saveDeviceSession(authData);
    onLoginSuccess(authData);
  };

  const verifyAndBuildAuth = async (cleanedKey) => {
    const result = await verifyLicenseKey({ license_key: cleanedKey });
    if (!result.data?.valid) {
      const failure = handleDeviceAuthFailure(result.data);
      const message = result.data?.error || 'Invalid license key';
      if (failure === 'pending') {
        throw new Error(message);
      }
      if (message.toLowerCase().includes('expired')) {
        throw new Error('Your subscription has expired. Enter a renewed license key to continue.');
      }
      throw new Error(message);
    }
    return {
      licenseKey: cleanedKey,
      expiresAt: result.data.expires_at,
      subscriptionType: result.data.subscription_type,
      email: result.data.email,
      authenticatedAt: Date.now(),
      deviceId: getDeviceId(),
    };
  };

  const verifyAndBuildAuthFromEmail = async (normalizedEmail, code) => {
    const result = await verifyEmailLoginCode({ email: normalizedEmail, code });
    if (!result.data?.valid) {
      const failure = handleDeviceAuthFailure(result.data);
      const message = result.data?.error || 'Invalid email or code';
      if (failure === 'pending') {
        throw new Error(message);
      }
      if (message.toLowerCase().includes('expired')) {
        throw new Error('Your subscription has expired. Contact support to renew.');
      }
      throw new Error(message);
    }
    const rawKey = result.data.license_key || '';
    const cleanedKey = String(rawKey).replace(/\s/g, '').replace(/-/g, '').toUpperCase();
    if (!cleanedKey) {
      throw new Error('Sign-in succeeded but license key was missing. Contact support.');
    }
    return {
      licenseKey: cleanedKey,
      expiresAt: result.data.expires_at,
      subscriptionType: result.data.subscription_type,
      email: result.data.email || normalizedEmail,
      authenticatedAt: Date.now(),
      deviceId: getDeviceId(),
    };
  };

  const finishLoginFlow = async (authData) => {
    onLicenseKeyLoginSuccess(authData.licenseKey);
    const availability = await getBiometricAvailability();
    if (availability.canUse && shouldPromptBiometricSetupAfterLogin(authData.licenseKey)) {
      setPendingAuth(authData);
      setLoginMode('biometric-setup');
      return;
    }
    if (getBiometricRegistration()) {
      saveDeviceSession(authData);
    }
    completeLogin(authData);
  };

  const handleEnableBiometric = async () => {
    if (!pendingAuth) return;
    setError('');
    setLoading(true);
    try {
      await registerBiometric({
        licenseKey: pendingAuth.licenseKey,
        email: pendingAuth.email,
      });
      saveDeviceSession(pendingAuth);
      setLoginMode('biometric');
      setDeviceSession(pendingAuth);
      completeLogin(pendingAuth);
    } catch (err) {
      setError(err.message || 'Could not enable biometric login on this device.');
    } finally {
      setLoading(false);
    }
  };

  const handleSkipBiometric = () => {
    if (!pendingAuth) return;
    dismissBiometricLoginSetup(pendingAuth.licenseKey);
    completeLogin(pendingAuth);
  };

  const handleBiometricLogin = async () => {
    setError('');
    setBiometricLoading(true);
    try {
      await authenticateWithBiometric();

      const sessionKey = deviceSession?.licenseKey;
      let cleanedKey = sessionKey
        ? String(sessionKey).replace(/\s/g, '').replace(/-/g, '').toUpperCase()
        : '';

      if (!cleanedKey) {
        const storedAuthRaw = localStorage.getItem('rugby_ai_auth');
        const storedKeyRaw = localStorage.getItem('rugby_ai_license_key');
        if (storedAuthRaw) {
          const storedAuth = JSON.parse(storedAuthRaw);
          cleanedKey = String(storedAuth?.licenseKey || '').replace(/\s/g, '').replace(/-/g, '').toUpperCase();
        }
        if (!cleanedKey && storedKeyRaw) {
          cleanedKey = String(storedKeyRaw).replace(/\s/g, '').replace(/-/g, '').toUpperCase();
        }
      }

      if (!cleanedKey) {
        setLoginMode('license');
        throw new Error('No saved license key on this device. Please enter your license key once.');
      }

      const authData = await verifyAndBuildAuth(cleanedKey);
      saveDeviceSession(authData);
      completeLogin(authData);
    } catch (err) {
      if (err.message?.toLowerCase().includes('expired')) {
        setLoginMode('license');
        setLicenseKey(formatLicenseKey(deviceSession?.licenseKey || ''));
      }
      setError(err.message || 'Biometric login failed. Use your license key instead.');
    } finally {
      setBiometricLoading(false);
    }
  };

  // Play full video once, then loop only the last 10 seconds (cutting off 2 seconds of black screen)
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const LOOP_DURATION = 10; // seconds of content to loop
    const BLACK_SCREEN_DURATION = 2; // seconds of black screen to skip at the end
    let loopStart = 0;
    // eslint-disable-next-line no-unused-vars
    let loopEnd = 0;

    const computeLoopBounds = () => {
      if (video.duration && video.duration > LOOP_DURATION + BLACK_SCREEN_DURATION) {
        // Start 12 seconds before end (10 seconds content + 2 seconds buffer for black screen)
        loopStart = video.duration - LOOP_DURATION - BLACK_SCREEN_DURATION;
        // End 2 seconds before actual end to avoid black screen
        loopEnd = video.duration - BLACK_SCREEN_DURATION;
      } else {
        loopStart = 0;
        loopEnd = video.duration || 0;
      }
    };

    const handleLoadedMetadata = () => {
      const source = video.currentSrc || video.src;
      console.log('✅ [Storage] Login video metadata loaded from:', source);
      computeLoopBounds();
    };

    const handleCanPlay = () => {
      const videoEl = videoRef.current;
      if (!videoEl) return;
      if (!document.hidden) {
        videoEl.play().catch(() => {});
      }
    };

    const handleError = (e) => {
      const videoEl = videoRef.current;
      if (!videoEl) return;
      const source = videoEl.currentSrc || videoEl.src || '';
      console.error('❌ [Storage] Login video failed to load from:', source);
      console.error('Error details:', e);
      if (source.includes('login_video.mp4') && !source.includes('firebasestorage')) return;
      try {
        videoEl.src = '/login_video.mp4';
        videoEl.load();
      } catch {}
    };

    // After the FIRST full play, jump back to loopStart and from then on we stay in that 10s loop
    const handleEnded = () => {
      computeLoopBounds();
      video.currentTime = loopStart;
      video.play().catch(() => {});
    };

    const handleTimeUpdate = () => {
      if (!video.duration) return;

      // Stop 2 seconds before the actual end to avoid black screen
      const endThreshold = video.duration - BLACK_SCREEN_DURATION;

      // Once we're in the looping phase, keep bouncing between loopStart and loopEnd
      if (video.currentTime >= endThreshold) {
        video.currentTime = loopStart;
        if (video.paused) {
          video.play().catch(() => {});
        }
      }
    };

    // Make sure the browser doesn't restart from 0 automatically
    video.loop = false;

    video.addEventListener('loadedmetadata', handleLoadedMetadata);
    video.addEventListener('canplay', handleCanPlay);
    video.addEventListener('ended', handleEnded);
    video.addEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('error', handleError);

    if (video.readyState >= 2) {
      handleCanPlay();
    }
    video.play().catch(() => {});

    return () => {
      video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      video.removeEventListener('canplay', handleCanPlay);
      video.removeEventListener('ended', handleEnded);
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('error', handleError);
    };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (credentialPanel === 'email') {
      if (emailStep === 'email') {
        await handleSendLoginCode(e);
      } else {
        await handleEmailLogin(e);
      }
      return;
    }

    setError('');
    setLoading(true);

    try {
      const cleanedKey = licenseKey.replace(/\s/g, '').replace(/-/g, '').toUpperCase();

      if (!cleanedKey) {
        setError('Please enter your license key');
        setLoading(false);
        return;
      }

      const authData = await verifyAndBuildAuth(cleanedKey);
      showToast('License verified. Welcome in.', 'success');
      await finishLoginFlow(authData);
    } catch (err) {
      const raw = err.message || 'Failed to verify license key. Please try again.';
      setError(raw);
      showToast(raw, raw.toLowerCase().includes('expired') ? 'error' : 'warning');
    } finally {
      setLoading(false);
    }
  };

  const handleSendLoginCode = async (e) => {
    if (e?.preventDefault) e.preventDefault();
    setError('');
    setCodeSentMessage('');
    setLoading(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      if (!normalizedEmail || !normalizedEmail.includes('@')) {
        const message = 'Enter the email address used when you bought your license.';
        setError(message);
        showToast(message, 'warning');
        return;
      }
      const result = await requestEmailLoginCode({ email: normalizedEmail });
      const status = result.data?.status;
      const message = result.data?.error || result.data?.message || '';

      if (status === 'sent' || (result.data?.success && !status)) {
        const sentMessage = result.data?.message || `We sent a 6-digit code to ${normalizedEmail}.`;
        setCodeSentMessage(sentMessage);
        showToast(sentMessage, 'success');
        setEmailStep('code');
        setLoginCode('');
        return;
      }

      if (status === 'not_found') {
        showToast(message || 'No license found for this email.', 'warning');
        return;
      }

      if (status === 'expired') {
        const expiredMessage = 'Your license key has expired.';
        setError(expiredMessage);
        showToast(message || expiredMessage, 'error');
        return;
      }

      const fallback = message || 'Could not send sign-in code. Try again.';
      setError(fallback);
      showToast(fallback, 'error');
    } catch (err) {
      const fallback = err.message || 'Could not send sign-in code. Try again.';
      setError(fallback);
      showToast(fallback, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleEmailLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      const code = loginCode.replace(/\D/g, '');
      if (!normalizedEmail) {
        setError('Enter your subscription email');
        return;
      }
      if (code.length !== 6) {
        setError('Enter the 6-digit code from your email');
        return;
      }
      const authData = await verifyAndBuildAuthFromEmail(normalizedEmail, code);
      showToast('Welcome back. Your license is still valid.', 'success');
      await finishLoginFlow(authData);
    } catch (err) {
      const raw = err.message || 'Sign-in failed. Check your code and try again.';
      const lower = raw.toLowerCase();
      if (lower.includes('expired')) {
        setError('Your license key has expired.');
        showToast('Your license key has expired.', 'error');
      } else if (lower.includes('no license found')) {
        showToast(raw, 'warning');
      } else {
        setError(raw);
        showToast(raw, 'error');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleOtpChange = (index, rawValue) => {
    const digits = String(rawValue || '').replace(/\D/g, '');
    if (!digits) {
      const next = loginCode.split('');
      next[index] = '';
      setLoginCode(next.join('').slice(0, 6));
      return;
    }
    const next = loginCode.split('');
    while (next.length < 6) next.push('');
    if (digits.length > 1) {
      digits.slice(0, 6).split('').forEach((digit, offset) => {
        next[offset] = digit;
      });
      setLoginCode(next.join('').slice(0, 6));
      const focusAt = Math.min(digits.length, 5);
      otpRefs.current[focusAt]?.focus();
      return;
    }
    next[index] = digits[0];
    const joined = next.join('').slice(0, 6);
    setLoginCode(joined);
    if (index < 5) otpRefs.current[index + 1]?.focus();
  };

  const handleOtpKeyDown = (index, event) => {
    if (event.key === 'Backspace' && !loginCode[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
  };

  const switchCredentialPanel = (panel) => {
    setError('');
    setCodeSentMessage('');
    setCredentialPanel(panel);
    if (panel === 'license') {
      setEmailStep('email');
      setLoginCode('');
    }
  };

  const renderLicensePanel = () => (
    <Box sx={{ pt: 0.5, width: '100%', minWidth: 0, maxWidth: '100%' }}>
      <TextField
        fullWidth
        label="License Key"
        value={licenseKey}
        onChange={handleKeyChange}
        placeholder="XXXX-XXXX-XXXX-XXXX"
        disabled={loading}
        variant="outlined"
        autoComplete="off"
        InputLabelProps={{ shrink: true }}
        sx={{
          ...credentialInputSx,
          '& .MuiOutlinedInput-input': {
            textAlign: 'center',
            letterSpacing: { xs: '0.12em', sm: '0.22em', md: '0.3em' },
            fontWeight: 700,
            textTransform: 'uppercase',
            fontSize: { xs: '0.82rem', sm: '0.9rem', md: '0.95rem' },
            fontFamily: 'monospace',
            px: { xs: 0.5, sm: 1 },
          },
        }}
        inputProps={{
          maxLength: 19,
          autoCapitalize: 'none',
          autoCorrect: 'off',
          spellCheck: 'false',
          style: { color: '#f9fafb' },
        }}
      />
    </Box>
  );

  const renderEmailPanel = () => (
    <Box sx={{ pt: 0.5, width: '100%', minWidth: 0, maxWidth: '100%' }}>
      {emailStep === 'email' ? (
        <TextField
          fullWidth
          label="Subscription email"
          type="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            setError('');
          }}
          placeholder="you@example.com"
          disabled={loading}
          variant="outlined"
          autoComplete="email"
          InputLabelProps={{ shrink: true }}
          sx={credentialInputSx}
          inputProps={{ style: { color: '#f9fafb' } }}
        />
      ) : (
        <>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 1,
              mb: 1.5,
              color: '#94a3b8',
              fontSize: '0.82rem',
              textAlign: 'center',
            }}
          >
            <CheckCircleOutlineIcon sx={{ fontSize: 18, color: '#86efac' }} />
            Code sent to {maskEmail(email)}
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'center', gap: { xs: 0.7, sm: 1 }, mb: 1.5 }}>
            {Array.from({ length: 6 }).map((_, index) => (
              <Box
                key={`otp-${index}`}
                component="input"
                ref={(node) => {
                  otpRefs.current[index] = node;
                }}
                value={loginCode[index] || ''}
                onChange={(event) => handleOtpChange(index, event.target.value)}
                onKeyDown={(event) => handleOtpKeyDown(index, event)}
                onPaste={(event) => {
                  event.preventDefault();
                  handleOtpChange(0, event.clipboardData.getData('text'));
                }}
                disabled={loading}
                inputMode="numeric"
                maxLength={1}
                aria-label={`Digit ${index + 1}`}
                sx={{
                  width: { xs: 40, sm: 46 },
                  height: { xs: 52, sm: 56 },
                  textAlign: 'center',
                  fontSize: '1.25rem',
                  fontWeight: 800,
                  fontFamily: 'monospace',
                  color: '#f9fafb',
                  borderRadius: 2,
                  border: '1.5px solid rgba(75,85,99,0.6)',
                  background: 'rgba(2,6,23,0.9)',
                  outline: 'none',
                  transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
                  '&:focus': {
                    borderColor: '#22c55e',
                    boxShadow: '0 0 0 3px rgba(34,197,94,0.16)',
                  },
                }}
              />
            ))}
          </Box>
          <Button
            fullWidth
            variant="text"
            disabled={loading}
            onClick={() => {
              setEmailStep('email');
              setLoginCode('');
              setCodeSentMessage('');
            }}
            sx={{ mt: 0.5, mb: 1, color: '#94a3b8', textTransform: 'none', fontSize: '0.8rem' }}
          >
            Use a different email
          </Button>
        </>
      )}
    </Box>
  );

  if (!loginCheckDone) {
    return (
      <Box
        sx={{
          position: 'fixed',
          inset: 0,
          zIndex: 40,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          height: '100dvh',
          minHeight: '100dvh',
          backgroundColor: '#0e1117',
        }}
      >
        <RugbyBallLoader size={120} color="#10b981" label="Loading..." />
      </Box>
    );
  }

  return (
    <Box
      sx={{
        minHeight: '100dvh',
        width: '100%',
        maxWidth: '100vw',
        display: 'flex',
        alignItems: { xs: 'flex-start', sm: 'center' },
        justifyContent: 'center',
        p: { xs: 1.5, sm: 3 },
        py: { xs: 2, sm: 3 },
        position: 'relative',
        overflowY: 'auto',
        overflowX: 'clip',
        WebkitOverflowScrolling: 'touch',
        boxSizing: 'border-box',
        backgroundColor: '#0e1117',
        // Keep Kick Off reachable above the mobile keyboard.
        pb: { xs: 'max(24px, env(safe-area-inset-bottom, 0px))', sm: 3 },
      }}
    >
      {/* Video Background */}
      <Box
        component="video"
        ref={videoRef}
        muted
        playsInline
        autoPlay
        preload="auto"
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          zIndex: 0,
          pointerEvents: 'none',
        }}
      >
        <source src={MEDIA_URLS.loginVideo} type="video/mp4" />
      </Box>

      {/* Dark overlay for better readability */}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          backgroundColor: 'rgba(2,6,23,0.4)',
          zIndex: 1,
          pointerEvents: 'none',
        }}
      />

      {/* Enhanced LOGIN CARD with glassmorphism */}
      <Zoom in timeout={600}>
      <Paper
          elevation={0}
        sx={{
          position: 'relative',
            zIndex: 2,
            width: '100%',
            maxWidth: { xs: 'min(500px, calc(100vw - 24px))', sm: 500 },
            minWidth: 0,
            flexShrink: 0,
            boxSizing: 'border-box',
          borderRadius: { xs: 3, sm: 4 },
            px: { xs: 2.5, sm: 5.5 },
            py: { xs: 3.5, sm: 6 },
          background:
              'linear-gradient(145deg, rgba(15,23,42,0.99), rgba(2,6,23,1))',
            border: '1.5px solid rgba(148,163,184,0.5)',
          boxShadow:
              '0 30px 60px rgba(0,0,0,0.95), ' +
              '0 0 0 1px rgba(30,41,59,0.8), ' +
              'inset 0 1px 1px rgba(255,255,255,0.1), ' +
              'inset 0 -1px 1px rgba(0,0,0,0.3)',
            overflow: 'visible',
            my: { xs: 'auto', sm: 0 },
        }}
      >
          {/* Premium static top accent bar */}
        <Box
          sx={{
            position: 'absolute',
              inset: '0 22% auto 22%',
            height: 4,
            borderRadius: '0 0 999px 999px',
            background:
              'linear-gradient(90deg, #22c55e 0%, #eab308 50%, #22c55e 100%)',
              boxShadow: '0 2px 12px rgba(34,197,94,0.8), 0 0 24px rgba(34,197,94,0.4)',
          }}
        />

          {/* Premium header */}
          <Fade in timeout={800}>
            <Box sx={{ textAlign: 'center', mb: { xs: 3.5, sm: 5 }, position: 'relative', zIndex: 1 }}>
          <Typography
                variant="h3"
            sx={{
              fontWeight: 800,
              letterSpacing: { xs: '0.04em', sm: '0.08em' },
              textTransform: 'uppercase',
                  fontSize: { xs: '1.35rem', sm: '1.875rem', md: '2.125rem' },
                  background: 'linear-gradient(135deg, #f9fafb 0%, #e5e7eb 50%, #86efac 100%)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  lineHeight: 1.2,
                  mb: 1.5,
            }}
          >
                Rugby AI Predictor
          </Typography>
          <Typography
                variant="body1"
            sx={{
                  color: '#d1d5db',
                  fontSize: { xs: '0.9375rem', sm: '0.9375rem' },
                  fontWeight: 400,
                  letterSpacing: '0.025em',
                  lineHeight: 1.6,
            }}
          >
                {loginMode === 'loading'
                  ? 'Checking your device profile…'
                  : loginMode === 'biometric' || loginMode === 'biometric-setup'
                  ? `Unlock with ${getBiometricLoginTitle()} on this device`
                  : credentialPanel === 'email'
                  ? emailStep === 'code'
                    ? 'Enter the 6-digit code we emailed you'
                    : 'Sign in with your subscription email'
                  : 'Enter your license key to unlock match predictions'}
          </Typography>
        </Box>
          </Fade>

        <form onSubmit={handleSubmit}>
            {loginCheckDone && error && (
              <Alert severity="error" icon={false} sx={{ ...loginErrorAlertSx, position: 'relative', zIndex: 2 }}>
                {error}
              </Alert>
            )}

            {loginCheckDone && loginMode === 'biometric-setup' && (
              <Fade in timeout={500}>
                <Box sx={{ position: 'relative', zIndex: 1, textAlign: 'center' }}>
                  <Typography sx={{ color: '#e5e7eb', mb: 1.5, fontWeight: 600 }}>
                    Enable {getBiometricLoginTitle()}?
                  </Typography>
                  <Typography sx={{ color: '#9ca3af', mb: 2, fontSize: '0.875rem', lineHeight: 1.6 }}>
                    Use {getBiometricLoginTitle()} on this device for faster sign-in.
                    Your license key still works on any other phone or computer.
                  </Typography>
                  <Alert severity="info" sx={{ mb: 2, textAlign: 'left', bgcolor: 'rgba(59,130,246,0.12)' }}>
                    {getBiometricSetupHint()}
                  </Alert>
                  <Button
                    fullWidth
                    variant="contained"
                    disabled={loading}
                    onClick={handleEnableBiometric}
                    startIcon={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
                        <FaceRetouchingNaturalIcon sx={{ fontSize: 18 }} />
                        <FingerprintIcon sx={{ fontSize: 18 }} />
                      </Box>
                    }
                    sx={{
                      mb: 1.5,
                      py: 1.6,
                      borderRadius: 3,
                      background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
                      fontWeight: 800,
                    }}
                  >
                    Enable {getBiometricLoginTitle()}
                  </Button>
                  <Button
                    fullWidth
                    variant="text"
                    disabled={loading}
                    onClick={handleSkipBiometric}
                    sx={{ color: '#9ca3af' }}
                  >
                    Skip — set up later in Profile
                  </Button>
                </Box>
              </Fade>
            )}

            {loginCheckDone && loginMode === 'biometric' && (
              <Fade in timeout={500}>
                <Box sx={{ position: 'relative', zIndex: 1, textAlign: 'center' }}>
                  <Button
                    fullWidth
                    variant="contained"
                    disabled={biometricLoading}
                    onClick={handleBiometricLogin}
                    startIcon={
                      biometricLoading ? (
                        <CircularProgress size={20} sx={{ color: '#ffffff' }} />
                      ) : (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
                          <FaceRetouchingNaturalIcon sx={{ fontSize: 20 }} />
                          <FingerprintIcon sx={{ fontSize: 20 }} />
                        </Box>
                      )
                    }
                    sx={{
                      py: 2,
                      borderRadius: 3,
                      background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
                      fontWeight: 800,
                      fontSize: { xs: '0.95rem', sm: '1.05rem' },
                      letterSpacing: '0.08em',
                      boxShadow: '0 4px 0 rgba(16, 185, 129, 0.8), 0 8px 16px rgba(0, 0, 0, 0.4)',
                    }}
                  >
                    {biometricLoading ? 'Verifying…' : `Unlock with ${getBiometricLoginTitle()}`}
                  </Button>
                  <Button
                    fullWidth
                    variant="text"
                    onClick={() => {
                      setError('');
                      setLoginMode('license');
                    }}
                    sx={{ mt: 2, color: '#6b7280', fontSize: '0.8rem', textTransform: 'none' }}
                  >
                    Use license key instead
                  </Button>
                </Box>
              </Fade>
            )}

            {loginCheckDone && loginMode === 'license' && (
              <>
            {deviceCheckMessage && credentialPanel === 'license' && (
              <Alert severity="info" sx={{ mb: 2, fontSize: '0.82rem', textAlign: 'left' }}>
                {deviceCheckMessage}
              </Alert>
            )}
            {biometricUnavailableReason && credentialPanel === 'license' && (
              <Alert severity="info" sx={{ mb: 2, fontSize: '0.82rem', textAlign: 'left' }}>
                {biometricUnavailableReason}
              </Alert>
            )}
            {codeSentMessage && credentialPanel === 'email' && emailStep === 'email' && (
              <Alert severity="success" sx={{ mb: 2, fontSize: '0.82rem', textAlign: 'left' }}>
                {codeSentMessage}
              </Alert>
            )}

            <Box
              sx={{
                width: '100%',
                position: 'relative',
                zIndex: 1,
                pt: 0.5,
                pb: 0.5,
                overflow: 'hidden',
              }}
            >
              {credentialPanel === 'email' ? renderEmailPanel() : renderLicensePanel()}
            </Box>

            <Fade in timeout={1200}>
              <Box>
          <Button
            type="submit"
            fullWidth
            variant="contained"
            disabled={loading}
            sx={{
              py: { xs: 1.75, sm: 2 },
              borderRadius: 3,
              background: loading
                ? '#1f2937'
                : 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
              color: '#ffffff',
              fontWeight: 800,
              fontSize: { xs: '0.95rem', sm: '1.05rem' },
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
              border: loading
                ? '2px solid #374151'
                : '2px solid #22c55e',
              boxShadow: loading
                      ? 'none'
                : '0 4px 0 rgba(16, 185, 129, 0.8), 0 8px 16px rgba(0, 0, 0, 0.4)',
              transition: 'all 0.2s ease',
              position: 'relative',
              overflow: 'hidden',
              '&::before': {
                content: '""',
                position: 'absolute',
                top: 0,
                left: '-100%',
                width: '100%',
                height: '100%',
                background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent)',
                transition: 'left 0.5s ease',
              },
                  '&:hover:not(:disabled)': {
                background: 'linear-gradient(135deg, #4ade80 0%, #22c55e 100%)',
                border: '2px solid #4ade80',
                boxShadow: '0 6px 0 rgba(16, 185, 129, 1), 0 12px 24px rgba(0, 0, 0, 0.5)',
                transform: 'translateY(-2px)',
                '&::before': {
                  left: '100%',
                },
                  },
                  '&:active:not(:disabled)': {
                transform: 'translateY(2px)',
                boxShadow: '0 2px 0 rgba(16, 185, 129, 0.8), 0 4px 8px rgba(0, 0, 0, 0.3)',
              },
              '&:disabled': {
                backgroundColor: '#1f2937',
                color: '#6b7280',
                border: '2px solid #374151',
                boxShadow: 'none',
                    cursor: 'not-allowed',
              },
            }}
          >
            {loading ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1.5 }}>
                <CircularProgress size={20} thickness={4.5} sx={{ color: '#ffffff' }} />
                <span>
                  {credentialPanel === 'email'
                    ? emailStep === 'email' ? 'Sending code…' : 'Verifying…'
                    : 'Verifying…'}
                </span>
              </Box>
            ) : (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1.25 }}>
                    <span>
                      {credentialPanel === 'email'
                        ? emailStep === 'email' ? 'Send sign-in code' : 'Sign in'
                        : 'Kick Off'}
                    </span>
                <Box
                  component="span"
                  sx={{
                    fontSize: '1.15em',
                    display: 'inline-flex',
                    alignItems: 'center',
                    lineHeight: 1,
                  }}
                >
                  →
                    </Box>
                  </Box>
            )}
          </Button>
              </Box>
            </Fade>

            <Button
              fullWidth
              variant="text"
              disabled={loading}
              onClick={() => switchCredentialPanel(credentialPanel === 'license' ? 'email' : 'license')}
              sx={{
                mt: 1.5,
                color: '#86efac',
                fontSize: '0.85rem',
                textTransform: 'none',
                fontWeight: 600,
              }}
            >
              {credentialPanel === 'license'
                ? "Don't have your key? Sign in with email"
                : 'Use license key instead'}
            </Button>

            {credentialPanel === 'email' && emailStep === 'code' && (
              <Button
                fullWidth
                variant="text"
                disabled={loading}
                onClick={handleSendLoginCode}
                sx={{ mt: 0.5, color: '#94a3b8', textTransform: 'none', fontSize: '0.8rem' }}
              >
                Resend code
              </Button>
            )}

            {getBiometricRegistration() && canReturnToBiometric && (
              <Button
                fullWidth
                variant="text"
                onClick={async () => {
                  setError('');
                  const deviceMode = await getDeviceLoginMode();
                  if (deviceMode.mode === 'biometric') {
                    setDeviceSession({
                      licenseKey: deviceMode.licenseKey,
                      email: deviceMode.email,
                      expiresAt: deviceMode.expiresAt,
                      subscriptionType: deviceMode.subscriptionType,
                    });
                    setLoginMode('biometric');
                  }
                }}
                sx={{ mt: 1.5, color: '#86efac', fontSize: '0.85rem', textTransform: 'none' }}
              >
                Back to {getBiometricLoginTitle()}
              </Button>
            )}
              </>
            )}
        </form>

          {loginMode === 'license' && credentialPanel === 'license' && (
          <Fade in timeout={1400}>
            <Box sx={{ mt: 4, textAlign: 'center', position: 'relative', zIndex: 1 }}>
          <Typography
            variant="caption"
            sx={{
              color: '#9ca3af',
                  fontSize: { xs: '0.75rem', sm: '0.8rem' },
                  lineHeight: 1.6,
                  display: 'block',
            }}
          >
                No license yet?{' '}
                <Box
                  component="span"
                  onClick={openPurchase}
                  sx={{
                    color: '#86efac',
                    fontWeight: 600,
                    cursor: 'pointer',
                    textDecoration: 'underline',
                    textDecorationColor: 'rgba(134,239,172,0.5)',
                    '&:hover': {
                      color: '#bbf7d0',
                      textDecorationColor: '#bbf7d0',
                    },
                  }}
                >
                  Purchase a subscription
                </Box>
                {' '}and your key will be emailed to you after payment.
          </Typography>
          <Typography
            variant="caption"
            sx={{
              color: '#64748b',
              fontSize: { xs: '0.68rem', sm: '0.72rem' },
              lineHeight: 1.55,
              display: 'block',
              mt: 1.5,
              maxWidth: 420,
              mx: 'auto',
            }}
          >
            {DEVICE_BINDING_NOTICE}
          </Typography>
        </Box>
          </Fade>
            )}
      </Paper>
      </Zoom>
      <Snackbar
        open={toast.open}
        autoHideDuration={5200}
        onClose={closeToast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        TransitionComponent={SlideUp}
        sx={{ mb: { xs: 2, sm: 3 } }}
      >
        <Alert
          onClose={closeToast}
          severity={toast.severity}
          variant="filled"
          action={
            (toast.severity === 'warning' || toast.message.toLowerCase().includes('expired')) ? (
              <Button color="inherit" size="small" onClick={openPurchase} sx={{ fontWeight: 800 }}>
                Buy license
              </Button>
            ) : null
          }
          sx={{
            minWidth: { xs: 280, sm: 360 },
            borderRadius: 2.5,
            fontWeight: 600,
            backgroundColor:
              toast.severity === 'success'
                ? '#14532d'
                : toast.severity === 'warning'
                  ? '#854d0e'
                  : toast.severity === 'error'
                    ? '#7f1d1d'
                    : '#1e3a2a',
          }}
        >
          {toast.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default LoginWidget;
