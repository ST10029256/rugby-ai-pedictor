import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Tab,
  Tabs,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import { TabLoadingScreen, VIEW_LOADER_SX } from '../utils/viewLoader';
import { getLeagueLineupMatches, getLeagueStandings, getMatchLineups } from '../firebase';
import { getPrimaryStandingsSeasonYear } from '../utils/season';
import {
  buildTeamLogoMapFromStandings,
  getHighlightlyLeagueId,
  readStandingsLogoCache,
  resolveTeamLogoUrl,
} from '../utils/teamLogos';
import { MEDIA_URLS } from '../utils/storageUrls';
import { hasMeaningfulTime, formatKickoffSAST } from '../utils/date';
import {
  analyzeSquad,
  groupBenchByPosition,
  groupStartersByPosition,
  jerseyPositionLabels,
  resolveTeamKit,
  RUGBY_SQUAD_SIZE,
  splitStartersAndBench,
  squadSummaryFromTeam,
} from '../utils/lineups';


/** Matches Standings tab loader container for error / info states. */
const LOADER_SX = VIEW_LOADER_SX;

/** Matches PredictionsDisplay kickoff typography — clean, no glow filters. */
const kickoffLabelSx = {
  fontWeight: 700,
  letterSpacing: { xs: 2.8, sm: 3.4, md: 3.8, lg: 4.2 },
  fontSize: { xs: '0.54rem', sm: '0.62rem', md: '0.72rem', lg: '0.8rem' },
  lineHeight: 1,
  textTransform: 'uppercase',
  color: 'rgba(226, 232, 240, 0.9)',
  display: 'block',
  textAlign: 'center',
};

const kickoffValueSx = {
  fontWeight: 900,
  letterSpacing: { xs: 1.15, sm: 1.4, md: 1.6, lg: 1.8 },
  textTransform: 'uppercase',
  fontSize: { xs: '1.34rem', sm: '1.6rem', md: '1.95rem', lg: '2.15rem' },
  lineHeight: 1,
  textAlign: 'center',
  color: '#f1f5f9',
};

const SYSTEM_FONT =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif';

const LUX = {
  accent: '#10b981',
  accentSoft: 'rgba(16,185,129,0.14)',
  border: 'rgba(255,255,255,0.10)',
  borderStrong: 'rgba(255,255,255,0.14)',
  text: 'rgba(255,255,255,0.92)',
  sub: 'rgba(255,255,255,0.70)',
  muted: 'rgba(255,255,255,0.55)',
};

/** Same MenuProps as History — prevents layout shift / viewport shrink on open. */
const SELECT_MENU_PROPS = {
  variant: 'menu',
  marginThreshold: 0,
  disableScrollLock: true,
  anchorOrigin: { vertical: 'bottom', horizontal: 'left' },
  transformOrigin: { vertical: 'top', horizontal: 'left' },
  PaperProps: {
    sx: {
      mt: 1,
      backgroundColor: 'rgba(17,24,39,0.98)',
      border: `1px solid ${LUX.borderStrong}`,
      backdropFilter: 'blur(14px)',
      maxHeight: { xs: '42vh', sm: '46vh' },
      overflowY: 'auto',
    },
  },
};

const lineupPredictionCardSx = {
  margin: '0 auto !important',
  mt: '0 !important',
  width: '100%',
  maxWidth: '100%',
  boxSizing: 'border-box',
};

const LeinsterJersey = ({ number, kit, uid }) => (
  <svg viewBox="0 0 100 120" width="100%" height="100%" aria-hidden="true">
    <defs>
      <linearGradient id={`lei-body-${uid}`} x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stopColor="#0091E0" />
        <stop offset="100%" stopColor={kit.primary} />
      </linearGradient>
      <filter id={`lei-shadow-${uid}`} x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="4" stdDeviation="3" floodColor="#000" floodOpacity="0.35" />
      </filter>
    </defs>
    <g filter={`url(#lei-shadow-${uid})`}>
      <path
        d="M22 18 L38 10 L50 14 L62 10 L78 18 L88 34 L82 48 L78 46 L78 112 L22 112 L22 46 L18 48 L12 34 Z"
        fill={`url(#lei-body-${uid})`}
        stroke={kit.collar}
        strokeWidth="2"
      />
      {/* White chest band — iconic Leinster home */}
      <path d="M24 42 L76 42 L74 58 L26 58 Z" fill={kit.stripe} opacity="0.98" />
      <path d="M38 10 L50 24 L62 10" fill="none" stroke={kit.stripe} strokeWidth="2.5" />
      <path d="M42 18 L50 28 L58 18" fill={kit.stripe} opacity="0.95" />
      <rect x="43" y="30" width="14" height="9" rx="2" fill={kit.collar} />
      {/* Sleeve cuffs */}
      <path d="M12 34 L18 48 L22 46 L16 32 Z" fill={kit.secondary} opacity="0.85" />
      <path d="M88 34 L82 48 L78 46 L84 32 Z" fill={kit.secondary} opacity="0.85" />
    </g>
    <text
      x="50"
      y="78"
      textAnchor="middle"
      dominantBaseline="middle"
      fill={kit.accent}
      fontSize="32"
      fontWeight="900"
      fontFamily="'Segoe UI', system-ui, sans-serif"
    >
      {number ?? '—'}
    </text>
  </svg>
);

const BullsJersey = ({ number, kit, uid }) => (
  <svg viewBox="0 0 100 120" width="100%" height="100%" aria-hidden="true">
    <defs>
      <linearGradient id={`bul-body-${uid}`} x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stopColor="#003590" />
        <stop offset="100%" stopColor={kit.primary} />
      </linearGradient>
      <filter id={`bul-shadow-${uid}`} x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="4" stdDeviation="3" floodColor="#000" floodOpacity="0.35" />
      </filter>
    </defs>
    <g filter={`url(#bul-shadow-${uid})`}>
      <path
        d="M22 18 L38 10 L50 14 L62 10 L78 18 L88 34 L82 48 L78 46 L78 112 L22 112 L22 46 L18 48 L12 34 Z"
        fill={`url(#bul-body-${uid})`}
        stroke={kit.collar}
        strokeWidth="2"
      />
      {/* Light blue shoulder yoke */}
      <path d="M22 18 L38 10 L50 14 L62 10 L78 18 L72 36 L28 36 Z" fill={kit.secondary} opacity="0.95" />
      <path d="M12 34 L22 18 L28 36 L18 48 Z" fill={kit.secondary} opacity="0.9" />
      <path d="M88 34 L78 18 L72 36 L82 48 Z" fill={kit.secondary} opacity="0.9" />
      {/* Side panels */}
      <path d="M22 46 L26 58 L26 112 L22 112 Z" fill={kit.secondary} opacity="0.55" />
      <path d="M78 46 L74 58 L74 112 L78 112 Z" fill={kit.secondary} opacity="0.55" />
      <path d="M38 10 L50 22 L62 10" fill="none" stroke={kit.accent} strokeWidth="2" opacity="0.7" />
      <rect x="42" y="26" width="16" height="10" rx="2" fill={kit.collar} />
    </g>
    <text
      x="50"
      y="78"
      textAnchor="middle"
      dominantBaseline="middle"
      fill={kit.accent}
      fontSize="32"
      fontWeight="900"
      fontFamily="'Segoe UI', system-ui, sans-serif"
    >
      {number ?? '—'}
    </text>
  </svg>
);

const ClassicJersey = ({ number, kit, uid }) => (
  <svg viewBox="0 0 100 120" width="100%" height="100%" aria-hidden="true">
    <defs>
      <linearGradient id={`cls-body-${uid}`} x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stopColor={kit.secondary} />
        <stop offset="100%" stopColor={kit.primary} />
      </linearGradient>
      <filter id={`cls-shadow-${uid}`} x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="4" stdDeviation="3" floodColor="#000" floodOpacity="0.35" />
      </filter>
    </defs>
    <g filter={`url(#cls-shadow-${uid})`}>
      <path
        d="M22 18 L38 10 L50 14 L62 10 L78 18 L88 34 L82 48 L78 46 L78 112 L22 112 L22 46 L18 48 L12 34 Z"
        fill={`url(#cls-body-${uid})`}
        stroke={kit.collar}
        strokeWidth="2"
      />
      <path d="M22 18 L38 10 L50 14 L62 10 L78 18 L72 34 L28 34 Z" fill={kit.secondary} opacity="0.9" />
      <path d="M12 34 L18 48 L22 46 L16 32 Z" fill={kit.secondary} opacity="0.85" />
      <path d="M88 34 L82 48 L78 46 L84 32 Z" fill={kit.secondary} opacity="0.85" />
      {(kit.design === 'stripe' || kit.stripe) && (
        <path d="M24 44 L76 44 L74 58 L26 58 Z" fill={kit.stripe || kit.accent} opacity="0.95" />
      )}
      <rect x="42" y="26" width="16" height="10" rx="2" fill={kit.collar} />
    </g>
    <text
      x="50"
      y="78"
      textAnchor="middle"
      dominantBaseline="middle"
      fill={kit.accent}
      fontSize="32"
      fontWeight="900"
      fontFamily="'Segoe UI', system-ui, sans-serif"
    >
      {number ?? '—'}
    </text>
  </svg>
);

const DefaultJersey = ({ number, kit, uid }) => (
  <ClassicJersey number={number} kit={kit} uid={uid} />
);

const RugbyJersey = ({ number, kit, size = 'md' }) => {
  const dims = size === 'lg'
    ? { w: { xs: 96, sm: 112 }, h: { xs: 114, sm: 132 } }
    : { w: { xs: 80, sm: 92 }, h: { xs: 96, sm: 108 } };
  const uid = `${kit.id}-${number}-${size}`.replace(/\W/g, '');

  return (
    <Box sx={{ width: dims.w, height: dims.h, mx: 'auto', flexShrink: 0 }}>
      {kit.design === 'leinster' && <LeinsterJersey number={number} kit={kit} uid={uid} />}
      {kit.design === 'bulls' && <BullsJersey number={number} kit={kit} uid={uid} />}
      {(kit.design === 'stripe' || kit.design === 'classic' || kit.design === 'default') && (
        <ClassicJersey number={number} kit={kit} uid={uid} />
      )}
      {kit.design !== 'leinster' && kit.design !== 'bulls' && kit.design !== 'stripe' && kit.design !== 'classic' && kit.design !== 'default' && (
        <DefaultJersey number={number} kit={kit} uid={uid} />
      )}
    </Box>
  );
};

const TeamCrest = ({ kit, alt, size = 72, leagueId = null, logoMap = {} }) => {
  const teamName = alt || kit?.name || '';
  const pickSrc = () =>
    kit?.logo ||
    resolveTeamLogoUrl(teamName, { leagueId, logoMap }) ||
    kit?.logoFallback ||
    null;

  const [src, setSrc] = useState(pickSrc);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setSrc(pickSrc());
    setFailed(false);
  }, [kit?.logo, kit?.logoFallback, teamName, leagueId, logoMap]);

  if (!src || failed) {
    return (
      <Box
        sx={{
          width: size,
          height: size,
          borderRadius: '50%',
          display: 'grid',
          placeItems: 'center',
          bgcolor: 'rgba(255,255,255,0.08)',
          border: '2px solid rgba(255,255,255,0.15)',
          fontWeight: 900,
          color: '#fff',
          fontSize: size * 0.35,
        }}
      >
        {(alt || '?').charAt(0)}
      </Box>
    );
  }

  return (
    <Box
      component="img"
      src={src}
      alt={alt}
      referrerPolicy="no-referrer"
      onError={() => {
        const fallback =
          kit?.logoFallback ||
          resolveTeamLogoUrl(teamName, { leagueId, logoMap: {} });
        if (fallback && src !== fallback) {
          setSrc(fallback);
          return;
        }
        setFailed(true);
      }}
      sx={{
        width: size,
        height: size,
        objectFit: 'contain',
        filter: 'drop-shadow(0 8px 16px rgba(0,0,0,0.45))',
      }}
    />
  );
};

const StatTile = ({ label, value, unit }) => (
  <Box
    sx={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 0.75,
      py: 1.35,
      px: 0.75,
      minHeight: 74,
      width: '100%',
      borderRadius: '12px',
      background: 'rgba(15, 23, 42, 0.55)',
      border: '1px solid rgba(74, 85, 104, 0.45)',
    }}
  >
    <Typography
      component="span"
      sx={{
        ...kickoffLabelSx,
        width: '100%',
        fontSize: { xs: '0.5rem', sm: '0.54rem' },
        letterSpacing: { xs: 2.2, sm: 2.6 },
        color: LUX.muted,
      }}
    >
      {label}
    </Typography>
    <Box sx={{ display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 0.35, width: '100%' }}>
      <Typography
        component="span"
        sx={{
          color: '#ffffff',
          fontWeight: 900,
          fontSize: { xs: '1.02rem', sm: '1.1rem' },
          lineHeight: 1,
          fontFamily: SYSTEM_FONT,
          letterSpacing: '-0.02em',
          textAlign: 'center',
        }}
      >
        {value ?? '—'}
      </Typography>
      {unit && (
        <Typography component="span" sx={{ color: '#94a3b8', fontWeight: 600, fontSize: '0.72rem', lineHeight: 1 }}>
          {unit}
        </Typography>
      )}
    </Box>
  </Box>
);

const PlayerStatsGrid = ({ player, kit }) => {
  const nationality = player?.country_code || player?.nationality || null;

  return (
    <Box
      sx={{
        width: '100%',
        display: 'grid',
        gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
        gap: 0.85,
        mt: 'auto',
        pt: 1.75,
        borderTop: '1px solid rgba(255,255,255,0.08)',
      }}
    >
      <StatTile
        label="Height"
        value={player?.height_cm ?? null}
        unit={player?.height_cm ? 'cm' : null}
      />
      <StatTile
        label="Weight"
        value={player?.weight_kg ?? null}
        unit={player?.weight_kg ? 'kg' : null}
      />
      <StatTile label="Age" value={player?.age != null ? player.age : null} unit={null} />
      <StatTile label="Nat" value={nationality} unit={null} />
    </Box>
  );
};

const PlayerLineupCard = ({ player, kit }) => {
  const num = player?.jersey_number;

  return (
    <Box
      className="lineup-player-card"
      sx={{
        position: 'relative',
        borderRadius: '20px',
        p: { xs: 1.75, sm: 2 },
        pb: { xs: 1.5, sm: 1.75 },
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        minHeight: { xs: 340, sm: 360 },
        textAlign: 'center',
        background: 'linear-gradient(145deg, #1a202c 0%, #2d3748 100%)',
        border: '1px solid rgba(74, 85, 104, 0.4)',
        boxShadow: '0 12px 40px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.05)',
        transition: 'transform 0.2s ease',
        '&:hover': {
          transform: 'translateY(-2px)',
        },
      }}
    >
      <Box
        sx={{
          position: 'absolute',
          top: 12,
          right: 12,
          zIndex: 2,
          px: 1,
          py: 0.4,
          borderRadius: 999,
          bgcolor: 'rgba(15, 23, 42, 0.85)',
          border: '1px solid rgba(74, 85, 104, 0.55)',
          color: '#e2e8f0',
          fontSize: '0.72rem',
          fontWeight: 800,
          letterSpacing: '0.08em',
          lineHeight: 1,
          fontFamily: SYSTEM_FONT,
        }}
      >
        #{num}
      </Box>

      <Box sx={{ position: 'relative', zIndex: 1, flex: '0 0 auto', pt: 0.25, pb: 1 }}>
        <RugbyJersey number={num} kit={kit} size="lg" />
      </Box>

      <Typography
        sx={{
          position: 'relative',
          zIndex: 1,
          color: '#ffffff',
          fontWeight: 800,
          fontSize: { xs: '1.05rem', sm: '1.15rem' },
          letterSpacing: '1px',
          lineHeight: 1.25,
          margin: '0.5rem 0',
          px: 0.5,
          wordBreak: 'break-word',
          fontFamily: SYSTEM_FONT,
        }}
      >
        {player?.name || 'Unknown'}
      </Typography>

      <Box sx={{ position: 'relative', zIndex: 1, flex: 1, display: 'flex', flexDirection: 'column', width: '100%', mt: 0.5 }}>
        <PlayerStatsGrid player={player} kit={kit} />
      </Box>
    </Box>
  );
};

const formatMatchDate = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
};

const premiumHeadingSx = {
  fontFamily: SYSTEM_FONT,
  fontWeight: 800,
  letterSpacing: { xs: '-0.02em', sm: '-0.025em', md: '-0.03em' },
  textTransform: 'none',
  fontSize: { xs: '1.38rem', sm: '1.72rem', md: '1.92rem' },
  lineHeight: 1.06,
  color: '#f8fafc',
};

const premiumDescriptorSx = {
  ...kickoffLabelSx,
  mt: 1.1,
  mb: 0,
  color: LUX.muted,
  fontWeight: 600,
  fontSize: { xs: '0.5rem', sm: '0.56rem', md: '0.6rem' },
  letterSpacing: { xs: 2.4, sm: 2.8, md: 3.2 },
};

const groupSubheadingTitleSx = {
  fontFamily: SYSTEM_FONT,
  fontWeight: 800,
  fontSize: { xs: '0.72rem', sm: '0.8rem' },
  letterSpacing: { xs: 0.12, sm: 0.16 },
  textTransform: 'uppercase',
  color: 'rgba(255,255,255,0.76)',
  lineHeight: 1.15,
};

const groupSubheadingMetaSx = {
  color: 'rgba(255,255,255,0.48)',
  fontSize: { xs: '0.72rem', sm: '0.76rem' },
  mt: 0.5,
  fontWeight: 500,
  letterSpacing: 0.02,
  lineHeight: 1.45,
};

const groupJerseyStripSx = {
  color: 'rgba(255,255,255,0.38)',
  fontSize: '0.64rem',
  mt: 0.65,
  fontWeight: 700,
  letterSpacing: '0.14em',
  textTransform: 'uppercase',
};

const headingRuleSx = {
  width: { xs: 40, sm: 48 },
  height: '1px',
  mx: 'auto',
  mt: 1.75,
  background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.22), transparent)',
};

const LineupSectionHeader = ({ eyebrow, title, subtitle }) => (
  <Box
    sx={{
      mb: { xs: 2, sm: 2.75 },
      mt: { xs: 2.5, sm: 3 },
      textAlign: 'center',
    }}
  >
    {eyebrow && (
      <Typography variant="overline" sx={{ ...kickoffLabelSx, mb: 1 }}>
        {eyebrow}
      </Typography>
    )}
    {title && (
      <Typography component="h2" sx={premiumHeadingSx}>
        {title}
      </Typography>
    )}
    {subtitle && (
      <Typography variant="overline" sx={{ ...premiumDescriptorSx, display: 'block' }}>
        {subtitle}
      </Typography>
    )}
    {(title || subtitle) && <Box sx={headingRuleSx} />}
  </Box>
);

const PhaseSectionHeader = ({ title, subtitle, showTopRule = true }) => (
  <Box
    sx={{
      borderTop: showTopRule ? `1px solid ${LUX.borderStrong}` : 'none',
      pt: showTopRule ? 2.75 : 0,
      pb: 0.5,
      mb: { xs: 2.75, sm: 3.25 },
      mt: showTopRule ? 0.25 : 0,
      textAlign: 'center',
    }}
  >
    <Typography component="h2" sx={premiumHeadingSx}>
      {title}
    </Typography>
    {subtitle && (
      <Typography variant="overline" sx={{ ...premiumDescriptorSx, display: 'block' }}>
        {subtitle}
      </Typography>
    )}
    <Box sx={headingRuleSx} />
  </Box>
);

const LineupScopeNav = ({ scope, onChange }) => (
  <Box
    sx={{
      display: 'flex',
      gap: 1,
      alignItems: 'center',
      flexWrap: 'wrap',
      justifyContent: 'center',
      mb: { xs: 1.5, sm: 2 },
    }}
  >
    {[
      { id: 'upcoming', label: 'Upcoming' },
      { id: 'historic', label: 'Historic Lineups' },
    ].map((item) => {
      const active = scope === item.id;
      return (
        <Button
          key={item.id}
          variant={active ? 'contained' : 'outlined'}
          size="small"
          onClick={() => onChange(item.id)}
          sx={{
            textTransform: 'none',
            fontWeight: 900,
            borderRadius: 999,
            px: 2.25,
            ...(active
              ? {
                  backgroundColor: 'rgba(16,185,129,0.18)',
                  color: LUX.accent,
                  boxShadow: 'none',
                  border: '1px solid rgba(16,185,129,0.35)',
                  '&:hover': { backgroundColor: 'rgba(16,185,129,0.24)' },
                }
              : {
                  borderColor: 'rgba(255,255,255,0.14)',
                  color: 'rgba(255,255,255,0.82)',
                  '&:hover': {
                    borderColor: 'rgba(255,255,255,0.22)',
                    backgroundColor: 'rgba(255,255,255,0.04)',
                  },
                }),
          }}
        >
          {item.label}
        </Button>
      );
    })}
  </Box>
);

const MatchSelectBar = ({ matches, selectedEventId, onChange }) => {
  if (!matches.length) return null;

  return (
    <Paper
      elevation={0}
      sx={{
        p: { xs: 1.25, sm: 1.5 },
        mb: { xs: 1.75, sm: 2 },
        borderRadius: 3,
        background: 'linear-gradient(180deg, rgba(255,255,255,0.045) 0%, rgba(0,0,0,0.12) 100%)',
        border: `1px solid ${LUX.border}`,
        boxShadow: '0 14px 46px rgba(0,0,0,0.26)',
      }}
    >
      <Box sx={{ minWidth: 0, maxWidth: { xs: '100%', sm: 520, md: 640 } }}>
        <FormControl size="small" fullWidth sx={{ minWidth: 0 }}>
          <InputLabel shrink sx={{ color: LUX.sub }}>
            Select match
          </InputLabel>
          <Select
            value={selectedEventId || matches[0]?.sport_event_id || ''}
            label="Select match"
            onChange={(e) => onChange(e.target.value)}
            MenuProps={SELECT_MENU_PROPS}
            sx={{
              color: LUX.text,
              borderRadius: 2.25,
              backgroundColor: 'rgba(255,255,255,0.04)',
              '& .MuiSelect-select': { pr: 4 },
              '& .MuiOutlinedInput-notchedOutline': { borderColor: LUX.border },
              '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.18)' },
              '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: LUX.accent },
              '& .MuiSvgIcon-root': { color: LUX.accent },
            }}
          >
            {matches.map((g) => (
              <MenuItem key={g.sport_event_id} value={g.sport_event_id} sx={{ color: LUX.text }}>
                <Typography sx={{ fontWeight: 800, fontSize: '0.9rem' }}>{g.label}</Typography>
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>
    </Paper>
  );
};

const PositionGroupBlock = ({ group, kit, compact = false, showTopDivider = false }) => {
  const jerseyStrip = group.jerseys?.map((n) => `#${n}`).join(' · ');
  const roleByJersey = group.roleByJersey || {};

  const gridSx = {
    'row-3': {
      display: 'grid',
      gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' },
      gap: { xs: 1.75, sm: 2.25 },
      maxWidth: 960,
      mx: 'auto',
    },
    'row-2': {
      display: 'grid',
      gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
      gap: { xs: 1.75, sm: 2.25 },
      maxWidth: 680,
      mx: 'auto',
    },
    'row-5': {
      display: 'grid',
      gridTemplateColumns: {
        xs: '1fr',
        sm: 'repeat(2, minmax(0, 1fr))',
        lg: 'repeat(3, minmax(0, 1fr))',
        xl: 'repeat(5, minmax(0, 1fr))',
      },
      gap: { xs: 1.75, sm: 2.25 },
      maxWidth: 1400,
      mx: 'auto',
    },
    solo: {
      display: 'grid',
      gridTemplateColumns: '1fr',
      gap: { xs: 1.75, sm: 2.25 },
      maxWidth: 380,
      mx: 'auto',
    },
  };

  const layout = group.layout || 'row-3';

  return (
    <Box
      sx={{
        mb: compact ? 2.25 : 3,
        pb: compact ? 0 : 0.25,
        pt: showTopDivider ? { xs: 2.25, sm: 2.75 } : 0,
        borderTop: showTopDivider ? '1px solid rgba(255,255,255,0.06)' : 'none',
      }}
    >
      <Box sx={{ textAlign: 'center', mb: { xs: 1.75, sm: 2 }, px: { xs: 0.5, sm: 1 } }}>
        <Typography sx={groupSubheadingTitleSx}>
          {group.title}
        </Typography>
        <Typography sx={groupSubheadingMetaSx}>
          {group.subtitle}
        </Typography>
        {jerseyStrip && (
          <Typography sx={groupJerseyStripSx}>
            {jerseyStrip}
          </Typography>
        )}
      </Box>

      <Box sx={gridSx[layout] || gridSx['row-3']}>
        {group.players.map((player) => {
          const roleLabel =
            roleByJersey[Number(player?.jersey_number)] ||
            jerseyPositionLabels[Number(player?.jersey_number)];
          return (
            <Box key={player.id || `${player.jersey_number}-${player.name}`} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}>
              {roleLabel && (
                <Typography
                  sx={{
                    color: LUX.muted,
                    fontWeight: 800,
                    fontSize: { xs: '0.58rem', sm: '0.62rem' },
                    letterSpacing: { xs: 2.4, sm: 2.8 },
                    textTransform: 'uppercase',
                    mb: 0.85,
                    textAlign: 'center',
                    lineHeight: 1,
                  }}
                >
                  {roleLabel}
                </Typography>
              )}
              <PlayerLineupCard player={player} kit={kit} />
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};

const MatchLineups = ({ leagueId, leagueName }) => {
  const theme = useTheme();
  const isWide = useMediaQuery(theme.breakpoints.up('lg'));

  const [loading, setLoading] = useState(true);
  const [matchesLoading, setMatchesLoading] = useState(true);
  const [error, setError] = useState(null);
  const [matchesError, setMatchesError] = useState(null);
  const [lineups, setLineups] = useState(null);
  const [matches, setMatches] = useState([]);
  const [selectedEventId, setSelectedEventId] = useState('');
  const [lineupScope, setLineupScope] = useState('upcoming');
  const [teamTab, setTeamTab] = useState(0);
  const [teamLogoMap, setTeamLogoMap] = useState({});

  const seasonYear = useMemo(
    () => (leagueId ? getPrimaryStandingsSeasonYear(leagueId) : null),
    [leagueId]
  );

  const kitOptions = useMemo(
    () => ({ leagueId, logoMap: teamLogoMap }),
    [leagueId, teamLogoMap]
  );

  useEffect(() => {
    if (!leagueId) {
      setTeamLogoMap({});
      return;
    }

    const cached = readStandingsLogoCache(leagueId);
    if (Object.keys(cached).length) setTeamLogoMap(cached);

    const hlId = getHighlightlyLeagueId(leagueId);
    if (!hlId) return;

    let cancelled = false;
    getLeagueStandings({
      sportsdbLeagueId: leagueId,
      highlightlyLeagueId: hlId,
      leagueName,
      season: seasonYear,
      forceRefresh: false,
    })
      .then((data) => {
        if (cancelled || !data?.success || !data?.standings) return;
        const map = buildTeamLogoMapFromStandings(data.standings);
        if (Object.keys(map).length) setTeamLogoMap((prev) => ({ ...prev, ...map }));
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [leagueId, leagueName, seasonYear]);

  useEffect(() => {
    if (!leagueId) {
      setMatchesLoading(false);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setMatchesLoading(true);
    setMatchesError(null);
    setMatches([]);
    setSelectedEventId('');
    setLineups(null);
    setError(null);

    getLeagueLineupMatches({
      sportsdbLeagueId: leagueId,
      matchScope: lineupScope,
    })
      .then((data) => {
        if (cancelled) return;
        const rows = Array.isArray(data?.matches) ? data.matches : [];
        if (data?.success && rows.length) {
          setMatches(rows);
          setSelectedEventId(rows[0].sport_event_id);
        } else {
          setMatches([]);
          setMatchesError(
            data?.error ||
              (lineupScope === 'upcoming'
                ? 'No upcoming fixtures with lineups found for this league.'
                : 'No completed matches with lineups found for this league.')
          );
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMatches([]);
          setMatchesError('Failed to load match list');
        }
      })
      .finally(() => {
        if (!cancelled) setMatchesLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [leagueId, lineupScope]);

  useEffect(() => {
    if (!leagueId || !selectedEventId || matchesLoading) {
      if (!matchesLoading && !selectedEventId) setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setTeamTab(0);

    getMatchLineups({ sportsdbLeagueId: leagueId, sportEventId: selectedEventId })
      .then((data) => {
        if (cancelled) return;
        if (data?.success && data?.lineups) {
          setLineups(data.lineups);
        } else {
          setError(data?.error || 'Lineups not available for this match');
          setLineups(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('Failed to load lineups');
          setLineups(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [leagueId, selectedEventId, matchesLoading]);

  const teams = lineups?.teams || [];
  const homeTeam = teams.find((t) => t.qualifier === 'home') || teams[0];
  const awayTeam = teams.find((t) => t.qualifier === 'away') || teams[1];
  const activeTeam = teamTab === 0 ? homeTeam : awayTeam;
  const resolveKit = (team) =>
    resolveTeamKit(team?.name, {
      ...kitOptions,
      competitorId: team?.id,
      primaryKit: team?.primary_kit,
      kitFallbackSpec: team?.kit_fallback_spec,
    });

  const activeKit = resolveKit(activeTeam);
  const squadAnalysis = useMemo(
    () => analyzeSquad(activeTeam?.players || []),
    [activeTeam]
  );
  const squadSummary = useMemo(() => {
    const fromApi = squadSummaryFromTeam(activeTeam);
    return { ...fromApi, unlisted: squadAnalysis.unlisted };
  }, [activeTeam, squadAnalysis.unlisted]);
  const unlistedPlayers = squadAnalysis.unlisted;

  const { starters, bench } = useMemo(
    () => splitStartersAndBench(activeTeam?.players || []),
    [activeTeam]
  );

  const starterGroups = useMemo(() => groupStartersByPosition(starters), [starters]);
  const benchGroups = useMemo(() => groupBenchByPosition(bench), [bench]);

  const match = lineups?.match || {};
  const selectedMatch = useMemo(
    () => matches.find((m) => m.sport_event_id === selectedEventId) || null,
    [matches, selectedEventId]
  );
  const featured = lineups?.featured || selectedMatch || {};

  if (matchesLoading || loading) {
    return <TabLoadingScreen label="Loading lineups..." />;
  }

  if (matchesError || !matches.length) {
    return (
      <Box sx={{ ...LOADER_SX, minHeight: 280, placeItems: 'start', pt: 4, px: 2 }}>
        <LineupScopeNav scope={lineupScope} onChange={setLineupScope} />
        <Alert severity="info" sx={{ borderRadius: 2, width: '100%', maxWidth: 720, mx: 'auto' }}>
          {matchesError || `No lineup matches found for ${leagueName || 'this league'}.`}
        </Alert>
      </Box>
    );
  }

  if (error || !lineups) {
    return (
      <Box
        sx={{
          width: '100%',
          maxWidth: '100%',
          mx: 0,
          p: { xs: 1.25, sm: 2.5, md: 3.5 },
          boxSizing: 'border-box',
        }}
      >
        <LineupScopeNav scope={lineupScope} onChange={setLineupScope} />
        <MatchSelectBar
          matches={matches}
          selectedEventId={selectedEventId}
          onChange={setSelectedEventId}
        />
        <Alert severity="warning" sx={{ borderRadius: 2, width: '100%', maxWidth: 720, mx: 'auto', mt: 2 }}>
          {error || 'No lineup data for this match — try another fixture from the list.'}
        </Alert>
      </Box>
    );
  }

  const homeKit = resolveKit(homeTeam);
  const awayKit = resolveKit(awayTeam);
  const homeScore = match.home_score ?? selectedMatch?.home_score ?? '—';
  const awayScore = match.away_score ?? selectedMatch?.away_score ?? '—';
  const matchStart = match.start_time || featured.start_time;
  const kickoffTimeDisplay =
    matchStart && hasMeaningfulTime(matchStart) ? formatKickoffSAST(matchStart) : '';

  return (
    <Box
      sx={{
        width: '100%',
        maxWidth: '100%',
        mx: 0,
        p: { xs: 1.25, sm: 2.5, md: 3.5 },
        boxSizing: 'border-box',
        overflowX: 'hidden',
      }}
    >
      <LineupScopeNav scope={lineupScope} onChange={setLineupScope} />
      <MatchSelectBar
        matches={matches}
        selectedEventId={selectedEventId}
        onChange={setSelectedEventId}
      />

      {/* Match hero — prediction-card style, flush top like History */}
      <Box
        className="prediction-card fade-in-up"
        sx={{
          ...lineupPredictionCardSx,
          backgroundImage: `url(${MEDIA_URLS.imageRugby})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          position: 'relative',
          mb: { xs: 1.75, sm: 2.25 },
          py: { xs: 2, sm: 2.5 },
          px: { xs: 1.5, sm: 2.5 },
          '&::after': {
            content: '""',
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(145deg, rgba(26, 32, 44, 0.88) 0%, rgba(45, 55, 72, 0.88) 100%)',
            zIndex: 0,
            pointerEvents: 'none',
          },
          '& > *': { position: 'relative', zIndex: 1 },
        }}
      >
        <Box sx={{ textAlign: 'center', mb: 1.5 }}>
          <Typography variant="overline" sx={kickoffLabelSx}>
            {match.competition || leagueName || 'United Rugby Championship'} · {featured.season || match.season || '25/26'}
          </Typography>
          <Typography
            className="match-title"
            component="h2"
            sx={{
              fontSize: { xs: '1.45rem', sm: '2rem' },
              fontWeight: 800,
              color: '#ffffff',
              mt: 1,
              mb: 0,
              letterSpacing: '0.5px',
            }}
          >
            {featured.round || match.round || 'Final'}
          </Typography>
        </Box>

        {kickoffTimeDisplay && (
          <Box sx={{ textAlign: 'center', mb: 1.5 }}>
            <Typography variant="overline" sx={kickoffLabelSx}>
              Kickoff
            </Typography>
            <Typography sx={{ ...kickoffValueSx, mt: 0.75 }}>
              {kickoffTimeDisplay}
            </Typography>
          </Box>
        )}

        <Typography className="match-date" sx={{ textAlign: 'center', mb: 0.5 }}>
          {formatMatchDate(matchStart)}
          {(match.venue || featured.venue) ? ` · ${match.venue || featured.venue}` : ''}
        </Typography>

        <Box sx={{ borderTop: `1px solid ${LUX.borderStrong}`, my: 2.25 }} />

        <Grid container spacing={{ xs: 0.5, sm: 2, md: 3 }} alignItems="center" justifyContent="center">
          <Grid item xs={5} sm={4} md={4} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 0 }}>
            <Box sx={{ mb: 1.25 }}>
              <TeamCrest kit={homeKit} alt={homeTeam?.name} size={isWide ? 72 : 60} leagueId={leagueId} logoMap={teamLogoMap} />
            </Box>
            <Typography className="team-name" sx={{ fontSize: { xs: '1rem !important', sm: '1.35rem !important' }, mb: 1 }}>
              {homeTeam?.name}
            </Typography>
            <Box
              component="div"
              className="team-score"
              sx={{
                fontSize: { xs: '2.75rem !important', sm: '4rem !important', md: '5.5rem !important' },
                minHeight: { xs: '100px !important', sm: '140px !important', md: '160px !important' },
                py: { xs: '1rem !important', sm: '1.25rem !important' },
              }}
            >
              {homeScore}
            </Box>
          </Grid>

          <Grid item xs={2} sm={4} md={4} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', alignSelf: 'stretch' }}>
            <Typography className="vs-text" sx={{ fontSize: { xs: '2rem !important', sm: '3.5rem !important', md: '4.5rem !important' }, mt: { xs: '3.5rem', sm: '4rem' } }}>
              FT
            </Typography>
          </Grid>

          <Grid item xs={5} sm={4} md={4} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 0 }}>
            <Box sx={{ mb: 1.25 }}>
              <TeamCrest kit={awayKit} alt={awayTeam?.name} size={isWide ? 72 : 60} leagueId={leagueId} logoMap={teamLogoMap} />
            </Box>
            <Typography className="team-name" sx={{ fontSize: { xs: '1rem !important', sm: '1.35rem !important' }, mb: 1 }}>
              {awayTeam?.name}
            </Typography>
            <Box
              component="div"
              className="team-score"
              sx={{
                fontSize: { xs: '2.75rem !important', sm: '4rem !important', md: '5.5rem !important' },
                minHeight: { xs: '100px !important', sm: '140px !important', md: '160px !important' },
                py: { xs: '1rem !important', sm: '1.25rem !important' },
              }}
            >
              {awayScore}
            </Box>
          </Grid>
        </Grid>
      </Box>

      {/* Team tabs */}
      <Tabs
        value={teamTab}
        onChange={(_, v) => setTeamTab(v)}
        variant="fullWidth"
        sx={{
          mt: { xs: 2.5, sm: 3 },
          mb: 3,
          minHeight: 64,
          borderRadius: '20px',
          bgcolor: 'rgba(26, 32, 44, 0.85)',
          border: '1px solid rgba(74, 85, 104, 0.45)',
          p: 1,
          '& .MuiTab-root': {
            color: 'rgba(226, 232, 240, 0.65)',
            fontWeight: 800,
            textTransform: 'none',
            fontSize: { xs: '0.88rem', sm: '0.95rem' },
            letterSpacing: '0.5px',
            minHeight: 52,
            px: { xs: 2, sm: 3 },
            py: 1.25,
            gap: 1.5,
            borderRadius: '14px',
            transition: 'background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease',
            flexDirection: 'row',
            justifyContent: 'center',
          },
          '& .MuiTab-iconWrapper': {
            marginRight: '14px !important',
            marginBottom: '0 !important',
          },
          '& .Mui-selected': {
            color: '#ffffff !important',
            bgcolor: 'rgba(255, 255, 255, 0.08)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
          },
          '& .MuiTabs-indicator': { display: 'none' },
          '& .MuiTabs-flexContainer': { gap: 0.75 },
        }}
      >
        <Tab
          icon={<TeamCrest kit={homeKit} alt={homeTeam?.name} size={32} leagueId={leagueId} logoMap={teamLogoMap} />}
          iconPosition="start"
          label={homeTeam?.name || 'Home'}
        />
        <Tab
          icon={<TeamCrest kit={awayKit} alt={awayTeam?.name} size={32} leagueId={leagueId} logoMap={teamLogoMap} />}
          iconPosition="start"
          label={awayTeam?.name || 'Away'}
        />
      </Tabs>

      {!squadSummary.isComplete && (
        <Alert severity="warning" sx={{ mb: 2.5, borderRadius: 2 }}>
          Squad data from SportRadar: {squadSummary.slotsFilled}/{squadSummary.expectedSlots || RUGBY_SQUAD_SIZE} numbered
          slots filled
          {squadSummary.missingJerseys?.length
            ? ` · missing #${squadSummary.missingJerseys.join(', #')}`
            : ''}
          {squadSummary.unlistedCount
            ? ` · ${squadSummary.unlistedCount} extra/unnumbered player(s) listed below`
            : ''}
          . Some fixtures only publish partial squads — this is a data coverage limit, not a display bug.
        </Alert>
      )}

      <LineupSectionHeader
        eyebrow="Lineup"
        title="Starting XV"
        subtitle={`${activeTeam?.name || 'Team'} · pack to backline`}
      />

      <Box
        className="prediction-card"
        sx={{
          ...lineupPredictionCardSx,
          mb: 4,
          py: { xs: 2, sm: 2.5 },
          px: { xs: 1.5, sm: 2.5 },
          background: 'linear-gradient(145deg, #1a202c 0%, #2d3748 100%)',
        }}
      >
        <PhaseSectionHeader
          title="Forwards"
          subtitle="Front row · Second row · Back row"
          showTopRule={false}
        />
        {starterGroups.forwards.map((group, idx) => (
          <PositionGroupBlock key={group.id} group={group} kit={activeKit} showTopDivider={idx > 0} />
        ))}

        <Box sx={{ borderTop: `1px solid ${LUX.borderStrong}`, my: { xs: 2.5, sm: 3 } }} />

        <PhaseSectionHeader
          title="Backline"
          subtitle="Halfbacks · Centres · Wings · Fullback"
          showTopRule={false}
        />
        {starterGroups.backs.map((group, idx) => (
          <PositionGroupBlock key={group.id} group={group} kit={activeKit} showTopDivider={idx > 0} />
        ))}
      </Box>

      <LineupSectionHeader eyebrow="Bench" subtitle="Replacements · 16 to 23" />

      <Box
        className="prediction-card"
        sx={{
          ...lineupPredictionCardSx,
          mb: { xs: 4, sm: 5 },
          py: { xs: 2, sm: 2.5 },
          px: { xs: 1.5, sm: 2.5 },
          background: 'linear-gradient(145deg, #1a202c 0%, #2d3748 100%)',
        }}
      >
        {benchGroups.map((group, idx) => (
          <Box key={group.id} sx={{ mb: idx < benchGroups.length - 1 ? 0 : 0 }}>
            <PositionGroupBlock group={group} kit={activeKit} compact showTopDivider={idx > 0} />
          </Box>
        ))}
      </Box>

      {unlistedPlayers.length > 0 && (
        <>
          <LineupSectionHeader
            eyebrow="Squad"
            title="Additional players"
            subtitle="No jersey slot · duplicate number · or outside 1–23"
          />
          <Box
            className="prediction-card"
            sx={{
              ...lineupPredictionCardSx,
              mb: { xs: 4, sm: 5 },
              py: { xs: 2, sm: 2.5 },
              px: { xs: 1.5, sm: 2.5 },
              background: 'linear-gradient(145deg, #1a202c 0%, #2d3748 100%)',
            }}
          >
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(3, 1fr)' },
                gap: { xs: 1.75, sm: 2.25 },
              }}
            >
              {unlistedPlayers.map((player) => (
                <Box key={player.id || `${player.jersey_number}-${player.name}`}>
                  <PlayerLineupCard player={player} kit={activeKit} />
                </Box>
              ))}
            </Box>
          </Box>
        </>
      )}
    </Box>
  );
};

export default MatchLineups;
