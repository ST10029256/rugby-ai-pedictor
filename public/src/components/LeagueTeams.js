import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Chip,
  Grid,
  Paper,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { TabLoadingScreen } from '../utils/viewLoader';
import { getLeagueLineupMatches, getLeagueStandings, getUpcomingMatches } from '../firebase';
import { getPrimaryStandingsSeasonYear } from '../utils/season';
import {
  buildTeamLogoMapFromStandings,
  canonicalTeamKey,
  dedupeTeams,
  extractTeamsFromStandings,
  getHighlightlyLeagueId,
  getStaticLeagueTeams,
  mergeTeamsIntoMap,
  readStandingsCache,
  readStandingsLogoCache,
} from '../utils/teamLogos';
import TeamLogoImage from './TeamLogoImage';

const LUX = {
  accent: '#10b981',
  gold: '#f4e4bc',
  goldSoft: 'rgba(214,185,122,0.32)',
  goldLine: 'rgba(245,225,170,0.7)',
  border: 'rgba(255,255,255,0.10)',
  borderStrong: 'rgba(255,255,255,0.14)',
  text: 'rgba(255,255,255,0.92)',
  sub: 'rgba(255,255,255,0.70)',
  muted: 'rgba(255,255,255,0.55)',
};

const NO_STANDINGS_LEAGUES = new Set([5479]);

const normKey = canonicalTeamKey;

const getLeagueMonogram = (name) => {
  const raw = String(name || '').trim();
  if (!raw) return 'T';
  const words = raw.replace(/[^a-zA-Z0-9\s]/g, ' ').split(/\s+/).filter(Boolean);
  const significant = words.filter((w) => w.length > 2);
  const pick = (significant.length ? significant : words).slice(0, 3);
  const letters = pick.map((w) => w[0]?.toUpperCase()).filter(Boolean);
  return letters.join('') || raw.slice(0, 2).toUpperCase();
};

const teamsAlertSx = {
  borderRadius: 2.5,
  bgcolor: 'rgba(255, 255, 255, 0.04)',
  border: `1px solid ${LUX.border}`,
  color: LUX.text,
  backdropFilter: 'blur(8px)',
  '& .MuiAlert-icon': { color: LUX.accent },
  '& .MuiAlert-message': { color: LUX.sub },
};

function addTeamsFromMatches(teamMap, matches, source) {
  for (const match of matches || []) {
    for (const side of [
      { nameKeys: ['home_team', 'home_team_name', 'homeTeam'], logoKeys: ['home_logo', 'home_team_logo'] },
      { nameKeys: ['away_team', 'away_team_name', 'awayTeam'], logoKeys: ['away_logo', 'away_team_logo'] },
    ]) {
      const name = side.nameKeys.map((key) => match?.[key]).find(Boolean);
      if (!name) continue;
      const key = normKey(name);
      const logo = side.logoKeys.map((keyName) => match?.[keyName]).find(Boolean) || null;
      if (key && teamMap.has(key)) {
        const existing = teamMap.get(key);
        if (!existing.logo && logo) teamMap.set(key, { ...existing, logo });
        continue;
      }
      if (!key || teamMap.has(key)) continue;
      teamMap.set(key, { name: String(name).trim(), logo, source });
    }
  }
}

/** Mobile / small screens: compact team tile for 2-column grid */
const TeamRow = ({ team, leagueId, logoMap }) => (
  <Paper
    elevation={0}
    sx={{
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 1,
      width: '100%',
      height: '100%',
      minHeight: 118,
      px: 1,
      py: 1.25,
      borderRadius: 2.5,
      overflow: 'hidden',
      textAlign: 'center',
      background:
        'linear-gradient(165deg, rgba(15,23,42,0.94) 0%, rgba(17,24,39,0.92) 48%, rgba(2,6,23,0.96) 100%)',
      border: '1px solid rgba(214,185,122,0.22)',
      boxShadow: '0 8px 24px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,250,236,0.05)',
      '&::before': {
        content: '""',
        position: 'absolute',
        top: 0,
        left: 12,
        right: 12,
        height: 2,
        borderRadius: '0 0 3px 3px',
        background: 'linear-gradient(90deg, transparent, rgba(245,225,170,0.75), transparent)',
      },
    }}
  >
    <Box
      sx={{
        width: 52,
        height: 52,
        flexShrink: 0,
        borderRadius: '14px',
        display: 'grid',
        placeItems: 'center',
        background:
          'radial-gradient(circle at 30% 25%, rgba(245,225,170,0.14), rgba(0,0,0,0.32) 70%)',
        border: '1px solid rgba(214,185,122,0.28)',
        boxShadow: 'inset 0 1px 0 rgba(255,250,236,0.1), 0 6px 14px rgba(0,0,0,0.28)',
      }}
    >
      <TeamLogoImage
        teamName={team.name}
        leagueId={leagueId}
        logoMap={logoMap}
        explicitLogo={team.logo}
        size={34}
      />
    </Box>

    <Typography
      sx={{
        color: '#f8fafc',
        fontWeight: 800,
        fontSize: '0.82rem',
        lineHeight: 1.25,
        letterSpacing: '-0.01em',
        px: 0.25,
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
        wordBreak: 'break-word',
      }}
    >
      {team.name}
    </Typography>
  </Paper>
);

/** Desktop: crest cards in a grid */
const TeamCard = ({ team, leagueId, logoMap }) => (
  <Paper
    elevation={0}
    sx={{
      p: 2.25,
      height: '100%',
      borderRadius: 3,
      background:
        'linear-gradient(165deg, rgba(15,23,42,0.94) 0%, rgba(17,24,39,0.96) 48%, rgba(2,6,23,0.98) 100%)',
      border: '1px solid rgba(214,185,122,0.22)',
      boxShadow: '0 10px 28px rgba(0,0,0,0.32), inset 0 1px 0 rgba(255,250,236,0.06)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 1.5,
      textAlign: 'center',
      transition: 'transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease',
      '&:hover': {
        transform: 'translateY(-4px)',
        borderColor: 'rgba(214,185,122,0.45)',
        boxShadow: '0 14px 44px rgba(0,0,0,0.38)',
      },
    }}
  >
    <TeamLogoImage teamName={team.name} leagueId={leagueId} logoMap={logoMap} explicitLogo={team.logo} />
    <Typography
      sx={{
        color: '#f8fafc',
        fontWeight: 800,
        fontSize: '0.98rem',
        lineHeight: 1.3,
        px: 0.5,
      }}
    >
      {team.name}
    </Typography>
  </Paper>
);

const LeagueTeams = ({ leagueId, leagueName }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [teams, setTeams] = useState([]);
  const [teamLogoMap, setTeamLogoMap] = useState({});
  const isCompact = useMediaQuery('(max-width:899.95px)');

  const seasonYear = useMemo(
    () => (leagueId ? getPrimaryStandingsSeasonYear(leagueId) : null),
    [leagueId]
  );

  useEffect(() => {
    if (!leagueId) {
      setTeams([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setTeams([]);

    const publishTeams = (teamMap, logoMap) => {
      if (cancelled) return;
      const list = dedupeTeams(Array.from(teamMap.values()), leagueId);
      setTeamLogoMap(logoMap);
      setTeams(list);
      setError(list.length ? null : `No teams found for ${leagueName || 'this league'} yet.`);
      setLoading(false);
    };

    const load = async () => {
      const teamMap = new Map();
      let logoMap = { ...readStandingsLogoCache(leagueId) };

      const cachedPayload = readStandingsCache(leagueId);
      if (cachedPayload?.standings) {
        logoMap = { ...logoMap, ...buildTeamLogoMapFromStandings(cachedPayload.standings) };
        if (!NO_STANDINGS_LEAGUES.has(Number(leagueId))) {
          mergeTeamsIntoMap(teamMap, extractTeamsFromStandings(cachedPayload.standings, 'cache'), 'cache');
        }
      }

      if (teamMap.size === 0) {
        mergeTeamsIntoMap(teamMap, getStaticLeagueTeams(leagueId), 'static');
      }

      if (teamMap.size > 0) {
        publishTeams(teamMap, logoMap);
      }

      const hlId = getHighlightlyLeagueId(leagueId);
      const useStandingsForList = hlId && !NO_STANDINGS_LEAGUES.has(Number(leagueId));

      if (hlId && useStandingsForList) {
        try {
          const data = await getLeagueStandings({
            sportsdbLeagueId: leagueId,
            highlightlyLeagueId: hlId,
            leagueName,
            season: seasonYear,
            forceRefresh: false,
          });
          if (data?.success && data?.standings) {
            logoMap = { ...logoMap, ...buildTeamLogoMapFromStandings(data.standings) };
            mergeTeamsIntoMap(teamMap, extractTeamsFromStandings(data.standings, 'standings'), 'standings');
          }
        } catch (e) {
          // fall through to fixtures
        }
      }

      if (teamMap.size < 8) {
        try {
          const upcoming = await getUpcomingMatches({ league_id: leagueId, limit: 100 });
          const rows = upcoming?.data?.matches || [];
          addTeamsFromMatches(teamMap, rows, 'upcoming');
        } catch (e) {
          // ignore
        }
      }

      if (teamMap.size < 8) {
        for (const scope of ['upcoming', 'historic']) {
          try {
            const data = await getLeagueLineupMatches({
              sportsdbLeagueId: leagueId,
              matchScope: scope,
            });
            const rows = Array.isArray(data?.matches) ? data.matches : [];
            addTeamsFromMatches(teamMap, rows, scope);
          } catch (e) {
            // ignore
          }
        }
      }

      publishTeams(teamMap, logoMap);
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [leagueId, leagueName, seasonYear]);

  if (loading) {
    return <TabLoadingScreen label="Loading teams..." />;
  }

  if (error || !teams.length) {
    return (
      <Alert severity="info" sx={teamsAlertSx}>
        {error || `No teams found for ${leagueName || 'this league'}.`}
      </Alert>
    );
  }

  return (
    <Box
      sx={{
        width: '100%',
        maxWidth: '100%',
        boxSizing: 'border-box',
      }}
    >
      <Paper
        elevation={0}
        sx={{
          p: { xs: 1.25, sm: 1.6 },
          mb: { xs: 2, sm: 2.5 },
          borderRadius: 3,
          border: `1px solid ${LUX.goldSoft}`,
          background:
            'linear-gradient(165deg, rgba(15,23,42,0.94) 0%, rgba(17,24,39,0.96) 48%, rgba(2,6,23,0.98) 100%)',
          boxShadow:
            '0 2px 0 rgba(255,240,212,0.12), 0 12px 28px rgba(2,6,23,0.45), inset 0 1px 0 rgba(255,250,236,0.08)',
          position: 'relative',
          overflow: 'hidden',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 3,
            background: `linear-gradient(90deg, rgba(214,185,122,0.08), ${LUX.goldLine}, rgba(214,185,122,0.08))`,
          },
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: { xs: 1, sm: 1.25 },
            flexWrap: 'nowrap',
            minWidth: 0,
          }}
        >
          <Box
            sx={{
              width: { xs: 42, sm: 46 },
              height: { xs: 42, sm: 46 },
              flexShrink: 0,
              borderRadius: 2.2,
              display: 'grid',
              placeItems: 'center',
              background:
                'linear-gradient(135deg, rgba(251,191,36,0.26) 0%, rgba(255,255,255,0.08) 100%)',
              border: '1px solid rgba(255,255,255,0.14)',
              color: '#fef3c7',
              fontWeight: 1000,
              letterSpacing: 0.7,
              fontSize: { xs: '0.78rem', sm: '0.85rem' },
              boxShadow: 'inset 0 1px 0 rgba(255,250,236,0.18)',
            }}
            title={leagueName || 'Teams'}
          >
            {getLeagueMonogram(leagueName)}
          </Box>

          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography
              component="h2"
              sx={{
                color: '#f8fafc',
                fontWeight: 900,
                fontSize: { xs: '1.05rem', sm: '1.2rem' },
                letterSpacing: 0.2,
                lineHeight: 1.2,
              }}
            >
              <Box
                component="span"
                sx={{
                  background:
                    'linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(251,191,36,0.86) 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                Teams
              </Box>
            </Typography>
            <Typography
              sx={{
                color: '#a7b2c7',
                fontSize: { xs: '0.72rem', sm: '0.8rem' },
                mt: 0.2,
                lineHeight: 1.25,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {leagueName ? `${leagueName} · every side` : 'Every side in this competition'}
            </Typography>
          </Box>

          <Chip
            label={`${teams.length}`}
            size="small"
            sx={{
              flexShrink: 0,
              minWidth: 36,
              background:
                'linear-gradient(135deg, rgba(193,154,79,0.2), rgba(245,225,170,0.14))',
              border: '1px solid rgba(214,185,122,0.45)',
              color: LUX.gold,
              fontWeight: 800,
              '& .MuiChip-label': {
                px: 1.1,
              },
            }}
          />
        </Box>
      </Paper>

      {isCompact ? (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
            gap: 1.1,
            width: '100%',
          }}
        >
          {teams.map((team) => (
            <TeamRow
              key={normKey(team.name)}
              team={team}
              leagueId={leagueId}
              logoMap={teamLogoMap}
            />
          ))}
        </Box>
      ) : (
        <Grid container spacing={{ md: 2.25 }}>
          {teams.map((team) => (
            <Grid item md={3} lg={2} key={normKey(team.name)}>
              <TeamCard team={team} leagueId={leagueId} logoMap={teamLogoMap} />
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
};

export default LeagueTeams;
