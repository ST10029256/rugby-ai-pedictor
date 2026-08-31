import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  IconButton,
  TextField,
  Typography,
} from '@mui/material';
import FaceRetouchingNaturalIcon from '@mui/icons-material/FaceRetouchingNatural';
import FingerprintIcon from '@mui/icons-material/Fingerprint';
import EditIcon from '@mui/icons-material/Edit';
import CheckIcon from '@mui/icons-material/Check';
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import {
  clearBiometricRegistration,
  getBiometricAvailability,
  getBiometricLabel,
  getBiometricLoginTitle,
  getBiometricRegistration,
  getBiometricSetupHint,
  registerBiometric,
  saveDeviceSession,
} from '../utils/biometricAuth';
import {
  AVATAR_EMOJI_OPTIONS,
  clearCustomAvatar,
  ensureProfileFromAuth,
  getAvatarEmoji,
  getAvatarImage,
  getDefaultDisplayName,
  getUserProfile,
  hasCustomAvatar,
  importAvatarFromFile,
  saveAvatarEmoji,
  saveUserProfile,
} from '../utils/userProfile';

const profileCardSx = {
  width: '100%',
  boxSizing: 'border-box',
  p: { xs: 2.5, sm: 3, md: 3.25 },
  borderRadius: '18px',
  background:
    'linear-gradient(145deg, rgba(15,23,42,0.94) 0%, rgba(30,41,59,0.88) 55%, rgba(16,185,129,0.08) 100%)',
  border: '1px solid rgba(16,185,129,0.22)',
  boxShadow: '0 16px 48px rgba(2,6,23,0.38)',
};

const sectionLabelSx = {
  color: '#64748b',
  fontSize: '0.68rem',
  fontWeight: 700,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  mb: 2,
  textAlign: 'center',
};

function useProfileState(authData, revision = 0) {
  const [profile, setProfile] = useState(() => getUserProfile());
  const [displayName, setDisplayName] = useState(() => getDefaultDisplayName(authData));

  useEffect(() => {
    if (!authData) return;
    const seeded = ensureProfileFromAuth(authData);
    setProfile(seeded);
    setDisplayName(getDefaultDisplayName(authData));
  }, [authData, revision]);

  return { profile, setProfile, displayName, setDisplayName };
}

function ProfileAvatar({ profile, size = 56, sx = {} }) {
  const image = getAvatarImage(profile);
  const emoji = getAvatarEmoji(profile);
  const shared = {
    width: size,
    height: size,
    bgcolor: 'rgba(16,185,129,0.18)',
    border: `${Math.max(2, Math.round(size / 28))}px solid rgba(16,185,129,0.4)`,
    boxShadow: '0 8px 24px rgba(16,185,129,0.18)',
    ...sx,
  };

  if (image) {
    return <Avatar src={image} alt="Profile" sx={shared} />;
  }

  return (
    <Avatar sx={{ ...shared, fontSize: size * 0.42 }}>
      {emoji}
    </Avatar>
  );
}

export function ProfileDrawerSummary({ authData, onOpenProfile, isActive, profileRevision = 0 }) {
  const { profile, displayName } = useProfileState(authData, profileRevision);

  return (
    <Box sx={{ width: '100%', flexShrink: 0 }}>
      <Box
        component="button"
        type="button"
        onClick={onOpenProfile}
        aria-label="Open profile"
        sx={{
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 0.75,
          py: 1.5,
          px: 1,
          borderRadius: '14px',
          cursor: 'pointer',
          font: 'inherit',
          background: isActive
            ? 'linear-gradient(135deg, rgba(16,185,129,0.18), rgba(16,185,129,0.08))'
            : 'rgba(255,255,255,0.03)',
          border: isActive ? '1px solid rgba(16,185,129,0.45)' : '1px solid rgba(255,255,255,0.08)',
          transition: 'all 0.2s ease',
          '&:hover': {
            background: 'rgba(16,185,129,0.12)',
            borderColor: 'rgba(16,185,129,0.35)',
          },
        }}
      >
        <ProfileAvatar profile={profile} size={56} />
        <Typography
          noWrap
          sx={{
            color: '#f8fafc',
            fontWeight: 700,
            fontSize: '0.95rem',
            maxWidth: '100%',
            textAlign: 'center',
          }}
        >
          {displayName || 'Rugby Fan'}
        </Typography>
      </Box>
    </Box>
  );
}

export function UserProfilePage({ authData, onProfileChange }) {
  const [revision, setRevision] = useState(0);
  const { profile, setProfile, displayName, setDisplayName } = useProfileState(authData, revision);
  const [editingName, setEditingName] = useState(false);
  const [biometricEnabled, setBiometricEnabled] = useState(() => Boolean(getBiometricRegistration()));
  const [bioMessage, setBioMessage] = useState('');
  const [bioError, setBioError] = useState('');
  const [avatarMessage, setAvatarMessage] = useState('');
  const [avatarError, setAvatarError] = useState('');
  const [bioLoading, setBioLoading] = useState(false);
  const [avatarLoading, setAvatarLoading] = useState(false);
  const [biometricCanUse, setBiometricCanUse] = useState(false);
  const [biometricUnavailableReason, setBiometricUnavailableReason] = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const availability = await getBiometricAvailability();
      if (cancelled) return;
      setBiometricCanUse(availability.canUse);
      setBiometricUnavailableReason(availability.reason || '');
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const notifyChange = useCallback(() => {
    setRevision((r) => r + 1);
    onProfileChange?.();
  }, [onProfileChange]);

  const refreshBiometric = useCallback(() => {
    setBiometricEnabled(Boolean(getBiometricRegistration()));
  }, []);

  const handleSaveName = () => {
    const trimmed = String(displayName || '').trim();
    if (!trimmed) {
      setBioError('Name cannot be empty.');
      return;
    }
    const next = saveUserProfile({ displayName: trimmed });
    setProfile(next);
    setEditingName(false);
    setBioError('');
    notifyChange();
  };

  const handleAvatarPick = (emoji) => {
    const next = saveAvatarEmoji(emoji);
    setProfile(next);
    setAvatarError('');
    setAvatarMessage('Emoji avatar selected.');
    notifyChange();
  };

  const handleAvatarImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleAvatarFileChange = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setAvatarLoading(true);
    setAvatarError('');
    setAvatarMessage('');
    try {
      const next = await importAvatarFromFile(file);
      setProfile(next);
      setAvatarMessage('Photo uploaded.');
      notifyChange();
    } catch (err) {
      setAvatarError(err.message || 'Could not upload photo.');
    } finally {
      setAvatarLoading(false);
    }
  };

  const handleRemoveCustomAvatar = () => {
    const next = clearCustomAvatar();
    setProfile(next);
    setAvatarError('');
    setAvatarMessage('Photo removed. Using emoji avatar.');
    notifyChange();
  };

  const handleEnableBiometric = async () => {
    if (!authData?.licenseKey) {
      setBioError('License key not found. Log out and sign in again.');
      return;
    }
    setBioLoading(true);
    setBioError('');
    setBioMessage('');
    try {
      clearBiometricRegistration();
      await registerBiometric({
        licenseKey: authData.licenseKey,
        email: authData.email,
      });
      saveDeviceSession({
        licenseKey: authData.licenseKey,
        expiresAt: authData.expiresAt,
        email: authData.email,
        subscriptionType: authData.subscriptionType,
      });
      refreshBiometric();
      setBioMessage(`${getBiometricLabel()} enabled on this device.`);
    } catch (err) {
      setBioError(err.message || 'Could not enable biometric login.');
    } finally {
      setBioLoading(false);
    }
  };

  const handleDisableBiometric = () => {
    clearBiometricRegistration();
    refreshBiometric();
    setBioMessage('Biometric login removed from this device.');
    setBioError('');
  };

  const avatarEmoji = getAvatarEmoji(profile);
  const usingCustomAvatar = hasCustomAvatar(profile);
  const bioTitle = getBiometricLoginTitle();

  return (
    <Box
      sx={{
        width: '100%',
        maxWidth: '100%',
        mx: 'auto',
        px: { xs: 2, sm: 3, md: 3, lg: 4 },
        py: { xs: 2.5, sm: 3.5, md: 4.5 },
        minHeight: { xs: 'calc(100svh - 180px)', sm: 'calc(100vh - 100px)' },
        boxSizing: 'border-box',
      }}
    >
      <Box sx={{ textAlign: 'center', mb: { xs: 3, md: 4 } }}>
        <Typography
          sx={{
            fontWeight: 800,
            fontSize: { xs: '1.75rem', sm: '2rem', md: '2.25rem' },
            letterSpacing: '-0.03em',
            mb: 0.75,
            background: 'linear-gradient(135deg, #fafafa 0%, #10b981 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          Profile
        </Typography>
        <Typography
          sx={{
            color: '#94a3b8',
            fontSize: { xs: '0.875rem', md: '0.95rem' },
            maxWidth: 420,
            mx: 'auto',
            lineHeight: 1.6,
          }}
        >
          Avatar, display name, and sign-in preferences
        </Typography>
        <Box
          sx={{
            width: 72,
            height: 2,
            mx: 'auto',
            mt: 2,
            borderRadius: 2,
            background: 'linear-gradient(90deg, transparent 0%, #10b981 50%, transparent 100%)',
            opacity: 0.75,
          }}
        />
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
          gap: { xs: 2.5, md: 3 },
          alignItems: 'stretch',
          width: '100%',
        }}
      >
        <Box sx={{ ...profileCardSx, gridColumn: '1 / -1' }}>
          <Typography sx={sectionLabelSx}>Avatar</Typography>

          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>
            <Box sx={{ position: 'relative', mb: 2.5 }}>
              <ProfileAvatar profile={profile} size={112} sx={{ width: 112, height: 112 }} />
              <IconButton
                onClick={handleAvatarImportClick}
                disabled={avatarLoading}
                aria-label="Upload profile photo"
                sx={{
                  position: 'absolute',
                  right: -4,
                  bottom: -4,
                  bgcolor: '#10b981',
                  color: '#0f172a',
                  border: '2px solid rgba(15,23,42,0.9)',
                  width: 38,
                  height: 38,
                  '&:hover': { bgcolor: '#34d399' },
                }}
              >
                <PhotoCameraIcon sx={{ fontSize: 20 }} />
              </IconButton>
            </Box>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              hidden
              onChange={handleAvatarFileChange}
            />

            <Box
              sx={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 1,
                justifyContent: 'center',
                mb: 2,
              }}
            >
              <Button
                variant="outlined"
                disabled={avatarLoading}
                onClick={handleAvatarImportClick}
                startIcon={<PhotoCameraIcon />}
                sx={{
                  textTransform: 'none',
                  borderColor: 'rgba(16,185,129,0.45)',
                  color: '#bbf7d0',
                  px: 2.5,
                }}
              >
                {avatarLoading ? 'Uploading…' : 'Import photo'}
              </Button>
              {usingCustomAvatar && (
                <Button
                  variant="text"
                  disabled={avatarLoading}
                  onClick={handleRemoveCustomAvatar}
                  startIcon={<DeleteOutlineIcon />}
                  sx={{ textTransform: 'none', color: '#94a3b8' }}
                >
                  Remove photo
                </Button>
              )}
            </Box>

            {avatarMessage && (
              <Alert severity="success" sx={{ mb: 1.5, width: '100%', maxWidth: { xs: '100%', sm: 480 } }}>
                {avatarMessage}
              </Alert>
            )}
            {avatarError && (
              <Alert severity="error" sx={{ mb: 1.5, width: '100%', maxWidth: { xs: '100%', sm: 480 } }}>
                {avatarError}
              </Alert>
            )}

            <Typography sx={{ color: '#64748b', fontSize: '0.8rem', mb: 1.5, textAlign: 'center' }}>
              Or choose an emoji
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'center' }}>
              {AVATAR_EMOJI_OPTIONS.map((emoji) => {
                const selected = !usingCustomAvatar && avatarEmoji === emoji;
                return (
                  <IconButton
                    key={emoji}
                    onClick={() => handleAvatarPick(emoji)}
                    sx={{
                      width: 46,
                      height: 46,
                      fontSize: '1.4rem',
                      borderRadius: '12px',
                      border: selected
                        ? '2px solid rgba(16,185,129,0.65)'
                        : '1px solid rgba(255,255,255,0.1)',
                      bgcolor: selected ? 'rgba(16,185,129,0.16)' : 'rgba(255,255,255,0.03)',
                      transition: 'all 0.15s ease',
                      '&:hover': {
                        bgcolor: 'rgba(16,185,129,0.12)',
                        transform: 'translateY(-1px)',
                      },
                    }}
                    aria-label={`Avatar ${emoji}`}
                  >
                    {emoji}
                  </IconButton>
                );
              })}
            </Box>
          </Box>
        </Box>

        <Box
          sx={{
            ...profileCardSx,
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            minHeight: { md: '100%' },
          }}
        >
          <Typography sx={{ ...sectionLabelSx, mb: 0 }}>Display name</Typography>
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              alignItems: 'center',
              width: '100%',
              py: { xs: 1, md: 0 },
            }}
          >
          {editingName ? (
            <Box
              sx={{
                display: 'flex',
                gap: 1,
                alignItems: 'center',
                justifyContent: 'center',
                width: '100%',
                maxWidth: 420,
                mx: 'auto',
              }}
            >
              <TextField
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                fullWidth
                autoFocus
                inputProps={{ maxLength: 32 }}
                sx={{
                  '& .MuiOutlinedInput-root': {
                    color: '#f8fafc',
                    borderRadius: '12px',
                    textAlign: 'center',
                    '& fieldset': { borderColor: 'rgba(16,185,129,0.45)' },
                  },
                  '& .MuiOutlinedInput-input': {
                    textAlign: 'center',
                  },
                }}
              />
              <IconButton onClick={handleSaveName} sx={{ color: '#86efac', flexShrink: 0 }}>
                <CheckIcon />
              </IconButton>
            </Box>
          ) : (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 0.75,
                width: '100%',
              }}
            >
              <Typography sx={{ color: '#f8fafc', fontWeight: 700, fontSize: '1.2rem' }}>
                {displayName || 'Rugby Fan'}
              </Typography>
              <IconButton onClick={() => setEditingName(true)} sx={{ color: '#94a3b8' }} aria-label="Edit name">
                <EditIcon />
              </IconButton>
            </Box>
          )}
          {authData?.email && (
            <Typography sx={{ color: '#64748b', fontSize: '0.875rem', mt: 1.25 }}>
              {authData.email}
            </Typography>
          )}
          </Box>
        </Box>

        <Box sx={profileCardSx}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 0.75,
              mb: 1.5,
              flexWrap: 'wrap',
              width: '100%',
            }}
          >
            <FaceRetouchingNaturalIcon sx={{ color: '#86efac', fontSize: 22 }} />
            <FingerprintIcon sx={{ color: '#86efac', fontSize: 22 }} />
            <Typography sx={{ color: '#f8fafc', fontWeight: 700, fontSize: '1rem', textAlign: 'center' }}>
              {bioTitle}
            </Typography>
            <Chip
              size="small"
              label={biometricEnabled ? 'On' : 'Off'}
              sx={{
                height: 24,
                fontWeight: 700,
                bgcolor: biometricEnabled ? 'rgba(16,185,129,0.18)' : 'rgba(100,116,139,0.2)',
                color: biometricEnabled ? '#86efac' : '#94a3b8',
              }}
            />
          </Box>

          <Typography sx={{ color: '#64748b', fontSize: '0.875rem', lineHeight: 1.65, mb: 2, textAlign: 'center', width: '100%' }}>
            {biometricCanUse
              ? 'Device-only unlock with Face ID, face unlock, or fingerprint. Your license stays tied to this browser/device profile and is verified on each login.'
              : biometricUnavailableReason || 'Biometric login is not available in this browser. Use Safari or Chrome on your phone over HTTPS.'}
          </Typography>

          {biometricCanUse && !biometricEnabled && (
            <Alert severity="info" sx={{ mb: 2, textAlign: 'left' }}>
              {getBiometricSetupHint()}
            </Alert>
          )}

          {bioMessage && (
            <Alert severity="success" sx={{ mb: 1.5 }}>
              {bioMessage}
            </Alert>
          )}
          {bioError && (
            <Alert severity="error" sx={{ mb: 1.5 }}>
              {bioError}
            </Alert>
          )}

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {biometricCanUse && (
              <Button
                fullWidth
                variant="outlined"
                disabled={bioLoading}
                onClick={handleEnableBiometric}
                startIcon={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
                    <FaceRetouchingNaturalIcon sx={{ fontSize: 18 }} />
                    <FingerprintIcon sx={{ fontSize: 18 }} />
                  </Box>
                }
                sx={{
                  py: 1.25,
                  textTransform: 'none',
                  borderColor: 'rgba(134,239,172,0.45)',
                  color: '#bbf7d0',
                }}
              >
                {biometricEnabled ? 'Change biometric login' : `Set up ${bioTitle}`}
              </Button>
            )}
            {biometricEnabled && (
              <Button
                fullWidth
                variant="text"
                onClick={handleDisableBiometric}
                sx={{ textTransform: 'none', color: '#94a3b8' }}
              >
                Remove biometric login
              </Button>
            )}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

const UserProfilePanel = UserProfilePage;
export default UserProfilePanel;
