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
} from '@mui/material';
import { verifyLicenseKey } from '../firebase';
import { MEDIA_URLS } from '../utils/storageUrls';

const LoginWidget = ({ onLoginSuccess, onShowSubscription }) => {
  const [licenseKey, setLicenseKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const videoRef = useRef(null);

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

  // Pre-fill license key from localStorage if available (after logout)
  useEffect(() => {
    const storedKey = localStorage.getItem('rugby_ai_license_key');
    if (storedKey) {
      // Format the stored key and pre-fill it
      const formatted = formatLicenseKey(storedKey);
      setLicenseKey(formatted);
    }
  }, []);

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
      // Try to autoplay when metadata is ready
      video.play().catch(() => {
        // Autoplay might be blocked, that's fine
      });
    };

    const handleCanPlay = () => {
      const video = videoRef.current;
      if (video) {
        const source = video.currentSrc || video.src;
        if (source.includes('firebasestorage.googleapis.com')) {
          console.log('✅ [Storage] Login video loaded successfully from Firebase Storage');
        } else {
          console.log('📁 [Local] Login video loaded from local file');
        }
      }
    };

    const handleError = (e) => {
      const video = videoRef.current;
      if (video) {
        const source = video.currentSrc || video.src;
        console.error('❌ [Storage] Login video failed to load from:', source);
        console.error('Error details:', e);
      }
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
    setError('');
    setLoading(true);

    try {
      const cleanedKey = licenseKey.replace(/\s/g, '').replace(/-/g, '').toUpperCase();

      if (!cleanedKey) {
        setError('Please enter your license key');
        setLoading(false);
        return;
      }

      const result = await verifyLicenseKey({ license_key: cleanedKey });

      if (result.data.valid) {
        const authData = {
          licenseKey: cleanedKey,
          expiresAt: result.data.expires_at,
          subscriptionType: result.data.subscription_type,
          email: result.data.email,
          authenticatedAt: Date.now(),
        };
        localStorage.setItem('rugby_ai_auth', JSON.stringify(authData));
        // Clear the separate license key storage since we now have full auth data
        localStorage.removeItem('rugby_ai_license_key');
        onLoginSuccess(authData);
      } else {
        setError(result.data.error || 'Invalid license key');
      }
    } catch (err) {
      console.error('Login error:', err);
      setError('Failed to verify license key. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: { xs: 2, sm: 3 },
        position: 'relative',
        overflow: 'hidden',
        backgroundColor: '#020617',
      }}
    >
      {/* Video Background */}
      <Box
        component="video"
        ref={videoRef}
        autoPlay
        muted
        playsInline
        preload="auto"
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          zIndex: 0,
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
            maxWidth: 500,
          width: '100%',
          borderRadius: 4,
            px: { xs: 4, sm: 5.5 },
            py: { xs: 4.5, sm: 6 },
          background:
              'linear-gradient(145deg, rgba(15,23,42,0.99), rgba(2,6,23,1))',
            border: '1.5px solid rgba(148,163,184,0.5)',
          boxShadow:
              '0 30px 60px rgba(0,0,0,0.95), ' +
              '0 0 0 1px rgba(30,41,59,0.8), ' +
              'inset 0 1px 1px rgba(255,255,255,0.1), ' +
              'inset 0 -1px 1px rgba(0,0,0,0.3)',
            overflow: 'hidden',
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
            <Box sx={{ textAlign: 'center', mb: 5, position: 'relative', zIndex: 1 }}>
          <Typography
                variant="h3"
            sx={{
              fontWeight: 800,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
                  fontSize: { xs: '1.5rem', sm: '1.875rem', md: '2.125rem' },
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
                  fontSize: { xs: '0.875rem', sm: '0.9375rem' },
                  fontWeight: 400,
                  letterSpacing: '0.025em',
                  lineHeight: 1.6,
            }}
          >
                Enter your license key to unlock match predictions
          </Typography>
        </Box>
          </Fade>

        <form onSubmit={handleSubmit}>
            <Fade in timeout={1000}>
              <Box sx={{ position: 'relative', zIndex: 1 }}>
          <TextField
            fullWidth
            label="License Key"
            value={licenseKey}
                  onChange={handleKeyChange}
            placeholder="XXXX-XXXX-XXXX-XXXX"
            disabled={loading}
            variant="outlined"
                  autoComplete="off"
            sx={{
                    mb: 2.5,
              '& .MuiOutlinedInput-root': {
                      backgroundColor: 'rgba(2,6,23,0.9)',
                color: '#f9fafb',
                      borderRadius: 2.5,
                      px: 2.5,
                      py: 0.5,
                      transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                      border: '1.5px solid transparent',
                      '& fieldset': {
                        borderColor: 'rgba(75,85,99,0.6)',
                        borderWidth: '1.5px',
                      },
                      '&:hover': {
                        backgroundColor: 'rgba(2,6,23,0.95)',
                '& fieldset': {
                          borderColor: 'rgba(34,197,94,0.7)',
                        },
                },
                      '&.Mui-focused': {
                        backgroundColor: 'rgba(2,6,23,1)',
                        boxShadow:
                          '0 0 0 2px rgba(34,197,94,0.25), ' +
                          '0 8px 16px rgba(34,197,94,0.3)',
                        '& fieldset': {
                  borderColor: '#22c55e',
                          borderWidth: '1.5px',
                },
                },
              },
              '& .MuiInputLabel-root': {
                color: '#9ca3af',
                      fontWeight: 500,
                '&.Mui-focused': {
                        color: '#86efac',
                        fontWeight: 600,
                },
              },
              input: {
                textAlign: 'center',
                      letterSpacing: '0.3em',
                      fontWeight: 700,
                textTransform: 'uppercase',
                      fontSize: { xs: '0.875rem', sm: '0.95rem' },
                      fontFamily: 'monospace',
              },
            }}
            inputProps={{
                    maxLength: 19,
              // Let users type lower/upper naturally (keyboard stays normal),
              // but we still format+uppercase the value in JS.
              autoCapitalize: 'none',
              autoCorrect: 'off',
              spellCheck: 'false',
              style: { color: '#f9fafb' },
            }}
          />
              </Box>
            </Fade>

          {error && (
              <Fade in>
            <Alert
              severity="error"
                  icon={false}
              sx={{
                    mb: 2.5,
                    borderRadius: 2,
                    backgroundColor: 'rgba(127,29,29,0.98)',
                color: '#fee2e2',
                    border: '1.5px solid rgba(248,113,113,0.7)',
                    fontSize: '0.875rem',
                textAlign: 'center',
                    fontWeight: 500,
                    boxShadow: '0 4px 12px rgba(127,29,29,0.5), inset 0 1px 0 rgba(255,255,255,0.1)',
              }}
            >
              {error}
            </Alert>
              </Fade>
          )}

            <Fade in timeout={1200}>
          <Button
            type="submit"
            fullWidth
            variant="contained"
            disabled={loading}
            sx={{
              py: 2,
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
                <span>Verifying...</span>
              </Box>
            ) : (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1.25 }}>
                    <span>Kick Off</span>
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
            </Fade>
        </form>

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
                  onClick={() => {
                    if (onShowSubscription) {
                      onShowSubscription();
                    } else {
                      // Fallback: try to open in new tab
                      window.open('/subscribe.html', '_blank', 'noopener,noreferrer');
                    }
                  }}
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
        </Box>
          </Fade>
      </Paper>
      </Zoom>
    </Box>
  );
};

export default LoginWidget;
