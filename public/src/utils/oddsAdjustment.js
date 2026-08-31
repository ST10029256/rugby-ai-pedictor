/**
 * The single place odds are turned into a probability.
 *
 * The AI prediction shown in the app is a stored, frozen value: every user sees
 * the identical number for a given match, because it was computed once before
 * kickoff and never recalculated. Odds are the only thing a user may vary, so
 * they are applied here as a clearly separate figure rather than being blended
 * back into the AI's output.
 *
 * That separation matters. Previously the browser overwrote the AI probability
 * with its own blend, using weights that differed from the backend's, so the
 * "AI prediction" a user saw depended on what they had typed into an odds box.
 */

// Weight given to the AI when combining it with a user's odds. The backend
// varies its weighting by how far the model and market disagree; this fixed
// split is used only for the user-facing "with your odds" figure, so that the
// same odds always produce the same number for everyone.
export const AI_WEIGHT = 0.4;
export const ODDS_WEIGHT = 0.6;

/** Decimal odds -> implied win probability, with the bookmaker margin removed. */
export function impliedHomeProbability(homeDecimal, awayDecimal) {
  const home = parseFloat(homeDecimal);
  const away = parseFloat(awayDecimal);
  if (!Number.isFinite(home) || !Number.isFinite(away) || home <= 0 || away <= 0) {
    return null;
  }
  const homeRaw = 1 / home;
  const awayRaw = 1 / away;
  const total = homeRaw + awayRaw;
  if (total <= 0) return null;
  return homeRaw / total;
}

export function hasUsableOdds(odds) {
  return !!(odds && parseFloat(odds.home) > 0 && parseFloat(odds.away) > 0);
}

/**
 * Combine the canonical AI probability with a user's odds.
 *
 * Returns null when the odds are unusable, so callers fall back to showing the
 * AI prediction on its own.
 */
export function oddsAdjustedView(aiHomeWinProb, odds, homeTeam, awayTeam) {
  if (!hasUsableOdds(odds)) return null;

  const oddsHomeWinProb = impliedHomeProbability(odds.home, odds.away);
  if (oddsHomeWinProb === null) return null;

  const ai = Number.isFinite(aiHomeWinProb) ? aiHomeWinProb : 0.5;
  const homeWinProb = AI_WEIGHT * ai + ODDS_WEIGHT * oddsHomeWinProb;

  let winner;
  let confidence;
  if (homeWinProb > 0.5) {
    winner = homeTeam;
    confidence = homeWinProb;
  } else if (homeWinProb < 0.5) {
    winner = awayTeam;
    confidence = 1 - homeWinProb;
  } else {
    winner = 'Draw';
    confidence = 0.5;
  }

  return {
    home_win_prob: homeWinProb,
    odds_implied_home_win_prob: oddsHomeWinProb,
    winner,
    confidence,
  };
}
