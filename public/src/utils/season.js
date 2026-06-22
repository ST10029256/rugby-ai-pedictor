/** SportsDB league IDs for competitions that span two calendar years (Aug–Jun). */
export const CROSS_YEAR_LEAGUE_IDS = new Set([4446, 4414, 4430]);

/** Highlightly league IDs keyed the same way (start year of the season). */
export const CROSS_YEAR_HIGHLIGHTLY_LEAGUE_IDS = new Set([65460, 11847, 14400]);

/**
 * Return the Highlightly/API start-year for the currently active standings season.
 */
export function getPrimaryStandingsSeasonYear(leagueId, now = new Date()) {
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  if (CROSS_YEAR_LEAGUE_IDS.has(Number(leagueId))) {
    return month <= 6 ? year - 1 : year;
  }
  return year;
}

/**
 * Human-readable season label for standings UI (e.g. "2025/26" instead of raw "2025").
 */
export function formatStandingsSeasonLabel(seasonYear, leagueId) {
  const yr = Number(seasonYear);
  if (!Number.isFinite(yr)) return String(seasonYear || '');
  if (CROSS_YEAR_LEAGUE_IDS.has(Number(leagueId))) {
    return `${yr}/${String(yr + 1).slice(-2)}`;
  }
  return String(yr);
}
