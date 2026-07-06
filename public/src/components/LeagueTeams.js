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
  getHighlightlyLeagueId,
  readStandingsLogoCache,
  resolveTeamLogoUrl,
} from '../utils/teamLogos';

const LUX = {
  accent: '#10b981',
  border: 'rgba(255,255,255,0.10)',
  borderStrong: 'rgba(255,255,255,0.14)',
  text: 'rgba(255,255,255,0.92)',
  sub: 'rgba(255,255,255,0.70)',
  muted: 'rgba(255,255,255,0.55)',
};

const NO_STANDINGS_LEAGUES = new Set([5479, 5480]);

const normKey = (name) =>
  String(name || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

function extractTeamsFromStandings(standings) {
  const out = [];
  const seen = new Set();
  if (!standings || !Array.isArray(standings.groups)) return out;

  for (const group of standings.groups) {
    const rows = group?.standings || group?.teams || [];
    for (const row of rows) {
      const team = row?.team || row || {};
      const name = team.name || team.team_name || team.strTeam || row.teamName;
      if (!name) continue;
      const key = normKey(name);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push({
        name: String(name).trim(),
        logo: team.logo || team.badge || team.image || row.logo || row.badge || null,
        source: 'standings',
      });
    }
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

function addTeamsFromMatches(teamMap, matches, source) {
  for (const match of matches || []) {
    for (const side of ['home_team', 'away_team']) {
      const name = match?.[side];
      if (!name) continue;
      const key = normKey(name);
      if (!key || teamMap.has(key)) continue;
      teamMap.set(key, { name: String(name).trim(), logo: null, source });
    }
  }
}

const TeamCard = ({ team, leagueId, logoMap }) => {
  const logo =
    team.logo ||
    resolveTeamLogoUrl(team.name, { leagueId, logoMap }) ||
    null;
  const [failed, setFailed] = useState(false);

  return (
    <Paper
      elevation={0}
      sx={{
        p: { xs: 1.5, sm: 2 },
        height: '100%',
        borderRadius: 3,
        background: 'linear-gradient(180deg, rgba(255,255,255,0.045) 0%, rgba(0,0,0,0.12) 100%)',
        border: `1px solid ${LUX.border}`,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 1.25,
        textAlign: 'center',
      }}
    >
      {logo && !failed ? (
        <Box
          component="img"
          src={logo}
          alt={team.name}
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          sx={{
            width: { xs: 56, sm: 72 },
            height: { xs: 56, sm: 72 },
            objectFit: 'contain',
            filter: 'drop-shadow(0 8px 16px rgba(0,0,0,0.45))',
          }}
        />
      ) : (
        <Box
          sx={{
            width: { xs: 56, sm: 72 },
            height: { xs: 56, sm: 72 },
            borderRadius: '50%',
            display: 'grid',
            placeItems: 'center',
            bgcolor: 'rgba(255,255,255,0.08)',
            border: '2px solid rgba(255,255,255,0.15)',
            fontWeight: 900,
            color: '#fff',
            fontSize: { xs: '1.4rem', sm: '1.75rem' },
          }}
        >
          {team.name.charAt(0)}
        </Box>
      )}
      <Typography
        sx={{
          color: LUX.text,
          fontWeight: 800,
          fontSize: { xs: '0.92rem', sm: '1rem' },
          lineHeight: 1.25,
        }}
      >
        {team.name}
      </Typography>
    </Paper>
  );
};

const LeagueTeams = ({ leagueId, leagueName }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [teams, setTeams] = useState([]);
  const [teamLogoMap, setTeamLogoMap] = useState({});
  const [sourcesUsed, setSourcesUsed] = useState([]);

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
    setSourcesUsed([]);

    const cached = readStandingsLogoCache(leagueId);
    if (Object.keys(cached).length) setTeamLogoMap(cached);

    const load = async () => {
      const used = [];
      const teamMap = new Map();
      let logoMap = { ...cached };

      const hlId = getHighlightlyLeagueId(leagueId);
      const tryStandings = hlId && !NO_STANDINGS_LEAGUES.has(Number(leagueId));

      if (tryStandings) {
        try {
          const data = await getLeagueStandings({
            sportsdbLeagueId: leagueId,
            highlightlyLeagueId: hlId,
            leagueName,
            season: seasonYear,
            forceRefresh: false,
          });
          if (data?.success && data?.standings) {
            const fromStandings = extractTeamsFromStandings(data.standings);
            logoMap = { ...logoMap, ...buildTeamLogoMapFromStandings(data.standings) };
            for (const team of fromStandings) {
              const key = normKey(team.name);
              if (key) teamMap.set(key, team);
            }
            if (fromStandings.length) used.push('standings');
          }
        } catch (e) {
          // fall through to fixtures
        }
      }

      if (teamMap.size === 0) {
        try {
          const upcoming = await getUpcomingMatches({ league_id: leagueId, limit: 100 });
          const rows = upcoming?.data?.matches || [];
          addTeamsFromMatches(teamMap, rows, 'upcoming');
          if (rows.length) used.push('upcoming fixtures');
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
            const before = teamMap.size;
            addTeamsFromMatches(teamMap, rows, scope);
            if (teamMap.size > before) used.push(`${scope} lineups`);
          } catch (e) {
            // ignore
          }
        }
      }

      if (cancelled) return;

      const list = Array.from(teamMap.values()).sort((a, b) => a.name.localeCompare(b.name));
      setTeamLogoMap(logoMap);
      setTeams(list);
      setSourcesUsed([...new Set(used)]);
      if (!list.length) {
        setError(`No teams found for ${leagueName || 'this league'} yet.`);
      }
      setLoading(false);
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
      <Box sx={{ p: { xs: 1.5, sm: 2.5 } }}>
        <Alert severity="info" sx={{ borderRadius: 2 }}>
          {error || `No teams found for ${leagueName || 'this league'}.`}
        </Alert>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        width: '100%',
        maxWidth: '100%',
        p: { xs: 1.25, sm: 2.5, md: 3.5 },
        boxSizing: 'border-box',
      }}
    >
      <Box sx={{ textAlign: 'center', mb: { xs: 2, sm: 2.5 } }}>
        <Typography
          component="h2"
          sx={{
            fontSize: { xs: '1.35rem', sm: '1.75rem' },
            fontWeight: 900,
            color: LUX.text,
            letterSpacing: '0.02em',
          }}
        >
          {leagueName || 'League'} Teams
        </Typography>
        <Typography sx={{ color: LUX.sub, mt: 0.75, fontSize: '0.92rem' }}>
          All sides competing in this league
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center', flexWrap: 'wrap', mt: 1.5 }}>
          <Chip
            label={`${teams.length} teams`}
            size="small"
            sx={{
              bgcolor: 'rgba(16,185,129,0.14)',
              color: LUX.accent,
              border: '1px solid rgba(16,185,129,0.28)',
              fontWeight: 700,
            }}
          />
          {sourcesUsed.map((source) => (
            <Chip
              key={source}
              label={source}
              size="small"
              sx={{
                bgcolor: 'rgba(255,255,255,0.06)',
                color: LUX.muted,
                border: `1px solid ${LUX.border}`,
                fontWeight: 600,
              }}
            />
          ))}
        </Box>
      </Box>

      <Grid container spacing={{ xs: 1.5, sm: 2 }}>
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
