import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Alert,
  Divider,
  Tooltip,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents';
import { getLeagueStandings, subscribeToStandingsCache } from '../firebase';
import RugbyBallLoader from './RugbyBallLoader';

// League ID mapping: Our league ID -> Highlightly league ID
const LEAGUE_ID_MAPPING = {
  4986: 73119, // Rugby Championship
  4446: 65460, // United Rugby Championship
  5069: 32271, // Currie Cup
  4574: 59503, // Rugby World Cup (no standings)
  4551: 61205, // Super Rugby
  4430: 14400, // French Top 14
  4414: 11847, // English Premiership Rugby (CORRECTED: was 5039 which was Austrian league)
  4714: 44185, // Six Nations Championship
  5479: 72268, // Rugby Union International Friendlies (Friendly International - no standings as friendlies don't have league tables)
};

const LeagueStandings = ({ leagueId, leagueName }) => {
  const [standings, setStandings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [logoCircleSize, setLogoCircleSize] = useState({ xs: 84, sm: 100 });
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const isLgUp = useMediaQuery(theme.breakpoints.up('lg'));

  const getLicenseCacheKey = (sportsdbLeagueId, highlightlyLeagueId) => {
    let license = 'anon';
    try {
      const raw = localStorage.getItem('rugby_ai_auth');
      if (raw) {
        const auth = JSON.parse(raw);
        if (auth?.licenseKey) license = String(auth.licenseKey);
      }
    } catch (e) {
      // ignore
    }
    return `standings_cache::${license}::sportsdb_${sportsdbLeagueId}::hl_${highlightlyLeagueId}`;
  };

  useEffect(() => {
    const loadStandings = async () => {
      if (!leagueId) {
        setLoading(false);
        return;
      }

      try {
        setError(null);

        const highlightlyLeagueId = LEAGUE_ID_MAPPING[leagueId];
        if (!highlightlyLeagueId) {
          setError('Standings not available for this league');
          setLoading(false);
          return;
        }
        
        // Special handling for International Friendlies - they don't have standings
        if (leagueId === 5479) {
          setError('Standings are not available for International Friendlies. Friendlies are exhibition matches and do not have league tables.');
          setLoading(false);
          return;
        }

        const cacheKey = getLicenseCacheKey(leagueId, highlightlyLeagueId);
        const now = Date.now();
        const TTL_MS = 6 * 60 * 60 * 1000; // 6 hours (prevents rate-limit spam on app open)
        const STALE_MAX_MS = 24 * 60 * 60 * 1000; // show stale data up to 24h if needed

        // Client-side cache (per license key) to avoid refetching every app open.
        // Strategy: fresh -> use and skip network. stale-but-recent -> show immediately, then revalidate.
        let cached = null;
        try {
          const raw = localStorage.getItem(cacheKey);
          if (raw) cached = JSON.parse(raw);
        } catch (e) {
          cached = null;
        }

        const cachedAt = cached?.cachedAt ? Number(cached.cachedAt) : null;
        const cachedStandings = cached?.standings || null;
        const cacheAge = cachedAt ? now - cachedAt : null;

        if (cachedStandings && cacheAge !== null && cacheAge >= 0 && cacheAge < TTL_MS) {
          setStandings(cachedStandings);
          setLoading(false);
          return;
        }

        if (cachedStandings && cacheAge !== null && cacheAge >= 0 && cacheAge < STALE_MAX_MS) {
          // Stale-while-revalidate: render instantly, refresh in background.
          setStandings(cachedStandings);
          setLoading(false);
        } else {
          setLoading(true);
        }

        const data = await getLeagueStandings({
          highlightlyLeagueId,
          sportsdbLeagueId: leagueId,
          leagueName,
        });
        
        if (data && data.success && data.standings) {
          setStandings(data.standings);
          try {
            localStorage.setItem(
              cacheKey,
              JSON.stringify({
                cachedAt: now,
                standings: data.standings,
                season: data.season ?? data.standings?.league?.season ?? null,
              })
            );
          } catch (e) {
            // ignore quota issues
          }
        } else {
          setError(data?.error || 'No standings data available');
        }
      } catch (err) {
        console.error('Error loading standings:', err);
        setError('Failed to load standings');
      } finally {
        setLoading(false);
      }
    };

    loadStandings();
  }, [leagueId]);

  // Subscribe to Firestore standings cache for real-time updates when API updates server cache
  useEffect(() => {
    if (!leagueId) return;
    const highlightlyLeagueId = LEAGUE_ID_MAPPING[leagueId];
    if (!highlightlyLeagueId || leagueId === 5479) return;

    const currentYear = new Date().getFullYear();
    const seasons = [currentYear, currentYear - 1];

    const unsub = subscribeToStandingsCache(highlightlyLeagueId, seasons, (newStandings) => {
      setStandings(newStandings);
      const cacheKey = getLicenseCacheKey(leagueId, highlightlyLeagueId);
      try {
        localStorage.setItem(
          cacheKey,
          JSON.stringify({
            cachedAt: Date.now(),
            standings: newStandings,
            season: newStandings?.league?.season ?? null,
          })
        );
      } catch (e) {
        // ignore quota issues
      }
    });

    return unsub;
  }, [leagueId]);

  if (!leagueId) {
    return null;
  }

  if (loading) {
    return (
      <Box sx={{ 
        width: '100%',
        minHeight: { xs: 'calc(100svh - 160px)', sm: 'calc(100vh - 180px)' },
        display: 'grid',
        placeItems: 'center',
        boxSizing: 'border-box',
      }}>
        <RugbyBallLoader size={100} color="#10b981" compact label="Loading standings..." />
      </Box>
    );
  }

  if (error) {
    return (
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Alert severity="info">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  if (!standings || !standings.groups || standings.groups.length === 0) {
    return (
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Alert severity="info">No standings data available for {leagueName || 'this league'}</Alert>
        </CardContent>
      </Card>
    );
  }

  // Get the first group (most leagues have one group)
  const group = standings.groups[0];
  const teams = group.standings || group.teams || [];

  if (teams.length === 0) {
    return (
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Alert severity="info">No teams found in standings</Alert>
        </CardContent>
      </Card>
    );
  }

  const groups = Array.isArray(standings.groups) ? standings.groups : [];

  const getTeamLogo = (teamData, row) => {
    if (!teamData || typeof teamData !== 'object') return null;
    return (
      teamData.logo ||
      teamData.image ||
      teamData.badge ||
      teamData.team_logo ||
      teamData.strTeamBadge ||
      (row && typeof row === 'object' ? row.logo || row.badge : null) ||
      null
    );
  };

  const toNumberOrNull = (v) => {
    if (v === null || v === undefined || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };

  const normalizeTeamRow = (team, index) => {
    const teamData = team?.team || team || {};
    const teamName = teamData?.name || teamData?.team_name || teamData?.strTeam || 'Unknown';

    const position = Number(team?.position ?? (index + 1)) || (index + 1);
    const points = Number(team?.points ?? 0) || 0;
    const wins = Number(team?.wins ?? 0) || 0;
    const draws = Number(team?.draws ?? 0) || 0;
    const losses = Number(team?.loses ?? team?.losses ?? 0) || 0;
    const played = Number(team?.gamesPlayed ?? team?.played ?? (wins + draws + losses)) || 0;

    // These often arrive as strings from various providers; normalize to numbers for UI + sorting.
    const bonusPoints = toNumberOrNull(
      team?.bonusPoints ??
        team?.bonus_points ??
        team?.bp ??
        team?.bonus ??
        team?.bonusPts ??
        team?.bonus_points_total ??
        null
    );

    const pointsFor = toNumberOrNull(
      team?.pointsFor ??
        team?.points_for ??
        team?.goalsFor ??
        team?.for ??
        team?.pf ??
        team?.points_scored ??
        team?.scored ??
        null
    );

    const pointsAgainst = toNumberOrNull(
      team?.pointsAgainst ??
        team?.points_against ??
        team?.goalsAgainst ??
        team?.against ??
        team?.pa ??
        team?.points_conceded ??
        team?.conceded ??
        null
    );

    const pointsDiff =
      toNumberOrNull(
        team?.pointsDifference ??
          team?.points_diff ??
          team?.difference ??
          team?.diff ??
          team?.pd ??
          team?.points_difference ??
          null
      ) ?? (pointsFor !== null && pointsAgainst !== null ? pointsFor - pointsAgainst : null);

    return {
      key: teamData?.id || team?.teamId || team?.id || `${teamName}-${index}`,
      teamData,
      teamName,
      logo: getTeamLogo(teamData, team),
      position,
      played,
      wins,
      draws,
      losses,
      points,
      bonusPoints,
      pointsFor,
      pointsAgainst,
      pointsDiff,
      raw: team,
    };
  };

  const getRankStyle = (position) => {
    if (position === 1) return { label: '1', bg: 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)', fg: '#111827', ring: 'rgba(251, 191, 36, 0.55)' };
    if (position === 2) return { label: '2', bg: 'linear-gradient(135deg, #e5e7eb 0%, #9ca3af 100%)', fg: '#111827', ring: 'rgba(229, 231, 235, 0.45)' };
    if (position === 3) return { label: '3', bg: 'linear-gradient(135deg, #f59e0b 0%, #b45309 100%)', fg: '#111827', ring: 'rgba(245, 158, 11, 0.35)' };
    if (position <= 8) return { label: String(position), bg: 'rgba(16, 185, 129, 0.16)', fg: '#d1fae5', ring: 'rgba(16, 185, 129, 0.25)' };
    return { label: String(position), bg: 'rgba(255, 255, 255, 0.08)', fg: '#e5e7eb', ring: 'rgba(255, 255, 255, 0.12)' };
  };

  const formatSigned = (n) => {
    if (typeof n !== 'number' || Number.isNaN(n)) return '—';
    return `${n > 0 ? '+' : ''}${n}`;
  };

  const getLeagueLogo = (leagueObj) => {
    if (!leagueObj || typeof leagueObj !== 'object') return null;
    return (
      leagueObj.logo ||
      leagueObj.badge ||
      leagueObj.image ||
      leagueObj.league_logo ||
      leagueObj.strLogo ||
      leagueObj.strBadge ||
      leagueObj.strBanner ||
      null
    );
  };

  const getLeagueMonogram = (name) => {
    const raw = String(name || '').trim();
    if (!raw) return '🏆';
    const words = raw
      .replace(/[^a-zA-Z0-9\s]/g, ' ')
      .split(/\s+/)
      .filter(Boolean);

    const significant = words.filter((w) => w.length > 2);
    const pick = (significant.length ? significant : words).slice(0, 4);
    const letters = pick.map((w) => w[0]?.toUpperCase()).filter(Boolean);
    return letters.slice(0, 3).join('') || raw.slice(0, 2).toUpperCase();
  };

  const getPodiumAccent = (position) => {
    if (position === 1) return { halo: 'rgba(251,191,36,0.22)', line: 'rgba(251,191,36,0.55)', label: 'Champion' };
    if (position === 2) return { halo: 'rgba(229,231,235,0.14)', line: 'rgba(229,231,235,0.35)', label: 'Runner-up' };
    if (position === 3) return { halo: 'rgba(245,158,11,0.14)', line: 'rgba(245,158,11,0.30)', label: '3rd' };
    return { halo: 'rgba(16,185,129,0.10)', line: 'rgba(16,185,129,0.22)', label: `#${position}` };
  };

  const renderPodium = (rows, { showBonus = false, showForAgainst = false } = {}) => {
    if (!rows || rows.length === 0) return null;
    const top = rows.slice(0, 3);
    if (top.length === 0) return null;

    const hasPF = rows.some((r) => r.pointsFor !== null);
    const hasPA = rows.some((r) => r.pointsAgainst !== null);
    const hasPD = rows.some((r) => r.pointsDiff !== null);
    const showTiles = showBonus || hasPF || hasPA || hasPD;
    const tileCols = 1 + (showBonus ? 1 : 0) + (hasPF ? 1 : 0) + (hasPA ? 1 : 0) + (hasPD ? 1 : 0);

    // Keep natural order (1,2,3). No raised champion card (user preference).
    const ordered = top;

    return (
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' },
          gap: { xs: 1, sm: 1.25, md: 1.5 },
          mb: { xs: 1.5, sm: 2 },
          px: { xs: 0.25, sm: 0 },
        }}
      >
        {ordered.map((r, i) => {
          if (!r) return null;
          const rank = getRankStyle(r.position);
          const accent = getPodiumAccent(r.position);
          const isChampion = r.position === 1;

          return (
            <Paper
              key={`podium-${r.key}`}
              elevation={0}
              sx={{
                position: 'relative',
                overflow: 'hidden',
                borderRadius: 3,
                p: { xs: 1.25, sm: 1.5 },
                background:
                  'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.045) 55%, rgba(255,255,255,0.03) 100%)',
                border: `1px solid ${accent.line}`,
                boxShadow: isChampion
                  ? '0 18px 55px rgba(0,0,0,0.40), 0 0 0 1px rgba(251,191,36,0.20)'
                  : '0 14px 40px rgba(0,0,0,0.30)',
                transition: 'transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease',
                '&::before': {
                  content: '""',
                  position: 'absolute',
                  inset: -1,
                  background: `radial-gradient(650px circle at 20% 10%, ${accent.halo} 0%, transparent 55%)`,
                  pointerEvents: 'none',
                },
                '&::after': {
                  content: '""',
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  height: 2,
                  background: `linear-gradient(90deg, transparent 0%, ${accent.line} 50%, transparent 100%)`,
                  opacity: 0.85,
                  pointerEvents: 'none',
                },
                '@media (prefers-reduced-motion: reduce)': {
                  transition: 'none',
                  transform: 'none',
                },
                '&:hover': {
                  borderColor: 'rgba(255,255,255,0.28)',
                  boxShadow: isChampion
                    ? '0 22px 70px rgba(0,0,0,0.42), 0 0 0 1px rgba(251,191,36,0.26)'
                    : '0 18px 55px rgba(0,0,0,0.38)',
                  transform: 'translateY(-6px)',
                  '@media (prefers-reduced-motion: reduce)': {
                    transform: 'none',
                  },
                },
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2, minWidth: 0 }}>
                  <Box
                    sx={{
                      width: 32,
                      height: 32,
                      borderRadius: '50%',
                      position: 'relative',
                      overflow: 'hidden',
                      display: 'grid',
                      placeItems: 'center',
                      background: rank.bg,
                      color: rank.fg,
                      fontWeight: 1000,
                      boxShadow: `0 0 0 2px ${rank.ring}, 0 10px 22px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.25)`,
                      border: '1px solid rgba(255,255,255,0.20)',
                      flexShrink: 0,
                      '&::after': {
                        content: '""',
                        position: 'absolute',
                        inset: 0,
                        background: 'linear-gradient(180deg, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.10) 45%, rgba(255,255,255,0.00) 100%)',
                        opacity: 0.22,
                        pointerEvents: 'none',
                      },
                    }}
                  >
                    {rank.label}
                  </Box>

                  {r.logo ? (
                    <Box
                      component="img"
                      src={r.logo}
                      alt={r.teamName}
                      referrerPolicy="no-referrer"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                      }}
                      sx={{
                        width: 62,
                        height: 62,
                        objectFit: 'contain',
                        display: 'block',
                        flexShrink: 0,
                        borderRadius: 2,
                      }}
                    />
                  ) : (
                    <Box sx={{ width: 62, height: 62, display: 'grid', placeItems: 'center', flexShrink: 0 }}>
                      <Typography sx={{ color: 'rgba(255,255,255,0.85)', fontWeight: 900 }}>
                        {r.teamName?.[0] || '?'}
                      </Typography>
                    </Box>
                  )}

                  <Box sx={{ minWidth: 0 }}>
                    <Typography
                      sx={{
                        color: 'rgba(255,255,255,0.98)',
                        fontWeight: 1000,
                        letterSpacing: 0.2,
                        fontSize: { xs: '0.92rem', sm: '0.98rem' },
                      }}
                      noWrap
                    >
                      {r.teamName}
                    </Typography>
                    <Typography sx={{ color: 'rgba(255,255,255,0.70)', fontSize: '0.78rem' }} noWrap>
                      {accent.label} • W {r.wins} • D {r.draws} • L {r.losses}
                    </Typography>
                  </Box>
                </Box>

                <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                  <Typography sx={{ color: '#fbbf24', fontWeight: 1100, fontSize: '1.2rem', lineHeight: 1.1 }}>
                    {r.points}
                  </Typography>
                  <Typography sx={{ color: 'rgba(255,255,255,0.65)', fontSize: '0.72rem' }}>points</Typography>
                </Box>
              </Box>

              {showTiles && (
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: `repeat(${tileCols}, minmax(0, 1fr))`,
                    gap: 1,
                    mt: 1.25,
                  }}
                >
                  <Box sx={{ textAlign: 'center', p: 0.8, borderRadius: 2, border: '1px solid rgba(255,255,255,0.10)', backgroundColor: 'rgba(0,0,0,0.12)' }}>
                    <Typography sx={{ color: 'rgba(255,255,255,0.70)', fontSize: '0.68rem' }}>Played</Typography>
                    <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 900 }}>{r.played}</Typography>
                  </Box>
                  {showBonus && (
                    <Box sx={{ textAlign: 'center', p: 0.8, borderRadius: 2, border: '1px solid rgba(255,255,255,0.10)', backgroundColor: 'rgba(0,0,0,0.12)' }}>
                      <Typography sx={{ color: 'rgba(255,255,255,0.70)', fontSize: '0.68rem' }}>Bonus</Typography>
                      <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 900 }}>
                        {r.bonusPoints !== null ? r.bonusPoints : '—'}
                      </Typography>
                    </Box>
                  )}
                  {hasPF && (
                    <Box sx={{ textAlign: 'center', p: 0.8, borderRadius: 2, border: '1px solid rgba(255,255,255,0.10)', backgroundColor: 'rgba(0,0,0,0.12)' }}>
                      <Typography sx={{ color: 'rgba(255,255,255,0.70)', fontSize: '0.68rem' }}>PF</Typography>
                      <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 900 }}>
                        {r.pointsFor !== null ? r.pointsFor : '—'}
                      </Typography>
                    </Box>
                  )}
                  {hasPA && (
                    <Box sx={{ textAlign: 'center', p: 0.8, borderRadius: 2, border: '1px solid rgba(255,255,255,0.10)', backgroundColor: 'rgba(0,0,0,0.12)' }}>
                      <Typography sx={{ color: 'rgba(255,255,255,0.70)', fontSize: '0.68rem' }}>PA</Typography>
                      <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 900 }}>
                        {r.pointsAgainst !== null ? r.pointsAgainst : '—'}
                      </Typography>
                    </Box>
                  )}
                  {hasPD && (
                    <Box sx={{ textAlign: 'center', p: 0.8, borderRadius: 2, border: '1px solid rgba(255,255,255,0.10)', backgroundColor: 'rgba(0,0,0,0.12)' }}>
                      <Typography sx={{ color: 'rgba(255,255,255,0.70)', fontSize: '0.68rem' }}>PD</Typography>
                      <Typography
                        sx={{
                          fontWeight: 1000,
                          color: typeof r.pointsDiff === 'number' && r.pointsDiff < 0 ? '#fecaca' : '#bbf7d0',
                        }}
                      >
                        {formatSigned(r.pointsDiff)}
                      </Typography>
                    </Box>
                  )}
                </Box>
              )}
            </Paper>
          );
        })}
      </Box>
    );
  };

  const renderGroup = (groupObj, groupIndex) => {
    const list = groupObj?.standings || groupObj?.teams || [];
    const rows = list.map(normalizeTeamRow).sort((a, b) => a.position - b.position);

    const showBonus = rows.some((r) => r.bonusPoints !== null);
    const showForAgainst = rows.some((r) => r.pointsFor !== null || r.pointsAgainst !== null || r.pointsDiff !== null);

    const groupName = groupObj?.name || groupObj?.group_name || (groups.length > 1 ? `Group ${groupIndex + 1}` : null);

    return (
      <Box key={groupName || groupIndex} sx={{ width: '100%' }}>
        {groupName && (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5, mt: groupIndex === 0 ? 0 : 2 }}>
            <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 800, letterSpacing: 0.2 }}>
              {groupName}
            </Typography>
            <Chip
              size="small"
              label={`${rows.length} teams`}
              sx={{
                backgroundColor: 'rgba(255,255,255,0.10)',
                color: 'rgba(255,255,255,0.85)',
                border: '1px solid rgba(255,255,255,0.12)',
              }}
            />
          </Box>
        )}

        {!isMobile && isLgUp && rows.length >= 3 && renderPodium(rows, { showBonus, showForAgainst })}

        {isMobile ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, px: 0.5 }}>
            {rows.map((r) => {
              const rank = getRankStyle(r.position);
              return (
                <Paper
                  key={r.key}
                  elevation={0}
                  sx={{
                    p: 1.5,
                    borderRadius: 2,
                    background:
                      r.position === 1
                        ? 'linear-gradient(135deg, rgba(251,191,36,0.12) 0%, rgba(255,255,255,0.05) 65%)'
                        : r.position <= 3
                          ? 'linear-gradient(135deg, rgba(245,158,11,0.10) 0%, rgba(255,255,255,0.045) 70%)'
                          : 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255, 255, 255, 0.12)',
                    boxShadow: '0 12px 34px rgba(0,0,0,0.30)',
                    position: 'relative',
                    overflow: 'hidden',
                    '&::before': {
                      content: '""',
                      position: 'absolute',
                      inset: -1,
                      background:
                        r.position <= 3
                          ? 'radial-gradient(520px circle at 20% 0%, rgba(251,191,36,0.16), transparent 55%)'
                          : 'radial-gradient(520px circle at 20% 0%, rgba(16,185,129,0.12), transparent 55%)',
                      pointerEvents: 'none',
                    },
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, minWidth: 0, flex: 1 }}>
                      <Box
                        sx={{
                          width: 28,
                          height: 28,
                          borderRadius: '50%',
                          position: 'relative',
                          overflow: 'hidden',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          background: rank.bg,
                          color: rank.fg,
                          fontWeight: 900,
                          fontSize: '0.8rem',
                          flexShrink: 0,
                          boxShadow: `0 0 0 2px ${rank.ring}, 0 10px 20px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.25)`,
                          border: '1px solid rgba(255,255,255,0.20)',
                          '&::after': {
                            content: '""',
                            position: 'absolute',
                            inset: 0,
                            background: 'linear-gradient(180deg, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.10) 45%, rgba(255,255,255,0.00) 100%)',
                            opacity: 0.22,
                            pointerEvents: 'none',
                          },
                        }}
                      >
                        {rank.label}
                      </Box>
                      {r.logo ? (
                        <Box
                          component="img"
                          src={r.logo}
                          alt={r.teamName}
                          referrerPolicy="no-referrer"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none';
                          }}
                          sx={{
                            width: 52,
                            height: 52,
                            objectFit: 'contain',
                            display: 'block',
                            flexShrink: 0,
                            borderRadius: 1.6,
                          }}
                        />
                      ) : (
                        <Box sx={{ width: 52, height: 52, display: 'grid', placeItems: 'center', flexShrink: 0 }}>
                          <Typography sx={{ color: 'rgba(255,255,255,0.85)', fontWeight: 900 }}>
                            {r.teamName?.[0] || '?'}
                          </Typography>
                        </Box>
                      )}
                      <Box sx={{ minWidth: 0 }}>
                        <Typography sx={{ color: 'white', fontWeight: 800, fontSize: '0.9rem' }} noWrap>
                          {r.teamName}
                        </Typography>
                        <Typography sx={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.75rem' }}>
                          W{r.wins} D{r.draws} L{r.losses}
                        </Typography>
                      </Box>
                    </Box>
                    <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                      <Typography sx={{ color: '#fbbf24', fontWeight: 900, fontSize: '1.1rem' }}>
                        {r.points}
                      </Typography>
                      <Typography sx={{ color: 'rgba(255,255,255,0.65)', fontSize: '0.7rem' }}>Pts</Typography>
                    </Box>
                  </Box>

                  {(showBonus || showForAgainst) && (
                    <Box
                      sx={{
                        display: 'grid',
                        gridTemplateColumns: `repeat(${1 + (showBonus ? 1 : 0) + (showForAgainst ? 2 : 0)}, minmax(0, 1fr))`,
                        gap: 1,
                        mt: 1.25,
                      }}
                    >
                      <Box sx={{ textAlign: 'center', p: 0.75, borderRadius: 1.75, border: '1px solid rgba(255,255,255,0.10)', backgroundColor: 'rgba(0,0,0,0.10)' }}>
                        <Typography sx={{ color: 'rgba(255,255,255,0.65)', fontSize: '0.66rem' }}>P</Typography>
                        <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 900, fontSize: '0.9rem' }}>{r.played}</Typography>
                      </Box>
                      {showBonus && (
                        <Box sx={{ textAlign: 'center', p: 0.75, borderRadius: 1.75, border: '1px solid rgba(255,255,255,0.10)', backgroundColor: 'rgba(0,0,0,0.10)' }}>
                          <Typography sx={{ color: 'rgba(255,255,255,0.65)', fontSize: '0.66rem' }}>BP</Typography>
                          <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 900, fontSize: '0.9rem' }}>
                            {r.bonusPoints !== null ? r.bonusPoints : '—'}
                          </Typography>
                        </Box>
                      )}
                      {showForAgainst && (
                        <Box sx={{ textAlign: 'center', p: 0.75, borderRadius: 1.75, border: '1px solid rgba(255,255,255,0.10)', backgroundColor: 'rgba(0,0,0,0.10)' }}>
                          <Typography sx={{ color: 'rgba(255,255,255,0.65)', fontSize: '0.66rem' }}>PF</Typography>
                          <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 900, fontSize: '0.9rem' }}>
                            {r.pointsFor !== null ? r.pointsFor : '—'}
                          </Typography>
                        </Box>
                      )}
                      {showForAgainst && (
                        <Box sx={{ textAlign: 'center', p: 0.75, borderRadius: 1.75, border: '1px solid rgba(255,255,255,0.10)', backgroundColor: 'rgba(0,0,0,0.10)' }}>
                          <Typography sx={{ color: 'rgba(255,255,255,0.65)', fontSize: '0.66rem' }}>PD</Typography>
                          <Typography
                            sx={{
                              fontWeight: 1000,
                              fontSize: '0.9rem',
                              color: typeof r.pointsDiff === 'number' && r.pointsDiff < 0 ? '#fecaca' : '#bbf7d0',
                            }}
                          >
                            {formatSigned(r.pointsDiff)}
                          </Typography>
                        </Box>
                      )}
                    </Box>
                  )}
                </Paper>
              );
            })}
          </Box>
        ) : (
          <TableContainer
            component={Paper}
            elevation={0}
            sx={{
              position: 'relative',
              background: 'linear-gradient(135deg, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0.04) 50%, rgba(255,255,255,0.03) 100%)',
              border: '1px solid rgba(255, 255, 255, 0.14)',
              backdropFilter: 'blur(16px)',
              borderRadius: 3,
              overflow: 'hidden',
              boxShadow: '0 18px 60px rgba(0,0,0,0.35)',
              '&::-webkit-scrollbar': { height: 10 },
              '&::-webkit-scrollbar-thumb': { backgroundColor: 'rgba(255,255,255,0.18)', borderRadius: 999 },
              '&::before': {
                content: '""',
                position: 'absolute',
                inset: -1,
                background:
                  'radial-gradient(900px circle at 10% 0%, rgba(251,191,36,0.16), transparent 45%), radial-gradient(900px circle at 90% 0%, rgba(16,185,129,0.16), transparent 45%)',
                pointerEvents: 'none',
              },
            }}
          >
            <Table size="small" sx={{ width: '100%', minWidth: 0, position: 'relative', zIndex: 1 }} stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell
                    align="center"
                    sx={{
                      position: 'sticky',
                      left: 0,
                      zIndex: 3,
                      color: 'rgba(255,255,255,0.95)',
                      fontWeight: 900,
                      letterSpacing: 0.35,
                      backgroundColor: 'rgba(17, 24, 39, 0.65)',
                      borderBottom: '1px solid rgba(255,255,255,0.10)',
                      width: 72,
                      boxShadow: 'inset -1px 0 0 rgba(255,255,255,0.08)',
                    }}
                  >
                    #
                  </TableCell>
                  <TableCell
                    align="left"
                    sx={{
                      position: 'sticky',
                      left: 72,
                      zIndex: 3,
                      color: 'rgba(255,255,255,0.95)',
                      fontWeight: 900,
                      letterSpacing: 0.35,
                      backgroundColor: 'rgba(17, 24, 39, 0.65)',
                      borderBottom: '1px solid rgba(255,255,255,0.10)',
                      pl: 2,
                      minWidth: 260,
                      boxShadow: 'inset -1px 0 0 rgba(255,255,255,0.08)',
                    }}
                  >
                    Team
                  </TableCell>
                  <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.9)', fontWeight: 900, backgroundColor: 'rgba(17, 24, 39, 0.65)', borderBottom: '1px solid rgba(255,255,255,0.10)' }}>P</TableCell>
                  <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.9)', fontWeight: 900, backgroundColor: 'rgba(17, 24, 39, 0.65)', borderBottom: '1px solid rgba(255,255,255,0.10)' }}>W</TableCell>
                  <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.9)', fontWeight: 900, backgroundColor: 'rgba(17, 24, 39, 0.65)', borderBottom: '1px solid rgba(255,255,255,0.10)' }}>D</TableCell>
                  <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.9)', fontWeight: 900, backgroundColor: 'rgba(17, 24, 39, 0.65)', borderBottom: '1px solid rgba(255,255,255,0.10)' }}>L</TableCell>
                  {showBonus && (
                    <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.9)', fontWeight: 900, backgroundColor: 'rgba(17, 24, 39, 0.65)', borderBottom: '1px solid rgba(255,255,255,0.10)' }}>
                      BP
                    </TableCell>
                  )}
                  {showForAgainst && (
                    <>
                      <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.9)', fontWeight: 900, backgroundColor: 'rgba(17, 24, 39, 0.65)', borderBottom: '1px solid rgba(255,255,255,0.10)' }}>PF</TableCell>
                      <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.9)', fontWeight: 900, backgroundColor: 'rgba(17, 24, 39, 0.65)', borderBottom: '1px solid rgba(255,255,255,0.10)' }}>PA</TableCell>
                      <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.9)', fontWeight: 900, backgroundColor: 'rgba(17, 24, 39, 0.65)', borderBottom: '1px solid rgba(255,255,255,0.10)' }}>PD</TableCell>
                    </>
                  )}
                  <TableCell
                    align="center"
                    sx={{
                      color: 'rgba(255,255,255,0.95)',
                      fontWeight: 1000,
                      backgroundColor: 'rgba(17, 24, 39, 0.65)',
                      borderBottom: '1px solid rgba(255,255,255,0.10)',
                      width: 110,
                    }}
                  >
                    Pts
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((r, idx) => {
                  const rank = getRankStyle(r.position);
                  const zebra = idx % 2 === 0;
                  return (
                    <TableRow
                      key={r.key}
                      sx={{
                        backgroundColor: zebra ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.035)',
                        transition: 'background-color 160ms ease, transform 160ms ease, box-shadow 160ms ease',
                        '&:hover': {
                          backgroundColor: 'rgba(16, 185, 129, 0.08)',
                          transform: 'translateY(-1px)',
                          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), inset 0 -1px 0 rgba(255,255,255,0.06)',
                        },
                        '@media (prefers-reduced-motion: reduce)': {
                          transition: 'none',
                          '&:hover': { transform: 'none' },
                        },
                      }}
                    >
                      <TableCell
                        align="center"
                        sx={{
                          position: 'sticky',
                          left: 0,
                          zIndex: 2,
                          borderBottom: '1px solid rgba(255,255,255,0.06)',
                          py: 1.25,
                          backgroundColor: zebra ? 'rgba(17, 24, 39, 0.38)' : 'rgba(17, 24, 39, 0.46)',
                          boxShadow: 'inset -1px 0 0 rgba(255,255,255,0.06)',
                        }}
                      >
                        <Box
                          sx={{
                            width: 32,
                            height: 32,
                            borderRadius: '50%',
                            position: 'relative',
                            overflow: 'hidden',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            margin: '0 auto',
                            background: rank.bg,
                            color: rank.fg,
                            fontWeight: 900,
                            fontSize: '0.9rem',
                            boxShadow: `0 0 0 2px ${rank.ring}, 0 10px 22px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.25)`,
                            border: '1px solid rgba(255,255,255,0.20)',
                            '&::after': {
                              content: '""',
                              position: 'absolute',
                              inset: 0,
                              background: 'linear-gradient(180deg, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.10) 45%, rgba(255,255,255,0.00) 100%)',
                              opacity: 0.22,
                              pointerEvents: 'none',
                            },
                          }}
                        >
                          {rank.label}
                        </Box>
                      </TableCell>

                      <TableCell
                        align="left"
                        sx={{
                          position: 'sticky',
                          left: 72,
                          zIndex: 2,
                          color: 'rgba(255,255,255,0.92)',
                          fontWeight: 900,
                          borderBottom: '1px solid rgba(255,255,255,0.06)',
                          pl: 2,
                          py: 1.25,
                          minWidth: 260,
                          backgroundColor: zebra ? 'rgba(17, 24, 39, 0.38)' : 'rgba(17, 24, 39, 0.46)',
                          boxShadow: 'inset -1px 0 0 rgba(255,255,255,0.06)',
                        }}
                      >
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
                          {r.logo ? (
                            <Box
                              component="img"
                              src={r.logo}
                              alt={r.teamName}
                              referrerPolicy="no-referrer"
                              onError={(e) => {
                                e.currentTarget.style.display = 'none';
                              }}
                              sx={{
                                width: 58,
                                height: 58,
                                objectFit: 'contain',
                                display: 'block',
                                flexShrink: 0,
                                borderRadius: 1.75,
                              }}
                            />
                          ) : (
                            <Box sx={{ width: 58, height: 58, display: 'grid', placeItems: 'center', flexShrink: 0 }}>
                              <Typography sx={{ color: 'rgba(255,255,255,0.85)', fontWeight: 900 }}>
                                {r.teamName?.[0] || '?'}
                              </Typography>
                            </Box>
                          )}
                          <Box sx={{ minWidth: 0 }}>
                            <Typography sx={{ color: 'rgba(255,255,255,0.98)', fontWeight: 950, letterSpacing: 0.2 }} noWrap>
                              {r.teamName}
                            </Typography>
                            <Typography sx={{ color: 'rgba(255,255,255,0.68)', fontSize: '0.78rem', letterSpacing: 0.1 }} noWrap>
                              W {r.wins} • D {r.draws} • L {r.losses}
                            </Typography>
                          </Box>
                        </Box>
                      </TableCell>

                      <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.82)', borderBottom: '1px solid rgba(255,255,255,0.06)', py: 1.25 }}>{r.played}</TableCell>
                      <TableCell align="center" sx={{ color: '#d1fae5', borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 800, py: 1.25 }}>{r.wins}</TableCell>
                      <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.82)', borderBottom: '1px solid rgba(255,255,255,0.06)', py: 1.25 }}>{r.draws}</TableCell>
                      <TableCell align="center" sx={{ color: '#fee2e2', borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 800, py: 1.25 }}>{r.losses}</TableCell>

                      {showBonus && (
                        <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.82)', borderBottom: '1px solid rgba(255,255,255,0.06)', py: 1.25 }}>
                          {r.bonusPoints !== null ? r.bonusPoints : '—'}
                        </TableCell>
                      )}

                      {showForAgainst && (
                        <>
                          <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.82)', borderBottom: '1px solid rgba(255,255,255,0.06)', py: 1.25 }}>
                            {r.pointsFor !== null ? r.pointsFor : '—'}
                          </TableCell>
                          <TableCell align="center" sx={{ color: 'rgba(255,255,255,0.82)', borderBottom: '1px solid rgba(255,255,255,0.06)', py: 1.25 }}>
                            {r.pointsAgainst !== null ? r.pointsAgainst : '—'}
                          </TableCell>
                          <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', py: 1.25 }}>
                            <Tooltip title="Points difference" placement="top" arrow>
                              <Typography
                                sx={{
                                  display: 'inline-block',
                                  px: 1.2,
                                  py: 0.35,
                                  borderRadius: 999,
                                  fontWeight: 900,
                                  fontSize: '0.82rem',
                                  color: typeof r.pointsDiff === 'number' && r.pointsDiff < 0 ? '#fee2e2' : '#d1fae5',
                                  backgroundColor: typeof r.pointsDiff === 'number' && r.pointsDiff < 0 ? 'rgba(239,68,68,0.14)' : 'rgba(16,185,129,0.16)',
                                  border: '1px solid rgba(255,255,255,0.10)',
                                }}
                              >
                                {typeof r.pointsDiff === 'number' ? `${r.pointsDiff > 0 ? '+' : ''}${r.pointsDiff}` : '—'}
                              </Typography>
                            </Tooltip>
                          </TableCell>
                        </>
                      )}

                      <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', py: 1.25 }}>
                        <Typography
                          sx={{
                            display: 'inline-block',
                            minWidth: 46,
                            textAlign: 'center',
                            px: 1.2,
                            py: 0.45,
                            borderRadius: 999,
                            fontWeight: 1000,
                            color: '#fbbf24',
                            backgroundColor: 'rgba(251, 191, 36, 0.10)',
                            border: '1px solid rgba(251, 191, 36, 0.18)',
                          }}
                        >
                          {r.points}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Box>
    );
  };

  return (
    <Box sx={{ width: '100%', mb: 3 }}>
      <Box sx={{ px: { xs: 0, sm: 0.5, md: 0.75 }, py: { xs: 0, sm: 0.5 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', flexDirection: { xs: 'column', sm: 'row' }, gap: 1.2, mb: 1.5 }}>
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              alignItems: 'center',
              justifyContent: { xs: 'center', sm: 'flex-start' },
              gap: { xs: 0.75, sm: 1 },
              width: { xs: '100%', sm: 'auto' },
            }}
          >
            {getLeagueLogo(standings?.league) ? (
              <Box
                component="img"
                src={getLeagueLogo(standings?.league)}
                alt={leagueName || 'League'}
                referrerPolicy="no-referrer"
                onLoad={(e) => {
                  const nw = e.currentTarget.naturalWidth || 0;
                  const nh = e.currentTarget.naturalHeight || 0;
                  const minSide = Math.min(nw, nh);
                  if (!minSide) return;
                  const xs = Math.max(74, Math.min(100, Math.round(minSide * 0.17)));
                  const sm = Math.max(88, Math.min(116, xs + 12));
                  setLogoCircleSize({ xs, sm });
                }}
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                  setLogoCircleSize({ xs: 84, sm: 100 });
                }}
                sx={{
                  height: logoCircleSize.xs,
                  width: logoCircleSize.xs,
                  [theme.breakpoints.up('sm')]: {
                    width: logoCircleSize.sm,
                    height: logoCircleSize.sm,
                  },
                  objectFit: 'contain',
                  display: 'block',
                  borderRadius: { xs: 2, sm: 2.5 },
                }}
              />
            ) : (
              <Box
                sx={{
                  width: logoCircleSize.xs,
                  height: logoCircleSize.xs,
                  [theme.breakpoints.up('sm')]: {
                    width: logoCircleSize.sm,
                    height: logoCircleSize.sm,
                  },
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                <Typography sx={{ fontWeight: 1000, fontSize: { xs: '0.95rem', sm: '1.05rem' }, color: '#fef3c7', letterSpacing: 0.6 }}>
                  {getLeagueMonogram(leagueName)}
                </Typography>
              </Box>
            )}
            <Box sx={{ textAlign: { xs: 'center', sm: 'left' } }}>
              <Typography
                variant="h5"
                sx={{
                  fontWeight: 1100,
                  color: 'white',
                  fontSize: { xs: '1.18rem', sm: '1.65rem', md: '1.8rem' },
                  letterSpacing: 0.25,
                  textShadow: '0 12px 40px rgba(0,0,0,0.55)',
                }}
              >
                <Box
                  component="span"
                  sx={{
                    background: 'linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(251,191,36,0.86) 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    backgroundClip: 'text',
                  }}
                >
                  {leagueName || 'League'} Standings
                </Box>
              </Typography>
            </Box>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: { xs: 'center', sm: 'flex-start' }, gap: 1, flexWrap: 'wrap', ml: { xs: 0, sm: 'auto' }, width: { xs: '100%', sm: 'auto' } }}>
            {standings.league?.season && (
              <Chip
                label={`Season ${standings.league.season}`}
                size="small"
                sx={{
                  backgroundColor: 'rgba(255, 255, 255, 0.10)',
                  color: 'rgba(255,255,255,0.88)',
                  border: '1px solid rgba(255,255,255,0.14)',
                }}
              />
            )}
            <Chip
              label={`${teams.length} teams`}
              size="small"
              sx={{
                backgroundColor: 'rgba(255, 255, 255, 0.08)',
                color: 'rgba(255,255,255,0.82)',
                border: '1px solid rgba(255,255,255,0.12)',
              }}
            />
          </Box>
        </Box>

        <Divider sx={{ borderColor: 'rgba(255,255,255,0.12)', mb: 2 }} />

        {/* Multi-group support (some leagues split tables) */}
        {groups.length > 1 ? (
          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            {groups.map((g, idx) => renderGroup(g, idx))}
          </Box>
        ) : (
          renderGroup(group, 0)
        )}
      </Box>
    </Box>
  );
};

export default LeagueStandings;

