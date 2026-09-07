/**
 * Competition + season finals formats for History (and any future bracket UI).
 *
 * Rugby leagues do not share a Round-of-32 bracket. Labels are taken from the
 * real finals system for that competition and season year.
 */

import { LEAGUE_IDS, resolveSeasonStartYear } from './season';

export { LEAGUE_IDS };
export const RUGBY_WORLD_CUP_LEAGUE_ID = LEAGUE_IDS.RWC;

/** Newest knockout stage first in the History list. */
export const PLAYOFF_STAGE_ORDER = [
  'Grand Final',
  'Final',
  'Championship Final',
  'Bronze Final',
  'Third-place',
  'Semi-finals',
  'Quarter-finals',
  'Round of 16',
  'Qualifying finals',
  'Elimination finals',
  'Playoffs',
  'Finals Weekend',
];

const MATCHDAY_GAP_DAYS = 4;

const PLAYOFF_MONTHS = {
  [LEAGUE_IDS.SUPER_RUGBY]: [6, 7],
  [LEAGUE_IDS.URC]: [5, 6, 7],
  [LEAGUE_IDS.TOP14]: [6, 7],
  [LEAGUE_IDS.PREMIERSHIP]: [5, 6, 7],
  [LEAGUE_IDS.CURRIE_CUP]: [8, 9, 10],
  [LEAGUE_IDS.RWC]: [9, 10, 11],
};

function daysBetweenIsoDates(aIso, bIso) {
  if (!aIso || !bIso) return 0;
  const [ay, am, ad] = String(aIso).slice(0, 10).split('-').map((v) => parseInt(v, 10));
  const [by, bm, bd] = String(bIso).slice(0, 10).split('-').map((v) => parseInt(v, 10));
  if (!ay || !am || !ad || !by || !bm || !bd) return 0;
  return (Date.UTC(by, bm - 1, bd) - Date.UTC(ay, am - 1, ad)) / (1000 * 60 * 60 * 24);
}

function matchIso(match) {
  return String(match?.date || match?.date_event || '').slice(0, 10);
}

function monthOfIso(iso) {
  const month = parseInt(String(iso || '').slice(5, 7), 10);
  return Number.isFinite(month) ? month : 0;
}

function yearOfIso(iso) {
  const year = parseInt(String(iso || '').slice(0, 4), 10);
  return Number.isFinite(year) ? year : 0;
}

function arraysEqual(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

export function seasonYearFromMatches(sortedMatches, leagueId) {
  if (!Array.isArray(sortedMatches) || sortedMatches.length === 0) return 0;
  const lastIso = matchIso(sortedMatches[sortedMatches.length - 1]);
  const firstIso = matchIso(sortedMatches[0]);
  const anchor = lastIso || firstIso;
  if (!anchor) return 0;
  return resolveSeasonStartYear(leagueId, anchor);
}

/**
 * Source of truth for bracket vs table competitions.
 * Super Rugby and RWC change shape between editions — never key only on league id.
 */
export function getCompetitionFinalsFormat(leagueId, seasonYear) {
  const id = Number(leagueId);
  const year = Number(seasonYear) || 0;

  if (id === LEAGUE_IDS.PREMIERSHIP) {
    return {
      hasBracket: true,
      stages: ['Semi-finals', 'Final'],
      patterns: [
        { sizes: [2, 1], labels: ['Semi-finals', 'Final'] },
        { sizes: [1], labels: ['Final'] },
      ],
      poolLabel: 'Week',
    };
  }

  if (id === LEAGUE_IDS.TOP14) {
    return {
      hasBracket: true,
      stages: ['Playoffs', 'Semi-finals', 'Final'],
      patterns: [
        { sizes: [2, 2, 1], labels: ['Playoffs', 'Semi-finals', 'Final'] },
        { sizes: [3, 2, 1], labels: ['Playoffs', 'Semi-finals', 'Final'] },
        { sizes: [4, 2, 1], labels: ['Playoffs', 'Semi-finals', 'Final'] },
        { sizes: [2, 1], labels: ['Semi-finals', 'Final'] },
        { sizes: [1], labels: ['Final'] },
      ],
      poolLabel: 'Week',
    };
  }

  if (id === LEAGUE_IDS.URC) {
    return {
      hasBracket: true,
      stages: ['Quarter-finals', 'Semi-finals', 'Final'],
      patterns: [
        { sizes: [4, 2, 1], labels: ['Quarter-finals', 'Semi-finals', 'Final'] },
        { sizes: [2, 1], labels: ['Semi-finals', 'Final'] },
        { sizes: [1], labels: ['Final'] },
      ],
      poolLabel: 'Week',
    };
  }

  if (id === LEAGUE_IDS.SUPER_RUGBY) {
    if (year >= 2027) {
      return {
        hasBracket: true,
        stages: ['Elimination finals', 'Semi-finals', 'Grand Final'],
        patterns: [
          { sizes: [2, 2, 1], labels: ['Elimination finals', 'Semi-finals', 'Grand Final'] },
          { sizes: [2, 1], labels: ['Semi-finals', 'Grand Final'] },
          { sizes: [1], labels: ['Grand Final'] },
        ],
        poolLabel: 'Week',
      };
    }
    if (year >= 2025) {
      return {
        hasBracket: true,
        stages: ['Qualifying finals', 'Semi-finals', 'Grand Final'],
        patterns: [
          { sizes: [3, 2, 1], labels: ['Qualifying finals', 'Semi-finals', 'Grand Final'] },
          { sizes: [2, 1], labels: ['Semi-finals', 'Grand Final'] },
          { sizes: [1], labels: ['Grand Final'] },
        ],
        poolLabel: 'Week',
      };
    }
    return {
      hasBracket: true,
      stages: ['Quarter-finals', 'Semi-finals', 'Grand Final'],
      patterns: [
        { sizes: [4, 2, 1], labels: ['Quarter-finals', 'Semi-finals', 'Grand Final'] },
        { sizes: [2, 1], labels: ['Semi-finals', 'Grand Final'] },
        { sizes: [1], labels: ['Grand Final'] },
      ],
      poolLabel: 'Week',
    };
  }

  if (id === LEAGUE_IDS.CURRIE_CUP) {
    return {
      hasBracket: true,
      stages: ['Semi-finals', 'Final'],
      patterns: [
        { sizes: [2, 1], labels: ['Semi-finals', 'Final'] },
        { sizes: [1], labels: ['Final'] },
      ],
      poolLabel: 'Week',
    };
  }

  if (id === LEAGUE_IDS.RWC) {
    if (year >= 2027) {
      return {
        hasBracket: true,
        stages: ['Round of 16', 'Quarter-finals', 'Semi-finals', 'Bronze Final', 'Final'],
        patterns: [
          { sizes: [8, 4, 2, 1, 1], labels: ['Round of 16', 'Quarter-finals', 'Semi-finals', 'Bronze Final', 'Final'] },
          { sizes: [8, 4, 2, 2], labels: ['Round of 16', 'Quarter-finals', 'Semi-finals', 'Bronze Final'] },
          { sizes: [8, 4, 2, 1], labels: ['Round of 16', 'Quarter-finals', 'Semi-finals', 'Final'] },
          { sizes: [8, 4, 2], labels: ['Round of 16', 'Quarter-finals', 'Semi-finals'] },
          { sizes: [8, 4], labels: ['Round of 16', 'Quarter-finals'] },
          { sizes: [8], labels: ['Round of 16'] },
        ],
        splitLastPairAsBronzeFinal: true,
        poolLabel: 'Week',
      };
    }
    return {
      hasBracket: true,
      stages: ['Quarter-finals', 'Semi-finals', 'Bronze Final', 'Final'],
      patterns: null,
      useLastEight: true,
      poolLabel: 'Week',
    };
  }

  if (id === LEAGUE_IDS.NATIONS_CHAMPIONSHIP) {
    return {
      hasBracket: true,
      stages: ['Finals Weekend', 'Championship Final'],
      patterns: [],
      // July Rounds 1–3 are ranking matches, not finals. Finals Weekend is late November.
      finalsDateRange: (y) => ({ start: `${y}-11-25`, end: `${y}-11-30` }),
      championshipFinalFromLastOfCluster: true,
      calendarYearSeason: true,
      poolLabel: 'Round',
    };
  }

  if (id === LEAGUE_IDS.SIX_NATIONS) {
    return { hasBracket: false, stages: [], patterns: [], poolLabel: 'Round' };
  }

  if (id === LEAGUE_IDS.RUGBY_CHAMPIONSHIP) {
    return { hasBracket: false, stages: [], patterns: [], poolLabel: 'Round' };
  }

  if (id === LEAGUE_IDS.FRIENDLIES) {
    return { hasBracket: false, stages: [], patterns: [], poolLabel: 'Week' };
  }

  return { hasBracket: false, stages: [], patterns: [], poolLabel: 'Week' };
}

export function regularRoundLabel(leagueId, roundNumber) {
  const format = getCompetitionFinalsFormat(leagueId, 0);
  const n = Number(roundNumber);
  if (format.poolLabel === 'Round') return `Round ${n}`;
  return `Week ${n}`;
}

export function buildRankingRoundEntries(poolMatches, leagueId, seasonAnchorIso) {
  const clusters = clusterMatchesByMatchday(poolMatches);
  return clusters
    .map((matches, idx) => {
      const displayRoundNum = idx + 1;
      const earliestDate = matches.reduce((min, m) => (!min || m.date < min ? m.date : min), null);
      return {
        key: `round-${seasonAnchorIso || 's'}-${displayRoundNum}`,
        label: regularRoundLabel(leagueId, displayRoundNum),
        matches,
        earliestDate,
        sortVal: displayRoundNum,
      };
    })
    .sort((a, b) => b.sortVal - a.sortVal || (b.earliestDate || '').localeCompare(a.earliestDate || ''));
}

export function clusterMatchesByMatchday(sortedMatches, gapDays = MATCHDAY_GAP_DAYS) {
  const clusters = [];
  let current = [];
  let prevIso = '';
  (sortedMatches || []).forEach((match) => {
    const iso = matchIso(match);
    if (!iso) {
      current.push(match);
      return;
    }
    if (!current.length || !prevIso || daysBetweenIsoDates(prevIso, iso) <= gapDays) {
      current.push(match);
    } else {
      clusters.push(current);
      current = [match];
    }
    prevIso = iso;
  });
  if (current.length) clusters.push(current);
  return clusters;
}

function lastMatchInPlayoffWindow(sortedMatches, leagueId) {
  const months = PLAYOFF_MONTHS[Number(leagueId)];
  if (!months) return false;
  const lastIso = matchIso(sortedMatches[sortedMatches.length - 1]);
  return months.includes(monthOfIso(lastIso));
}

function matchPlayoffPattern(clusterSizes, patterns) {
  if (!patterns?.length || !clusterSizes.length) return null;

  for (const pattern of patterns) {
    const n = pattern.sizes.length;
    const preceding = clusterSizes.length - n;
    if (typeof pattern.minPrecedingClusters === 'number' && preceding < pattern.minPrecedingClusters) {
      continue;
    }
    if (n <= clusterSizes.length && arraysEqual(clusterSizes.slice(-n), pattern.sizes)) {
      return { offset: clusterSizes.length - n, labels: pattern.labels, pattern };
    }
  }

  for (const pattern of patterns) {
    for (let n = pattern.sizes.length - 1; n >= 1; n -= 1) {
      const prefix = pattern.sizes.slice(0, n);
      const preceding = clusterSizes.length - n;
      if (typeof pattern.minPrecedingClusters === 'number' && preceding < pattern.minPrecedingClusters) {
        continue;
      }
      if (prefix.length <= clusterSizes.length && arraysEqual(clusterSizes.slice(-n), prefix)) {
        return { offset: clusterSizes.length - n, labels: pattern.labels.slice(0, n), pattern };
      }
    }
  }
  return null;
}

function assignRugbyWorldCupClassic(sortedMatches, identify) {
  const byId = {};
  if (!Array.isArray(sortedMatches) || sortedMatches.length < 8) return byId;
  const last8 = sortedMatches.slice(-8);
  const stages = [
    'Quarter-finals',
    'Quarter-finals',
    'Quarter-finals',
    'Quarter-finals',
    'Semi-finals',
    'Semi-finals',
    'Bronze Final',
    'Final',
  ];
  last8.forEach((match, idx) => {
    byId[String(identify(match))] = stages[idx];
  });
  return byId;
}

function assignRugbyWorldCup2027Fallback(sortedMatches, identify) {
  const byId = {};
  if (!Array.isArray(sortedMatches) || sortedMatches.length < 16) return byId;
  const last16 = sortedMatches.slice(-16);
  const stages = [
    ...Array(8).fill('Round of 16'),
    ...Array(4).fill('Quarter-finals'),
    ...Array(2).fill('Semi-finals'),
    'Bronze Final',
    'Final',
  ];
  last16.forEach((match, idx) => {
    byId[String(identify(match))] = stages[idx];
  });
  return byId;
}

function kickoffSortKey(match) {
  return String(match?.kickoff_at || match?.timestamp || match?.date || '');
}

/**
 * Map match identity -> knockout stage label. Empty object if this season
 * has no bracket, or finals have not started yet.
 */
export function assignHistoryPlayoffStages(sortedMatches, leagueId, matchIdentity) {
  const byId = {};
  const id = Number(leagueId);
  const identify = typeof matchIdentity === 'function'
    ? matchIdentity
    : (m) => m?.match_id ?? `${matchIso(m)}-${m?.home_team || ''}-${m?.away_team || ''}`;

  if (!Array.isArray(sortedMatches) || sortedMatches.length === 0) return byId;

  const seasonYear = seasonYearFromMatches(sortedMatches, id);
  const format = getCompetitionFinalsFormat(id, seasonYear);
  if (!format.hasBracket) return byId;

  if (typeof format.finalsDateRange === 'function') {
    const range = format.finalsDateRange(seasonYear || yearOfIso(matchIso(sortedMatches[sortedMatches.length - 1])));
    const clusters = clusterMatchesByMatchday(sortedMatches);
    clusters.forEach((cluster) => {
      const inFinals = cluster.some((m) => {
        const iso = matchIso(m);
        return iso >= range.start && iso <= range.end;
      });
      if (!inFinals) return;
      const ordered = [...cluster].sort((a, b) => kickoffSortKey(a).localeCompare(kickoffSortKey(b)));
      ordered.forEach((match, matchIdx) => {
        const isLast = format.championshipFinalFromLastOfCluster && matchIdx === ordered.length - 1;
        byId[String(identify(match))] = isLast ? 'Championship Final' : 'Finals Weekend';
      });
    });
    return byId;
  }

  if (!lastMatchInPlayoffWindow(sortedMatches, id)) return byId;

  if (format.useLastEight) {
    return assignRugbyWorldCupClassic(sortedMatches, identify);
  }

  const clusters = clusterMatchesByMatchday(sortedMatches);
  const sizes = clusters.map((cluster) => cluster.length);
  const matched = matchPlayoffPattern(sizes, format.patterns || []);

  if (matched) {
    matched.labels.forEach((label, idx) => {
      const cluster = [...(clusters[matched.offset + idx] || [])].sort((a, b) => (
        kickoffSortKey(a).localeCompare(kickoffSortKey(b))
      ));
      const isLastPlayoffCluster = idx === matched.labels.length - 1;
      if (format.splitLastPairAsBronzeFinal && label === 'Bronze Final' && cluster.length === 2) {
        byId[String(identify(cluster[0]))] = 'Bronze Final';
        byId[String(identify(cluster[1]))] = 'Final';
        return;
      }
      if (format.championshipFinalFromLastOfCluster && isLastPlayoffCluster && cluster.length >= 2) {
        cluster.forEach((match, matchIdx) => {
          const isLast = matchIdx === cluster.length - 1;
          byId[String(identify(match))] = isLast ? 'Championship Final' : 'Finals Weekend';
        });
        return;
      }
      cluster.forEach((match) => {
        byId[String(identify(match))] = label;
      });
    });
    return byId;
  }

  if (id === LEAGUE_IDS.RWC && seasonYear >= 2027) {
    return assignRugbyWorldCup2027Fallback(sortedMatches, identify);
  }

  return byId;
}

export function playoffStageSortVal(stage) {
  const idx = PLAYOFF_STAGE_ORDER.indexOf(stage);
  return idx >= 0 ? 1000 - idx : 0;
}
