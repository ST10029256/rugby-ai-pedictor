// Date helpers used for stable keys and UI when a match date is missing.
// NOTE: `Date.toISOString()` returns UTC, which can shift the day near midnight in local time.

export function getLocalYYYYMMDD(date = new Date()) {
  const d = date instanceof Date ? date : new Date(date);
  const tzOffsetMinutes = d.getTimezoneOffset();
  const local = new Date(d.getTime() - tzOffsetMinutes * 60 * 1000);
  return local.toISOString().slice(0, 10);
}

function toDateObject(dateLike) {
  if (!dateLike) return null;
  if (dateLike instanceof Date) {
    return Number.isNaN(dateLike.getTime()) ? null : dateLike;
  }
  if (typeof dateLike === 'number') {
    const ms = dateLike > 1e12 ? dateLike : dateLike * 1000;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  if (typeof dateLike === 'object') {
    if (typeof dateLike.toDate === 'function') {
      try {
        const d = dateLike.toDate();
        if (d instanceof Date && !Number.isNaN(d.getTime())) return d;
      } catch {
        // Ignore and continue trying other shapes.
      }
    }
    if (typeof dateLike.toMillis === 'function') {
      try {
        const d = new Date(dateLike.toMillis());
        if (!Number.isNaN(d.getTime())) return d;
      } catch {
        // Ignore and continue trying other shapes.
      }
    }
    if (typeof dateLike.seconds === 'number') {
      const d = new Date(dateLike.seconds * 1000);
      return Number.isNaN(d.getTime()) ? null : d;
    }
  }
  try {
    const raw = String(dateLike).trim();
    const hasTimezoneSuffix = /([zZ]|[+\-]\d{2}:\d{2})$/.test(raw);
    const isDateTimeNoTz = /^\d{4}-\d{2}-\d{2}[T\s]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?$/.test(raw);
    // API payloads sometimes provide UTC-like datetime strings without timezone.
    // Treat those as UTC explicitly so UI conversion to GMT+2 is correct.
    const normalized = isDateTimeNoTz && !hasTimezoneSuffix ? `${raw.replace(' ', 'T')}Z` : raw;
    const d = new Date(normalized);
    return Number.isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

// Many upstream sources only provide a date (no kickoff time). Some pipelines
// end up storing these as midnight UTC (T00:00:00+00:00), which renders as a
// "fixed" local time (e.g. 02:00 in UTC+2). Treat midnight as "unknown time"
// for UI purposes unless a real time is provided.
export function hasMeaningfulTime(dateLike) {
  if (!dateLike) return false;

  // For strings, inspect the raw time component directly to avoid timezone
  // conversion turning UTC midnight into local 02:00.
  if (typeof dateLike === 'string') {
    const s = dateLike.trim();
    const m = s.match(/[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?/) || s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (!m) return false;
    const hh = Number(m[1]);
    const mm = Number(m[2]);
    const ss = Number(m[3] || 0);
    return !(hh === 0 && mm === 0 && ss === 0);
  }

  const d = toDateObject(dateLike);
  if (d) {
    // Use UTC so a stored 00:00Z does not become "02:00" and look meaningful.
    return !(d.getUTCHours() === 0 && d.getUTCMinutes() === 0 && d.getUTCSeconds() === 0);
  }

  return false;
}

export function formatLocalDate(dateLike) {
  try {
    return new Date(dateLike).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return '';
  }
}

export function formatLocalTime(dateLike) {
  try {
    return new Date(dateLike).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export function formatSASTTime(dateLike) {
  try {
    const date = toDateObject(dateLike);
    if (!date) {
      return '';
    }
    return date.toLocaleTimeString('en-ZA', {
      timeZone: 'Africa/Johannesburg',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  } catch {
    return '';
  }
}

export function formatSASTTimePM(dateLike) {
  try {
    const date = toDateObject(dateLike);
    if (!date) {
      return '';
    }
    const value = date.toLocaleTimeString('en-US', {
      timeZone: 'Africa/Johannesburg',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
    return value.replace(/^0/, '');
  } catch {
    return '';
  }
}

export function formatSASTDateYMD(dateLike) {
  try {
    const date = toDateObject(dateLike);
    if (!date) {
      return '';
    }
    // Stable YYYY-MM-DD rendering in GMT+2.
    return date.toLocaleDateString('en-CA', {
      timeZone: 'Africa/Johannesburg',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  } catch {
    return '';
  }
}

const PREMIERSHIP_2026_SAST_KICKOFFS = {
  '2026-03-20|bath|saracens': '19:45',
  '2026-03-21|northampton saints|newcastle red bulls': '15:00',
  '2026-03-21|harlequins|gloucester': '15:00',
  '2026-03-21|exeter chiefs|sale sharks': '15:05',
  '2026-03-22|leicester tigers|bristol bears': '15:00',
  '2026-03-27|newcastle red bulls|exeter chiefs': '19:45',
  '2026-03-28|gloucester|leicester tigers': '13:00',
  '2026-03-28|bristol bears|harlequins': '15:30',
  '2026-03-28|saracens|northampton saints': '18:00',
  '2026-03-29|sale sharks|bath': '15:00',
  '2026-04-17|bristol bears|gloucester': '19:45',
  '2026-04-18|leicester tigers|newcastle red bulls': '15:00',
  '2026-04-18|exeter chiefs|northampton saints': '15:05',
  '2026-04-18|bath|harlequins': '17:30',
  '2026-04-19|sale sharks|saracens': '15:00',
  '2026-04-24|newcastle red bulls|bristol bears': '19:45',
  '2026-04-25|harlequins|sale sharks': '15:00',
  '2026-04-25|saracens|leicester tigers': '15:05',
  '2026-04-25|northampton saints|bath': '17:30',
  '2026-04-25|gloucester|exeter chiefs': '15:00',
  '2026-04-26|gloucester|exeter chiefs': '15:00',
};

function normalizeTeamNameForKey(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/\brugby\b/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function getYYYYMMDDFromAny(dateLike) {
  if (!dateLike) return '';
  const raw = String(dateLike).trim();
  const explicitIsoDate = raw.match(/^\d{4}-\d{2}-\d{2}/);
  if (explicitIsoDate) {
    return explicitIsoDate[0];
  }
  const d = toDateObject(raw);
  if (!d) return '';
  const tzOffsetMinutes = d.getTimezoneOffset();
  const local = new Date(d.getTime() - tzOffsetMinutes * 60 * 1000);
  return local.toISOString().slice(0, 10);
}

function addDaysToISODate(isoDate, days) {
  try {
    const [y, m, d] = String(isoDate).split('-').map((v) => parseInt(v, 10));
    if (!y || !m || !d) return '';
    const dt = new Date(Date.UTC(y, m - 1, d));
    dt.setUTCDate(dt.getUTCDate() + days);
    return dt.toISOString().slice(0, 10);
  } catch {
    return '';
  }
}

function extractTimeHHMM(timeLike) {
  if (!timeLike) return '';
  const m = String(timeLike).trim().match(/(\d{1,2}):(\d{2})/);
  if (!m) return '';
  const hh = m[1].padStart(2, '0');
  const mm = m[2];
  if (hh === '00' && mm === '00') return '';
  return `${hh}:${mm}`;
}

function getPremiershipOverrideKickoff(match, leagueId) {
  const league = Number(leagueId ?? match?.league_id ?? 0);
  if (league !== 4414) return null;

  const datePart = getYYYYMMDDFromAny(match?.date_event || match?.kickoff_at || match?.timestamp);
  if (!datePart) return null;

  const home = normalizeTeamNameForKey(match?.home_team);
  const away = normalizeTeamNameForKey(match?.away_team);
  const candidateDates = [datePart, addDaysToISODate(datePart, -1), addDaysToISODate(datePart, 1)];
  let hhmm = '';
  for (const candidateDate of candidateDates) {
    if (!candidateDate) continue;
    const key = `${candidateDate}|${home}|${away}`;
    hhmm = PREMIERSHIP_2026_SAST_KICKOFFS[key] || '';
    if (hhmm) break;
  }
  if (!hhmm) return null;

  // Store as explicit SAST offset so display is stable on any client timezone.
  return `${datePart}T${hhmm}:00+02:00`;
}

export function getKickoffAtFromMatch(match, fallbackLeagueId = null) {
  if (!match || typeof match !== 'object') return null;
  const leagueId = Number(fallbackLeagueId ?? match?.league_id ?? 0);

  const canonicalDate = getYYYYMMDDFromAny(
    match.date_event || match.dateEvent || match.kickoff_at || match.kickoffAt
  );

  const directCandidates = [
    { value: match.kickoff_at, source: 'kickoff_at' },
    { value: match.kickoffAt, source: 'kickoffAt' },
    { value: match.date_event, source: 'date_event' },
    { value: match.dateEvent, source: 'dateEvent' },
    { value: match.timestamp, source: 'timestamp' },
    { value: match.strTimestamp, source: 'strTimestamp' },
  ];

  for (const { value: candidate, source } of directCandidates) {
    if (hasMeaningfulTime(candidate)) {
      const raw = String(candidate).trim();
      const hasTimezoneSuffix = /([zZ]|[+\-]\d{2}:\d{2})$/.test(raw);
      const isDateTimeNoTz = /^\d{4}-\d{2}-\d{2}[T\s]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?$/.test(raw);
      let normalized = raw;
      if (isDateTimeNoTz && !hasTimezoneSuffix) {
        const normalizedBase = raw.replace(' ', 'T');
        // Six Nations feed timestamps are effectively local fixture times, not UTC.
        // Keep them as SAST to avoid +2h drift (e.g. 20:10 shown as 22:10).
        if (leagueId === 4714 && (source === 'timestamp' || source === 'strTimestamp')) {
          normalized = `${normalizedBase}+02:00`;
        } else {
          normalized = `${normalizedBase}Z`;
        }
      }

      // Some providers occasionally send stale/misaligned timestamps. If we have a
      // canonical match date, only trust timestamp fields when they are close to it.
      if ((source === 'timestamp' || source === 'strTimestamp') && canonicalDate) {
        const tsDate = getYYYYMMDDFromAny(normalized);
        const isWithinOneDay =
          tsDate === canonicalDate ||
          tsDate === addDaysToISODate(canonicalDate, -1) ||
          tsDate === addDaysToISODate(canonicalDate, 1);
        if (!isWithinOneDay) {
          // For Six Nations, the API can carry previous-round timestamp dates but
          // still the correct kickoff time-of-day. Reuse the time on the fixture date.
          if (leagueId !== 4714) {
            continue;
          }
          const hhmm = extractTimeHHMM(normalized);
          if (!hhmm) {
            continue;
          }
          return `${canonicalDate}T${hhmm}:00+02:00`;
        }
        // If timestamp time is valid but date drifts by one day, pin it to the fixture date
        // so UI shows the correct round date with the supplied kickoff time.
        if (tsDate && tsDate !== canonicalDate) {
          const hhmm = extractTimeHHMM(normalized);
          if (hhmm) {
            return leagueId === 4714
              ? `${canonicalDate}T${hhmm}:00+02:00`
              : `${canonicalDate}T${hhmm}:00Z`;
          }
        }
      }

      return normalized;
    }
  }

  const datePart = getYYYYMMDDFromAny(
    match.date_event || match.dateEvent || match.kickoff_at || match.kickoffAt || match.timestamp
  );
  const explicitTime = extractTimeHHMM(
    match.start_time || match.startTime || match.time_event || match.timeEvent || match.strTime
  );
  if (datePart && explicitTime) {
    // `start_time` fields are treated as local league kickoff (SAST in this UI).
    return `${datePart}T${explicitTime}:00+02:00`;
  }

  return getPremiershipOverrideKickoff(match, fallbackLeagueId);
}


