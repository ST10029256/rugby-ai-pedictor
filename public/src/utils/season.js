/**
 * Season-year rules for every competition in the app.
 *
 * URC, Premiership, Top 14 and EPCR cups cross two calendar years.
 * Everything else is a single calendar year / World Cup edition year —
 * including Nations Championship and the women's internationals.
 */

import { LEAGUE_IDS, WXV_OLD_FORMAT_SEASON_YEAR, isWxvOldFormatIds } from './leagues';

export { LEAGUE_IDS };

export const CALENDAR_YEAR_LEAGUE_IDS = new Set([
  LEAGUE_IDS.SUPER_RUGBY,
  LEAGUE_IDS.SIX_NATIONS,
  LEAGUE_IDS.RUGBY_CHAMPIONSHIP,
  LEAGUE_IDS.CURRIE_CUP,
  LEAGUE_IDS.NATIONS_CHAMPIONSHIP,
  LEAGUE_IDS.RWC,
  LEAGUE_IDS.FRIENDLIES,
  LEAGUE_IDS.WOMEN_RWC,
  LEAGUE_IDS.WOMEN_SIX_NATIONS,
  LEAGUE_IDS.WXV_1,
  LEAGUE_IDS.WXV_2,
  LEAGUE_IDS.WXV_3,
]);

export const CROSS_YEAR_LEAGUE_IDS = new Set([
  LEAGUE_IDS.URC,
  LEAGUE_IDS.PREMIERSHIP,
  LEAGUE_IDS.TOP14,
  LEAGUE_IDS.CHAMPIONS_CUP,
  LEAGUE_IDS.CHALLENGE_CUP,
]);

/** Highlightly league IDs keyed the same way (start year of the season). */
export const CROSS_YEAR_HIGHLIGHTLY_LEAGUE_IDS = new Set([
  65460, 11847, 14400, 46738, 45036,
]);

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
  if (
    id === LEAGUE_IDS.URC ||
    id === LEAGUE_IDS.PREMIERSHIP ||
    id === LEAGUE_IDS.CHAMPIONS_CUP ||
    id === LEAGUE_IDS.CHALLENGE_CUP
  ) {
    return 9;
  }
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

export function getViewStandingsSeasonYear(leagueId, leagueIds, now = new Date()) {
  if (isWxvOldFormatIds(leagueIds)) return WXV_OLD_FORMAT_SEASON_YEAR;
  return getPrimaryStandingsSeasonYear(leagueId, now);
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
