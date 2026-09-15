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
export const WXV_MEMBER_IDS = [LEAGUE_IDS.WXV_1, LEAGUE_IDS.WXV_2, LEAGUE_IDS.WXV_3];

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
  { id: LEAGUE_IDS.WXV_1, name: 'WXV', matchLabel: 'WXV 1', gender: GENDER_WOMEN, highlightlyId: 120775, neutralMode: true, memberIds: WXV_MEMBER_IDS },
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
  return canonicalizePickerLeagueId(leagueId) === LEAGUE_IDS.WXV_1;
}

export function defaultBundleMember(leagueId) {
  const primary = canonicalizePickerLeagueId(leagueId);
  const ids = BUNDLE_BY_PRIMARY[primary];
  if (!ids?.length) return null;
  if (primary === LEAGUE_IDS.CHAMPIONS_CUP) return ids[0];
  return null;
}

export function bundleMemberOptions(leagueId) {
  const primary = canonicalizePickerLeagueId(leagueId);
  const ids = BUNDLE_BY_PRIMARY[primary];
  if (!ids) return [];
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
  return [...members];
}

export function leagueViewDisplayName(pickerLeagueId, bundleMemberId, fallback = 'Unknown') {
  const ids = queryLeagueIds(pickerLeagueId, bundleMemberId);
  if (ids.length === 1) {
    const config = getLeagueConfig(ids[0]);
    return config?.matchLabel || config?.name || fallback;
  }
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
