/**
 * League-scoped display labels so odds/predictions match standings names.
 *
 * Each Currie Cup province now has its own identity in the database, so these
 * are labels only. Short URC-style names (Lions, Bulls) still appear from odds
 * feeds and older records, hence the aliases.
 */

const CURRIE_CUP_LEAGUE_ID = 5069;

/** normalized key -> standings-style display label */
const CURRIE_CUP_DISPLAY = {
  lions: 'Golden Lions',
  goldenlions: 'Golden Lions',
  bulls: 'Blue Bulls',
  bluebulls: 'Blue Bulls',
  sharks: 'Sharks XV',
  sharksxv: 'Sharks XV',
  sharkscurriecup: 'Sharks XV',
  stormers: 'Western Province',
  stormersxxiii: 'Western Province',
  stormersxiii: 'Western Province',
  westernprovince: 'Western Province',
  boland: 'Boland',
  bolandcavaliers: 'Boland',
  freestatecheetahs: 'Cheetahs',
  cheetahs: 'Cheetahs',
  pumas: 'Pumas',
  mrunewnationpumas: 'Pumas',
  newnationpumas: 'Pumas',
  griquas: 'Griquas',
};

/**
 * Any label -> the name the database and model use for that province.
 * These are separate teams from the URC/Super Rugby franchises that share a
 * short name, so a Currie Cup fixture must never be sent to the model as
 * "Bulls" or "Sharks".
 */
const CURRIE_CUP_MODEL = {
  lions: 'Golden Lions',
  goldenlions: 'Golden Lions',
  bulls: 'Blue Bulls',
  bluebulls: 'Blue Bulls',
  sharks: 'Sharks XV',
  sharksxv: 'Sharks XV',
  sharkscurriecup: 'Sharks XV',
  cheetahs: 'Free State Cheetahs',
  freestatecheetahs: 'Free State Cheetahs',
  stormers: 'Western Province',
  stormersxxiii: 'Western Province',
  stormersxiii: 'Western Province',
  westernprovince: 'Western Province',
  boland: 'Boland Cavaliers',
  bolandcavaliers: 'Boland Cavaliers',
};

function normalizeKey(name) {
  return String(name || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '');
}

export function displayTeamNameForLeague(name, leagueId) {
  const raw = String(name || '').trim();
  if (!raw) return raw;
  if (Number(leagueId) !== CURRIE_CUP_LEAGUE_ID) return raw;
  return CURRIE_CUP_DISPLAY[normalizeKey(raw)] || raw;
}

export function modelTeamNameForLeague(name, leagueId) {
  const raw = String(name || '').trim();
  if (!raw) return raw;
  if (Number(leagueId) !== CURRIE_CUP_LEAGUE_ID) return raw;
  return CURRIE_CUP_MODEL[normalizeKey(raw)] || raw;
}

/** Attach standings-style labels for UI; keep raw names for the prediction model. */
export function applyLeagueDisplayNames(match, leagueId) {
  if (!match || typeof match !== 'object') return match;
  const homeIncoming = match.home_team_raw || match.home_team || match.home_team_name || '';
  const awayIncoming = match.away_team_raw || match.away_team || match.away_team_name || '';
  // Canonicalise either way: records written before the provinces were split
  // still carry short franchise names in home_team_raw.
  const homeRaw = modelTeamNameForLeague(match.home_team_raw || homeIncoming, leagueId);
  const awayRaw = modelTeamNameForLeague(match.away_team_raw || awayIncoming, leagueId);
  return {
    ...match,
    home_team_raw: homeRaw,
    away_team_raw: awayRaw,
    home_team: displayTeamNameForLeague(homeIncoming, leagueId),
    away_team: displayTeamNameForLeague(awayIncoming, leagueId),
  };
}

export function modelTeamNameForPrediction(match, side = 'home') {
  if (side === 'away') {
    return String(match?.away_team_raw || match?.away_team || '').trim();
  }
  return String(match?.home_team_raw || match?.home_team || '').trim();
}
