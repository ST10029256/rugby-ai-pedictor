/** Rugby Union on-field display order (front row first, fullback last, then bench). */
import { resolveTeamLogoUrl } from './teamLogos';

export const rugbyUnionDisplayOrder = [
  1, 2, 3,
  4, 5,
  6, 7, 8,
  9, 10,
  12, 13,
  11, 14,
  15,
  16, 17, 18, 19, 20, 21, 22, 23,
];

export const jerseyPositionLabels = {
  1: 'Loosehead Prop',
  2: 'Hooker',
  3: 'Tighthead Prop',
  4: 'Lock',
  5: 'Lock',
  6: 'Blindside Flanker',
  7: 'Openside Flanker',
  8: 'Number Eight',
  9: 'Scrum-half',
  10: 'Fly-half',
  12: 'Inside Centre',
  13: 'Outside Centre',
  11: 'Left Wing',
  14: 'Right Wing',
  15: 'Fullback',
};

export const RUGBY_SQUAD_SIZE = 23;

const orderIndex = new Map(rugbyUnionDisplayOrder.map((num, idx) => [num, idx]));

export const sortPlayersByDisplayOrder = (players = []) => {
  return [...players].sort((a, b) => {
    const ai = orderIndex.get(Number(a?.jersey_number)) ?? 999;
    const bi = orderIndex.get(Number(b?.jersey_number)) ?? 999;
    if (ai !== bi) return ai - bi;
    return Number(a?.jersey_number || 0) - Number(b?.jersey_number || 0);
  });
};

export const splitStartersAndBench = (players = []) => {
  const { byJersey } = analyzeSquad(players);
  const sorted = sortPlayersByDisplayOrder(
    [...byJersey.values(), ...getUnlistedPlayers(players)]
  );
  return {
    starters: sorted.filter((p) => {
      const n = Number(p?.jersey_number);
      return Number.isFinite(n) && n >= 1 && n <= 15;
    }),
    bench: sorted.filter((p) => {
      const n = Number(p?.jersey_number);
      return Number.isFinite(n) && n >= 16 && n <= RUGBY_SQUAD_SIZE;
    }),
  };
};

/** Starter groups — pack first, then backline (showcase order). */
export const STARTER_POSITION_GROUPS = [
  {
    id: 'front-row',
    title: 'Front Row',
    subtitle: 'Loosehead prop · Hooker · Tighthead prop',
    jerseys: [1, 2, 3],
    phase: 'forwards',
    layout: 'row-3',
    roleByJersey: {
      1: 'Loosehead Prop',
      2: 'Hooker',
      3: 'Tighthead Prop',
    },
  },
  {
    id: 'locks',
    title: 'Second Row',
    subtitle: 'Lock · Lock',
    jerseys: [4, 5],
    phase: 'forwards',
    layout: 'row-2',
    roleByJersey: { 4: 'Lock', 5: 'Lock' },
  },
  {
    id: 'back-row',
    title: 'Back Row',
    subtitle: 'Blindside flanker · Openside flanker · Number eight',
    jerseys: [6, 7, 8],
    phase: 'forwards',
    layout: 'row-3',
    roleByJersey: {
      6: 'Blindside Flanker',
      7: 'Openside Flanker',
      8: 'Number Eight',
    },
  },
  {
    id: 'halfbacks',
    title: 'Halfbacks',
    subtitle: 'Scrum-half · Fly-half',
    jerseys: [9, 10],
    phase: 'backs',
    layout: 'row-2',
    roleByJersey: { 9: 'Scrum-half', 10: 'Fly-half' },
  },
  {
    id: 'centres',
    title: 'Centres',
    subtitle: 'Inside centre · Outside centre',
    jerseys: [12, 13],
    phase: 'backs',
    layout: 'row-2',
    roleByJersey: { 12: 'Inside Centre', 13: 'Outside Centre' },
  },
  {
    id: 'wings',
    title: 'Wings',
    subtitle: 'Left wing · Right wing',
    jerseys: [11, 14],
    phase: 'backs',
    layout: 'row-2',
    roleByJersey: { 11: 'Left Wing', 14: 'Right Wing' },
  },
  {
    id: 'fullback',
    title: 'Fullback',
    subtitle: 'Last line of defence · Counter-attack',
    jerseys: [15],
    phase: 'backs',
    layout: 'solo',
    roleByJersey: { 15: 'Fullback' },
  },
];

export const BENCH_POSITION_GROUPS = [
  {
    id: 'bench-forwards',
    title: 'Forward Bench',
    subtitle: 'Hooker · Props · Lock · Back row · 16–20',
    jerseys: [16, 17, 18, 19, 20],
    layout: 'row-5',
  },
  {
    id: 'bench-backs',
    title: 'Backline Bench',
    subtitle: 'Scrum-half · Fly-half · Utility back · 21–23',
    jerseys: [21, 22, 23],
    layout: 'row-3',
  },
];

const pickPlayersByJerseys = (players = [], jerseys = []) => {
  const { byJersey } = analyzeSquad(players);
  return jerseys.map((j) => byJersey.get(j)).filter(Boolean);
};

/** Map jersey slots + track duplicates / missing numbers for display. */
export const analyzeSquad = (players = []) => {
  const byJersey = new Map();
  const unlisted = [];

  for (const player of players) {
    const raw = player?.jersey_number;
    const num = raw == null || raw === '' ? null : Number(raw);
    if (!Number.isFinite(num) || num < 1 || num > RUGBY_SQUAD_SIZE) {
      unlisted.push(player);
      continue;
    }
    if (byJersey.has(num)) {
      unlisted.push(player);
    } else {
      byJersey.set(num, player);
    }
  }

  const missingJerseys = [];
  for (let j = 1; j <= RUGBY_SQUAD_SIZE; j += 1) {
    if (!byJersey.has(j)) missingJerseys.push(j);
  }

  return {
    totalRows: players.length,
    slotsFilled: byJersey.size,
    expectedSlots: RUGBY_SQUAD_SIZE,
    missingJerseys,
    unlisted,
    byJersey,
    isComplete: byJersey.size >= RUGBY_SQUAD_SIZE && unlisted.length === 0,
  };
};

export const getUnlistedPlayers = (players = []) => analyzeSquad(players).unlisted;

export const squadSummaryFromTeam = (team) => {
  if (team?.squad_summary) {
    const s = team.squad_summary;
    return {
      totalRows: s.total_rows ?? 0,
      slotsFilled: s.slots_filled ?? 0,
      expectedSlots: s.expected_slots ?? RUGBY_SQUAD_SIZE,
      missingJerseys: s.missing_jerseys ?? [],
      unlistedCount: s.unlisted_count ?? 0,
      isComplete: Boolean(s.is_complete),
    };
  }
  return analyzeSquad(team?.players || []);
};

export const groupStartersByPosition = (starters = []) => {
  const groups = STARTER_POSITION_GROUPS.map((g) => ({
    ...g,
    players: pickPlayersByJerseys(starters, g.jerseys),
  })).filter((g) => g.players.length > 0);

  return {
    groups,
    forwards: groups.filter((g) => g.phase === 'forwards'),
    backs: groups.filter((g) => g.phase === 'backs'),
  };
};

export const groupBenchByPosition = (bench = []) => {
  return BENCH_POSITION_GROUPS.map((g) => ({
    ...g,
    players: pickPlayersByJerseys(bench, g.jerseys),
  })).filter((g) => g.players.length > 0);
};

/** Kit colour specs — design: leinster | bulls | stripe | classic */
const TEAM_KIT_SPECS = {
  leinster: {
    id: 'leinster',
    design: 'leinster',
    primary: '#0082CA',
    secondary: '#003087',
    accent: '#FFFFFF',
    collar: '#003087',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 130, 202, 0.45)',
  },
  munster: {
    id: 'munster',
    design: 'stripe',
    primary: '#C8102E',
    secondary: '#8B0000',
    accent: '#FFFFFF',
    collar: '#8B0000',
    stripe: '#FFFFFF',
    glow: 'rgba(200, 16, 46, 0.4)',
  },
  ulster: {
    id: 'ulster',
    design: 'stripe',
    primary: '#E30613',
    secondary: '#1A1A1A',
    accent: '#FFFFFF',
    collar: '#1A1A1A',
    stripe: '#FFFFFF',
    glow: 'rgba(227, 6, 19, 0.35)',
  },
  connacht: {
    id: 'connacht',
    design: 'stripe',
    primary: '#006838',
    secondary: '#004D2A',
    accent: '#FFFFFF',
    collar: '#004D2A',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 104, 56, 0.35)',
  },
  glasgow: {
    id: 'glasgow',
    design: 'classic',
    primary: '#2D2D2D',
    secondary: '#5C6BC0',
    accent: '#FFFFFF',
    collar: '#1A1A1A',
    stripe: '#5C6BC0',
    glow: 'rgba(92, 107, 192, 0.3)',
  },
  edinburgh: {
    id: 'edinburgh',
    design: 'stripe',
    primary: '#003366',
    secondary: '#8B0000',
    accent: '#FFFFFF',
    collar: '#003366',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 51, 102, 0.35)',
  },
  cardiff: {
    id: 'cardiff',
    design: 'classic',
    primary: '#0B3D91',
    secondary: '#1A1A1A',
    accent: '#FFFFFF',
    collar: '#0B3D91',
    stripe: '#FFFFFF',
    glow: 'rgba(11, 61, 145, 0.35)',
  },
  ospreys: {
    id: 'ospreys',
    design: 'classic',
    primary: '#1A1A1A',
    secondary: '#4A4A4A',
    accent: '#FFFFFF',
    collar: '#333333',
    stripe: '#FFFFFF',
    glow: 'rgba(255, 255, 255, 0.15)',
  },
  scarlets: {
    id: 'scarlets',
    design: 'classic',
    primary: '#C8102E',
    secondary: '#8B0000',
    accent: '#FFFFFF',
    collar: '#8B0000',
    stripe: '#FFFFFF',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  dragons: {
    id: 'dragons',
    design: 'stripe',
    primary: '#FFD700',
    secondary: '#C8102E',
    accent: '#1A1A1A',
    collar: '#C8102E',
    stripe: '#C8102E',
    glow: 'rgba(255, 215, 0, 0.3)',
  },
  benetton: {
    id: 'benetton',
    design: 'stripe',
    primary: '#006838',
    secondary: '#004D2A',
    accent: '#FFFFFF',
    collar: '#004D2A',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 104, 56, 0.35)',
  },
  zebre: {
    id: 'zebre',
    design: 'classic',
    primary: '#1A1A1A',
    secondary: '#006838',
    accent: '#FFFFFF',
    collar: '#006838',
    stripe: '#006838',
    glow: 'rgba(0, 104, 56, 0.25)',
  },
  bulls: {
    id: 'bulls',
    design: 'bulls',
    primary: '#002776',
    secondary: '#009CDE',
    accent: '#FFFFFF',
    collar: '#001A4D',
    stripe: '#009CDE',
    glow: 'rgba(0, 156, 222, 0.4)',
  },
  stormers: {
    id: 'stormers',
    design: 'stripe',
    primary: '#0033A0',
    secondary: '#001A4D',
    accent: '#FFFFFF',
    collar: '#001A4D',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 51, 160, 0.35)',
  },
  sharks: {
    id: 'sharks',
    design: 'classic',
    primary: '#1A1A1A',
    secondary: '#00A9A5',
    accent: '#FFFFFF',
    collar: '#00A9A5',
    stripe: '#00A9A5',
    glow: 'rgba(0, 169, 165, 0.3)',
  },
  lions: {
    id: 'lions',
    design: 'stripe',
    primary: '#C8102E',
    secondary: '#8B0000',
    accent: '#FFD700',
    collar: '#8B0000',
    stripe: '#FFD700',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  blues: {
    id: 'blues',
    design: 'classic',
    primary: '#003DA5',
    secondary: '#001F5C',
    accent: '#FFFFFF',
    collar: '#001F5C',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 61, 165, 0.35)',
  },
  chiefs: {
    id: 'chiefs',
    design: 'stripe',
    primary: '#C8102E',
    secondary: '#FFD700',
    accent: '#1A1A1A',
    collar: '#8B0000',
    stripe: '#FFD700',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  crusaders: {
    id: 'crusaders',
    design: 'classic',
    primary: '#1A1A1A',
    secondary: '#C8102E',
    accent: '#FFFFFF',
    collar: '#C8102E',
    stripe: '#C8102E',
    glow: 'rgba(200, 16, 46, 0.3)',
  },
  highlanders: {
    id: 'highlanders',
    design: 'classic',
    primary: '#4B0082',
    secondary: '#FFD700',
    accent: '#FFFFFF',
    collar: '#4B0082',
    stripe: '#FFD700',
    glow: 'rgba(75, 0, 130, 0.35)',
  },
  hurricanes: {
    id: 'hurricanes',
    design: 'classic',
    primary: '#FFD700',
    secondary: '#1A1A1A',
    accent: '#1A1A1A',
    collar: '#1A1A1A',
    stripe: '#1A1A1A',
    glow: 'rgba(255, 215, 0, 0.3)',
  },
  brumbies: {
    id: 'brumbies',
    design: 'stripe',
    primary: '#003DA5',
    secondary: '#FFD700',
    accent: '#FFFFFF',
    collar: '#003DA5',
    stripe: '#FFD700',
    glow: 'rgba(0, 61, 165, 0.35)',
  },
  reds: {
    id: 'reds',
    design: 'classic',
    primary: '#C8102E',
    secondary: '#8B0000',
    accent: '#FFFFFF',
    collar: '#8B0000',
    stripe: '#FFFFFF',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  waratahs: {
    id: 'waratahs',
    design: 'classic',
    primary: '#6B0F1A',
    secondary: '#4A0A12',
    accent: '#FFFFFF',
    collar: '#4A0A12',
    stripe: '#FFFFFF',
    glow: 'rgba(107, 15, 26, 0.35)',
  },
  rebels: {
    id: 'rebels',
    design: 'classic',
    primary: '#1A1A1A',
    secondary: '#003DA5',
    accent: '#FFFFFF',
    collar: '#003DA5',
    stripe: '#003DA5',
    glow: 'rgba(0, 61, 165, 0.3)',
  },
  force: {
    id: 'force',
    design: 'classic',
    primary: '#FFFFFF',
    secondary: '#003DA5',
    accent: '#003DA5',
    collar: '#003DA5',
    stripe: '#003DA5',
    glow: 'rgba(0, 61, 165, 0.25)',
  },
  drua: {
    id: 'drua',
    design: 'classic',
    primary: '#003DA5',
    secondary: '#FFFFFF',
    accent: '#FFFFFF',
    collar: '#003DA5',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 61, 165, 0.35)',
  },
  moana: {
    id: 'moana',
    design: 'classic',
    primary: '#003DA5',
    secondary: '#00A9A5',
    accent: '#FFFFFF',
    collar: '#003DA5',
    stripe: '#00A9A5',
    glow: 'rgba(0, 61, 165, 0.3)',
  },
  saracens: {
    id: 'saracens',
    design: 'classic',
    primary: '#1A1A1A',
    secondary: '#C8102E',
    accent: '#FFFFFF',
    collar: '#C8102E',
    stripe: '#C8102E',
    glow: 'rgba(200, 16, 46, 0.3)',
  },
  bath: {
    id: 'bath',
    design: 'stripe',
    primary: '#003DA5',
    secondary: '#001F5C',
    accent: '#FFFFFF',
    collar: '#001F5C',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 61, 165, 0.35)',
  },
  exeter: {
    id: 'exeter',
    design: 'stripe',
    primary: '#003366',
    secondary: '#FFD700',
    accent: '#FFFFFF',
    collar: '#003366',
    stripe: '#FFD700',
    glow: 'rgba(0, 51, 102, 0.35)',
  },
  leicester: {
    id: 'leicester',
    design: 'stripe',
    primary: '#006838',
    secondary: '#004D2A',
    accent: '#FFFFFF',
    collar: '#004D2A',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 104, 56, 0.35)',
  },
  bristol: {
    id: 'bristol',
    design: 'classic',
    primary: '#003DA5',
    secondary: '#C8102E',
    accent: '#FFFFFF',
    collar: '#003DA5',
    stripe: '#C8102E',
    glow: 'rgba(0, 61, 165, 0.35)',
  },
  sale: {
    id: 'sale',
    design: 'classic',
    primary: '#003DA5',
    secondary: '#1A1A1A',
    accent: '#FFFFFF',
    collar: '#1A1A1A',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 61, 165, 0.35)',
  },
  gloucester: {
    id: 'gloucester',
    design: 'classic',
    primary: '#C8102E',
    secondary: '#FFFFFF',
    accent: '#1A1A1A',
    collar: '#8B0000',
    stripe: '#FFFFFF',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  harlequins: {
    id: 'harlequins',
    design: 'classic',
    primary: '#6B0F7A',
    secondary: '#4A0A55',
    accent: '#FFFFFF',
    collar: '#4A0A55',
    stripe: '#00A651',
    glow: 'rgba(107, 15, 122, 0.35)',
  },
  northampton: {
    id: 'northampton',
    design: 'classic',
    primary: '#006838',
    secondary: '#004D2A',
    accent: '#FFD700',
    collar: '#004D2A',
    stripe: '#FFD700',
    glow: 'rgba(0, 104, 56, 0.35)',
  },
  newcastle: {
    id: 'newcastle',
    design: 'classic',
    primary: '#1A1A1A',
    secondary: '#003DA5',
    accent: '#FFFFFF',
    collar: '#003DA5',
    stripe: '#003DA5',
    glow: 'rgba(0, 61, 165, 0.3)',
  },
  toulouse: {
    id: 'toulouse',
    design: 'classic',
    primary: '#C8102E',
    secondary: '#8B0000',
    accent: '#FFFFFF',
    collar: '#8B0000',
    stripe: '#FFFFFF',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  racing: {
    id: 'racing',
    design: 'classic',
    primary: '#87CEEB',
    secondary: '#FFFFFF',
    accent: '#003DA5',
    collar: '#003DA5',
    stripe: '#FFFFFF',
    glow: 'rgba(135, 206, 235, 0.35)',
  },
  rochelle: {
    id: 'rochelle',
    design: 'classic',
    primary: '#FFD700',
    secondary: '#1A1A1A',
    accent: '#1A1A1A',
    collar: '#1A1A1A',
    stripe: '#1A1A1A',
    glow: 'rgba(255, 215, 0, 0.3)',
  },
  clermont: {
    id: 'clermont',
    design: 'classic',
    primary: '#FFD700',
    secondary: '#003DA5',
    accent: '#1A1A1A',
    collar: '#003DA5',
    stripe: '#003DA5',
    glow: 'rgba(255, 215, 0, 0.3)',
  },
  bordeaux: {
    id: 'bordeaux',
    design: 'classic',
    primary: '#6B0F7A',
    secondary: '#FFFFFF',
    accent: '#FFFFFF',
    collar: '#4A0A55',
    stripe: '#FFFFFF',
    glow: 'rgba(107, 15, 122, 0.35)',
  },
  toulon: {
    id: 'toulon',
    design: 'classic',
    primary: '#C8102E',
    secondary: '#1A1A1A',
    accent: '#FFFFFF',
    collar: '#1A1A1A',
    stripe: '#FFFFFF',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  england: {
    id: 'england',
    design: 'classic',
    primary: '#FFFFFF',
    secondary: '#C8102E',
    accent: '#003366',
    collar: '#C8102E',
    stripe: '#C8102E',
    glow: 'rgba(200, 16, 46, 0.25)',
  },
  france: {
    id: 'france',
    design: 'classic',
    primary: '#003DA5',
    secondary: '#FFFFFF',
    accent: '#C8102E',
    collar: '#003DA5',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 61, 165, 0.35)',
  },
  ireland: {
    id: 'ireland',
    design: 'classic',
    primary: '#006838',
    secondary: '#004D2A',
    accent: '#FFFFFF',
    collar: '#004D2A',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 104, 56, 0.35)',
  },
  wales: {
    id: 'wales',
    design: 'classic',
    primary: '#C8102E',
    secondary: '#8B0000',
    accent: '#FFFFFF',
    collar: '#8B0000',
    stripe: '#FFFFFF',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  scotland: {
    id: 'scotland',
    design: 'classic',
    primary: '#003DA5',
    secondary: '#FFFFFF',
    accent: '#FFFFFF',
    collar: '#003DA5',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 61, 165, 0.35)',
  },
  italy: {
    id: 'italy',
    design: 'classic',
    primary: '#006838',
    secondary: '#FFFFFF',
    accent: '#C8102E',
    collar: '#006838',
    stripe: '#FFFFFF',
    glow: 'rgba(0, 104, 56, 0.35)',
  },
  'south africa': {
    id: 'south_africa',
    design: 'classic',
    primary: '#006838',
    secondary: '#FFD700',
    accent: '#FFFFFF',
    collar: '#004D2A',
    stripe: '#FFD700',
    glow: 'rgba(0, 104, 56, 0.35)',
  },
  'new zealand': {
    id: 'new_zealand',
    design: 'classic',
    primary: '#1A1A1A',
    secondary: '#333333',
    accent: '#FFFFFF',
    collar: '#333333',
    stripe: '#FFFFFF',
    glow: 'rgba(255, 255, 255, 0.15)',
  },
  australia: {
    id: 'australia',
    design: 'classic',
    primary: '#FFD700',
    secondary: '#006838',
    accent: '#003DA5',
    collar: '#006838',
    stripe: '#006838',
    glow: 'rgba(255, 215, 0, 0.3)',
  },
  argentina: {
    id: 'argentina',
    design: 'stripe',
    primary: '#75AADB',
    secondary: '#FFFFFF',
    accent: '#1A1A1A',
    collar: '#75AADB',
    stripe: '#FFFFFF',
    glow: 'rgba(117, 170, 219, 0.35)',
  },
  chile: {
    id: 'chile',
    design: 'classic',
    primary: '#C8102E',
    secondary: '#003DA5',
    accent: '#FFFFFF',
    collar: '#003DA5',
    stripe: '#FFFFFF',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  portugal: {
    id: 'portugal',
    design: 'classic',
    primary: '#C8102E',
    secondary: '#006838',
    accent: '#FFFFFF',
    collar: '#006838',
    stripe: '#FFFFFF',
    glow: 'rgba(200, 16, 46, 0.35)',
  },
  japan: {
    id: 'japan',
    design: 'classic',
    primary: '#FFFFFF',
    secondary: '#C8102E',
    accent: '#1A1A1A',
    collar: '#C8102E',
    stripe: '#C8102E',
    glow: 'rgba(200, 16, 46, 0.25)',
  },
  boland: {
    id: 'boland',
    design: 'classic',
    primary: '#006838',
    secondary: '#FFD700',
    accent: '#FFFFFF',
    collar: '#004D2A',
    stripe: '#FFD700',
    glow: 'rgba(0, 104, 56, 0.35)',
  },
  zimbabwe: {
    id: 'zimbabwe',
    design: 'classic',
    primary: '#006838',
    secondary: '#FFD700',
    accent: '#C8102E',
    collar: '#004D2A',
    stripe: '#FFD700',
    glow: 'rgba(0, 104, 56, 0.35)',
  },
  maori: {
    id: 'maori',
    design: 'classic',
    primary: '#1A1A1A',
    secondary: '#333333',
    accent: '#FFFFFF',
    collar: '#333333',
    stripe: '#FFFFFF',
    glow: 'rgba(255, 255, 255, 0.15)',
  },
};

/** Audit gaps — keyed by SportRadar competitor_id (not team name). */
export const COMPETITOR_KIT_FALLBACKS = {
  'sr:competitor:92190': 'boland',
  'sr:competitor:393526': 'chile',
  'sr:competitor:7956': 'portugal',
  'sr:competitor:364712': 'drua',
  'sr:competitor:761406': 'moana',
  'sr:competitor:154064': 'england',
  'sr:competitor:42525': 'england',
  'sr:competitor:391538': 'france',
  'sr:competitor:200093': 'ireland',
  'sr:competitor:950175': 'japan',
  'sr:competitor:180006': 'maori',
  'sr:competitor:135744': 'scotland',
  'sr:competitor:263743': 'south africa',
  'sr:competitor:186787': 'zimbabwe',
  'sr:competitor:1325146': 'italy',
};

/** Ordered rules — first match wins (more specific patterns first). */
const KIT_MATCH_RULES = [
  [/exeter/i, 'exeter'],
  [/leinster/i, 'leinster'],
  [/munster/i, 'munster'],
  [/ulster/i, 'ulster'],
  [/connacht/i, 'connacht'],
  [/glasgow/i, 'glasgow'],
  [/edinburgh/i, 'edinburgh'],
  [/cardiff/i, 'cardiff'],
  [/osprey/i, 'ospreys'],
  [/scarlet/i, 'scarlets'],
  [/dragon/i, 'dragons'],
  [/benetton|treviso/i, 'benetton'],
  [/zebre/i, 'zebre'],
  [/stormer|dhl stormer/i, 'stormers'],
  [/hollywoodbets shark|cell c shark|\bsharks\b/i, 'sharks'],
  [/sale shark/i, 'sale'],
  [/bull|vodacom bull|blue bull/i, 'bulls'],
  [/emirates lion|golden lion|fidelity.*lion|\blions\b/i, 'lions'],
  [/auckland blue|\bblues\b/i, 'blues'],
  [/exeter/i, 'exeter'],
  [/\bchiefs\b/i, 'chiefs'],
  [/crusader/i, 'crusaders'],
  [/highlander/i, 'highlanders'],
  [/hurricane/i, 'hurricanes'],
  [/brumb/i, 'brumbies'],
  [/queensland red|\breds\b/i, 'reds'],
  [/waratah/i, 'waratahs'],
  [/rebel/i, 'rebels'],
  [/western force|\bforce\b/i, 'force'],
  [/drua/i, 'drua'],
  [/moana/i, 'moana'],
  [/boland|cavalier/i, 'boland'],
  [/chile/i, 'chile'],
  [/portugal/i, 'portugal'],
  [/japan/i, 'japan'],
  [/zimbabwe/i, 'zimbabwe'],
  [/maori/i, 'maori'],
  [/saracen/i, 'saracens'],
  [/\bbath\b/i, 'bath'],
  [/leicester|tiger/i, 'leicester'],
  [/bristol/i, 'bristol'],
  [/gloucester/i, 'gloucester'],
  [/harlequin/i, 'harlequins'],
  [/northampton/i, 'northampton'],
  [/newcastle|falcon/i, 'newcastle'],
  [/toulouse|toulousain/i, 'toulouse'],
  [/racing 92|racing92/i, 'racing'],
  [/rochel/i, 'rochelle'],
  [/clermont/i, 'clermont'],
  [/bordeaux/i, 'bordeaux'],
  [/toulon/i, 'toulon'],
  [/south africa|springbok/i, 'south africa'],
  [/new zealand|all black/i, 'new zealand'],
  [/australia|wallab/i, 'australia'],
  [/argentin/i, 'argentina'],
  [/\bengland\b/i, 'england'],
  [/\bfrance\b/i, 'france'],
  [/\bireland\b/i, 'ireland'],
  [/\bwales\b/i, 'wales'],
  [/\bscotland\b/i, 'scotland'],
  [/\bitaly\b/i, 'italy'],
];

const matchKitSpecId = (teamName = '') => {
  const raw = String(teamName);
  for (const [pattern, id] of KIT_MATCH_RULES) {
    if (pattern.test(raw)) return id;
  }
  return null;
};

const hashTeamColors = (teamName = '') => {
  let hash = 0;
  const s = String(teamName);
  for (let i = 0; i < s.length; i += 1) {
    hash = s.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  const primary = `hsl(${hue}, 55%, 32%)`;
  const secondary = `hsl(${hue}, 45%, 22%)`;
  return {
    id: 'generated',
    design: 'classic',
    primary,
    secondary,
    accent: '#FFFFFF',
    collar: secondary,
    stripe: '#FFFFFF',
    glow: `hsla(${hue}, 55%, 45%, 0.3)`,
  };
};

const hexToRgba = (hex, alpha = 0.35) => {
  const h = String(hex || '').replace('#', '');
  if (h.length !== 6) return `rgba(128, 128, 128, ${alpha})`;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

/** Convert SportRadar primary_kit colours into a renderable kit spec. */
export const kitFromSportradarPrimary = (primaryKit, competitorId = null) => {
  if (!primaryKit || !primaryKit.base) return null;
  const primary = primaryKit.base;
  const secondary = primaryKit.sleeve || primary;
  const accent = primaryKit.number || '#FFFFFF';
  const stripe = primaryKit.horizontal_stripes_color || secondary;
  const design = primaryKit.horizontal_stripes || primaryKit.stripes ? 'stripe' : 'classic';
  return {
    id: competitorId || 'sportradar',
    design,
    primary,
    secondary,
    accent,
    collar: secondary,
    stripe,
    glow: hexToRgba(primary, 0.35),
    source: 'sportradar',
  };
};

export const resolveTeamKit = (teamName = '', options = {}) => {
  const {
    leagueId = null,
    logoMap = {},
    competitorId = null,
    primaryKit = null,
    kitFallbackSpec = null,
  } = options;

  const cid = competitorId ? String(competitorId) : null;
  const fromApi = kitFromSportradarPrimary(primaryKit, cid);
  const fallbackSpecId =
    kitFallbackSpec ||
    (cid && COMPETITOR_KIT_FALLBACKS[cid]) ||
    null;
  const nameSpecId = matchKitSpecId(teamName);
  const specId = fromApi ? null : fallbackSpecId || nameSpecId;

  const base = fromApi
    ? { ...fromApi }
    : specId && TEAM_KIT_SPECS[specId]
      ? { ...TEAM_KIT_SPECS[specId] }
      : { ...hashTeamColors(teamName) };

  const logo = resolveTeamLogoUrl(teamName, { leagueId, logoMap });
  const staticLogo = resolveTeamLogoUrl(teamName, { leagueId, logoMap: {} });

  return {
    ...base,
    name: teamName || 'Team',
    competitorId: cid,
    logo,
    logoFallback: staticLogo || logo,
  };
};

export const URC_FINAL_EVENT_ID = 'sr:sport_event:71961126';
