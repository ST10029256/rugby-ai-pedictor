import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Typography } from '@mui/material';
import { getLiveMatches, getUpcomingMatches } from '../firebase';
import { TabLoadingScreen } from '../utils/viewLoader';
import { formatKickoffSAST, formatSASTDateYMD, getKickoffAtFromMatch } from '../utils/date';
import { readStandingsLogoCache } from '../utils/teamLogos';
import TeamLogoImage from './TeamLogoImage';

const LIVE_STATES = new Set(['First half', 'Second half', 'Half time']);
const POLL_MS = 30000;

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

function fixtureKey(match, leagueId) {
  const dateIso = matchDateIso(match, leagueId);
  return `${dateIso}|${teamKey(match?.home_team)}|${teamKey(match?.away_team)}`;
}

function overlayLive(base, live) {
  if (!live) return base;
  const liveKickoff = live.kickoff_at || live.date_event || live.date;
  return {
    ...base,
    home_score: live.home_score ?? base.home_score,
    away_score: live.away_score ?? base.away_score,
    state: live.state || base.state,
    game_time: live.game_time ?? base.game_time,
    is_live: live.is_live ?? base.is_live,
    home_logo: base.home_logo || live.home_logo,
    away_logo: base.away_logo || live.away_logo,
    venue: base.venue || live.venue,
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
  const state = match.state || 'Not started';
  return {
    ...match,
    formatted_date: match.formatted_date || dateIso,
    kickoff_at: match.kickoff_at || kickoffAt,
    state,
    is_live: LIVE_STATES.has(String(state)),
  };
}

function mergeBroadcastMatches(upcoming, live, leagueId) {
  const { today, tomorrow } = sastTodayTomorrow();
  const allowed = new Set([today, tomorrow]);
  const inWindow = (match) => allowed.has(matchDateIso(match, leagueId));

  const upcomingInWindow = (Array.isArray(upcoming) ? upcoming : []).filter(inWindow);
  const liveInWindow = (Array.isArray(live) ? live : []).filter(inWindow);
  const liveByKey = new Map(liveInWindow.map((match) => [fixtureKey(match, leagueId), match]));
  const usedLive = new Set();
  const merged = upcomingInWindow.map((match) => {
    const key = fixtureKey(match, leagueId);
    const liveMatch = liveByKey.get(key);
    if (liveMatch) usedLive.add(key);
    return toBoardMatch(overlayLive(match, liveMatch), leagueId);
  });

  liveInWindow.forEach((match) => {
    const key = fixtureKey(match, leagueId);
    if (!usedLive.has(key)) merged.push(toBoardMatch(match, leagueId));
  });

  merged.sort((a, b) => {
    const aLive = LIVE_STATES.has(String(a.state || '')) ? 0 : 1;
    const bLive = LIVE_STATES.has(String(b.state || '')) ? 0 : 1;
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
  return 'Kickoff';
}

function clockLabel(match) {
  const state = String(match?.state || '');
  const minute = match?.game_time;
  if (minute != null && String(minute).trim() !== '') {
    return `${String(minute).replace(/'/g, '')}'`;
  }
  if (state === 'Half time') return 'HT';
  if (state === 'First half') return '1H';
  if (state === 'Second half') return '2H';
  return null;
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
  const state = match.state || 'Not started';
  const isLive = LIVE_STATES.has(state);
  const homeScore = scoreValue(match.home_score);
  const awayScore = scoreValue(match.away_score);
  const kickoffAt = getKickoffAtFromMatch(match, leagueId);
  const kickoffLabel = formatKickoffSAST(kickoffAt) || match.start_time || '';
  const clock = clockLabel(match);
  const pred = predictionParts(match.prediction);
  const homeName = match.home_team || 'Home';
  const awayName = match.away_team || 'Away';
  const venueParts = splitVenue(match.venue);
  const showScore = isLive || homeScore != null || awayScore != null;

  return (
    <Box className={`broadcast-arena${isLive ? ' is-live' : ' is-upcoming'}`}>
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
            <span className="broadcast-upcoming-tag">Up next</span>
          )}
          <span className="broadcast-comp">
            {match.league || leagueName || 'Rugby'}
            {match.round ? ` · ${match.round}` : ''}
          </span>
        </Box>

        <Box className="broadcast-hud-center">
          {isLive ? (
            <>
              <strong className="broadcast-minute">{clock || '—'}</strong>
              <span className="broadcast-phase">{phaseLabel(state)}</span>
            </>
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

      {(match.venue || (pred && pred.ph != null && pred.pa != null)) && (
        <Box className="broadcast-footer">
          {match.venue ? (
            <span className="broadcast-venue">
              <strong>{venueParts.ground}</strong>
              {venueParts.city ? <em>{venueParts.city}</em> : null}
            </span>
          ) : null}
          {pred && pred.ph != null && pred.pa != null ? (
            <span className="broadcast-model">{`${pred.ph}-${pred.pa}`}</span>
          ) : null}
        </Box>
      )}
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

  const logoMap = useMemo(() => readStandingsLogoCache(leagueId) || {}, [leagueId]);
  const displayLeagueName = leagueName;

  const fetchMatches = useCallback(async ({ quiet = false, refreshUpcoming = false } = {}) => {
    if (!leagueId) {
      setMatches([]);
      setError('');
      if (!quiet) setLoading(false);
      return;
    }
    if (!quiet) setLoading(true);
    try {
      const shouldRefreshUpcoming = refreshUpcoming || upcomingRef.current.length === 0;
      const [liveResult, upcomingResult] = await Promise.all([
        getLiveMatches({ league_id: leagueId }).catch((err) => {
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
      setMatches(merged);
      if (livePayload.error && merged.length === 0) {
        setError(String(livePayload.error));
      } else {
        setError('');
      }
    } catch (err) {
      console.warn('Live broadcast fetch failed:', err?.message || err);
      if (!quiet) {
        setError('Live feed temporarily unavailable.');
        setMatches([]);
      }
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => {
    setMatches([]);
    setError('');
    setLoading(true);
    upcomingRef.current = [];
    fetchMatches({ quiet: false, refreshUpcoming: true });
    const interval = setInterval(() => {
      fetchMatches({ quiet: true, refreshUpcoming: false }).catch(() => {});
    }, POLL_MS);
    return () => clearInterval(interval);
  }, [fetchMatches]);

  const liveCount = useMemo(
    () => matches.filter((m) => LIVE_STATES.has(String(m?.state || ''))).length,
    [matches]
  );

  const mastBits = useMemo(() => {
    const featured =
      matches.find((m) => LIVE_STATES.has(String(m?.state || ''))) || matches[0];
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
                  : !LIVE_STATES.has(String(match?.state || '')) &&
                    LIVE_STATES.has(String(prev?.state || ''))
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
