import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Typography } from '@mui/material';
import { getLiveMatches, getUpcomingMatches } from '../firebase';
import { TabLoadingScreen } from '../utils/viewLoader';
import { formatKickoffSAST, formatSASTDateYMD, getKickoffAtFromMatch } from '../utils/date';
import { readStandingsLogoCache } from '../utils/teamLogos';
import TeamLogoImage from './TeamLogoImage';

const PLAYING_STATES = new Set([
  'First half',
  'Second half',
  'Extra time',
  'Extra first half',
  'Extra second half',
  'Penalties',
  'Live',
]);
const BREAK_STATES = new Set(['Half time', 'Extra time half time']);
const LIVE_STATES = new Set([...PLAYING_STATES, ...BREAK_STATES]);
const FINISHED_STATES = new Set(['Finished', 'Full time', 'FT', 'Ended', 'AET', 'After extra time']);

const alertSx = {
  borderRadius: 2.5,
  bgcolor: 'transparent',
  border: '1px solid rgba(255,255,255,0.10)',
  color: 'rgba(255,255,255,0.92)',
  backdropFilter: 'none',
  '& .MuiAlert-icon': { color: '#10b981' },
  '& .MuiAlert-message': { color: 'rgba(255,255,255,0.70)' },
};

function addDaysYmd(ymd, days) {
  const [y, m, d] = String(ymd || '').split('-').map(Number);
  if (!y || !m || !d) return '';
  const dt = new Date(Date.UTC(y, m - 1, d + Number(days || 0)));
  return dt.toISOString().slice(0, 10);
}

function sastTodayTomorrow() {
  const today = formatSASTDateYMD(new Date());
  return { today, tomorrow: addDaysYmd(today, 1) };
}

function matchDateIso(match, leagueId) {
  const kickoff = getKickoffAtFromMatch(match, leagueId);
  const fromKickoff = formatSASTDateYMD(kickoff);
  if (fromKickoff) return fromKickoff;
  const raw = String(
    match?.formatted_date ||
    match?.date_event ||
    match?.dateEvent ||
    match?.kickoff_at ||
    match?.date ||
    ''
  ).trim();
  const direct = raw.match(/^\d{4}-\d{2}-\d{2}/);
  return direct ? direct[0] : '';
}

function teamKey(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function normalizeState(raw) {
  const s = String(raw || '')
    .toLowerCase()
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!s) return '';
  if (['first half', '1st half', '1h'].includes(s)) return 'First half';
  if (['second half', '2nd half', '2h'].includes(s)) return 'Second half';
  if (['half time', 'halftime', 'ht'].includes(s)) return 'Half time';
  if (['extra time', 'et', 'aet', 'after extra time'].includes(s)) return 'Extra time';
  if (['extra first half', 'et first half', 'extra time first half'].includes(s)) return 'Extra first half';
  if (['extra second half', 'et second half', 'extra time second half'].includes(s)) return 'Extra second half';
  if (['extra time half time', 'et half time', 'extra half time'].includes(s)) return 'Extra time half time';
  if (['penalties', 'penalty shootout', 'pens', 'pso'].includes(s)) return 'Penalties';
  if (['finished', 'full time', 'ft', 'ended'].includes(s)) return 'Finished';
  if (['not started', 'scheduled', 'ns', 'tbd'].includes(s)) return 'Not started';
  if (['live', 'in play', 'in progress'].includes(s)) return 'Live';
  return String(raw || '').trim();
}

function fixtureKey(match, leagueId) {
  const dateIso = matchDateIso(match, leagueId);
  return `${dateIso}|${teamKey(match?.home_team)}|${teamKey(match?.away_team)}`;
}

function teamsKey(match) {
  return `${teamKey(match?.home_team)}|${teamKey(match?.away_team)}`;
}

function findLiveOverlay(match, liveByExact, liveByTeams, leagueId) {
  return liveByExact.get(fixtureKey(match, leagueId)) || liveByTeams.get(teamsKey(match)) || null;
}

function detectedState(match) {
  const normalized = normalizeState(match?.state);
  if (FINISHED_STATES.has(normalized) || LIVE_STATES.has(normalized)) return normalized;
  return normalized || 'Not started';
}

function firstText(...values) {
  for (const value of values) {
    const text = String(value || '').trim();
    if (text && text !== '[object Object]' && !/^stadium$/i.test(text)) return text;
  }
  return '';
}

function scoreSignature(matches) {
  return (matches || [])
    .map((m) => `${m.match_id || teamsKey(m)}:${m.state || ''}:${m.home_score ?? ''}:${m.away_score ?? ''}`)
    .join('|');
}

function overlayLive(base, live) {
  if (!live) return base;
  const liveKickoff = live.kickoff_at || live.date_event || live.date;
  const liveState = normalizeState(live.state);
  const detectedLive = LIVE_STATES.has(liveState);
  return {
    ...base,
    home_score: live.home_score ?? base.home_score,
    away_score: live.away_score ?? base.away_score,
    state: liveState || base.state,
    is_live: detectedLive,
    home_logo: base.home_logo || live.home_logo,
    away_logo: base.away_logo || live.away_logo,
    venue: firstText(live.venue, live.stadium, base.venue, base.stadium),
    round: base.round || live.round,
    prediction: base.prediction || live.prediction,
    date: live.date || base.date,
    date_event: liveKickoff || base.date_event,
    kickoff_at: liveKickoff || base.kickoff_at,
    start_time: live.start_time || base.start_time,
    formatted_date: live.formatted_date || base.formatted_date,
  };
}

function toBoardMatch(match, leagueId) {
  const dateIso = matchDateIso(match, leagueId);
  const kickoffAt = getKickoffAtFromMatch(match, leagueId);
  const state = detectedState(match);
  return {
    ...match,
    formatted_date: match.formatted_date || dateIso,
    kickoff_at: match.kickoff_at || kickoffAt,
    state,
    is_live: LIVE_STATES.has(state),
    venue: firstText(match.venue, match.stadium, match.strVenue),
  };
}

function mergeBroadcastMatches(upcoming, live, leagueId) {
  const { today, tomorrow } = sastTodayTomorrow();
  const allowed = new Set([today, tomorrow]);
  const inWindow = (match) => allowed.has(matchDateIso(match, leagueId));

  const upcomingInWindow = (Array.isArray(upcoming) ? upcoming : []).filter(inWindow);
  const liveInWindow = (Array.isArray(live) ? live : []).filter((match) => {
    const dateIso = matchDateIso(match, leagueId);
    return !dateIso || allowed.has(dateIso);
  });
  const liveByExact = new Map(liveInWindow.map((match) => [fixtureKey(match, leagueId), match]));
  const liveByTeams = new Map(liveInWindow.map((match) => [teamsKey(match), match]));
  const usedLive = new Set();
  const merged = upcomingInWindow.map((match) => {
    const liveMatch = findLiveOverlay(match, liveByExact, liveByTeams, leagueId);
    if (liveMatch) {
      usedLive.add(fixtureKey(liveMatch, leagueId));
      usedLive.add(teamsKey(liveMatch));
    }
    return toBoardMatch(overlayLive(match, liveMatch), leagueId);
  });

  liveInWindow.forEach((match) => {
    const exact = fixtureKey(match, leagueId);
    const teams = teamsKey(match);
    if (!usedLive.has(exact) && !usedLive.has(teams)) merged.push(toBoardMatch(match, leagueId));
  });

  merged.sort((a, b) => {
    const aLive = LIVE_STATES.has(detectedState(a)) ? 0 : 1;
    const bLive = LIVE_STATES.has(detectedState(b)) ? 0 : 1;
    if (aLive !== bLive) return aLive - bLive;
    const aKick = getKickoffAtFromMatch(a, leagueId) || a.date_event || a.date || '';
    const bKick = getKickoffAtFromMatch(b, leagueId) || b.date_event || b.date || '';
    return String(aKick).localeCompare(String(bKick));
  });
  return merged;
}

function scoreValue(raw) {
  if (raw === null || raw === undefined || raw === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function phaseLabel(state) {
  const s = String(state || '');
  if (s === 'First half') return '1st half';
  if (s === 'Second half') return '2nd half';
  if (s === 'Half time') return 'Half-time';
  if (s === 'Extra time') return 'Extra time';
  if (s === 'Extra first half') return 'ET 1st half';
  if (s === 'Extra second half') return 'ET 2nd half';
  if (s === 'Extra time half time') return 'ET half-time';
  if (s === 'Penalties') return 'Penalties';
  if (s === 'Finished') return 'Full time';
  if (s === 'Live') return 'Live';
  return 'Kickoff';
}

function predictionParts(prediction) {
  if (!prediction || prediction.error) return null;
  const home = Number(prediction.home_win_prob ?? prediction.home_probability);
  const away = Number(prediction.away_win_prob ?? prediction.away_probability);
  if (!Number.isFinite(home) || !Number.isFinite(away)) return null;
  const hp = home <= 1 ? Math.round(home * 100) : Math.round(home);
  const ap = away <= 1 ? Math.round(away * 100) : Math.round(away);
  const ph = scoreValue(prediction.predicted_home_score);
  const pa = scoreValue(prediction.predicted_away_score);
  return { hp, ap, ph, pa };
}

function formatMatchDate(isoLike) {
  const raw = String(isoLike || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return '';
  const [y, m, d] = raw.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
}

function splitVenue(venue) {
  const raw = String(venue || '').trim();
  if (!raw) return { ground: '', city: '' };
  const idx = raw.lastIndexOf(',');
  if (idx === -1) return { ground: raw, city: '' };
  return { ground: raw.slice(0, idx).trim(), city: raw.slice(idx + 1).trim() };
}

const PITCH_PHOTO = '/rugby-field.png';

function RugbyPitch() {
  return (
    <>
      <img className="broadcast-pitch-photo" src={PITCH_PHOTO} alt="" aria-hidden="true" />
      <div className="broadcast-pitch-shade" aria-hidden="true" />
    </>
  );
}

function BroadcastBoard({
  match,
  index,
  total,
  leagueId,
  leagueName,
  logoMap,
}) {
  const state = detectedState(match);
  const isLive = LIVE_STATES.has(state);
  const isFinished = FINISHED_STATES.has(state) || state === 'Finished';
  const homeScore = scoreValue(match.home_score);
  const awayScore = scoreValue(match.away_score);
  const kickoffAt = getKickoffAtFromMatch(match, leagueId);
  const kickoffLabel = formatKickoffSAST(kickoffAt) || match.start_time || '';
  const pred = predictionParts(match.prediction);
  const homeName = match.home_team || 'Home';
  const awayName = match.away_team || 'Away';
  const venueParts = splitVenue(firstText(match.venue, match.stadium, match.strVenue));
  const showVenue = Boolean(venueParts.ground);
  const showDetectedPhase = isLive || isFinished;
  const showScore = isLive || isFinished || homeScore != null || awayScore != null;
  const statusTag = isLive ? 'On air' : isFinished ? 'Full time' : 'Up next';

  return (
    <Box className={`broadcast-arena${isLive ? ' is-live' : isFinished ? ' is-finished' : ' is-upcoming'}`}>
      <div className="broadcast-pitch">
        <RugbyPitch />
      </div>

      <Box className="broadcast-hud">
        <Box className="broadcast-hud-left">
          {isLive ? (
            <span className="broadcast-onair">
              <i />
              On air
            </span>
          ) : (
            <span className={isFinished ? 'broadcast-ft-tag' : 'broadcast-upcoming-tag'}>{statusTag}</span>
          )}
          <span className="broadcast-comp">
            {match.league || leagueName || 'Rugby'}
            {match.round ? ` · ${match.round}` : ''}
          </span>
        </Box>

        <Box className="broadcast-hud-center">
          {showDetectedPhase ? (
            <span className="broadcast-phase is-detected">{phaseLabel(state)}</span>
          ) : (
            <>
              <strong className="broadcast-minute is-ko">{kickoffLabel || 'TBC'}</strong>
              <span className="broadcast-phase">Kickoff</span>
            </>
          )}
        </Box>

        <Box className="broadcast-hud-right">
          <span className="broadcast-fixture-no">
            {String(index + 1).padStart(2, '0')}
            {total > 1 ? ` / ${String(total).padStart(2, '0')}` : ''}
          </span>
        </Box>
      </Box>

      <Box className="broadcast-scoreboard">
        <Box className="broadcast-team-block home">
          <div className="broadcast-crest">
            <TeamLogoImage
              teamName={homeName}
              leagueId={leagueId}
              logoMap={logoMap}
              explicitLogo={match.home_logo}
              size={156}
              alt={homeName}
            />
          </div>
          <Typography className="broadcast-team-name">{homeName}</Typography>
          <span className="broadcast-side-tag">Home</span>
        </Box>

        <Box className="broadcast-score-block">
          <span className="broadcast-score-home">{showScore ? (homeScore ?? 0) : ''}</span>
          {showScore ? (
            <i className="broadcast-dash" aria-hidden="true" />
          ) : (
            <span className="broadcast-vs">vs</span>
          )}
          <span className="broadcast-score-away">{showScore ? (awayScore ?? 0) : ''}</span>
        </Box>

        <Box className="broadcast-team-block away">
          <div className="broadcast-crest">
            <TeamLogoImage
              teamName={awayName}
              leagueId={leagueId}
              logoMap={logoMap}
              explicitLogo={match.away_logo}
              size={156}
              alt={awayName}
            />
          </div>
          <Typography className="broadcast-team-name">{awayName}</Typography>
          <span className="broadcast-side-tag">Away</span>
        </Box>
      </Box>

      {(showVenue || (pred && pred.ph != null && pred.pa != null)) ? (
        <Box className="broadcast-footer">
          {showVenue ? (
            <span className="broadcast-venue">
              <strong>{venueParts.ground}</strong>
              {venueParts.city ? <em>{venueParts.city}</em> : null}
            </span>
          ) : null}
          {pred && pred.ph != null && pred.pa != null ? (
            <span className="broadcast-model">{`${pred.ph}-${pred.pa}`}</span>
          ) : null}
        </Box>
      ) : null}
    </Box>
  );
}

function PitchSeparator({ label }) {
  return (
    <Box className="broadcast-divider" role="separator" aria-label={label || 'Next match'}>
      <span />
      <em>{label || 'Next'}</em>
      <span />
    </Box>
  );
}

function EmptyBroadcast({ leagueName }) {
  return (
    <Box className="broadcast-arena is-empty">
      <div className="broadcast-pitch">
        <RugbyPitch />
      </div>
      <Box className="broadcast-empty-copy">
        <Typography className="broadcast-empty-kicker">Field open</Typography>
        <Typography className="broadcast-empty-title">No matches today or tomorrow</Typography>
        <Typography className="broadcast-empty-sub">
          When {leagueName || 'this competition'} has a fixture today or tomorrow, it shows here.
        </Typography>
      </Box>
    </Box>
  );
}

function LiveBroadcast({ leagueId, leagueName }) {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const upcomingRef = useRef([]);
  const scoreSigRef = useRef('');

  const logoMap = useMemo(() => readStandingsLogoCache(leagueId) || {}, [leagueId]);
  const displayLeagueName = leagueName;

  const fetchMatches = useCallback(async ({
    quiet = false,
    refreshUpcoming = false,
    wait = false,
    since = '',
  } = {}) => {
    if (!leagueId) {
      setMatches([]);
      setError('');
      if (!quiet) setLoading(false);
      return { merged: [], signature: '', detection: false };
    }
    if (!quiet) setLoading(true);
    try {
      const shouldRefreshUpcoming = refreshUpcoming || upcomingRef.current.length === 0;
      const [liveResult, upcomingResult] = await Promise.all([
        getLiveMatches({
          league_id: leagueId,
          wait: Boolean(wait),
          since: since || undefined,
        }).catch((err) => {
          console.warn('Live broadcast live feed failed:', err?.message || err);
          return { data: { matches: [] } };
        }),
        shouldRefreshUpcoming
          ? getUpcomingMatches({ league_id: leagueId, limit: 50 }).catch((err) => {
              console.warn('Live broadcast upcoming feed failed:', err?.message || err);
              return { data: { matches: upcomingRef.current } };
            })
          : Promise.resolve(null),
      ]);

      const livePayload = liveResult?.data || {};
      const liveMatches = Array.isArray(livePayload.matches) ? livePayload.matches : [];
      if (upcomingResult) {
        const upcomingPayload = upcomingResult?.data || {};
        upcomingRef.current = Array.isArray(upcomingPayload.matches) ? upcomingPayload.matches : [];
      }

      const merged = mergeBroadcastMatches(upcomingRef.current, liveMatches, leagueId);
      const nextSig = livePayload.signature || scoreSignature(merged);
      if (!quiet || nextSig !== scoreSigRef.current) {
        scoreSigRef.current = nextSig;
        setMatches(merged);
      }
      if (livePayload.error && merged.length === 0) {
        setError(String(livePayload.error));
      } else {
        setError('');
      }
      return {
        merged,
        signature: nextSig,
        detection: livePayload.detection === true,
      };
    } catch (err) {
      console.warn('Live broadcast fetch failed:', err?.message || err);
      if (!quiet) {
        setError('Live feed temporarily unavailable.');
        setMatches([]);
      }
      return null;
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => {
    let cancelled = false;
    let kickoffTimer = null;
    let listening = false;
    const catchupTimers = [];

    const stopKickoff = () => {
      if (kickoffTimer) {
        clearTimeout(kickoffTimer);
        kickoffTimer = null;
      }
    };

    const stopCatchups = () => {
      while (catchupTimers.length) {
        clearTimeout(catchupTimers.pop());
      }
    };

    const delay = (ms) =>
      new Promise((resolve) => {
        const timer = setTimeout(() => {
          const idx = catchupTimers.indexOf(timer);
          if (idx >= 0) catchupTimers.splice(idx, 1);
          resolve();
        }, ms);
        catchupTimers.push(timer);
      });

    const waitUntilVisible = () =>
      new Promise((resolve) => {
        if (!document.hidden) {
          resolve();
          return;
        }
        const onVisible = () => {
          if (document.hidden) return;
          document.removeEventListener('visibilitychange', onVisible);
          resolve();
        };
        document.addEventListener('visibilitychange', onVisible);
      });

    const matchKickoffMs = (match) => {
      const iso = getKickoffAtFromMatch(match, leagueId);
      const t = iso ? new Date(iso).getTime() : NaN;
      return Number.isFinite(t) ? t : null;
    };

    // Watch from 2 minutes before kickoff until Highlightly reports live or FT.
    // Do not drop the watch just because the clock passed kickoff while the
    // feed is still "Not started" — that lag is normal.
    const needsDetectionWatch = (board) =>
      (board || []).some((match) => {
        const state = detectedState(match);
        if (FINISHED_STATES.has(state)) return false;
        if (LIVE_STATES.has(state)) return true;
        const t = matchKickoffMs(match);
        if (t == null) return false;
        return Date.now() >= t - 2 * 60 * 1000;
      });

    const nextListenAtMs = (board) => {
      const times = (board || [])
        .map((match) => {
          const state = detectedState(match);
          if (FINISHED_STATES.has(state) || LIVE_STATES.has(state)) return null;
          const t = matchKickoffMs(match);
          return t == null ? null : t - 2 * 60 * 1000;
        })
        .filter((t) => t != null && t > Date.now())
        .sort((a, b) => a - b);
      return times[0] ?? null;
    };

    const armKickoff = (board) => {
      stopKickoff();
      if (cancelled) return;
      if (needsDetectionWatch(board)) {
        listenForDetections(scoreSigRef.current);
        return;
      }
      const listenAt = nextListenAtMs(board);
      if (listenAt == null) return;
      const wait = Math.min(Math.max(listenAt - Date.now(), 250), 6 * 60 * 60 * 1000);
      kickoffTimer = setTimeout(() => {
        kickoffTimer = null;
        fetchMatches({ quiet: true, refreshUpcoming: true })
          .then((result) => {
            if (!cancelled && result?.merged) armDetectors(result.merged, result);
          })
          .catch(() => {});
      }, wait);
    };

    const listenForDetections = async (since) => {
      if (listening || cancelled) return;
      listening = true;
      stopKickoff();
      let cursor = since || '';
      let lastBoard = null;
      let missStreak = 0;
      const catchupMs = [8000, 15000, 30000, 45000, 90000, 180000];
      try {
        while (!cancelled) {
          await waitUntilVisible();
          if (cancelled) return;
          const result = await fetchMatches({
            quiet: true,
            refreshUpcoming: false,
            wait: true,
            since: cursor,
          });
          if (cancelled) return;
          if (!result) {
            const waitMs = catchupMs[Math.min(missStreak, catchupMs.length - 1)];
            missStreak += 1;
            await delay(waitMs);
            continue;
          }
          lastBoard = result.merged;
          cursor = result.signature || cursor;
          if (!needsDetectionWatch(result.merged)) break;
          // Production wait loop holds until Highlightly flips. If this
          // endpoint is still one-shot, space catch-up reads instead of
          // giving up at kickoff.
          if (!result.detection) {
            const waitMs = catchupMs[Math.min(missStreak, catchupMs.length - 1)];
            missStreak += 1;
            await delay(waitMs);
          } else {
            missStreak = 0;
          }
        }
      } finally {
        listening = false;
      }
      if (!cancelled && lastBoard) armKickoff(lastBoard);
    };

    const armDetectors = (board, meta) => {
      if (cancelled) return;
      if (needsDetectionWatch(board)) {
        listenForDetections(meta?.signature || scoreSigRef.current);
        return;
      }
      armKickoff(board);
    };

    setMatches([]);
    setError('');
    setLoading(true);
    upcomingRef.current = [];
    scoreSigRef.current = '';
    fetchMatches({ quiet: false, refreshUpcoming: true })
      .then((result) => {
        if (!cancelled && result?.merged) armDetectors(result.merged, result);
      })
      .catch(() => {});

    const onVisible = () => {
      if (document.hidden) return;
      fetchMatches({ quiet: true, refreshUpcoming: false })
        .then((result) => {
          if (!cancelled && result?.merged) armDetectors(result.merged, result);
        })
        .catch(() => {});
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      stopKickoff();
      stopCatchups();
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [fetchMatches, leagueId]);

  const liveCount = useMemo(
    () => matches.filter((m) => LIVE_STATES.has(detectedState(m))).length,
    [matches]
  );

  const mastBits = useMemo(() => {
    const featured =
      matches.find((m) => LIVE_STATES.has(detectedState(m))) || matches[0];
    if (!featured) return [];
    const dateLabel = formatMatchDate(featured.formatted_date || featured.date || featured.date_event);
    const kickoff =
      formatKickoffSAST(getKickoffAtFromMatch(featured, leagueId)) || featured.start_time || '';
    return [dateLabel, kickoff].filter(Boolean);
  }, [matches, leagueId]);

  if (loading) {
    return <TabLoadingScreen label="Opening the field..." />;
  }

  return (
    <Box className="live-broadcast" sx={{ width: '100%', maxWidth: 'none', pb: { xs: 4, sm: 5 } }}>
      <Box className="broadcast-mast">
        <Box className="broadcast-mast-copy">
          <Typography className="broadcast-mast-title">{displayLeagueName || 'Rugby Union'}</Typography>
          {mastBits.length > 0 ? (
            <p className="broadcast-mast-sub">
              {mastBits.map((bit) => (
                <span key={bit}>{bit}</span>
              ))}
            </p>
          ) : null}
        </Box>
        {liveCount > 0 ? (
          <span className="broadcast-mast-live">
            <i />
            Live
          </span>
        ) : (
          <span className="broadcast-mast-idle">Standby</span>
        )}
      </Box>

      {error ? (
        <Alert severity="info" sx={{ ...alertSx, mb: 2.5 }}>
          {error}
        </Alert>
      ) : null}

      {matches.length === 0 ? (
        <EmptyBroadcast leagueName={displayLeagueName} />
      ) : (
        <Box className="broadcast-stage">
          {matches.map((match, index) => {
            const prev = matches[index - 1];
            const showSeparator = index > 0;
            const { today, tomorrow } = sastTodayTomorrow();
            const matchDay = matchDateIso(match, leagueId);
            const prevDay = matchDateIso(prev, leagueId);
            const sepLabel =
              matchDay === tomorrow && prevDay !== tomorrow
                ? 'Tomorrow'
                : matchDay === today && prevDay !== today
                  ? 'Today'
                  : !LIVE_STATES.has(detectedState(match)) &&
                    LIVE_STATES.has(detectedState(prev))
                    ? 'Up next'
                    : `Fixture ${String(index + 1).padStart(2, '0')}`;

            return (
              <React.Fragment key={match.match_id || `${match.home_team}-${match.away_team}-${index}`}>
                {showSeparator ? <PitchSeparator label={sepLabel} /> : null}
                <BroadcastBoard
                  match={match}
                  index={index}
                  total={matches.length}
                  leagueId={leagueId}
                  leagueName={displayLeagueName}
                  logoMap={logoMap}
                />
              </React.Fragment>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

export default LiveBroadcast;
