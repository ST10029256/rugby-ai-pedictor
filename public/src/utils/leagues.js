/**
 * App league catalog: display names, gender, picker groups, Highlightly ids.
 *
 * Local ids stay in the SportsDB-style range already used by the app.
 * Highlightly names differ (e.g. "European Rugby Champions Cup"); we show
 * the competition names we want in the picker.
 */

export const GENDER_MEN = 'men';
export const GENDER_WOMEN = 'women';

export const GENDER_OPTIONS = [
  { id: GENDER_MEN, label: "Men's" },
  { id: GENDER_WOMEN, label: "Women's" },
];

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
  CHAMPIONS_CUP: 5481,
  CHALLENGE_CUP: 5482,
  WOMEN_RWC: 5483,
  WOMEN_SIX_NATIONS: 5484,
  WXV_1: 5485,
  WXV_2: 5486,
  WXV_3: 5487,
};

/** Cups/tiers that share one picker row. */
export const EPCR_MEMBER_IDS = [LEAGUE_IDS.CHAMPIONS_CUP, LEAGUE_IDS.CHALLENGE_CUP];
export const WXV_MEMBER_IDS = [LEAGUE_IDS.WXV_1];
export const WXV_OLD_FORMAT_IDS = [LEAGUE_IDS.WXV_1, LEAGUE_IDS.WXV_2, LEAGUE_IDS.WXV_3];
export const WXV_OLD_FORMAT_VALUE = 'wxv-old-format';
export const WXV_GLOBAL_SERIES_FROM_YEAR = 2026;
export const WXV_OLD_FORMAT_SEASON_YEAR = 2024;

const BUNDLE_BY_PRIMARY = {
  [LEAGUE_IDS.CHAMPIONS_CUP]: EPCR_MEMBER_IDS,
  [LEAGUE_IDS.WXV_1]: WXV_MEMBER_IDS,
};

const PICKER_PRIMARY_BY_MEMBER = {
  [LEAGUE_IDS.CHALLENGE_CUP]: LEAGUE_IDS.CHAMPIONS_CUP,
  [LEAGUE_IDS.WXV_2]: LEAGUE_IDS.WXV_1,
  [LEAGUE_IDS.WXV_3]: LEAGUE_IDS.WXV_1,
};

/** Picker order. Bundled cups/tiers are hidden; only EPCR and WXV appear. */
export const LEAGUE_CATALOG = [
  { id: LEAGUE_IDS.URC, name: 'United Rugby Championship', gender: GENDER_MEN, highlightlyId: 65460, neutralMode: false },
  { id: LEAGUE_IDS.PREMIERSHIP, name: 'English Premiership Rugby', gender: GENDER_MEN, highlightlyId: 11847, neutralMode: false },
  { id: LEAGUE_IDS.TOP14, name: 'French Top 14', gender: GENDER_MEN, highlightlyId: 14400, neutralMode: false },
  { id: LEAGUE_IDS.SUPER_RUGBY, name: 'Super Rugby', gender: GENDER_MEN, highlightlyId: 61205, neutralMode: false },
  { id: LEAGUE_IDS.CURRIE_CUP, name: 'Currie Cup', gender: GENDER_MEN, highlightlyId: 32271, neutralMode: false },
  { id: LEAGUE_IDS.CHAMPIONS_CUP, name: 'EPCR', matchLabel: 'Champions Cup', gender: GENDER_MEN, highlightlyId: 46738, neutralMode: false, memberIds: EPCR_MEMBER_IDS },
  { id: LEAGUE_IDS.CHALLENGE_CUP, name: 'EPCR Challenge Cup', matchLabel: 'Challenge Cup', gender: GENDER_MEN, highlightlyId: 45036, neutralMode: false, picker: false, bundleId: LEAGUE_IDS.CHAMPIONS_CUP },
  { id: LEAGUE_IDS.RUGBY_CHAMPIONSHIP, name: 'Rugby Championship', gender: GENDER_MEN, highlightlyId: 73119, neutralMode: false },
  { id: LEAGUE_IDS.SIX_NATIONS, name: 'Six Nations Championship', gender: GENDER_MEN, highlightlyId: 44185, neutralMode: true },
  { id: LEAGUE_IDS.NATIONS_CHAMPIONSHIP, name: 'Nations Championship', gender: GENDER_MEN, highlightlyId: 124179, neutralMode: true },
  { id: LEAGUE_IDS.RWC, name: 'Rugby World Cup', gender: GENDER_MEN, highlightlyId: 59503, neutralMode: true },
  { id: LEAGUE_IDS.FRIENDLIES, name: 'Rugby Union International Friendlies', gender: GENDER_MEN, highlightlyId: 72268, neutralMode: true },
  { id: LEAGUE_IDS.WOMEN_SIX_NATIONS, name: "Women's Six Nations", gender: GENDER_WOMEN, highlightlyId: 47589, neutralMode: true },
  { id: LEAGUE_IDS.WOMEN_RWC, name: "Women's Rugby World Cup", gender: GENDER_WOMEN, highlightlyId: 60354, neutralMode: true },
  { id: LEAGUE_IDS.WXV_1, name: 'WXV', matchLabel: 'Global Series', gender: GENDER_WOMEN, highlightlyId: 120775, neutralMode: true, memberIds: WXV_MEMBER_IDS },
  { id: LEAGUE_IDS.WXV_2, name: 'WXV 2', matchLabel: 'WXV 2', gender: GENDER_WOMEN, highlightlyId: 121626, neutralMode: true, picker: false, bundleId: LEAGUE_IDS.WXV_1 },
  { id: LEAGUE_IDS.WXV_3, name: 'WXV 3', matchLabel: 'WXV 3', gender: GENDER_WOMEN, highlightlyId: 122477, neutralMode: true, picker: false, bundleId: LEAGUE_IDS.WXV_1 },
];

export const LEAGUE_CONFIGS = Object.fromEntries(
  LEAGUE_CATALOG.map((league) => [
    league.id,
    {
      name: league.name,
      neutral_mode: league.neutralMode,
      gender: league.gender,
      picker: league.picker !== false,
      matchLabel: league.matchLabel || league.name,
      memberIds: league.memberIds || [league.id],
      bundleId: league.bundleId || null,
      highlightlyId: league.highlightlyId,
    },
  ])
);

export const LEAGUE_ID_MAPPING = Object.fromEntries(
  LEAGUE_CATALOG.map((league) => [league.id, league.highlightlyId])
);

export const WOMEN_LEAGUE_IDS = new Set(
  LEAGUE_CATALOG.filter((league) => league.gender === GENDER_WOMEN).map((league) => league.id)
);

export const INTERNATIONAL_LEAGUE_IDS = new Set([
  LEAGUE_IDS.RUGBY_CHAMPIONSHIP,
  LEAGUE_IDS.RWC,
  LEAGUE_IDS.SIX_NATIONS,
  LEAGUE_IDS.FRIENDLIES,
  LEAGUE_IDS.NATIONS_CHAMPIONSHIP,
  LEAGUE_IDS.WOMEN_RWC,
  LEAGUE_IDS.WOMEN_SIX_NATIONS,
  LEAGUE_IDS.WXV_1,
  LEAGUE_IDS.WXV_2,
  LEAGUE_IDS.WXV_3,
]);

const CATALOG_BY_ID = new Map(LEAGUE_CATALOG.map((league) => [league.id, league]));

export function getLeagueConfig(leagueId) {
  return CATALOG_BY_ID.get(Number(leagueId)) || LEAGUE_CONFIGS[Number(leagueId)] || null;
}

export function leagueDisplayName(leagueId, fallback = 'Unknown') {
  return getLeagueConfig(leagueId)?.name || fallback;
}

export function genderForLeague(leagueId) {
  return getLeagueConfig(leagueId)?.gender || GENDER_MEN;
}

export function isWomensLeague(leagueId) {
  return WOMEN_LEAGUE_IDS.has(Number(leagueId));
}

export function catalogOrderIndex(leagueId) {
  const idx = LEAGUE_CATALOG.findIndex((league) => league.id === Number(leagueId));
  return idx < 0 ? 9999 : idx;
}

export const BUNDLE_ALL_VALUE = 'all';

export function expandLeagueIds(leagueId) {
  const id = Number(leagueId);
  if (!Number.isFinite(id)) return [];
  return (BUNDLE_BY_PRIMARY[id] || [id]).map((n) => Number(n));
}

export function isBundledPickerLeague(leagueId) {
  return Boolean(BUNDLE_BY_PRIMARY[canonicalizePickerLeagueId(leagueId)]);
}

export function bundleSubpickerLabel(leagueId) {
  const primary = canonicalizePickerLeagueId(leagueId);
  if (primary === LEAGUE_IDS.CHAMPIONS_CUP) return 'Select Cup';
  if (primary === LEAGUE_IDS.WXV_1) return 'Select Series';
  return 'Select Split';
}

export function bundleAllowsAll(leagueId) {
  return false;
}

export function defaultBundleMember(leagueId) {
  const primary = canonicalizePickerLeagueId(leagueId);
  const ids = BUNDLE_BY_PRIMARY[primary];
  if (!ids?.length) return null;
  return ids[0];
}

export function isWxvOldFormatMember(bundleMemberId) {
  return String(bundleMemberId) === WXV_OLD_FORMAT_VALUE;
}

export const WXV_OLD_FORMAT_WXV1_GAMES = 18; // 2023 + 2024, 9 matches each

export function isWxvGlobalSeriesIds(leagueIds) {
  const ids = [...new Set((leagueIds || []).map(Number).filter((id) => Number.isFinite(id) && id > 0))];
  return ids.length === 1 && ids[0] === LEAGUE_IDS.WXV_1;
}

export function wxvTrainingGamesFromMetrics(leagueIds, rowsById) {
  const ids = [...new Set((leagueIds || []).map(Number).filter((id) => Number.isFinite(id) && id > 0))];
  const gamesFor = (id) => Number(rowsById?.[id]?.training_games) || 0;
  if (isWxvOldFormatIds(ids)) {
    return ids.reduce((sum, id) => {
      const total = gamesFor(id);
      if (id === LEAGUE_IDS.WXV_1) return sum + Math.min(total, WXV_OLD_FORMAT_WXV1_GAMES);
      return sum + total;
    }, 0);
  }
  if (isWxvGlobalSeriesIds(ids)) {
    return Math.max(0, gamesFor(LEAGUE_IDS.WXV_1) - WXV_OLD_FORMAT_WXV1_GAMES);
  }
  return ids.reduce((sum, id) => sum + gamesFor(id), 0);
}

export function bundleMemberDisplayName(optionId, options = []) {
  const match = (options || []).find((opt) => String(opt.id) === String(optionId));
  if (match?.name) return match.name;
  if (isWxvOldFormatMember(optionId)) return 'WXV 1 / 2 / 3';
  return getLeagueConfig(optionId)?.matchLabel || getLeagueConfig(optionId)?.name || '';
}

export function isWxvOldFormatIds(leagueIds) {
  const ids = [...new Set((leagueIds || []).map(Number))];
  return (
    ids.includes(LEAGUE_IDS.WXV_1) &&
    ids.includes(LEAGUE_IDS.WXV_2) &&
    ids.includes(LEAGUE_IDS.WXV_3)
  );
}

export function leagueMatchLabel(leagueId, seasonYear) {
  if (
    Number(leagueId) === LEAGUE_IDS.WXV_1 &&
    Number(seasonYear) < WXV_GLOBAL_SERIES_FROM_YEAR
  ) {
    return 'WXV 1';
  }
  const config = getLeagueConfig(leagueId);
  return config?.matchLabel || config?.name || `League ${leagueId}`;
}

export function wxvViewYearRange(leagueIds) {
  const ids = [...new Set((leagueIds || []).map(Number).filter((id) => Number.isFinite(id) && id > 0))];
  if (!ids.length) return null;
  if (isWxvOldFormatIds(ids)) return { maxExclusive: WXV_GLOBAL_SERIES_FROM_YEAR };
  if (ids.length === 1 && ids[0] === LEAGUE_IDS.WXV_1) {
    return { minInclusive: WXV_GLOBAL_SERIES_FROM_YEAR };
  }
  return null;
}

export function wxvViewYearAllowed(year, leagueIds) {
  const range = wxvViewYearRange(leagueIds);
  if (!range) return true;
  const y = Number(year);
  if (!Number.isFinite(y)) return true;
  if (range.minInclusive != null && y < range.minInclusive) return false;
  if (range.maxExclusive != null && y >= range.maxExclusive) return false;
  return true;
}

export function matchInWxvView(match, leagueIds) {
  const range = wxvViewYearRange(leagueIds);
  if (!range) return true;
  const iso = String(
    match?.date_event || match?.date || match?.kickoff_at || match?.timestamp || ''
  ).slice(0, 10);
  const year = Number(iso.slice(0, 4));
  if (!Number.isFinite(year)) return true;
  return wxvViewYearAllowed(year, leagueIds);
}

export function filterHistoryPayloadForWxvView(data, leagueIds) {
  if (!data || !wxvViewYearRange(leagueIds)) return data;
  const next = { ...data };
  if (next.matches_by_year_week) {
    next.matches_by_year_week = Object.fromEntries(
      Object.entries(next.matches_by_year_week).filter(([year]) => wxvViewYearAllowed(year, leagueIds))
    );
  }
  if (Array.isArray(next.all_matches)) {
    next.all_matches = next.all_matches.filter((match) => matchInWxvView(match, leagueIds));
  }
  if (Array.isArray(next.available_years)) {
    next.available_years = next.available_years.filter((year) => wxvViewYearAllowed(year, leagueIds));
  }
  if (next.selected_year && !wxvViewYearAllowed(next.selected_year, leagueIds)) {
    const years = (next.available_years || Object.keys(next.matches_by_year_week || {}))
      .map(String)
      .sort()
      .reverse();
    next.selected_year = years[0] || null;
  }
  return next;
}

export function bundleMemberOptions(leagueId) {
  const primary = canonicalizePickerLeagueId(leagueId);
  const ids = BUNDLE_BY_PRIMARY[primary];
  if (!ids) return [];
  if (primary === LEAGUE_IDS.WXV_1) {
    return [
      { id: LEAGUE_IDS.WXV_1, name: 'Global Series' },
      { id: WXV_OLD_FORMAT_VALUE, name: 'WXV 1 / 2 / 3' },
    ];
  }
  const members = ids.map((id) => {
    const config = getLeagueConfig(id);
    return { id, name: config?.matchLabel || config?.name || `League ${id}` };
  });
  if (!bundleAllowsAll(primary)) return members;
  const groupName = getLeagueConfig(primary)?.name || 'All';
  return [{ id: BUNDLE_ALL_VALUE, name: `All ${groupName}` }, ...members];
}

export function queryLeagueIds(pickerLeagueId, bundleMemberId) {
  const primary = canonicalizePickerLeagueId(pickerLeagueId);
  const members = BUNDLE_BY_PRIMARY[primary];
  if (!members) {
    const id = Number(pickerLeagueId);
    return Number.isFinite(id) ? [id] : [];
  }
  if (primary === LEAGUE_IDS.WXV_1 && isWxvOldFormatMember(bundleMemberId)) {
    return [...WXV_OLD_FORMAT_IDS];
  }
  if (
    bundleMemberId == null ||
    bundleMemberId === '' ||
    bundleMemberId === BUNDLE_ALL_VALUE
  ) {
    if (primary === LEAGUE_IDS.CHAMPIONS_CUP) return [members[0]];
    return [...members];
  }
  const member = Number(bundleMemberId);
  if (members.includes(member)) return [member];
  return [members[0]];
}

export function leagueViewDisplayName(pickerLeagueId, bundleMemberId, fallback = 'Unknown') {
  if (isWxvOldFormatMember(bundleMemberId)) return 'WXV 1 / 2 / 3';
  const ids = queryLeagueIds(pickerLeagueId, bundleMemberId);
  if (ids.length === 1) {
    const config = getLeagueConfig(ids[0]);
    return config?.matchLabel || config?.name || fallback;
  }
  if (isWxvOldFormatIds(ids)) return 'WXV 1 / 2 / 3';
  return leagueDisplayName(pickerLeagueId, fallback);
}

export function canonicalizePickerLeagueId(leagueId) {
  const id = Number(leagueId);
  if (!Number.isFinite(id)) return id;
  return PICKER_PRIMARY_BY_MEMBER[id] || id;
}

export function isPickerLeague(leagueId) {
  const config = getLeagueConfig(leagueId);
  return Boolean(config && config.picker !== false);
}

export function leagueIdsMatch(filterLeagueId, itemLeagueId, filterIds) {
  const wanted = new Set(
    Array.isArray(filterIds) && filterIds.length ? filterIds.map(Number) : expandLeagueIds(filterLeagueId)
  );
  return wanted.has(Number(itemLeagueId));
}

export function sortLeaguesForPicker(leagues) {
  return [...(leagues || [])].sort((a, b) => {
    const byName = String(a?.name || '').localeCompare(String(b?.name || ''), 'en', {
      sensitivity: 'base',
      numeric: true,
    });
    if (byName !== 0) return byName;
    return Number(a?.id || 0) - Number(b?.id || 0);
  });
}

export function enrichLeagueForPicker(league) {
  const pickerId = canonicalizePickerLeagueId(league?.id);
  const config = getLeagueConfig(pickerId) || getLeagueConfig(league?.id);
  return {
    ...league,
    id: pickerId,
    name: config?.name || league?.name,
    gender: config?.gender || GENDER_MEN,
  };
}

export function leaguesForPicker(leagues) {
  const collapsed = new Map();
  (leagues || []).forEach((league) => {
    const enriched = enrichLeagueForPicker(league);
    if (!isPickerLeague(enriched.id)) return;
    const existing = collapsed.get(enriched.id);
    collapsed.set(enriched.id, {
      ...enriched,
      upcoming_matches: (existing?.upcoming_matches || 0) + (league.upcoming_matches || 0),
      recent_matches: (existing?.recent_matches || 0) + (league.recent_matches || 0),
      has_news: Boolean(existing?.has_news || league.has_news),
      total_news: (existing?.total_news || 0) + (league.total_news || 0),
    });
  });
  return sortLeaguesForPicker([...collapsed.values()]);
}
