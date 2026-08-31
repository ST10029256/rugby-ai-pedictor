import { getPrimaryStandingsSeasonYear } from './season';
import leagueTeamsFallback from './leagueTeamsFallback.json';
import staticTeamLogos from './staticTeamLogos.json';

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

export const INTERNATIONAL_LEAGUE_IDS = new Set([4986, 4574, 4714, 5479, 5480]);

const PREM_LEAGUE_ID = 4414;

/** Generated from rugby-ai-predictor/prediction/config.py — run scripts/export_static_team_logos.py */
export const STATIC_TEAM_LOGO_FALLBACKS = staticTeamLogos;

export const normTeamLogoKey = (name) =>
  String(name || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

export const stripClubSuffix = (name) =>
  normTeamLogoKey(name)
    .replace(/\b(rugby union|rugby|rfc|fc|rc|ps)\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

export const compactTeamKey = (name) => stripClubSuffix(name).replace(/\s+/g, '');

/** Canonical key for deduping Portugal vs Portugal Rugby, etc. */
export const canonicalTeamKey = (name) => compactTeamKey(name);

const INTL_FRANCHISE_TO_NATIONAL = {
  fijiandrua: 'fiji',
};

export const pickPreferredTeamName = (names) =>
  [...names].sort((a, b) => {
    const aHasRugby = /\brugby\b/i.test(a) ? 1 : 0;
    const bHasRugby = /\brugby\b/i.test(b) ? 1 : 0;
    if (aHasRugby !== bHasRugby) return aHasRugby - bHasRugby;
    return a.length - b.length;
  })[0];

export const shouldSkipIntlFranchiseDuplicate = (name, leagueId, presentKeys) => {
  if (!INTERNATIONAL_LEAGUE_IDS.has(Number(leagueId))) return false;
  const key = compactTeamKey(name);
  const national = INTL_FRANCHISE_TO_NATIONAL[key];
  return Boolean(national && presentKeys.has(national));
};

/** Merge duplicate sides (same canonical key) and prefer clean display names. */
export const dedupeTeams = (teams, leagueId = null) => {
  const map = new Map();
  const presentKeys = new Set();

  for (const team of teams || []) {
    const key = canonicalTeamKey(team.name);
    if (!key) continue;
    if (shouldSkipIntlFranchiseDuplicate(team.name, leagueId, presentKeys)) continue;

    const existing = map.get(key);
    if (!existing) {
      map.set(key, {
        ...team,
        name: String(team.name).trim(),
        aliases: [String(team.name).trim()],
      });
      presentKeys.add(key);
      continue;
    }

    existing.aliases = [...new Set([...existing.aliases, String(team.name).trim()])];
    if (!existing.logo && team.logo) existing.logo = team.logo;
    existing.name = pickPreferredTeamName([existing.name, team.name]);
  }

  return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
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
  const stripped = stripClubSuffix(teamName);
  if (stripped && stripped !== key) variants.push(stripped);
  const words = stripped.split(/\s+/).filter(Boolean);
  if (words.length >= 2) variants.push(words.slice(0, 2).join(' '));
  if (words.length >= 1) variants.push(words[0]);
  return [...new Set(variants.filter(Boolean))];
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
      for (const variant of logoKeyVariants(name)) {
        if (variant && !map[variant]) map[variant] = logo;
      }
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

export const readStandingsCache = (leagueId) => {
  try {
    const hlId = LEAGUE_ID_MAPPING[Number(leagueId)];
    if (!hlId) return null;
    const raw = localStorage.getItem(getLicenseCacheKey(leagueId, hlId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.standings) return null;
    return parsed;
  } catch (e) {
    return null;
  }
};

export const readStandingsLogoCache = (leagueId) => {
  const cached = readStandingsCache(leagueId);
  if (!cached?.standings) return {};
  return buildTeamLogoMapFromStandings(cached.standings);
};

/** Pull team rows from a standings payload (SportRadar / Highlightly shape). */
export const extractTeamsFromStandings = (standings, source = 'standings') => {
  const out = [];
  const seen = new Set();
  if (!standings || !Array.isArray(standings.groups)) return out;

  for (const group of standings.groups) {
    const rows = group?.standings || group?.teams || [];
    for (const row of rows) {
      const team = row?.team || row || {};
      const name = team.name || team.team_name || team.strTeam || row.teamName;
      if (!name) continue;
      const key = canonicalTeamKey(name);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push({
        name: String(name).trim(),
        logo:
          team.logo ||
          team.badge ||
          team.image ||
          team.strTeamBadge ||
          row.logo ||
          row.badge ||
          null,
        source,
      });
    }
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
};

/** Offline roster when standings / fixtures APIs are slow or empty. */
export const getStaticLeagueTeams = (leagueId) => {
  const names = leagueTeamsFallback[String(Number(leagueId))];
  if (!Array.isArray(names) || !names.length) return [];
  return names.map((name) => ({
    name: String(name).trim(),
    logo: resolveStaticTeamLogoUrl(name, leagueId),
    source: 'static',
  }));
};

export const mergeTeamsIntoMap = (teamMap, teams, source = null) => {
  for (const team of teams || []) {
    const name = team?.name;
    if (!name) continue;
    const key = canonicalTeamKey(name);
    if (!key) continue;
    const existing = teamMap.get(key);
    if (existing) {
      if (!existing.logo && team.logo) {
        teamMap.set(key, { ...existing, logo: team.logo });
      }
      continue;
    }
    teamMap.set(key, {
      name: String(name).trim(),
      logo: team.logo || null,
      source: source || team.source || 'unknown',
    });
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

export const resolveTeamLogoUrl = (teamName, { leagueId = null, logoMap = {} } = {}) => {
  const fromStandings = lookupTeamLogoInMap(teamName, logoMap);
  if (fromStandings && !isBrokenPremLogoUrl(fromStandings, leagueId)) {
    return fromStandings;
  }
  return resolveStaticTeamLogoUrl(teamName, leagueId);
};

/** Ordered crest URLs — try each in sequence when an image fails to load. */
export const buildTeamLogoCandidates = (
  teamName,
  { leagueId = null, logoMap = {}, explicitLogo = null } = {}
) => {
  const candidates = [];
  const add = (url) => {
    if (!url || typeof url !== 'string') return;
    if (isBrokenPremLogoUrl(url, leagueId)) return;
    if (!candidates.includes(url)) candidates.push(url);
  };

  add(explicitLogo);
  add(lookupTeamLogoInMap(teamName, logoMap));
  add(resolveStaticTeamLogoUrl(teamName, leagueId));

  return candidates;
};

export const getHighlightlyLeagueId = (leagueId) => LEAGUE_ID_MAPPING[Number(leagueId)] || null;

export const getStandingsSeasonForLeague = (leagueId) =>
  leagueId ? getPrimaryStandingsSeasonYear(leagueId) : null;
