import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Chip,
  Grid,
  Paper,
  Typography,
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
  border: 'rgba(255,255,255,0.10)',
  borderStrong: 'rgba(255,255,255,0.14)',
  text: 'rgba(255,255,255,0.92)',
  sub: 'rgba(255,255,255,0.70)',
  muted: 'rgba(255,255,255,0.55)',
};

const NO_STANDINGS_LEAGUES = new Set([5479, 5480]);

const normKey = canonicalTeamKey;

const headingRuleSx = {
  width: { xs: 72, sm: 96 },
  height: 3,
  mx: 'auto',
  mt: 1.25,
  borderRadius: 999,
  background: 'linear-gradient(90deg, transparent, rgba(16,185,129,0.85), transparent)',
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

const TeamCard = ({ team, leagueId, logoMap }) => (
  <Paper
    elevation={0}
    sx={{
      p: { xs: 2, sm: 2.25 },
      height: '100%',
      borderRadius: 3,
      background: 'linear-gradient(180deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.14) 100%)',
      border: `1px solid ${LUX.border}`,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 1.5,
      textAlign: 'center',
      transition: 'transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease',
      '&:hover': {
        transform: 'translateY(-4px)',
        borderColor: 'rgba(16,185,129,0.32)',
        boxShadow: '0 14px 44px rgba(0,0,0,0.38)',
      },
    }}
  >
    <TeamLogoImage teamName={team.name} leagueId={leagueId} logoMap={logoMap} explicitLogo={team.logo} />
    <Typography
      sx={{
        color: LUX.text,
        fontWeight: 800,
        fontSize: { xs: '0.9rem', sm: '0.98rem' },
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
      <Box sx={{ textAlign: 'center', mb: { xs: 2.5, sm: 3 } }}>
        <Typography
          component="p"
          sx={{
            color: LUX.muted,
            fontWeight: 800,
            fontSize: { xs: '0.62rem', sm: '0.68rem' },
            letterSpacing: { xs: 2.8, sm: 3.2 },
            textTransform: 'uppercase',
          }}
        >
          {leagueName || 'League'}
        </Typography>
        <Typography
          component="h2"
          sx={{
            fontSize: { xs: '1.45rem', sm: '1.85rem' },
            fontWeight: 900,
            color: LUX.text,
            letterSpacing: '0.02em',
            mt: 0.75,
          }}
        >
          Teams
        </Typography>
        <Typography sx={{ color: LUX.sub, mt: 0.85, fontSize: { xs: '0.88rem', sm: '0.95rem' } }}>
          Every side in this competition
        </Typography>
        <Box sx={headingRuleSx} />
        <Chip
          label={`${teams.length} teams`}
          size="small"
          sx={{
            mt: 1.75,
            bgcolor: 'rgba(16,185,129,0.14)',
            color: LUX.accent,
            border: '1px solid rgba(16,185,129,0.28)',
            fontWeight: 700,
          }}
        />
      </Box>

      <Grid container spacing={{ xs: 1.5, sm: 2, md: 2.25 }}>
        {teams.map((team) => (
          <Grid item xs={6} sm={4} md={3} lg={2} key={normKey(team.name)}>
            <TeamCard team={team} leagueId={leagueId} logoMap={teamLogoMap} />
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

export default LeagueTeams;
