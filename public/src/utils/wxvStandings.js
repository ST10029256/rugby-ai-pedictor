import { LEAGUE_IDS, WXV_GLOBAL_SERIES_FROM_YEAR } from './leagues';

export { WXV_GLOBAL_SERIES_FROM_YEAR };

export const WXV_GLOBAL_SERIES_TEAMS = [
  'Australia Women',
  'Canada Women',
  'England Women',
  'France Women',
  'Ireland Women',
  'Italy Women',
  'Japan Women',
  'New Zealand Women',
  'Scotland Women',
  'South Africa Women',
  'USA Women',
  'Wales Women',
];

export function wxvTeamKey(name) {
  const raw = String(name || '')
    .toLowerCase()
    .replace(/women'?s?/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
  if (raw === 'united states' || raw === 'usa' || raw === 'us') return 'usa';
  return raw;
}

function emptyRow(name) {
  return {
    position: 0,
    team: { id: 0, name },
    name,
    points: 0,
    gamesPlayed: 0,
    played: 0,
    wins: 0,
    draws: 0,
    loses: 0,
    losses: 0,
    scoredPoints: 0,
    pointsFor: 0,
    receivedPoints: 0,
    pointsAgainst: 0,
    pointsDifference: 0,
    pointsDiff: 0,
    bonusPoints: 0,
  };
}

function rankRows(rows) {
  const ordered = [...rows].sort((a, b) => {
    const pts = (Number(b.points) || 0) - (Number(a.points) || 0);
    if (pts) return pts;
    const pd =
      (Number(b.pointsDifference ?? b.pointsDiff) || 0) -
      (Number(a.pointsDifference ?? a.pointsDiff) || 0);
    if (pd) return pd;
    const pf =
      (Number(b.scoredPoints ?? b.pointsFor) || 0) -
      (Number(a.scoredPoints ?? a.pointsFor) || 0);
    if (pf) return pf;
    const wins = (Number(b.wins) || 0) - (Number(a.wins) || 0);
    if (wins) return wins;
    const aName = String(a.team?.name || a.name || '');
    const bName = String(b.team?.name || b.name || '');
    return aName.localeCompare(bName);
  });
  ordered.forEach((row, idx) => {
    row.position = idx + 1;
  });
  return ordered;
}

export function padWxvStandings(standings, leagueId, seasonYear) {
  if (!standings || typeof standings !== 'object') return standings;
  const year = Number(seasonYear ?? standings.league?.season);
  if (Number(leagueId) !== LEAGUE_IDS.WXV_1 || year < WXV_GLOBAL_SERIES_FROM_YEAR) {
    return standings;
  }

  const groups = Array.isArray(standings.groups) ? standings.groups.map((group) => ({ ...group })) : [{ standings: [] }];
  const group = groups[0];
  const listKey = Array.isArray(group.teams) && !Array.isArray(group.standings) ? 'teams' : 'standings';
  const rows = [...(group[listKey] || [])];
  const seen = new Set(rows.map((row) => wxvTeamKey(row?.team?.name || row?.name)));
  WXV_GLOBAL_SERIES_TEAMS.forEach((name) => {
    const key = wxvTeamKey(name);
    if (seen.has(key)) return;
    seen.add(key);
    rows.push(emptyRow(name));
  });
  group[listKey] = rankRows(rows);
  if (!group.name) group.name = 'Global Series';

  return {
    ...standings,
    groups,
  };
}

export function standingsSeasonYear(standings) {
  const raw = standings?.league?.season ?? standings?.league?.season_label;
  const year = Number(String(raw || '').slice(0, 4));
  return Number.isFinite(year) ? year : null;
}

export function wxvStandingsForView(standings, leagueId, seasonYear) {
  if (!standings) return null;
  return padWxvStandings(standings, leagueId, seasonYear);
}
