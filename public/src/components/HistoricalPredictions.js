import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Grid,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Paper,
  Divider,
  Button,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import { getHistoricalPredictions, getHistoricalBacktest } from '../firebase';
import RugbyBallLoader from './RugbyBallLoader';
import { hasMeaningfulTime, formatSASTDateYMD, formatSASTTimePM } from '../utils/date';
import leagueSeasonWindows from '../data/leagueSeasonWindows.json';

const HistoricalPredictions = ({ leagueId, leagueName }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [selectedYear, setSelectedYear] = useState(null);
  const [availableYears, setAvailableYears] = useState([]);
  const [evaluationMode, setEvaluationMode] = useState('replay'); // 'backtest' | 'replay'
  const [expandedWeeks, setExpandedWeeks] = useState(new Set());
  const autoPreferredYearAppliedRef = useRef(false);
  const lastInitialFetchRef = useRef({ leagueId: null, atMs: 0 });
  const theme = useTheme();
  const isSmDown = useMediaQuery(theme.breakpoints.down('sm'));

  useEffect(() => {
    const now = Date.now();
    const isDuplicateStrictModeRun =
      lastInitialFetchRef.current.leagueId === leagueId &&
      now - lastInitialFetchRef.current.atMs < 1500;
    if (isDuplicateStrictModeRun) {
      console.log('[History] Skipping duplicate initial fetch (strict mode guard)', { leagueId });
      return;
    }
    lastInitialFetchRef.current = { leagueId, atMs: now };
    // Reset selection when league changes
    setSelectedYear(null);
    setExpandedWeeks(new Set());
    autoPreferredYearAppliedRef.current = false;
    fetchHistoricalData();
  }, [leagueId]);

  const currentYear = useMemo(() => String(new Date().getFullYear()), []);
  const isRugbyWorldCup = Number(leagueId) === 4574;
  const isEnglishPremiership = Number(leagueId) === 4414;
  const preferredRwcYears = useMemo(() => ['2023', '2019', '2015', '2011', '2007'], []);
  const LUX = useMemo(
    () => ({
      gold: '#fbbf24',
      goldSoft: 'rgba(251,191,36,0.16)',
      bgA: 'rgba(17, 24, 39, 0.72)',
      bgB: 'rgba(15, 23, 42, 0.72)',
      border: 'rgba(255,255,255,0.10)',
      borderStrong: 'rgba(255,255,255,0.14)',
      text: 'rgba(255,255,255,0.92)',
      sub: 'rgba(255,255,255,0.70)',
      muted: 'rgba(255,255,255,0.62)',
    }),
    []
  );
  const HISTORY_BATCH_SIZE = 500;
  const detectedSeasonRanges = useMemo(() => {
    const all = Array.isArray(leagueSeasonWindows?.leagues) ? leagueSeasonWindows.leagues : [];
    const targetLeagueId = Number(leagueId);
    const leagueEntry = all.find((entry) => Number(entry?.league_id) === targetLeagueId);
    const seasons = Array.isArray(leagueEntry?.seasons) ? leagueEntry.seasons : [];
    return seasons
      .map((s, idx) => {
        const startDate = String(s?.start_date || '').slice(0, 10);
        const rawEndDate = String(s?.end_date || '').slice(0, 10);
        let endDate = rawEndDate;
        const start = new Date(`${startDate}T00:00:00Z`);
        const end = new Date(`${rawEndDate}T00:00:00Z`);
        const isLatestDetectedSeason = idx === seasons.length - 1;
        const isValidRange = !Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime());

        // If the newest season only spills into Jan/Feb of the following year,
        // treat it as an incomplete carry-over and cap display at Dec 31.
        if (isLatestDetectedSeason && isValidRange) {
          const startYear = start.getUTCFullYear();
          const endYear = end.getUTCFullYear();
          const endMonth = end.getUTCMonth() + 1;
          const crossesToNextYear = endYear === startYear + 1;
          if (crossesToNextYear && endMonth <= 2) {
            endDate = `${startYear}-12-31`;
          }
        }

        return { startDate, endDate, rawEndDate };
      })
      .filter((s) => s.startDate && s.endDate)
      .sort((a, b) => a.startDate.localeCompare(b.startDate));
  }, [leagueId]);
  const seasonGapDays = useMemo(() => {
    const overrides = leagueSeasonWindows?.league_gap_overrides || {};
    const rawOverride = overrides[String(leagueId)] ?? overrides[Number(leagueId)];
    const parsed = Number(rawOverride);
    if (Number.isFinite(parsed) && parsed >= 1) return parsed;
    return 90;
  }, [leagueId]);
  const shouldHidePremiershipSuppressedWindowMatch = (match) => {
    if (!isEnglishPremiership) return false;
    const iso = String(match?.date || '').slice(0, 10);
    if (!iso) return false;
    const isShort2018Window = iso >= '2018-08-01' && iso <= '2018-10-31';
    const isShort2020Window = iso >= '2020-02-01' && iso <= '2020-02-29';
    return isShort2018Window || isShort2020Window;
  };
  const filterSuppressedMatches = (matches = []) =>
    (Array.isArray(matches) ? matches : []).filter((m) => !shouldHidePremiershipSuppressedWindowMatch(m));

  const mergeMatchesByYearWeek = (baseMap = {}, incomingMap = {}) => {
    const out = { ...baseMap };
    Object.entries(incomingMap || {}).forEach(([year, weeks]) => {
      if (!out[year]) out[year] = {};
      Object.entries(weeks || {}).forEach(([weekKey, matches]) => {
        const existing = Array.isArray(out[year][weekKey]) ? out[year][weekKey] : [];
        const incoming = Array.isArray(matches) ? matches : [];
        const seen = new Set(existing.map((m) => m?.match_id ?? `${(m?.date || '').slice(0, 10)}-${m?.home_team || ''}-${m?.away_team || ''}`));
        const merged = [...existing];
        incoming.forEach((m) => {
          const id = m?.match_id ?? `${(m?.date || '').slice(0, 10)}-${m?.home_team || ''}-${m?.away_team || ''}`;
          if (seen.has(id)) return;
          seen.add(id);
          merged.push(m);
        });
        out[year][weekKey] = merged;
      });
    });
    return out;
  };

  const buildStatsFromMatches = (matches = []) => {
    const totalMatches = matches.length;
    let totalPredictions = 0;
    let correctPredictions = 0;
    const scoreErrors = [];
    const byLeague = {};

    matches.forEach((m) => {
      if (m?.prediction_correct !== null && m?.prediction_correct !== undefined) {
        totalPredictions += 1;
        if (m.prediction_correct === true) correctPredictions += 1;
      }
      if (Number.isFinite(m?.prediction_error)) scoreErrors.push(Number(m.prediction_error));
      const lid = m?.league_id;
      if (lid === null || lid === undefined) return;
      if (!byLeague[lid]) {
        byLeague[lid] = {
          league_name: m?.league_name || `League ${lid}`,
          total_matches: 0,
          total_predictions: 0,
          correct_predictions: 0,
          accuracy_percentage: 0,
        };
      }
      byLeague[lid].total_matches += 1;
      if (m?.prediction_correct !== null && m?.prediction_correct !== undefined) {
        byLeague[lid].total_predictions += 1;
        if (m.prediction_correct === true) byLeague[lid].correct_predictions += 1;
      }
    });

    Object.values(byLeague).forEach((entry) => {
      entry.accuracy_percentage = entry.total_predictions > 0
        ? Number(((entry.correct_predictions / entry.total_predictions) * 100).toFixed(2))
        : 0;
    });

    return {
      statistics: {
        total_matches: totalMatches,
        total_predictions: totalPredictions,
        correct_predictions: correctPredictions,
        accuracy_percentage: totalPredictions > 0 ? Number(((correctPredictions / totalPredictions) * 100).toFixed(2)) : 0,
        average_score_error: scoreErrors.length > 0 ? Number((scoreErrors.reduce((a, b) => a + b, 0) / scoreErrors.length).toFixed(2)) : null,
      },
      by_league: byLeague,
    };
  };

  const fetchHistoricalData = async (yearOverride = null, modeOverride = null, options = {}) => {
    if (!leagueId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = { league_id: leagueId };
      if (yearOverride) payload.year = yearOverride;
      if (options?.refresh) payload.refresh = true;
      const mode = modeOverride || evaluationMode;
      const startedAt = performance.now();
      console.log('[History] Fetch start', {
        leagueId,
        mode,
        year: payload.year || 'auto',
        refresh: Boolean(payload.refresh),
      });

      let result = null;
      if (mode === 'backtest') {
        const backtestStart = performance.now();
        result = await getHistoricalBacktest(payload);
        console.log('[History] Backtest response', {
          durationMs: Number((performance.now() - backtestStart).toFixed(1)),
          selectedYear: result?.data?.selected_year || null,
          totalMatches: result?.data?.statistics?.total_matches ?? null,
        });
      } else {
        let offset = 0;
        let pagesFetched = 0;
        let mergedData = null;
        while (pagesFetched < 20) {
          const pagePayload = { ...payload, limit: HISTORY_BATCH_SIZE, offset };
          const pageStart = performance.now();
          const page = await getHistoricalPredictions(pagePayload);
          const pageData = page?.data || {};
          console.log('[History] Replay page', {
            page: pagesFetched + 1,
            offset,
            limit: HISTORY_BATCH_SIZE,
            returnedRows: pageData?.pagination?.returned_rows ?? null,
            totalRows: pageData?.pagination?.total_rows ?? null,
            hasMore: Boolean(pageData?.pagination?.has_more),
            nextOffset: pageData?.pagination?.next_offset ?? null,
            durationMs: Number((performance.now() - pageStart).toFixed(1)),
          });
          if (!mergedData) {
            mergedData = { ...pageData, matches_by_year_week: pageData.matches_by_year_week || {}, all_matches: pageData.all_matches || [] };
          } else {
            mergedData.matches_by_year_week = mergeMatchesByYearWeek(mergedData.matches_by_year_week, pageData.matches_by_year_week || {});
            mergedData.all_matches = [...(mergedData.all_matches || []), ...(pageData.all_matches || [])];
          }
          pagesFetched += 1;
          const hasMore = Boolean(pageData?.pagination?.has_more);
          const nextOffset = Number(pageData?.pagination?.next_offset ?? 0);
          if (!hasMore || !Number.isFinite(nextOffset) || nextOffset <= offset) break;
          offset = nextOffset;
        }

        if (mergedData) {
          const derived = buildStatsFromMatches(mergedData.all_matches || []);
          mergedData.statistics = derived.statistics;
          mergedData.by_league = derived.by_league;
          console.log('[History] Replay merged', {
            pagesFetched,
            mergedMatches: mergedData?.all_matches?.length || 0,
            selectedYear: mergedData?.selected_year || null,
          });
          result = { data: mergedData };
        } else {
          result = { data: null };
        }
      }
      if (result?.data) {
        setData(result.data);

        const fromBackendYears = Array.isArray(result.data.available_years) ? result.data.available_years : [];
        setAvailableYears(fromBackendYears);
        
        // Prefer backend-selected year (prevents loading everything at once)
        const backendSelected = result.data.selected_year ? String(result.data.selected_year) : null;
        if (backendSelected) {
          setSelectedYear(backendSelected);
        } else if (result.data.matches_by_year_week) {
          // Fallback: derive from payload
          const years = Object.keys(result.data.matches_by_year_week).sort().reverse();
          if (years.length > 0) setSelectedYear(years[0]);
        }

        // Luxury UX: ensure Year selector always includes the current year.
        // Also pick a sensible default automatically ONCE:
        // - World Cup: prefer tournament years (2023/2019/...)
        // - Other leagues: prefer current year if present, else backend most recent.
        if (!yearOverride && !autoPreferredYearAppliedRef.current) {
          const derivedYears = result.data.matches_by_year_week ? Object.keys(result.data.matches_by_year_week) : [];
          const yearSet = new Set([...fromBackendYears.map(String), ...derivedYears.map(String), currentYear]);
          const mergedYears = Array.from(yearSet).filter(Boolean);

          const chooseRwc = () => {
            for (const y of preferredRwcYears) {
              if (yearSet.has(y)) return y;
            }
            return backendSelected || mergedYears.sort().reverse()[0] || null;
          };

          const chooseDefault = () => {
            if (isRugbyWorldCup) return chooseRwc();
            if (yearSet.has(currentYear)) return currentYear;
            return backendSelected || mergedYears.sort().reverse()[0] || null;
          };

          const preferred = chooseDefault();
          if (preferred && preferred !== backendSelected) {
            console.log('[History] Auto-selecting preferred year and refetching', {
              preferredYear: preferred,
              backendSelected,
              mode,
            });
            autoPreferredYearAppliedRef.current = true;
            setSelectedYear(preferred);
            // Refetch just that year (keeps payload small).
            await fetchHistoricalData(preferred, mode);
            return;
          }
        }
        console.log('[History] Fetch success', {
          durationMs: Number((performance.now() - startedAt).toFixed(1)),
          selectedYear: result?.data?.selected_year || null,
          totalMatches: result?.data?.statistics?.total_matches ?? null,
          totalPredictions: result?.data?.statistics?.total_predictions ?? null,
        });
      } else {
        setError('No data returned from server');
      }
    } catch (err) {
      console.error('Error fetching historical predictions:', err);
      setError(err.message || 'Failed to load historical predictions');
    } finally {
      setLoading(false);
    }
  };

  const handleWeekToggle = (weekKey) => {
    setExpandedWeeks(prev => {
      const newSet = new Set(prev);
      if (newSet.has(weekKey)) {
        newSet.delete(weekKey);
      } else {
        newSet.add(weekKey);
      }
      return newSet;
    });
  };

  if (loading) {
    return (
      <Box
        sx={{
          width: '100%',
          minHeight: { xs: 'calc(100svh - 160px)', sm: 'calc(100vh - 180px)' },
          display: 'grid',
          placeItems: 'center',
          boxSizing: 'border-box',
        }}
      >
        <RugbyBallLoader size={100} color="#10b981" compact label="Loading history..." />
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography color="error" variant="h6" gutterBottom>
          Error Loading Data
        </Typography>
        <Typography color="text.secondary">{error}</Typography>
      </Box>
    );
  }

  if (!data || !data.matches_by_year_week) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography color="text.secondary">No historical data available</Typography>
      </Box>
    );
  }

  const years = (() => {
    const withMatches = Object.keys(data.matches_by_year_week || {}).map(String).filter(Boolean);
    const base = (availableYears && availableYears.length > 0)
      ? availableYears.map(String)
      : withMatches;
    let baseNumericYears = [...new Set(base.filter((y) => !isNaN(parseInt(y, 10))))].filter(Boolean).sort().reverse();
    if (isEnglishPremiership) {
      baseNumericYears = baseNumericYears.filter((y) => y !== '2019');
    }
    const numericYears = isRugbyWorldCup
      ? baseNumericYears
      : [...new Set([...baseNumericYears, currentYear])].sort().reverse();
    const allOption = [];
    if (isRugbyWorldCup) {
      // Keep RWC selector clean: only real tournament years (every 4 years).
      const rwcYears = numericYears.filter((y) => {
        const n = parseInt(y, 10);
        return Number.isFinite(n) && (n - 2023) % 4 === 0;
      });
      return [...allOption, ...rwcYears];
    }
    return [...allOption, ...numericYears];
  })();
  const yearSummary = data?.year_summary || {};
  const stats = data.statistics || {};
  const hasCompletedMatches = Number(stats.total_matches || 0) > 0;
  const selectedYearDateRange = (() => {
    const yr = String(selectedYear || '');
    if (!yr || yr === 'all') return null;
    const yearData = data?.matches_by_year_week?.[yr];
    if (!yearData) return null;
    const allDates = filterSuppressedMatches(Object.values(yearData).flat())
      .filter((m) => {
        const matchYear = String((m?.year || String(m?.date || '').slice(0, 4)));
        return matchYear === yr;
      })
      .map((m) => String(m?.date || '').slice(0, 10))
      .filter(Boolean);
    if (!allDates.length) return null;
    const sorted = [...allDates].sort();
    return { firstDate: sorted[0], lastDate: sorted[sorted.length - 1] };
  })();

  const selectedYearDetectedSeasonRange = (() => {
    if (!selectedYearDateRange || detectedSeasonRanges.length === 0) return null;
    const toUtcMs = (iso) => new Date(`${iso}T00:00:00Z`).getTime();
    const blockStartMs = toUtcMs(selectedYearDateRange.firstDate);
    const blockEndMs = toUtcMs(selectedYearDateRange.lastDate);
    let best = null;
    let bestOverlapMs = -1;
    detectedSeasonRanges.forEach((range) => {
      const rangeStartMs = toUtcMs(range.startDate);
      const rangeEndMs = toUtcMs(range.endDate);
      const overlapStart = Math.max(blockStartMs, rangeStartMs);
      const overlapEnd = Math.min(blockEndMs, rangeEndMs);
      const overlapMs = Math.max(0, overlapEnd - overlapStart);
      if (overlapMs > bestOverlapMs) {
        bestOverlapMs = overlapMs;
        best = range;
      }
    });
    return best;
  })();

  const selectedSeasonLabel = (() => {
    const yr = Number(selectedYear);
    if (!Number.isFinite(yr) || selectedYear === 'all') return '';
    const statusText = hasCompletedMatches ? 'Results available' : 'Results pending';
    const formatRange = (startIso, endIso) => {
      const start = new Date(`${startIso}T00:00:00`);
      const end = new Date(`${endIso}T00:00:00`);
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return '';
      const startMo = start.toLocaleDateString('en-US', { month: 'short' });
      const endMo = end.toLocaleDateString('en-US', { month: 'short' });
      const startYr = start.getFullYear();
      const endYr = end.getFullYear();
      return startYr === endYr ? `${startMo} – ${endMo} ${startYr}` : `${startMo} ${startYr} – ${endMo} ${endYr}`;
    };
    if (selectedYearDetectedSeasonRange) {
      const startYear = new Date(`${selectedYearDetectedSeasonRange.startDate}T00:00:00`).getFullYear();
      const endYear = new Date(`${selectedYearDetectedSeasonRange.endDate}T00:00:00`).getFullYear();
      const isAlignedToSelectedYear = isRugbyWorldCup
        ? (startYear === yr || endYear === yr)
        : endYear === yr;
      const windowLabel = formatRange(selectedYearDetectedSeasonRange.startDate, selectedYearDetectedSeasonRange.endDate);
      if (windowLabel && isAlignedToSelectedYear) {
        return isRugbyWorldCup
          ? `Tournament window: ${windowLabel} • ${statusText}`
          : `Season window: ${windowLabel} • ${statusText}`;
      }
    }
    if (isRugbyWorldCup) return `Tournament year: ${yr} • ${statusText}`;
    return `Season: Sep ${yr - 1} - Jun ${yr} • ${statusText}`;
  })();

  const titleMonogram = (() => {
    const raw = String(leagueName || '').trim();
    if (!raw) return 'H';
    const words = raw.replace(/[^a-zA-Z0-9\s]/g, ' ').split(/\s+/).filter(Boolean);
    const significant = words.filter((w) => w.length > 2);
    const pick = (significant.length ? significant : words).slice(0, 3);
    const letters = pick.map((w) => w[0]?.toUpperCase()).filter(Boolean);
    return letters.join('') || raw.slice(0, 2).toUpperCase();
  })();

  return (
    <Box
      sx={{
        width: '100%',
        maxWidth: '100%',
        mx: 0,
        p: { xs: 1.25, sm: 2.5, md: 3.5 },
        boxSizing: 'border-box',
        overflowX: 'hidden', // avoid tiny-screen horizontal scroll
      }}
    >
      {/* Luxury header + summary */}
      <Paper
        elevation={0}
        sx={{
          position: 'relative',
          overflow: 'hidden',
          borderRadius: { xs: 2.5, sm: 3 },
          p: { xs: 1.5, sm: 2.25, md: 2.75 },
          mb: { xs: 2, sm: 2.5, md: 3 },
          background:
            'radial-gradient(1200px circle at 12% -10%, rgba(251,191,36,0.18), transparent 45%), linear-gradient(135deg, rgba(15,23,42,0.82) 0%, rgba(17,24,39,0.78) 70%)',
          border: `1px solid ${LUX.borderStrong}`,
          boxShadow: '0 18px 70px rgba(0,0,0,0.40)',
          '&::after': {
            content: '""',
            position: 'absolute',
            inset: -1,
            borderRadius: 'inherit',
            padding: '1px',
            background: 'linear-gradient(135deg, rgba(251,191,36,0.48), rgba(255,255,255,0.08), rgba(251,191,36,0.22))',
            WebkitMask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
            WebkitMaskComposite: 'xor',
            maskComposite: 'exclude',
            pointerEvents: 'none',
            opacity: 0.85,
          },
        }}
      >
        <Box sx={{ display: 'flex', gap: 1.25, alignItems: 'center', flexWrap: 'wrap', width: '100%' }}>
          <Box
            sx={{
              width: 42,
              height: 42,
              borderRadius: 2.2,
              display: 'grid',
              placeItems: 'center',
              background: 'linear-gradient(135deg, rgba(251,191,36,0.26) 0%, rgba(255,255,255,0.08) 100%)',
              border: '1px solid rgba(255,255,255,0.14)',
              color: '#fef3c7',
              fontWeight: 1000,
              letterSpacing: 0.7,
            }}
            title={leagueName || 'History'}
          >
            {titleMonogram}
          </Box>

          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography
              sx={{
                color: 'white',
                fontWeight: 1100,
                letterSpacing: 0.2,
                fontSize: { xs: '1.15rem', sm: '1.55rem', md: '1.75rem' },
              }}
              noWrap
            >
              Historical Performance
            </Typography>
            <Typography sx={{ color: LUX.sub, mt: 0.35, fontSize: '0.86rem' }}>
              {leagueName || 'League'} • Past predictions vs actual results
            </Typography>
          </Box>

          <Box
            sx={{
              display: 'flex',
              gap: 1,
              alignItems: 'center',
              flexWrap: 'wrap',
              width: '100%',
              justifyContent: 'center',
              mt: { xs: 0.75, sm: 0.25 },
            }}
          >
            <Button
              variant={evaluationMode === 'replay' ? 'contained' : 'outlined'}
              size="small"
              onClick={() => {
                const newMode = 'replay';
                setEvaluationMode(newMode);
                setExpandedWeeks(new Set());
                fetchHistoricalData(selectedYear, newMode);
              }}
              sx={{
                textTransform: 'none',
                fontWeight: 900,
                borderRadius: 999,
                ...(evaluationMode === 'replay'
                  ? {
                      backgroundColor: 'rgba(251,191,36,0.16)',
                      color: LUX.gold,
                      boxShadow: 'none',
                      border: '1px solid rgba(251,191,36,0.22)',
                      '&:hover': { backgroundColor: 'rgba(251,191,36,0.22)' },
                    }
                  : {
                      borderColor: 'rgba(255,255,255,0.14)',
                      color: 'rgba(255,255,255,0.82)',
                      '&:hover': { borderColor: 'rgba(255,255,255,0.22)', backgroundColor: 'rgba(255,255,255,0.04)' },
                    }),
              }}
            >
              Past Results
            </Button>
          </Box>
        </Box>

        <Box
          sx={{
            mt: 1.75,
            display: 'grid',
            gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(4, 1fr)' },
            gap: { xs: 1, sm: 1.25, md: 1.5 },
            width: '100%',
          }}
        >
          {[
            { label: 'Matches', value: stats.total_matches || 0 },
            { label: 'Correct', value: stats.correct_predictions || 0 },
            { label: 'Accuracy', value: `${stats.accuracy_percentage?.toFixed(1) || '0.0'}%` },
            { label: 'Avg error', value: stats.average_score_error?.toFixed(1) || 'N/A' },
          ].map((m) => (
            <Box
              key={m.label}
              sx={{
                p: { xs: 1, sm: 1.25, md: 1.5 },
                borderRadius: 2,
                border: `1px solid ${LUX.border}`,
                background: 'linear-gradient(180deg, rgba(255,255,255,0.06) 0%, rgba(0,0,0,0.10) 100%)',
                minHeight: { xs: 72, sm: 80, md: 88 },
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                textAlign: 'center',
              }}
            >
              <Typography
                sx={{
                  color: LUX.muted,
                  fontSize: { xs: '0.7rem', sm: '0.75rem', md: '0.8rem' },
                  letterSpacing: 0.12,
                  textTransform: 'uppercase',
                  fontWeight: 800,
                  lineHeight: 1.3,
                }}
              >
                {m.label}
              </Typography>
              <Typography
                sx={{
                  color: 'white',
                  fontWeight: 1100,
                  fontSize: { xs: '1.25rem', sm: '1.4rem', md: '1.5rem' },
                  mt: 0.5,
                  lineHeight: 1.2,
                }}
              >
                {m.value}
              </Typography>
            </Box>
          ))}
        </Box>
      </Paper>

      {/* Filters */}
      <Paper
        elevation={0}
        sx={{
          p: { xs: 1.25, sm: 1.5 },
          mb: { xs: 1.75, sm: 2 },
          borderRadius: 3,
          background: 'linear-gradient(180deg, rgba(255,255,255,0.045) 0%, rgba(0,0,0,0.12) 100%)',
          border: `1px solid ${LUX.border}`,
          boxShadow: '0 14px 46px rgba(0,0,0,0.26)',
        }}
      >
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            gap: 1.25,
            width: '100%',
          }}
        >
          {years.length > 1 && (
            <Box sx={{ minWidth: 0, maxWidth: { xs: '100%', sm: 360, md: 380 } }}>
              <FormControl
                size="small"
                fullWidth
                sx={{
                  minWidth: 0,
                }}
              >
                <InputLabel sx={{ color: 'rgba(255,255,255,0.70)' }} shrink={Boolean(selectedYear && selectedYear !== 'all')}>
                  Year
                </InputLabel>
                <Select
                  value={selectedYear || ''}
                  label="Year"
                  onChange={(e) => {
                    const newYear = e.target.value;
                    setSelectedYear(newYear);
                    setExpandedWeeks(new Set());
                    // Use backend cache by default; only bypass cache on explicit manual refresh actions.
                    fetchHistoricalData(newYear === 'all' ? 'all' : newYear, evaluationMode, { refresh: false });
                  }}
                  sx={{
                    color: 'rgba(255,255,255,0.92)',
                    borderRadius: 2.25,
                    backgroundColor: 'rgba(255,255,255,0.04)',
                    '& .MuiSelect-select': { pr: 4 },
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: LUX.border },
                    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.18)' },
                    '& .MuiSvgIcon-root': { color: LUX.gold },
                  }}
                  MenuProps={{
                    variant: 'menu',
                    marginThreshold: 0,
                    disableScrollLock: true,
                    anchorOrigin: { vertical: 'bottom', horizontal: 'left' },
                    transformOrigin: { vertical: 'top', horizontal: 'left' },
                    PaperProps: {
                      sx: {
                        mt: 1,
                        backgroundColor: 'rgba(17,24,39,0.98)',
                        border: `1px solid ${LUX.border}`,
                        backdropFilter: 'blur(14px)',
                        maxHeight: { xs: '42vh', sm: '46vh' },
                        overflowY: 'auto',
                      },
                    },
                  }}
                >
                  {years.map((year) => {
                    return (
                      <MenuItem key={year} value={year} sx={{ color: 'rgba(255,255,255,0.92)' }}>
                        <Box
                          sx={{
                            display: 'flex',
                            alignItems: { xs: 'flex-start', sm: 'center' },
                            justifyContent: 'space-between',
                            width: '100%',
                            gap: 1.25,
                            minWidth: 0,
                            flexWrap: { xs: 'wrap', sm: 'nowrap' },
                          }}
                        >
                          <Typography sx={{ fontWeight: 900, minWidth: 0 }}>{year === 'all' ? 'All years' : year}</Typography>
                        </Box>
                      </MenuItem>
                    );
                  })}
                </Select>
              </FormControl>
              {selectedSeasonLabel ? (
                <Typography sx={{ mt: 0.7, color: 'rgba(255,255,255,0.72)', fontSize: '0.82rem', fontWeight: 700 }}>
                  {selectedSeasonLabel}
                </Typography>
              ) : null}
            </Box>
          )}

        </Box>
      </Paper>

      {/* Matches grouped by season (Sept–Jun); 90-day gap = new season; clear dividers */}
      {(() => {
        const _allMatchesGlobal = filterSuppressedMatches(
          Object.values(data.matches_by_year_week || {}).flatMap((yd) => Object.values(yd).flat())
        );
        const selYr = selectedYear && selectedYear !== 'all' ? String(selectedYear) : null;
        const prevYr = selYr && selYr !== 'all' ? String(Number(selYr) - 1) : null;
        const prevYrData = prevYr ? (data.matches_by_year_week || {})[prevYr] : null;
        const prevYrMatches = prevYrData ? filterSuppressedMatches(Object.values(prevYrData).flat()) : [];

        const SEASON_GAP_DAYS = seasonGapDays;
        const daysBetweenIsoDates = (aIso, bIso) => {
          if (!aIso || !bIso) return 0;
          const [ay, am, ad] = String(aIso).slice(0, 10).split('-').map((v) => parseInt(v, 10));
          const [by, bm, bd] = String(bIso).slice(0, 10).split('-').map((v) => parseInt(v, 10));
          if (!ay || !am || !ad || !by || !bm || !bd) return 0;
          const aMs = Date.UTC(ay, am - 1, ad);
          const bMs = Date.UTC(by, bm - 1, bd);
          return (bMs - aMs) / (1000 * 60 * 60 * 24);
        };

        const splitIntoSeasons = (matchList) => {
          const sorted = [...matchList].filter((m) => m.date).sort((a, b) => (a.date || '').localeCompare(b.date || ''));
          if (sorted.length === 0) return [];
          const seasons = [];
          let current = [sorted[0]];
          for (let i = 1; i < sorted.length; i++) {
            const prev = sorted[i - 1].date?.slice(0, 10) || '';
            const curr = sorted[i].date?.slice(0, 10) || '';
            const daysDiff = daysBetweenIsoDates(prev, curr);
            if (daysDiff >= SEASON_GAP_DAYS) {
              seasons.push(current);
              current = [sorted[i]];
            } else {
              current.push(sorted[i]);
            }
          }
          seasons.push(current);
          return seasons;
        };

        const buildRoundEntriesForSeason = (matchList) => {
          const sorted = [...matchList].filter((m) => m.date).sort((a, b) => (a.date || '').localeCompare(b.date || ''));
          if (!sorted.length) return [];
          const matchIdentity = (m) => m.match_id ?? `${(m.date || '').slice(0, 10)}-${m.home_team || ''}-${m.away_team || ''}`;
          const seasonAnchorIso = String(sorted[0].date || '').slice(0, 10) || '';
          const knockoutById = {};
          const knockoutIds = new Set();
          if (isRugbyWorldCup && sorted.length >= 8) {
            const last8 = sorted.slice(-8); // QF x4, SF x2, 3rd place x1, Final x1
            if (last8.length === 8) {
              const assignStage = (m, stage) => {
                const id = matchIdentity(m);
                knockoutById[id] = stage;
                knockoutIds.add(id);
              };
              assignStage(last8[7], 'Final');
              assignStage(last8[6], 'Third-place');
              assignStage(last8[5], 'Semi-finals');
              assignStage(last8[4], 'Semi-finals');
              assignStage(last8[3], 'Quarter-finals');
              assignStage(last8[2], 'Quarter-finals');
              assignStage(last8[1], 'Quarter-finals');
              assignStage(last8[0], 'Quarter-finals');
            }
          }

          const poolMatches = sorted.filter((m) => !knockoutIds.has(matchIdentity(m)));
          if (!poolMatches.length && knockoutIds.size > 0) {
            const stageOrder = ['Final', 'Third-place', 'Semi-finals', 'Quarter-finals'];
            return stageOrder
              .map((stage, idx) => {
                const matches = sorted.filter((m) => knockoutById[matchIdentity(m)] === stage);
                if (!matches.length) return null;
                const earliestDate = matches.reduce((min, m) => (!min || m.date < min ? m.date : min), null);
                return {
                  key: `stage-${seasonAnchorIso}-${stage.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
                  label: stage,
                  matches,
                  earliestDate,
                  sortVal: 1000 - idx,
                };
              })
              .filter(Boolean);
          }

          const poolAnchorIso = String(poolMatches[0]?.date || seasonAnchorIso).slice(0, 10) || seasonAnchorIso;
          const byRawWeekNum = {};
          poolMatches.forEach((m) => {
            const dateIso = String(m.date || '').slice(0, 10);
            const daysFromStart = Math.max(0, daysBetweenIsoDates(poolAnchorIso, dateIso));
            // Week numbering is anchored to actual season start:
            // days 0-6 => Week 1, days 7-13 => Week 2, etc.
            const rawWeekNum = Math.floor(daysFromStart / 7) + 1;
            const key = String(rawWeekNum);
            if (!byRawWeekNum[key]) byRawWeekNum[key] = [];
            byRawWeekNum[key].push(m);
          });

          // Prevent skipped numbering (Week 1, Week 3) by reindexing only observed fixture weeks.
          const orderedRawWeeks = Object.keys(byRawWeekNum)
            .map((k) => parseInt(k, 10))
            .filter((n) => Number.isFinite(n))
            .sort((a, b) => a - b);

          const baseEntries = orderedRawWeeks
            .map((rawWeekNum, idx) => {
              const matches = byRawWeekNum[String(rawWeekNum)] || [];
              const displayWeekNum = idx + 1;
              const earliestDate = matches.reduce((min, m) => (!min || m.date < min ? m.date : min), null);
              return {
                key: `week-${seasonAnchorIso}-${displayWeekNum}`,
                label: `Week ${displayWeekNum}`,
                matches,
                earliestDate,
                sortVal: displayWeekNum,
              };
            })
            .sort((a, b) => b.sortVal - a.sortVal || (b.earliestDate || '').localeCompare(a.earliestDate || ''));

          if (knockoutIds.size > 0) {
            const stageOrder = ['Final', 'Third-place', 'Semi-finals', 'Quarter-finals'];
            const stageEntries = stageOrder
              .map((stage, idx) => {
                const matches = sorted.filter((m) => knockoutById[matchIdentity(m)] === stage);
                if (!matches.length) return null;
                const earliestDate = matches.reduce((min, m) => (!min || m.date < min ? m.date : min), null);
                return {
                  key: `stage-${seasonAnchorIso}-${stage.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
                  label: stage,
                  matches,
                  earliestDate,
                  sortVal: 1000 - idx,
                };
              })
              .filter(Boolean);
            return [...stageEntries, ...baseEntries];
          }

          return baseEntries;
        };

        const formatSeasonLabel = (firstDate, lastDate, opts = {}) => {
          if (!firstDate || !lastDate) return 'Season';
          const firstIso = String(firstDate).slice(0, 10);
          const lastIso = String(lastDate).slice(0, 10);
          const toLabel = (startIso, endIso) => {
            const start = new Date(`${startIso}T00:00:00`);
            const end = new Date(`${endIso}T00:00:00`);
            if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 'Season';
            const startMo = start.toLocaleDateString('en-US', { month: 'short' });
            const endMo = end.toLocaleDateString('en-US', { month: 'short' });
            const startYr = start.getFullYear();
            const endYr = end.getFullYear();
            if (startYr === endYr) return `${startMo} – ${endMo} ${startYr}`;
            return `${startMo} ${startYr} – ${endMo} ${endYr}`;
          };

          // Use detected season windows when possible so widget labels match real league seasons.
          if (detectedSeasonRanges.length > 0) {
            const toUtcMs = (iso) => new Date(`${iso}T00:00:00Z`).getTime();
            const blockStartMs = toUtcMs(firstIso);
            const blockEndMs = toUtcMs(lastIso);
            let best = null;
            let bestOverlapMs = -1;

            detectedSeasonRanges.forEach((range) => {
              const rangeStartMs = toUtcMs(range.startDate);
              const rangeEndMs = toUtcMs(range.endDate);
              const overlapStart = Math.max(blockStartMs, rangeStartMs);
              const overlapEnd = Math.min(blockEndMs, rangeEndMs);
              const overlapMs = Math.max(0, overlapEnd - overlapStart);
              if (overlapMs > bestOverlapMs) {
                bestOverlapMs = overlapMs;
                best = range;
              }
            });

            if (best) {
              const touches = firstIso <= best.endDate && lastIso >= best.startDate;
              if (touches) {
                const detectedEndForLabel = opts.useActualDetectedEnd
                  ? (best.rawEndDate || best.endDate)
                  : best.endDate;
                return toLabel(best.startDate, detectedEndForLabel);
              }
            }
          }

          return toLabel(firstIso, lastIso);
        };

        const merged = [...prevYrMatches, ..._allMatchesGlobal].filter((m) => m.date);
        const seenIds = new Set();
        const allForSplit = merged
          .filter((m) => {
            const id = m.match_id ?? `${(m.date || '').slice(0, 10)}-${m.home_team || ''}-${m.away_team || ''}`;
            if (seenIds.has(id)) return false;
            seenIds.add(id);
            return true;
          })
          .sort((a, b) => (a.date || '').localeCompare(b.date || ''));
        const seasons = splitIntoSeasons(allForSplit);
        const seasonBoundaryMeta = new Map(
          seasons.map((season, seasonIdx) => {
            const seasonFirstDate = season.reduce((min, m) => (!min || m.date < min ? m.date : min), null);
            const seasonLastDate = season.reduce((max, m) => (!max || m.date > max ? m.date : max), null);
            const hasNextSeason = seasonIdx < seasons.length - 1;
            const daysSinceSeasonLast = seasonLastDate
              ? (Date.now() - new Date(seasonLastDate).getTime()) / (1000 * 60 * 60 * 24)
              : Number.POSITIVE_INFINITY;
            // Closed season if another season already started, or if it's stale beyond the split gap.
            const isSeasonClosed = hasNextSeason || daysSinceSeasonLast >= SEASON_GAP_DAYS;
            return [`${seasonFirstDate || ''}|${seasonLastDate || ''}`, { isSeasonClosed }];
          })
        );
        const seasonsFiltered = selYr
          ? seasons.filter((s) => s.some((m) => {
              const y = String((m.year || (m.date || '').slice(0, 4)));
              return y === selYr;
            }))
          : seasons;

        const endColor = '#c97a6a';
        const endColorBg = 'linear-gradient(135deg, rgba(160, 85, 70, 0.16) 0%, rgba(130, 65, 55, 0.08) 100%)';
        const SeasonSectionHeader = ({ label, variant, placement = 'default' }) => {
          const prefix = variant === 'end' ? 'End of Season ' : variant === 'start' ? 'Start of Season ' : '';
          const isStart = variant === 'start';
          const isEnd = variant === 'end';
          const spacingByPlacement = {
            default: { mt: 2, mb: 2 },
            // Visually center between last round card and upcoming divider line.
            beforeDivider: { mt: 6, mb: 0 },
            // Visually center between divider line and first round card.
            afterDivider: { mt: 0, mb: 8 },
          };
          const spacing = spacingByPlacement[placement] || spacingByPlacement.default;
          return (
            <Box sx={{ mt: spacing.mt, mb: spacing.mb, position: 'relative', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Typography
                  sx={{
                    position: 'relative',
                    zIndex: 1,
                    color: isStart ? LUX.gold : isEnd ? endColor : 'rgba(255,255,255,0.85)',
                    fontWeight: 900,
                    fontSize: { xs: '1rem', sm: '1.15rem' },
                    letterSpacing: 0.3,
                    textTransform: 'uppercase',
                    px: 2,
                    py: 0.5,
                    borderRadius: 2,
                    background: isStart ? 'linear-gradient(135deg, rgba(251,191,36,0.12) 0%, rgba(251,191,36,0.06) 100%)' : isEnd ? endColorBg : 'rgba(255,255,255,0.04)',
                    border: isStart ? '1px solid rgba(251,191,36,0.25)' : isEnd ? '1px solid rgba(180, 90, 75, 0.45)' : '1px solid rgba(255,255,255,0.08)',
                    whiteSpace: 'nowrap',
                    width: 'fit-content',
                    mx: 'auto',
                    textAlign: 'center',
                  }}
                >
                  {prefix}{label}
                </Typography>
            </Box>
          );
        };

        const SeasonBlockDivider = () => (
          <Box
            sx={{
              my: 5,
              py: 3,
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              '&::before': {
                content: '""',
                position: 'absolute',
                left: 0,
                right: 0,
                top: '50%',
                transform: 'translateY(-50%)',
                height: 6,
                background: 'linear-gradient(90deg, transparent 0%, rgba(251,191,36,0.12) 10%, rgba(251,191,36,0.45) 50%, rgba(251,191,36,0.12) 90%, transparent 100%)',
                borderRadius: 3,
                boxShadow: '0 0 20px rgba(251,191,36,0.15)',
              },
              '&::after': {
                content: '""',
                position: 'absolute',
                left: '5%',
                right: '5%',
                top: '50%',
                transform: 'translateY(-50%)',
                height: 2,
                background: 'linear-gradient(90deg, transparent, rgba(251,191,36,0.4), transparent)',
                borderRadius: 1,
              },
            }}
          />
        );

        const matchYear = (m) => String((m.year || (m.date || '').slice(0, 4)));
        const shouldSuppressPremiershipShortSeasonHeader = (seasonFirstDate, seasonLastDate) => {
          if (!isEnglishPremiership || !seasonFirstDate || !seasonLastDate) return false;
          const firstIso = String(seasonFirstDate).slice(0, 10);
          const lastIso = String(seasonLastDate).slice(0, 10);
          const first = new Date(`${firstIso}T00:00:00Z`);
          const last = new Date(`${lastIso}T00:00:00Z`);
          if (Number.isNaN(first.getTime()) || Number.isNaN(last.getTime())) return false;
          const isShort2018Window = (
            first.getUTCFullYear() === 2018 &&
            last.getUTCFullYear() === 2018 &&
            first.getUTCMonth() === 7 && // Aug
            last.getUTCMonth() === 9 // Oct
          );
          const isShort2020Window = (
            first.getUTCFullYear() === 2020 &&
            last.getUTCFullYear() === 2020 &&
            first.getUTCMonth() === 1 && // Feb
            last.getUTCMonth() === 1 // Feb
          );
          return isShort2018Window || isShort2020Window;
        };
        const isSeasonClosedByGap = (seasonLastDate, hasNewerSeason = false) => {
          if (hasNewerSeason) return true;
          if (!seasonLastDate) return false;
          const daysSinceSeasonLast = (Date.now() - new Date(seasonLastDate).getTime()) / (1000 * 60 * 60 * 24);
          return daysSinceSeasonLast >= SEASON_GAP_DAYS;
        };

        if (seasonsFiltered.length > 0) {
          let seasonsOrdered = [...seasonsFiltered].reverse();
          if (selYr) {
            seasonsOrdered = [...seasonsOrdered].sort((a, b) => {
              const aDisp = a.filter((m) => matchYear(m) === selYr);
              const bDisp = b.filter((m) => matchYear(m) === selYr);
              const aFirst = aDisp.length ? aDisp.reduce((min, m) => (!min || m.date < min ? m.date : min), null) : null;
              const bFirst = bDisp.length ? bDisp.reduce((min, m) => (!min || m.date < min ? m.date : min), null) : null;
              if (!aFirst && !bFirst) return 0;
              if (!aFirst) return 1;
              if (!bFirst) return -1;
              return (aFirst || '').localeCompare(bFirst || '');
            });
          }
          const splitDisplayByGap = (matches, gapDays = 90) => {
            if (!matches.length) return [];
            const sorted = [...matches].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
            const groups = [];
            let current = [sorted[0]];
            for (let i = 1; i < sorted.length; i++) {
              const prev = sorted[i - 1].date?.slice(0, 10) || '';
              const curr = sorted[i].date?.slice(0, 10) || '';
              const daysDiff = daysBetweenIsoDates(prev, curr);
              if (daysDiff >= gapDays) {
                groups.push(current);
                current = [sorted[i]];
              } else {
                current.push(sorted[i]);
              }
            }
            groups.push(current);
            return groups;
          };

          const blocksToRender = [];
          seasonsOrdered.forEach((seasonMatches, idx) => {
            let displayMatches = selYr ? seasonMatches.filter((m) => matchYear(m) === selYr) : seasonMatches;
            if (displayMatches.length === 0) return;
            const seasonFirstDate = seasonMatches.reduce((min, m) => (!min || m.date < min ? m.date : min), null);
            const seasonLastDate = seasonMatches.reduce((max, m) => (!max || m.date > max ? m.date : max), null);
            const seasonFirstMo = seasonFirstDate ? new Date(seasonFirstDate).getMonth() : -1;
            const seasonLastMo = seasonLastDate ? new Date(seasonLastDate).getMonth() : -1;
            const isPartialStart = seasonFirstMo >= 7 && seasonFirstMo <= 9 && seasonFirstDate && seasonLastDate && seasonFirstDate.slice(0, 4) === seasonLastDate.slice(0, 4) && seasonLastMo >= 9 && seasonLastMo <= 11;
            const isPartialEnd = seasonFirstMo >= 0 && seasonFirstMo <= 5 && seasonLastMo >= 0 && seasonLastMo <= 5 && seasonFirstDate && seasonLastDate && seasonFirstDate.slice(0, 4) === seasonLastDate.slice(0, 4);
            const seasonMetaKey = `${seasonFirstDate || ''}|${seasonLastDate || ''}`;
            const isSeasonClosed = seasonBoundaryMeta.get(seasonMetaKey)?.isSeasonClosed ?? false;
            const startSeasonLabel = formatSeasonLabel(seasonFirstDate, seasonLastDate, {
              isPartialStart,
              isPartialEnd,
              useActualDetectedEnd: true,
            });
            const endSeasonLabel = formatSeasonLabel(seasonFirstDate, seasonLastDate, { isPartialStart, isPartialEnd });
            const matchedDetectedRange = (() => {
              if (!seasonFirstDate || !seasonLastDate || detectedSeasonRanges.length === 0) return null;
              const seasonFirstIso = String(seasonFirstDate).slice(0, 10);
              const seasonLastIso = String(seasonLastDate).slice(0, 10);
              const toUtcMs = (iso) => new Date(`${iso}T00:00:00Z`).getTime();
              const blockStartMs = toUtcMs(seasonFirstIso);
              const blockEndMs = toUtcMs(seasonLastIso);
              let best = null;
              let bestOverlapMs = -1;
              detectedSeasonRanges.forEach((range) => {
                const rangeStartMs = toUtcMs(range.startDate);
                const rangeEndMs = toUtcMs(range.endDate);
                const overlapStart = Math.max(blockStartMs, rangeStartMs);
                const overlapEnd = Math.min(blockEndMs, rangeEndMs);
                const overlapMs = Math.max(0, overlapEnd - overlapStart);
                if (overlapMs > bestOverlapMs) {
                  bestOverlapMs = overlapMs;
                  best = range;
                }
              });
              return best;
            })();
            const seasonIsSameYear = Boolean(
              seasonFirstDate &&
              seasonLastDate &&
              String(seasonFirstDate).slice(0, 4) === String(seasonLastDate).slice(0, 4)
            );
            const subBlocks = [displayMatches];
            subBlocks.forEach((subMatches, subIdx) => {
              const displayFirstDate = subMatches.reduce((min, m) => (!min || m.date < min ? m.date : min), null);
              const displayLastDate = subMatches.reduce((max, m) => (!max || m.date > max ? m.date : max), null);
              const includesSeasonStart = Boolean(displayFirstDate && seasonFirstDate && displayFirstDate === seasonFirstDate);
              const includesSeasonEnd = Boolean(
                displayLastDate &&
                seasonLastDate &&
                displayLastDate === seasonLastDate &&
                isSeasonClosed
              );
              blocksToRender.push({
                seasonMatches,
                subMatches,
                startSeasonLabel,
                endSeasonLabel,
                includesSeasonStart,
                includesSeasonEnd,
                seasonIsSameYear,
                idx,
                subIdx,
                displayFirstDate,
                matchedDetectedRange,
              });
            });
          });

          blocksToRender.sort((a, b) => (b.displayFirstDate || '').localeCompare(a.displayFirstDate || ''));
          const hasAnySeasonStartBlock = blocksToRender.some((b) => b.includesSeasonStart);

          return blocksToRender.map(({
            seasonMatches,
            subMatches,
            startSeasonLabel,
            endSeasonLabel,
            includesSeasonStart,
            includesSeasonEnd,
            seasonIsSameYear,
            idx,
            subIdx,
            displayFirstDate,
            matchedDetectedRange,
          }, blockIdx) => {
            const displayYear = subMatches.length > 0 ? matchYear(subMatches[0]) : null;
            const roundEntriesRaw = buildRoundEntriesForSeason(seasonMatches);
            const roundEntries = roundEntriesRaw
              .map((re) => ({
                ...re,
                matches: displayYear ? re.matches.filter((m) => matchYear(m) === displayYear) : re.matches,
              }))
              .filter((re) => re.matches.length > 0);
            const subMatchIds = new Set(subMatches.map((m) => m.match_id ?? `${(m.date || '').slice(0, 10)}-${m.home_team}-${m.away_team}`));
            const roundEntriesFiltered = roundEntries
              .map((re) => ({ ...re, matches: re.matches.filter((m) => subMatchIds.has(m.match_id ?? `${(m.date || '').slice(0, 10)}-${m.home_team}-${m.away_team}`)) }))
              .filter((re) => re.matches.length > 0);
            const suppressSeasonHeader = shouldSuppressPremiershipShortSeasonHeader(
              seasonMatches.reduce((min, m) => (!min || m.date < min ? m.date : min), null),
              seasonMatches.reduce((max, m) => (!max || m.date > max ? m.date : max), null),
            );
            const shouldShowStartHeader = includesSeasonStart && roundEntriesFiltered.length > 0 && !suppressSeasonHeader;
            const displayLastIso = subMatches.reduce((max, m) => (!max || m.date > max ? m.date : max), null)?.slice(0, 10) || '';
            const reachesDetectedSeasonEnd = Boolean(
              !matchedDetectedRange ||
              (displayLastIso && displayLastIso >= matchedDetectedRange.endDate)
            );
            // Top block can show End only for same-year seasons (short tournaments).
            const shouldShowEndHeader =
              includesSeasonEnd &&
              roundEntriesFiltered.length > 0 &&
              reachesDetectedSeasonEnd &&
              !suppressSeasonHeader &&
              (blockIdx > 0 || seasonIsSameYear || !hasAnySeasonStartBlock);

            return (
              <React.Fragment key={`season-${idx}-${subIdx}-${displayFirstDate}`}>
              <Box sx={{ mb: blockIdx < blocksToRender.length - 1 ? 0 : 4 }}>
                {roundEntriesFiltered.length === 0 && (
                  <Paper elevation={0} sx={{ p: 3, borderRadius: 3, background: 'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(0,0,0,0.10) 100%)', border: `1px solid ${LUX.border}`, mb: 2 }}>
                    <Typography sx={{ color: LUX.text, fontWeight: 900, mb: 0.35 }}>No completed matches</Typography>
                  </Paper>
                )}
                {roundEntriesFiltered.map(({ key: gk, label: gl, matches }, roundIdx) => {
                  if (!matches?.length) return null;
                  const orderedMatches = [...matches].sort((a, b) => (b.date || '').localeCompare(a.date || ''));
                  const accordionKey = `block-${blockIdx}-${gk}`;
                  const ie = expandedWeeks.has(accordionKey);
                  const dates = matches.map((m) => m.date).filter(Boolean).sort();
                  const fmt = (d) => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  const dl = dates.length ? (dates[0] === dates[dates.length - 1] ? fmt(dates[0]) : `${fmt(dates[0])} – ${fmt(dates[dates.length - 1])}`) : '';
                  return (
                    <React.Fragment key={accordionKey}>
                      {shouldShowEndHeader && roundIdx === 0 && (
                        <SeasonSectionHeader
                          label={endSeasonLabel}
                          variant="end"
                          placement={blockIdx > 0 ? 'afterDivider' : 'default'}
                        />
                      )}
                      <Accordion
                      expanded={ie}
                      onChange={() => handleWeekToggle(accordionKey)}
                      sx={{
                        mb: 2,
                        background: 'linear-gradient(180deg, rgba(255,255,255,0.055) 0%, rgba(0,0,0,0.10) 100%)',
                        border: `1px solid ${ie ? 'rgba(251,191,36,0.20)' : LUX.border}`,
                        borderRadius: '16px !important',
                        '&:before': { display: 'none' },
                        '&.Mui-expanded': { background: 'linear-gradient(180deg, rgba(255,255,255,0.07) 0%, rgba(0,0,0,0.14) 100%)' },
                        transition: 'border-color 160ms ease, background 160ms ease',
                      }}
                    >
                      <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: LUX.gold }} />} sx={{ '& .MuiAccordionSummary-content': { alignItems: 'center' } }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, width: '100%', flexWrap: 'wrap', minWidth: 0 }}>
                          <Typography variant="h6" sx={{ color: 'rgba(255,255,255,0.95)', fontWeight: 1000, minWidth: 0, flex: '0 1 auto', fontSize: { xs: '1.05rem', sm: '1.25rem' } }}>{gl}</Typography>
                          <Chip label={`${orderedMatches.length} match${orderedMatches.length !== 1 ? 'es' : ''}`} size="small" sx={{ backgroundColor: 'rgba(251,191,36,0.12)', color: LUX.gold, fontWeight: 900, border: '1px solid rgba(251,191,36,0.18)' }} />
                          {dl && <Typography variant="body2" sx={{ color: '#9ca3af', ml: { xs: 0, sm: 'auto' }, flexBasis: { xs: '100%', sm: 'auto' }, textAlign: { xs: 'left', sm: 'right' }, fontSize: { xs: '0.82rem', sm: '0.88rem' } }}>{dl}</Typography>}
                        </Box>
                      </AccordionSummary>
                      <AccordionDetails
                        sx={{
                          px: { xs: 1, sm: 2 },
                          pt: { xs: 0, sm: 1 },
                          pb: { xs: 1.5, sm: 2 },
                          display: 'flex',
                          justifyContent: 'center',
                          overflowX: 'hidden',
                        }}
                      >
                        <Grid
                          container
                          spacing={{ xs: 1.75, sm: 2 }}
                          justifyContent="center"
                          sx={{ width: '100%', mx: 0, my: 0 }}
                        >
                      {orderedMatches.map((match, mi) => (
                            <Grid
                              item
                              xs={12}
                              sm={12}
                              md={4}
                              key={match.match_id ?? `${(match.date || '').slice(0, 10)}-${match.home_team}-${match.away_team}-${mi}`}
                          sx={{ display: 'flex', justifyContent: 'stretch', alignItems: 'stretch' }}
                            >
                              <MatchCard match={match} />
                            </Grid>
                          ))}
                        </Grid>
                      </AccordionDetails>
                    </Accordion>
                    </React.Fragment>
                  );
                })}
                {shouldShowStartHeader && (
                  <SeasonSectionHeader
                    label={startSeasonLabel}
                    variant="start"
                    placement={blockIdx < blocksToRender.length - 1 ? 'beforeDivider' : 'default'}
                  />
                )}
              </Box>
              {blockIdx < blocksToRender.length - 1 && <SeasonBlockDivider />}
              </React.Fragment>
            );
          });
        }

        return (selectedYear ? [selectedYear] : years).map((year) => {
        const yearData = data.matches_by_year_week[year];
        if (!yearData) {
          return (
            <Box key={year} sx={{ mb: 4 }}>
              <Typography
                variant="h4"
                sx={{
                  mb: 3,
                  color: '#fafafa',
                  fontWeight: 700,
                  fontSize: { xs: '1.35rem', sm: '2.1rem' },
                  pb: 2,
                  borderBottom: '2px solid rgba(16, 185, 129, 0.3)',
                }}
              >
                {year}
              </Typography>
              <Paper
                elevation={0}
                sx={{
                  p: 3,
                  borderRadius: 3,
                  background: 'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(0,0,0,0.10) 100%)',
                  border: `1px solid ${LUX.border}`,
                }}
              >
                <Typography sx={{ color: LUX.text, fontWeight: 900, mb: 0.35 }}>
                  No results available for {year} yet
                </Typography>
                <Typography sx={{ color: LUX.sub }}>
                  Fixtures are scheduled, but final scores are not available yet. Check back after matches finish.
                </Typography>
              </Paper>
            </Box>
          );
        }

        const allMatches = filterSuppressedMatches(Object.values(yearData).flat());
        const prevYear = year ? String(Number(year) - 1) : null;
        const prevYearData = prevYear ? (data.matches_by_year_week || {})[prevYear] : null;
        const prevYearMatches = prevYearData ? filterSuppressedMatches(Object.values(prevYearData).flat()) : [];
        const yearMerged = [...prevYearMatches, ...allMatches].filter((m) => m.date);
        const yearSeenIds = new Set();
        const combined = yearMerged
          .filter((m) => {
            const id = m.match_id ?? `${(m.date || '').slice(0, 10)}-${m.home_team || ''}-${m.away_team || ''}`;
            if (yearSeenIds.has(id)) return false;
            yearSeenIds.add(id);
            return true;
          })
          .sort((a, b) => (a.date || '').localeCompare(b.date || ''));
        const yearSeasons = splitIntoSeasons(combined).filter((s) => s.some((m) => String((m.year || (m.date || '').slice(0, 4))) === year)).reverse();

        return (
          <Box key={year} sx={{ mb: 4 }}>
            <Typography
              variant="h4"
              sx={{
                mb: 3,
                color: '#fafafa',
                fontWeight: 700,
                fontSize: { xs: '1.35rem', sm: '2.1rem' },
                pb: 2,
                borderBottom: '2px solid rgba(16, 185, 129, 0.3)',
              }}
            >
              {year}
            </Typography>

            {yearSeasons.length === 0 && (
              <Paper
                elevation={0}
                sx={{
                  p: 3,
                  borderRadius: 3,
                  background: 'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(0,0,0,0.10) 100%)',
                  border: `1px solid ${LUX.border}`,
                  mb: 2,
                }}
              >
                <Typography sx={{ color: LUX.text, fontWeight: 900, mb: 0.35 }}>
                  No results available for {year} yet
                </Typography>
                <Typography sx={{ color: LUX.sub }}>
                  Fixtures are scheduled, but final scores are not available yet. Check back after matches finish.
                </Typography>
              </Paper>
            )}

            {yearSeasons.map((seasonMatches, sIdx) => {
              const displayMatches = seasonMatches.filter((m) => matchYear(m) === year);
              if (displayMatches.length === 0) return null;
              const seasonFirstDate = seasonMatches.reduce((min, m) => (!min || m.date < min ? m.date : min), null);
              const seasonLastDate = seasonMatches.reduce((max, m) => (!max || m.date > max ? m.date : max), null);
              const firstMo = seasonFirstDate ? new Date(seasonFirstDate).getMonth() : -1;
              const lastMo = seasonLastDate ? new Date(seasonLastDate).getMonth() : -1;
              const isStartBlock = firstMo >= 6 && firstMo <= 11;
              const isEndBlock = lastMo >= 3 && lastMo <= 5;
              const isPartialStart = isStartBlock && sIdx === 0 && firstMo >= 7 && firstMo <= 9 && seasonFirstDate && seasonLastDate && seasonFirstDate.slice(0, 4) === seasonLastDate.slice(0, 4);
              const isPartialEnd = isEndBlock && lastMo >= 0 && lastMo <= 5 && seasonFirstDate && seasonLastDate && seasonFirstDate.slice(0, 4) === seasonLastDate.slice(0, 4);
              const startSeasonLabel = formatSeasonLabel(seasonFirstDate, seasonLastDate, {
                isPartialStart,
                isPartialEnd,
                useActualDetectedEnd: true,
              });
              const endSeasonLabel = formatSeasonLabel(seasonFirstDate, seasonLastDate, { isPartialStart, isPartialEnd });
              const blockVariant = isEndBlock ? 'end' : 'start';
              const roundEntriesRaw = buildRoundEntriesForSeason(seasonMatches);
              const roundEntries = roundEntriesRaw
                .map((re) => ({ ...re, matches: re.matches.filter((m) => matchYear(m) === year) }))
                .filter((re) => re.matches.length > 0);
              const hasNewerSeason = sIdx > 0;
              const suppressSeasonHeader = shouldSuppressPremiershipShortSeasonHeader(seasonFirstDate, seasonLastDate);
              const shouldShowStartHeader = roundEntries.length > 0 && !suppressSeasonHeader;
              const isSameYearSeason = Boolean(
                seasonFirstDate &&
                seasonLastDate &&
                String(seasonFirstDate).slice(0, 4) === String(seasonLastDate).slice(0, 4)
              );
              // Top block can show End only for same-year seasons (short tournaments).
              const shouldShowEndHeader =
                roundEntries.length > 0 &&
                isSeasonClosedByGap(seasonLastDate, hasNewerSeason) &&
                !suppressSeasonHeader &&
                (sIdx > 0 || isSameYearSeason);
              return (
                <React.Fragment key={`${year}-s${sIdx}`}>
                <Box sx={{ mb: sIdx < yearSeasons.length - 1 ? 0 : 0 }}>
                  {roundEntries.map(({ key: groupKey, label: groupLabel, matches }, roundIdx) => {
              if (!matches || matches.length === 0) return null;
              const orderedMatches = [...matches].sort((a, b) => (b.date || '').localeCompare(a.date || ''));

              const isExpanded = expandedWeeks.has(groupKey);
              const showEndHeaderThisRound = shouldShowEndHeader && roundIdx === 0;

              return (
                <React.Fragment key={groupKey}>
                {showEndHeaderThisRound && (
                  <SeasonSectionHeader
                    label={endSeasonLabel}
                    variant="end"
                    placement={sIdx > 0 ? 'afterDivider' : 'default'}
                  />
                )}
                <Accordion
                  expanded={isExpanded}
                  onChange={() => handleWeekToggle(groupKey)}
                  sx={{
                    mb: 2,
                    background: 'linear-gradient(180deg, rgba(255,255,255,0.055) 0%, rgba(0,0,0,0.10) 100%)',
                    border: `1px solid ${isExpanded ? 'rgba(251,191,36,0.20)' : LUX.border}`,
                    borderRadius: '16px !important',
                    '&:before': { display: 'none' },
                    '&.Mui-expanded': {
                      background: 'linear-gradient(180deg, rgba(255,255,255,0.07) 0%, rgba(0,0,0,0.14) 100%)',
                    },
                    transition: 'border-color 160ms ease, background 160ms ease',
                  }}
                >
                  <AccordionSummary
                    expandIcon={<ExpandMoreIcon sx={{ color: LUX.gold }} />}
                    sx={{
                      '& .MuiAccordionSummary-content': {
                        alignItems: 'center',
                      },
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, width: '100%', flexWrap: 'wrap', minWidth: 0 }}>
                      <Typography
                        variant="h6"
                        sx={{
                          color: 'rgba(255,255,255,0.95)',
                          fontWeight: 1000,
                          minWidth: 0,
                          flex: '0 1 auto',
                          fontSize: { xs: '1.05rem', sm: '1.25rem' },
                        }}
                      >
                        {groupLabel}
                      </Typography>
                      <Chip
                        label={`${orderedMatches.length} match${orderedMatches.length !== 1 ? 'es' : ''}`}
                        size="small"
                        sx={{
                          backgroundColor: 'rgba(251,191,36,0.12)',
                          color: LUX.gold,
                          fontWeight: 900,
                          border: '1px solid rgba(251,191,36,0.18)',
                        }}
                      />
                      {orderedMatches[0]?.date && (() => {
                        const dates = orderedMatches.map((m) => m.date).filter(Boolean).sort();
                        const first = dates[0];
                        const last = dates[dates.length - 1];
                        const fmt = (d) => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                        const dateLabel = first === last ? fmt(first) : `${fmt(first)} – ${fmt(last)}`;
                        return (
                          <Typography
                            variant="body2"
                            sx={{
                              color: '#9ca3af',
                              ml: { xs: 0, sm: 'auto' },
                              flexBasis: { xs: '100%', sm: 'auto' },
                              textAlign: { xs: 'left', sm: 'right' },
                              fontSize: { xs: '0.82rem', sm: '0.88rem' },
                            }}
                          >
                            {dateLabel}
                          </Typography>
                        );
                      })()}
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails
                    sx={{
                      px: { xs: 1, sm: 2 },
                      pt: { xs: 0, sm: 1 },
                      pb: { xs: 1.5, sm: 2 },
                      display: 'flex',
                      justifyContent: 'center',
                      overflowX: 'hidden',
                    }}
                  >
                    <Grid
                      container
                      spacing={{ xs: 1.75, sm: 2 }}
                      justifyContent="center"
                      sx={{ width: '100%', mx: 0, my: 0 }}
                    >
                      {orderedMatches.map((match) => (
                        <Grid item xs={12} sm={12} md={4} key={match.match_id} sx={{ display: 'flex', justifyContent: 'stretch', alignItems: 'stretch' }}>
                          <MatchCard match={match} />
                        </Grid>
                      ))}
                    </Grid>
                  </AccordionDetails>
                </Accordion>
                </React.Fragment>
              );
            })}
                {shouldShowStartHeader && (
                  <SeasonSectionHeader
                    label={startSeasonLabel}
                    variant="start"
                    placement={yearSeasons.length > 1 && sIdx < yearSeasons.length - 1 ? 'beforeDivider' : 'default'}
                  />
                )}
                </Box>
                {yearSeasons.length > 1 && sIdx < yearSeasons.length - 1 && <SeasonBlockDivider />}
                </React.Fragment>
              );
            })}
          </Box>
        );
      });
    })()}
    </Box>
  );
};

const MatchCard = ({ match }) => {
  const {
    date,
    kickoff_at,
    went_to_extra_time,
    home_team,
    away_team,
    actual_home_score,
    actual_away_score,
    predicted_home_score,
    predicted_away_score,
    predicted_winner,
    prediction_correct,
    prediction_confidence,
    prediction_error,
    league_name,
  } = match;

  const actualWinner = actual_home_score > actual_away_score ? home_team : actual_away_score > actual_home_score ? away_team : 'Draw';
  const predictedWinnerTeam = predicted_winner === 'Home' ? home_team : predicted_winner === 'Away' ? away_team : 'Draw';
  const gold = '#fbbf24';
  const displayDateRaw = kickoff_at || date;
  const showTime = hasMeaningfulTime(displayDateRaw);
  const formattedKickoffDateYMD = formatSASTDateYMD(displayDateRaw);
  const formattedKickoffDate = formattedKickoffDateYMD
    ? new Date(`${formattedKickoffDateYMD}T00:00:00`).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : '';
  const formattedKickoffTime = showTime ? formatSASTTimePM(displayDateRaw) : '';

  const isWin = prediction_correct === true;
  const isLoss = prediction_correct === false;
  const accent = isWin ? '#fbbf24' : isLoss ? '#ef4444' : null;
  const accentSoft = isWin ? 'rgba(251,191,36,' : isLoss ? 'rgba(239,68,68,' : null;

  return (
    <Card
      sx={{
        width: '100%',
        maxWidth: '100%',
        mx: 0,
        transform: 'none',
        position: 'relative',
        overflow: 'hidden',
        background: isWin
          ? 'linear-gradient(160deg, #3d3418 0%, #2a2410 30%, #1c1a0e 60%, #151308 100%)'
          : isLoss
            ? 'linear-gradient(160deg, #2e1416 0%, #241012 30%, #1a0c0e 60%, #120809 100%)'
            : 'linear-gradient(180deg, rgba(255,255,255,0.055) 0%, rgba(0,0,0,0.16) 100%)',
        borderRadius: 3,
        border: isWin
          ? '1px solid rgba(251,191,36,0.25)'
          : isLoss
            ? '1px solid rgba(239,68,68,0.22)'
            : '1px solid rgba(255,255,255,0.08)',
        borderLeft: accent ? `4px solid ${accent}` : '1px solid rgba(255,255,255,0.08)',
        transition: 'transform 220ms ease, box-shadow 220ms ease',
        boxShadow: isWin
          ? '0 4px 24px rgba(251,191,36,0.10), 0 8px 28px rgba(0,0,0,0.20)'
          : isLoss
            ? '0 4px 24px rgba(239,68,68,0.08), 0 8px 28px rgba(0,0,0,0.20)'
            : '0 8px 28px rgba(0,0,0,0.16)',
        '&::before': accent ? {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '2px',
          background: `linear-gradient(90deg, ${accent} 0%, ${accentSoft}0.4) 30%, transparent 65%)`,
          pointerEvents: 'none',
          zIndex: 3,
        } : {},
        '&::after': accent ? {
          content: '""',
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '1px',
          background: `linear-gradient(90deg, ${accentSoft}0.5) 0%, ${accentSoft}0.15) 30%, transparent 55%)`,
          pointerEvents: 'none',
          zIndex: 3,
        } : {},
        '&:hover': {
          transform: 'translateY(-3px) scale(1.008)',
          boxShadow: isWin
            ? '0 0 28px rgba(251,191,36,0.16), 0 18px 44px rgba(0,0,0,0.28)'
            : isLoss
              ? '0 0 28px rgba(239,68,68,0.12), 0 18px 44px rgba(0,0,0,0.28)'
              : '0 14px 40px rgba(0,0,0,0.26)',
        },
      }}
    >
      {/* Corner ribbon triangle */}
      {accent && (
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            right: 0,
            width: 0,
            height: 0,
            borderStyle: 'solid',
            borderWidth: '0 40px 40px 0',
            borderColor: `transparent ${accent} transparent transparent`,
            opacity: 0.30,
            zIndex: 4,
          }}
        />
      )}

      {/* Diagonal stripe texture — subtle background pattern */}
      {accent && (
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            opacity: 0.045,
            backgroundImage: `repeating-linear-gradient(
              -45deg,
              ${accent},
              ${accent} 1px,
              transparent 1px,
              transparent 8px
            )`,
            pointerEvents: 'none',
            zIndex: 0,
          }}
        />
      )}

      {/* Inner glow from left bar */}
      {accent && (
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            bottom: 0,
            width: '50%',
            background: `linear-gradient(90deg, ${accentSoft}0.12) 0%, transparent 100%)`,
            pointerEvents: 'none',
            zIndex: 0,
          }}
        />
      )}

      <CardContent
        sx={{
          position: 'relative',
          zIndex: 1,
          p: { xs: 1.1, sm: 2 },
          pl: { xs: accent ? 1.5 : 1.1, sm: accent ? 2.25 : 2 },
          pr: { xs: accent ? 1.5 : 1.1, sm: accent ? 2.25 : 2 },
        }}
      >
        {/* Header row */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: { xs: 0.85, sm: 1.5 }, gap: 1 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, minWidth: 0 }}>
            <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.70)', fontWeight: 700, fontSize: { xs: '0.7rem', sm: '0.86rem' } }}>
              {formattedKickoffDate}
              {showTime ? ` • ${formattedKickoffTime}` : ''}
            </Typography>
            {went_to_extra_time ? (
              <Chip
                size="small"
                label="AET"
                sx={{
                  height: 18,
                  width: 'fit-content',
                  fontSize: '0.68rem',
                  fontWeight: 900,
                  backgroundColor: 'rgba(245,158,11,0.16)',
                  color: '#fde68a',
                  border: '1px solid rgba(245,158,11,0.22)',
                }}
              />
            ) : null}
          </Box>
          {prediction_correct !== null && (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 28,
                height: 28,
                borderRadius: '50%',
                background: isWin
                  ? 'radial-gradient(circle, rgba(251,191,36,0.18) 0%, transparent 70%)'
                  : 'radial-gradient(circle, rgba(239,68,68,0.15) 0%, transparent 70%)',
              }}
            >
              {prediction_correct ? (
                <CheckCircleIcon sx={{ color: gold, fontSize: { xs: 18, sm: 20 } }} />
              ) : (
                <CancelIcon sx={{ color: '#ef4444', fontSize: { xs: 18, sm: 20 } }} />
              )}
            </Box>
          )}
        </Box>

        {/* Teams and Scores */}
        <Box
          sx={{
            mb: { xs: 1, sm: 2 },
            width: '100%',
            textAlign: { xs: 'center', sm: 'left' },
            display: 'flex',
            flexDirection: 'column',
            alignItems: { xs: 'center', sm: 'stretch' },
          }}
        >
          {[
            { team: home_team, actual: actual_home_score, predicted: predicted_home_score },
            { team: away_team, actual: actual_away_score, predicted: predicted_away_score },
          ].map((row, i) => (
            <Box
              key={i}
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: 'auto auto auto', sm: '1fr auto auto' },
                width: { xs: 'fit-content', sm: '100%' },
                mx: { xs: 'auto', sm: 0 },
                justifyContent: { xs: 'center', sm: 'stretch' },
                alignItems: 'center',
                minWidth: 0,
                mb: i === 0 ? 0.75 : 0,
                columnGap: { xs: 0.55, sm: 0.5 },
                maxWidth: { xs: 'calc(100% - 4px)', sm: '100%' },
              }}
            >
              <Typography
                sx={{
                  color: 'rgba(255,255,255,0.96)',
                  fontWeight: 800,
                  minWidth: 0,
                  fontSize: { xs: '0.88rem', sm: '1rem' },
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  textAlign: { xs: 'center', sm: 'left' },
                  maxWidth: { xs: '60vw', sm: 'none' },
                }}
              >
                {row.team}
              </Typography>
              <Typography component="span" sx={{ color: gold, fontWeight: 1000, fontSize: { xs: '1rem', sm: '1.25rem' }, lineHeight: 1, ml: { xs: 0, sm: 1 }, flexShrink: 0, textAlign: 'center' }}>
                {row.actual ?? '?'}
              </Typography>
              {row.predicted !== null && (
                <Typography component="span" sx={{ color: '#9ca3af', fontSize: { xs: '0.7rem', sm: '0.9rem' }, lineHeight: 1, ml: { xs: 0, sm: 0.5 }, flexShrink: 0, textAlign: 'center' }}>
                  ({Math.round(row.predicted)})
                </Typography>
              )}
            </Box>
          ))}
        </Box>

        {/* Divider — styled to match accent */}
        <Divider
          sx={{
            my: { xs: 0.9, sm: 1.5 },
            borderColor: accent ? `${accentSoft}0.12)` : 'rgba(255,255,255,0.08)',
            borderStyle: accent ? 'dashed' : 'solid',
          }}
        />

        {/* Prediction Info */}
        {predicted_winner && predicted_winner !== 'Error' && (
          <Box sx={{ display: 'flex', flexDirection: 'column', width: '100%', gap: 0.35 }}>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.55)', fontWeight: 700, letterSpacing: 1.2, fontSize: { xs: '0.58rem', sm: '0.68rem' }, textTransform: 'uppercase', alignSelf: 'flex-start' }}>
              AI predicted
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, width: '100%' }}>
              <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: { xs: '0.82rem', sm: '0.95rem' } }}>
                {predictedWinnerTeam}
              </Typography>
              {prediction_confidence && (
                <Chip
                  label={`${(prediction_confidence * 100).toFixed(0)}%`}
                  size="small"
                  sx={{
                    height: { xs: 18, sm: 20 },
                    fontSize: { xs: '0.62rem', sm: '0.7rem' },
                    fontWeight: 900,
                    backgroundColor: accent ? `${accentSoft}0.12)` : 'rgba(251,191,36,0.14)',
                    color: accent || gold,
                    border: `1px solid ${accent ? `${accentSoft}0.22)` : 'rgba(251,191,36,0.18)'}`,
                    borderRadius: '6px',
                  }}
                />
              )}
            </Box>
            {prediction_error !== null && (
              <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.50)', fontSize: { xs: '0.62rem', sm: '0.74rem' }, textAlign: 'center', width: '100%' }}>
                Score error: {prediction_error.toFixed(1)} points
              </Typography>
            )}
          </Box>
        )}

        {predicted_winner === 'Error' && (
          <Typography variant="caption" sx={{ color: '#ef4444' }}>
            Could not generate prediction
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

export default HistoricalPredictions;

