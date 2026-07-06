import { getPrimaryStandingsSeasonYear } from './season';

/** Local league id → Highlightly league id (same as standings). */
export const LEAGUE_ID_MAPPING = {
  4986: 73119,
  4446: 65460,
  5069: 32271,
  4574: 59503,
  4551: 61205,
  4430: 14400,
  4414: 11847,
  4714: 44185,
  5479: 72268,
  5480: 124179,
};

const PREM_LEAGUE_ID = 4414;

export const normTeamLogoKey = (name) =>
  String(name || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

/** Mirrors backend STATIC_TEAM_LOGOS — last-resort crest URLs. */
export const STATIC_TEAM_LOGO_FALLBACKS = {
  leinster: 'https://upload.wikimedia.org/wikipedia/en/thumb/a/a4/LeinsterRugby_logo_2019.svg/500px-LeinsterRugby_logo_2019.svg.png',
  'leinster rugby': 'https://upload.wikimedia.org/wikipedia/en/thumb/a/a4/LeinsterRugby_logo_2019.svg/500px-LeinsterRugby_logo_2019.svg.png',
  munster: 'https://upload.wikimedia.org/wikipedia/en/thumb/f/fb/Munster_Rugby_logo.svg/500px-Munster_Rugby_logo.svg.png',
  'munster rugby': 'https://upload.wikimedia.org/wikipedia/en/thumb/f/fb/Munster_Rugby_logo.svg/500px-Munster_Rugby_logo.svg.png',
  ulster: 'https://upload.wikimedia.org/wikipedia/en/thumb/c/c0/Ulster_Rugby_logo.svg/500px-Ulster_Rugby_logo.svg.png',
  'ulster rugby': 'https://upload.wikimedia.org/wikipedia/en/thumb/c/c0/Ulster_Rugby_logo.svg/500px-Ulster_Rugby_logo.svg.png',
  connacht: 'https://upload.wikimedia.org/wikipedia/en/thumb/6/67/ConnachtRugby_2017logo.svg/500px-ConnachtRugby_2017logo.svg.png',
  'connacht rugby': 'https://upload.wikimedia.org/wikipedia/en/thumb/6/67/ConnachtRugby_2017logo.svg/500px-ConnachtRugby_2017logo.svg.png',
  'glasgow warriors': 'https://upload.wikimedia.org/wikipedia/en/thumb/0/06/Glasgow_Warriors_Logo.svg/330px-Glasgow_Warriors_Logo.svg.png',
  glasgow: 'https://upload.wikimedia.org/wikipedia/en/thumb/0/06/Glasgow_Warriors_Logo.svg/330px-Glasgow_Warriors_Logo.svg.png',
  edinburgh: 'https://upload.wikimedia.org/wikipedia/en/thumb/e/e3/Edinburgh_Rugby_logo_2018.svg/500px-Edinburgh_Rugby_logo_2018.svg.png',
  'edinburgh rugby': 'https://upload.wikimedia.org/wikipedia/en/thumb/e/e3/Edinburgh_Rugby_logo_2018.svg/500px-Edinburgh_Rugby_logo_2018.svg.png',
  'cardiff rugby': 'https://upload.wikimedia.org/wikipedia/en/1/1f/Cardiff_Rugby_logo_%282021%29.jpg',
  cardiff: 'https://upload.wikimedia.org/wikipedia/en/1/1f/Cardiff_Rugby_logo_%282021%29.jpg',
  ospreys: 'https://upload.wikimedia.org/wikipedia/en/thumb/2/2c/Ospreys_Rugby_logo.svg/500px-Ospreys_Rugby_logo.svg.png',
  scarlets: 'https://upload.wikimedia.org/wikipedia/en/thumb/0/07/Scarlets_logo.svg/330px-Scarlets_logo.svg.png',
  dragons: 'https://upload.wikimedia.org/wikipedia/en/9/9b/Dragons_RFC_logo.png',
  'dragons rfc': 'https://upload.wikimedia.org/wikipedia/en/9/9b/Dragons_RFC_logo.png',
  benetton: 'https://upload.wikimedia.org/wikipedia/en/thumb/a/ac/Benetton_rugby.svg/500px-Benetton_rugby.svg.png',
  'benetton rugby': 'https://upload.wikimedia.org/wikipedia/en/thumb/a/ac/Benetton_rugby.svg/500px-Benetton_rugby.svg.png',
  'benetton treviso': 'https://highlightly.net/rugby/images/teams/334376.png',
  zebre: 'https://upload.wikimedia.org/wikipedia/en/5/5d/Zebre_parma_logo23.png',
  'zebre parma': 'https://upload.wikimedia.org/wikipedia/en/5/5d/Zebre_parma_logo23.png',
  bulls: 'https://highlightly.net/rugby/images/teams/250978.png',
  'vodacom bulls': 'https://highlightly.net/rugby/images/teams/250978.png',
  'blue bulls': 'https://highlightly.net/rugby/images/teams/250978.png',
  stormers: 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/16/StormersRugbyClubLogo2025.svg/500px-StormersRugbyClubLogo2025.svg.png',
  'dhl stormers': 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/16/StormersRugbyClubLogo2025.svg/500px-StormersRugbyClubLogo2025.svg.png',
  sharks: 'https://upload.wikimedia.org/wikipedia/en/9/9f/Sharks_rugby_union_logo.png',
  'hollywoodbets sharks': 'https://upload.wikimedia.org/wikipedia/en/9/9f/Sharks_rugby_union_logo.png',
  'the sharks': 'https://highlightly.net/rugby/images/teams/257786.png',
  lions: 'https://highlightly.net/rugby/images/teams/253531.png',
  'emirates lions': 'https://highlightly.net/rugby/images/teams/253531.png',
  'golden lions': 'https://highlightly.net/rugby/images/teams/253531.png',
  blues: 'https://upload.wikimedia.org/wikipedia/en/c/cd/Auckland_Blues_rugby_logo.webp',
  'auckland blues': 'https://upload.wikimedia.org/wikipedia/en/c/cd/Auckland_Blues_rugby_logo.webp',
  chiefs: 'https://upload.wikimedia.org/wikipedia/en/8/87/Chiefs_rugby_union_logo.jpg',
  crusaders: 'https://upload.wikimedia.org/wikipedia/en/thumb/b/bd/Crusaders_%28rugby_union%29_logo.png/330px-Crusaders_%28rugby_union%29_logo.png',
  highlanders: 'https://upload.wikimedia.org/wikipedia/en/thumb/a/a7/Highlanders_NZ_rugby_union_team_logo.svg/330px-Highlanders_NZ_rugby_union_team_logo.svg.png',
  hurricanes: 'https://upload.wikimedia.org/wikipedia/en/thumb/2/28/Wellington_Hurricanes_logo.png/330px-Wellington_Hurricanes_logo.png',
  brumbies: 'https://upload.wikimedia.org/wikipedia/en/thumb/5/53/Brumbies_Rugby_logo.svg/500px-Brumbies_Rugby_logo.svg.png',
  reds: 'https://upload.wikimedia.org/wikipedia/en/thumb/e/e1/QLD_reds_logo.svg/500px-QLD_reds_logo.svg.png',
  'queensland reds': 'https://upload.wikimedia.org/wikipedia/en/thumb/e/e1/QLD_reds_logo.svg/500px-QLD_reds_logo.svg.png',
  waratahs: 'https://upload.wikimedia.org/wikipedia/en/thumb/6/6f/Waratahs_logo.svg/500px-Waratahs_logo.svg.png',
  rebels: 'https://upload.wikimedia.org/wikipedia/en/thumb/a/a3/Melbourne_Rebels_logo.svg/330px-Melbourne_Rebels_logo.svg.png',
  'western force': 'https://upload.wikimedia.org/wikipedia/en/0/01/Western_force_rugby_logo.png',
  'fijian drua': 'https://upload.wikimedia.org/wikipedia/en/thumb/9/9c/FijianDruaLogo.svg/250px-FijianDruaLogo.svg.png',
  'moana pasifika': 'https://upload.wikimedia.org/wikipedia/en/2/20/Moana_Pasifika_logo.jpg',
  'northampton saints': 'https://highlightly.net/rugby/images/teams/56099.png',
  'bath rugby': 'https://highlightly.net/rugby/images/teams/50142.png',
  bath: 'https://highlightly.net/rugby/images/teams/50142.png',
  'exeter chiefs': 'https://highlightly.net/rugby/images/teams/51844.png',
  'leicester tigers': 'https://highlightly.net/rugby/images/teams/54397.png',
  saracens: 'https://highlightly.net/rugby/images/teams/57801.png',
  'bristol bears': 'https://highlightly.net/rugby/images/teams/50993.png',
  'sale sharks': 'https://highlightly.net/rugby/images/teams/56950.png',
  'gloucester rugby': 'https://highlightly.net/rugby/images/teams/52695.png',
  harlequins: 'https://highlightly.net/rugby/images/teams/53546.png',
  'newcastle falcons': 'https://highlightly.net/rugby/images/teams/69715.png',
  'stade toulousain': 'https://highlightly.net/rugby/images/teams/91841.png',
  toulouse: 'https://highlightly.net/rugby/images/teams/91841.png',
  montpellier: 'https://highlightly.net/rugby/images/teams/87586.png',
  'stade francais': 'https://highlightly.net/rugby/images/teams/90990.png',
  'racing 92': 'https://highlightly.net/rugby/images/teams/89288.png',
  'stade rochelais': 'https://highlightly.net/rugby/images/teams/85884.png',
  'la rochelle': 'https://highlightly.net/rugby/images/teams/85884.png',
  clermont: 'https://highlightly.net/rugby/images/teams/85033.png',
  'union bordeaux': 'https://highlightly.net/rugby/images/teams/82480.png',
  bordeaux: 'https://highlightly.net/rugby/images/teams/82480.png',
  toulon: 'https://highlightly.net/rugby/images/teams/88437.png',
  castres: 'https://highlightly.net/rugby/images/teams/84182.png',
  lyon: 'https://highlightly.net/rugby/images/teams/86735.png',
  bayonne: 'https://highlightly.net/rugby/images/teams/81629.png',
  perpignan: 'https://highlightly.net/rugby/images/teams/102904.png',
  england: 'https://media.api-sports.io/rugby/teams/386.png',
  france: 'https://media.api-sports.io/rugby/teams/387.png',
  ireland: 'https://media.api-sports.io/rugby/teams/388.png',
  italy: 'https://media.api-sports.io/rugby/teams/389.png',
  scotland: 'https://media.api-sports.io/rugby/teams/390.png',
  wales: 'https://media.api-sports.io/rugby/teams/391.png',
  argentina: 'https://media.api-sports.io/rugby/teams/460.png',
  australia: 'https://media.api-sports.io/rugby/teams/461.png',
  'new zealand': 'https://media.api-sports.io/rugby/teams/465.png',
  'south africa': 'https://media.api-sports.io/rugby/teams/467.png',
  fiji: 'https://media.api-sports.io/rugby/teams/28.png',
  japan: 'https://media.api-sports.io/rugby/teams/463.png',
};

const isBrokenPremLogoUrl = (url, leagueId) => {
  if (Number(leagueId) !== PREM_LEAGUE_ID) return false;
  if (!url || typeof url !== 'string') return false;
  return url.includes('upload.wikimedia.org') && url.includes('/thumb/');
};

const logoKeyVariants = (teamName) => {
  const key = normTeamLogoKey(teamName);
  if (!key) return [];
  const variants = [key];
  const stripped = key.replace(/\b(rugby|fc|rc|rfc)\b/g, ' ').replace(/\s+/g, ' ').trim();
  if (stripped && stripped !== key) variants.push(stripped);
  const words = stripped.split(/\s+/).filter(Boolean);
  if (words.length >= 2) variants.push(words.slice(0, 2).join(' '));
  if (words.length >= 1) variants.push(words[0]);
  return [...new Set(variants)];
};

export const resolveStaticTeamLogoUrl = (teamName, leagueId = null) => {
  for (const variant of logoKeyVariants(teamName)) {
    const url = STATIC_TEAM_LOGO_FALLBACKS[variant];
    if (url && !isBrokenPremLogoUrl(url, leagueId)) return url;
  }
  return null;
};

export const buildTeamLogoMapFromStandings = (standings) => {
  const map = {};
  if (!standings || !Array.isArray(standings.groups)) return map;

  for (const group of standings.groups) {
    const rows = group?.standings || group?.teams || [];
    for (const row of rows) {
      const team = row?.team || row || {};
      const name = team.name || team.team_name || team.strTeam || row.teamName;
      const logo = team.logo || team.badge || team.image || row.logo || row.badge;
      if (!name || !logo) continue;
      const key = normTeamLogoKey(name);
      if (key && !map[key]) map[key] = logo;
    }
  }
  return map;
};

const getLicenseCacheKey = (sportsdbLeagueId, highlightlyLeagueId) => {
  let license = 'anon';
  try {
    const raw = localStorage.getItem('rugby_ai_auth');
    if (raw) {
      const auth = JSON.parse(raw);
      if (auth?.licenseKey) license = String(auth.licenseKey);
    }
  } catch (e) {
    // ignore
  }
  return `standings_cache_v5::${license}::sportsdb_${sportsdbLeagueId}::hl_${highlightlyLeagueId}`;
};

export const readStandingsLogoCache = (leagueId) => {
  try {
    const hlId = LEAGUE_ID_MAPPING[Number(leagueId)];
    if (!hlId) return {};
    const raw = localStorage.getItem(getLicenseCacheKey(leagueId, hlId));
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return buildTeamLogoMapFromStandings(parsed?.standings);
  } catch (e) {
    return {};
  }
};

export const lookupTeamLogoInMap = (teamName, logoMap = {}) => {
  if (!teamName || !logoMap || typeof logoMap !== 'object') return null;
  for (const variant of logoKeyVariants(teamName)) {
    if (logoMap[variant]) return logoMap[variant];
  }
  const keys = Object.keys(logoMap);
  const norm = normTeamLogoKey(teamName);
  for (const k of keys) {
    if (k.includes(norm) || norm.includes(k)) return logoMap[k];
  }
  return null;
};

/**
 * Resolve crest URL: standings map first, then static fallbacks.
 */
export const resolveTeamLogoUrl = (teamName, { leagueId = null, logoMap = {} } = {}) => {
  const fromStandings = lookupTeamLogoInMap(teamName, logoMap);
  if (fromStandings && !isBrokenPremLogoUrl(fromStandings, leagueId)) {
    return fromStandings;
  }
  return resolveStaticTeamLogoUrl(teamName, leagueId);
};

export const getHighlightlyLeagueId = (leagueId) => LEAGUE_ID_MAPPING[Number(leagueId)] || null;

export const getStandingsSeasonForLeague = (leagueId) =>
  leagueId ? getPrimaryStandingsSeasonYear(leagueId) : null;
