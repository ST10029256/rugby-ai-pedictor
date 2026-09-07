/**
 * Season-year rules for every competition in the app.
 *
 * Only URC, Premiership and Top 14 cross two calendar years.
 * Everything else is a single calendar year / World Cup edition year —
 * including Nations Championship (July + November + Finals Weekend).
 */

export const LEAGUE_IDS = {
  RUGBY_CHAMPIONSHIP: 4986,
  URC: 4446,
  CURRIE_CUP: 5069,
  RWC: 4574,
  SUPER_RUGBY: 4551,
  TOP14: 4430,
  PREMIERSHIP: 4414,
  SIX_NATIONS: 4714,
  FRIENDLIES: 5479,
  NATIONS_CHAMPIONSHIP: 5480,
};

export const CALENDAR_YEAR_LEAGUE_IDS = new Set([
  LEAGUE_IDS.SUPER_RUGBY,
  LEAGUE_IDS.SIX_NATIONS,
  LEAGUE_IDS.RUGBY_CHAMPIONSHIP,
  LEAGUE_IDS.CURRIE_CUP,
  LEAGUE_IDS.NATIONS_CHAMPIONSHIP,
  LEAGUE_IDS.RWC,
  LEAGUE_IDS.FRIENDLIES,
]);

export const CROSS_YEAR_LEAGUE_IDS = new Set([
  LEAGUE_IDS.URC,
  LEAGUE_IDS.PREMIERSHIP,
  LEAGUE_IDS.TOP14,
]);

/** Highlightly league IDs keyed the same way (start year of the season). */
export const CROSS_YEAR_HIGHLIGHTLY_LEAGUE_IDS = new Set([65460, 11847, 14400]);

function utcYearMonth(value) {
  if (value == null || value === '') return null;
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value)) {
    const year = parseInt(value.slice(0, 4), 10);
    const month = parseInt(value.slice(5, 7), 10);
    if (!year || !month) return null;
    return { year, month };
  }
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1 };
}

/** First calendar month of a new cross-year season (1–12). */
export function crossYearSeasonStartMonth(leagueId) {
  const id = Number(leagueId);
  if (id === LEAGUE_IDS.TOP14) return 8;
  if (id === LEAGUE_IDS.URC || id === LEAGUE_IDS.PREMIERSHIP) return 9;
  return null;
}

export function isCalendarYearLeague(leagueId) {
  return CALENDAR_YEAR_LEAGUE_IDS.has(Number(leagueId));
}

export function isCrossYearLeague(leagueId) {
  return CROSS_YEAR_LEAGUE_IDS.has(Number(leagueId));
}

/**
 * Season start year for a kickoff (or "now" if no date).
 * Calendar-year leagues: the UTC calendar year of the match.
 * URC / Premiership: Sep–Aug window, start year flips in September.
 * Top 14: Aug–Jul window, start year flips in August.
 */
export function resolveSeasonStartYear(leagueId, kickoffDate = new Date()) {
  const parts = utcYearMonth(kickoffDate);
  if (!parts) return new Date().getUTCFullYear();
  const startMonth = crossYearSeasonStartMonth(leagueId);
  if (!startMonth) return parts.year;
  return parts.month >= startMonth ? parts.year : parts.year - 1;
}

/**
 * Display / grouping key for a match date.
 * Calendar-year: "2026"
 * Cross-year: "2025-26"
 */
export function resolveSeasonLabel(leagueId, kickoffDate = new Date()) {
  const startYear = resolveSeasonStartYear(leagueId, kickoffDate);
  if (isCrossYearLeague(leagueId)) {
    return `${startYear}-${String(startYear + 1).slice(-2)}`;
  }
  return String(startYear);
}

/**
 * Start-year for the currently active standings season.
 */
export function getPrimaryStandingsSeasonYear(leagueId, now = new Date()) {
  return resolveSeasonStartYear(leagueId, now);
}

/**
 * Human-readable season label for standings UI (e.g. "2025-26").
 */
export function formatStandingsSeasonLabel(seasonYear, leagueId) {
  const raw = String(seasonYear || '').trim();
  if (/^\d{4}-\d{2}$/.test(raw)) return raw;
  const yr = Number(raw);
  if (!Number.isFinite(yr)) return raw;
  if (isCrossYearLeague(leagueId)) {
    return `${yr}-${String(yr + 1).slice(-2)}`;
  }
  return String(yr);
}
