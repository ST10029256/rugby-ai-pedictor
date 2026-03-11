import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Chip, IconButton, Link, Paper, Stack, Typography, useMediaQuery } from '@mui/material';
import SportsIcon from '@mui/icons-material/Sports';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import RugbyBallLoader from './RugbyBallLoader';
import { getNewsFeed } from '../firebase';

const LEAGUE_CONFIGS = {
  4986: { name: 'Rugby Championship' },
  4446: { name: 'United Rugby Championship' },
  5069: { name: 'Currie Cup' },
  4574: { name: 'Rugby World Cup' },
  4551: { name: 'Super Rugby' },
  4430: { name: 'French Top 14' },
  4414: { name: 'English Premiership Rugby' },
  4714: { name: 'Six Nations Championship' },
  5479: { name: 'Rugby Union International Friendlies' },
};

const URL_PATTERN = /(https?:\/\/[^\s]+)/g;
const PLAYABLE_VIDEO_EXT_PATTERN = /\.(mp4|webm|ogg|m3u8)(\?.*)?$/i;
const IMAGE_EXT_PATTERN = /\.(jpg|jpeg|png|gif|webp|avif)(\?.*)?$/i;
const URL_EXACT_PATTERN = /^https?:\/\/[^\s]+$/i;
const DEFAULT_AVATAR_URL = 'https://abs.twimg.com/sticky/default_profile_images/default_profile_400x400.png';
const VERIFIED_BADGE_URL = 'https://abs.twimg.com/icons/apple-touch-icon-192x192.png';
const VIDEO_PROXY_ENDPOINT = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/proxy_video_http';

function RugbyPoleGlyph({ width = 22, height = 36 } = {}) {
  const sideInset = Math.max(1, Math.round(width * 0.08));
  const poleStroke = Math.max(2, Math.round(width * 0.12));
  const postWidth = poleStroke;
  const postHeight = Math.max(14, Math.round(height * 0.9));
  const crossbarHeight = poleStroke;
  const crossbarTop = Math.round(height * 0.54);
  return (
    <Box sx={{ position: 'relative', width, height, flexShrink: 0 }}>
      <Box
        sx={{
          position: 'absolute',
          left: sideInset,
          bottom: 0,
          width: postWidth,
          height: postHeight,
          borderRadius: 1,
          background: `linear-gradient(180deg, 
            #ffffff 0%, 
            #f8f9fa 20%, 
            #ffffff 40%,
            #f0f0f0 60%,
            #ffffff 80%,
            #e8e8e8 100%
          )`,
          boxShadow: `
            0 0 6px rgba(255, 255, 255, 0.65),
            inset 1px 0 2px rgba(255, 255, 255, 0.9),
            inset -1px 0 2px rgba(0, 0, 0, 0.12),
            0 1px 3px rgba(0, 0, 0, 0.25)
          `,
          border: '1px solid rgba(255, 255, 255, 0.9)',
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          right: sideInset,
          bottom: 0,
          width: postWidth,
          height: postHeight,
          borderRadius: 1,
          background: `linear-gradient(180deg, 
            #ffffff 0%, 
            #f8f9fa 20%, 
            #ffffff 40%,
            #f0f0f0 60%,
            #ffffff 80%,
            #e8e8e8 100%
          )`,
          boxShadow: `
            0 0 6px rgba(255, 255, 255, 0.65),
            inset 1px 0 2px rgba(255, 255, 255, 0.9),
            inset -1px 0 2px rgba(0, 0, 0, 0.12),
            0 1px 3px rgba(0, 0, 0, 0.25)
          `,
          border: '1px solid rgba(255, 255, 255, 0.9)',
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          left: sideInset,
          top: crossbarTop,
          width: `calc(100% - ${sideInset * 2}px)`,
          height: crossbarHeight,
          borderRadius: 1,
          background: `linear-gradient(90deg, 
            #ffffff 0%, 
            #f8f9fa 20%, 
            #ffffff 40%,
            #f0f0f0 60%,
            #ffffff 80%,
            #e8e8e8 100%
          )`,
          boxShadow: `
            0 0 6px rgba(255, 255, 255, 0.65),
            inset 0 1px 2px rgba(255, 255, 255, 0.9),
            inset 0 -1px 2px rgba(0, 0, 0, 0.12),
            0 1px 3px rgba(0, 0, 0, 0.25)
          `,
          border: '1px solid rgba(255, 255, 255, 0.9)',
        }}
      />
    </Box>
  );
}

function formatTimeAgo(timestamp) {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  if (!Number.isFinite(then)) return '';
  const diffMs = Math.max(0, now - then);
  const min = Math.floor(diffMs / 60000);
  const hr = Math.floor(min / 60);
  const day = Math.floor(hr / 24);
  if (min < 60) return `${min}m`;
  if (hr < 24) return `${hr}h`;
  if (day < 7) return `${day}d`;
  return new Date(timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function isLikelyVideoUrl(url) {
  if (!url) return false;
  const lowered = String(url).toLowerCase();
  return (
    PLAYABLE_VIDEO_EXT_PATTERN.test(lowered) ||
    lowered.includes('video.twimg.com') ||
    lowered.includes('/amplify_video/') ||
    lowered.includes('/ext_tw_video/')
  );
}

function shouldProxyVideoUrl(url) {
  if (!url) return false;
  const lowered = String(url).toLowerCase();
  return lowered.includes('video.twimg.com');
}

function buildPlayableVideoSrc(url) {
  if (!url) return null;
  if (!shouldProxyVideoUrl(url)) return url;
  return `${VIDEO_PROXY_ENDPOINT}?url=${encodeURIComponent(String(url))}`;
}

function getPlayableVideoSources(url) {
  if (!url) return [];
  const directSrc = String(url);
  const proxySrc = buildPlayableVideoSrc(url);
  const host = typeof window !== 'undefined'
    ? String(window.location?.hostname || '').toLowerCase()
    : '';
  const isLocalDevHost = host === 'localhost' || host === '127.0.0.1';
  const ordered = isLocalDevHost ? [directSrc, proxySrc] : [proxySrc, directSrc];
  return ordered.filter((value, index, arr) => value && arr.indexOf(value) === index);
}

function isTwitterUrl(value) {
  if (!value) return false;
  const lowered = String(value).toLowerCase();
  return lowered.includes('twitter.com/') || lowered.includes('x.com/');
}

function extractHandleFromUrl(value) {
  if (!value) return '';
  const m = String(value).match(/(?:twitter\.com|x\.com)\/([^/?#]+)/i);
  return m?.[1] || '';
}

function extractMediaUrl(value) {
  if (!value) return '';
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'object') {
    return String(
      value.url ||
      value.src ||
      value.media_url ||
      value.video_url ||
      value.playback_url ||
      ''
    ).trim();
  }
  return '';
}

function isLikelyImageUrl(url) {
  if (!url) return false;
  const lowered = String(url).toLowerCase();
  return IMAGE_EXT_PATTERN.test(lowered) || lowered.includes('/image/');
}

function parseResolutionFromUrl(url) {
  if (!url) return { width: 0, height: 0 };
  const value = String(url).toLowerCase();
  const resMatch = value.match(/\/(\d{2,5})x(\d{2,5})\//);
  if (resMatch) {
    return {
      width: Number(resMatch[1]) || 0,
      height: Number(resMatch[2]) || 0,
    };
  }
  return { width: 0, height: 0 };
}

function normalizeVideoCandidate(value) {
  const url = extractMediaUrl(value);
  const { width: parsedWidth, height: parsedHeight } = parseResolutionFromUrl(url);
  let bitrate = 0;
  let width = parsedWidth;
  let height = parsedHeight;

  if (value && typeof value === 'object') {
    bitrate = Number(
      value.bitrate ??
      value.bit_rate ??
      value.bandwidth ??
      value.max_bitrate ??
      0
    ) || 0;
    width = Number(value.width ?? value.w ?? width) || width;
    height = Number(value.height ?? value.h ?? height) || height;
  }

  if (!bitrate && url) {
    const q = String(url).match(/[?&](?:bitrate|br|bandwidth)=(\d+)/i);
    bitrate = q ? (Number(q[1]) || 0) : 0;
  }

  return { url, bitrate, width, height };
}

function getMediaCandidates(item) {
  const media = item?.media || {};
  const embedded = item?.embedded_content || {};
  const related = item?.related_stats || {};
  return [
    media.video_url,
    ...(Array.isArray(media?.image_urls) ? media.image_urls : []),
    ...(Array.isArray(media?.videos) ? media.videos : []),
    ...(Array.isArray(media?.images) ? media.images : []),
    ...(Array.isArray(media?.media_urls) ? media.media_urls : []),
    ...(Array.isArray(media?.video_variants) ? media.video_variants : []),
    embedded.video_url,
    embedded.media_url,
    embedded.image_url,
    embedded.thumbnail_url,
    embedded.poster_url,
    embedded.embed_url,
    embedded.url,
    item?.video_url,
    item?.media_url,
    item?.image_url,
    item?.thumbnail_url,
    related?.video_url,
    related?.media_url,
    related?.image_url,
    ...(Array.isArray(related?.media_urls) ? related.media_urls : []),
    ...(Array.isArray(related?.video_variants) ? related.video_variants : []),
    item?.url,
    ...String(item?.content || '').match(URL_PATTERN) || [],
  ].filter(Boolean);
}

function getPostMedia(item) {
  const candidates = getMediaCandidates(item);
  const videoCandidates = candidates
    .map((value) => normalizeVideoCandidate(value))
    .filter((candidate) => candidate.url && isLikelyVideoUrl(candidate.url))
    .filter((candidate, index, arr) => arr.findIndex((itemCandidate) => itemCandidate.url === candidate.url) === index)
    .sort((a, b) => {
      const bitrateDelta = (b.bitrate || 0) - (a.bitrate || 0);
      if (bitrateDelta !== 0) return bitrateDelta;
      const areaA = (a.width || 0) * (a.height || 0);
      const areaB = (b.width || 0) * (b.height || 0);
      return areaB - areaA;
    })
    .map((candidate) => candidate.url);
  const videoUrl = videoCandidates[0] || null;
  const imageUrls = candidates
    .map((value) => extractMediaUrl(value))
    .filter((v) => v && !isLikelyVideoUrl(v) && isLikelyImageUrl(v))
    .filter((v, i, arr) => arr.indexOf(v) === i)
    .slice(0, 4);
  return { videoUrl, imageUrls, videoCandidates };
}

function linkifyText(text) {
  const value = String(text || '');
  if (!value) return null;
  const parts = value.split(URL_PATTERN);
  const HASHTAG_PATTERN = /(#[A-Za-z][A-Za-z0-9_]*)/g;

  return parts.flatMap((part, idx) => {
    if (URL_EXACT_PATTERN.test(part)) {
      return [
        (
        <Link
          key={`link-${idx}`}
          href={part}
          target="_blank"
          rel="noopener noreferrer"
          underline="hover"
          sx={{ color: '#1d9bf0', wordBreak: 'break-all' }}
        >
          {part}
        </Link>
        ),
      ];
    }

    const hashtagParts = part.split(HASHTAG_PATTERN);
    return hashtagParts.map((segment, segmentIdx) => {
      if (/^#[A-Za-z][A-Za-z0-9_]*$/.test(segment)) {
        const tag = segment.replace(/^#/, '');
        return (
          <Link
            key={`hashtag-${idx}-${segmentIdx}`}
            href={`https://x.com/hashtag/${encodeURIComponent(tag)}`}
            target="_blank"
            rel="noopener noreferrer"
            underline="hover"
            sx={{ color: '#60a5fa', fontWeight: 700 }}
          >
            {segment}
          </Link>
        );
      }
      return <React.Fragment key={`text-${idx}-${segmentIdx}`}>{segment}</React.Fragment>;
    });
  });
}

function sanitizePostContent(text, { authorName = '', authorHandle = '' } = {}) {
  const value = String(text || '').replace(/\r\n/g, '\n').trim();
  if (!value) return '';

  const lines = value.split('\n');
  const normalizedAuthorName = String(authorName || '').trim().toLowerCase();
  const normalizedHandle = String(authorHandle || '').replace(/^@+/, '').trim().toLowerCase();
  const blockedHeaderNames = new Set(['verified', 'unverified', 'official']);
  let cursor = 0;

  // Remove duplicated tweet-style headers sometimes included in scraped content.
  while (cursor < lines.length) {
    const rawLine = String(lines[cursor] || '').trim();
    const normalized = rawLine.toLowerCase();

    if (!rawLine) {
      cursor += 1;
      continue;
    }
    if (blockedHeaderNames.has(normalized)) {
      cursor += 1;
      continue;
    }
    if (normalizedAuthorName && normalized === normalizedAuthorName) {
      cursor += 1;
      continue;
    }
    if (normalizedHandle && normalized === `@${normalizedHandle}`) {
      cursor += 1;
      continue;
    }
    if (/^[·•]\s*\d+\s*(m|h|d|w|mo|y)$/i.test(rawLine) || /^\d+\s*(m|h|d|w|mo|y)$/i.test(rawLine)) {
      cursor += 1;
      continue;
    }
    break;
  }

  return lines.slice(cursor).join('\n').trim();
}

function removeRedundantTrailingLinks(text, { openOnXUrl = '' } = {}) {
  let value = String(text || '').trim();
  if (!value || !openOnXUrl) return value;

  const normalizeUrl = (input) => {
    try {
      const parsed = new URL(String(input || '').trim());
      const host = parsed.hostname.toLowerCase().replace(/^www\./, '');
      return `${host}${parsed.pathname}${parsed.search}`.replace(/\/+$/, '');
    } catch {
      return String(input || '').trim().toLowerCase();
    }
  };

  const normalizedOpenOnX = normalizeUrl(openOnXUrl);
  const trailingUrlPattern = /^(.*?)(?:\s+)(https?:\/\/[^\s]+)\s*$/s;

  while (true) {
    const match = value.match(trailingUrlPattern);
    if (!match) break;

    const url = match[2];
    let shouldRemove = false;

    try {
      const host = new URL(url).hostname.toLowerCase().replace(/^www\./, '');
      if (host === 't.co') shouldRemove = true;
    } catch {
      // Ignore parsing failures and keep evaluating with normalized comparison.
    }

    if (normalizeUrl(url) === normalizedOpenOnX) shouldRemove = true;
    if (!shouldRemove) break;

    value = String(match[1] || '').trimEnd();
  }

  return value.trim();
}

const NewsFeed = ({ userPreferences = {}, leagueId = null, leagueName = null }) => {
  const [newsItems, setNewsItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failedVideoSrcs, setFailedVideoSrcs] = useState({});
  const [imageIndexByPost, setImageIndexByPost] = useState({});
  const [reelsMode, setReelsMode] = useState(false);
  const [activeReelIndex, setActiveReelIndex] = useState(0);
  const requestRunRef = useRef(0);
  const perLeagueCacheRef = useRef({});
  const touchStartXByPostRef = useRef({});
  const reelsScrollRef = useRef(null);
  const reelVideoRefs = useRef({});
  const isSmallScreen = useMediaQuery('(max-width:600px)');
  const isMobileReels = useMediaQuery('(max-width:768px)');

  const displayLeagueName = useMemo(() => {
    if (leagueName) return leagueName;
    if (leagueId && LEAGUE_CONFIGS[leagueId]) return LEAGUE_CONFIGS[leagueId].name;
    return leagueId ? `League ${leagueId}` : 'All Leagues';
  }, [leagueId, leagueName]);
  const displayLeagueChipLabel = useMemo(() => {
    if (!isSmallScreen) return displayLeagueName;
    if (displayLeagueName === 'United Rugby Championship') return 'URC';
    return displayLeagueName;
  }, [displayLeagueName, isSmallScreen]);

  const sortedItems = useMemo(() => {
    return [...newsItems].sort((a, b) => new Date(b?.timestamp || 0) - new Date(a?.timestamp || 0));
  }, [newsItems]);
  const followedTeamsKey = useMemo(
    () => JSON.stringify(Array.isArray(userPreferences?.followed_teams) ? userPreferences.followed_teams : []),
    [userPreferences?.followed_teams]
  );
  const followedLeaguesKey = useMemo(
    () => JSON.stringify(Array.isArray(userPreferences?.followed_leagues) ? userPreferences.followed_leagues : []),
    [userPreferences?.followed_leagues]
  );
  const followedTeams = useMemo(() => JSON.parse(followedTeamsKey), [followedTeamsKey]);
  const followedLeagues = useMemo(() => JSON.parse(followedLeaguesKey), [followedLeaguesKey]);
  const mediaReelItems = useMemo(() => {
    return sortedItems
      .map((item, index) => {
        const itemKey = item?.id || `${item?.timestamp}-${item?.title}-${index}`;
        const media = getPostMedia(item);
        const videoSources = media.videoCandidates
          .flatMap((candidateUrl) => getPlayableVideoSources(candidateUrl))
          .filter((src) => !failedVideoSrcs[src]);
        const videoSrc = videoSources[0] || null;
        const imageUrl = media.imageUrls[0] || null;
        const sourceUrl = item?.embedded_content?.url || item?.source_url || item?.url || null;
        const rawHandle = String(item?.author_handle || item?.source_handle || '').trim();
        const inferredHandle = extractHandleFromUrl(sourceUrl || '');
        const authorHandle = (rawHandle.replace(/^@+/, '') || inferredHandle || '').trim();
        const authorName = String(item?.author_name || item?.source_name || item?.publisher || '').trim()
          || (authorHandle ? `@${authorHandle}` : 'Rugby Source');
        const authorAvatar =
          item?.author_avatar ||
          item?.profile_image_url ||
          (authorHandle ? `https://unavatar.io/x/${authorHandle}` : DEFAULT_AVATAR_URL);
        const title = String(item?.title || '').trim();
        const content = removeRedundantTrailingLinks(
          sanitizePostContent(item?.content, { authorName, authorHandle }),
          { openOnXUrl: sourceUrl }
        );
        return {
          itemKey,
          item,
          videoSrc,
          imageUrl,
          authorName,
          authorHandle,
          authorAvatar,
          title,
          content,
        };
      })
      .filter((entry) => Boolean(entry.videoSrc || entry.imageUrl));
  }, [sortedItems, failedVideoSrcs]);

  useEffect(() => {
    if (!reelsMode) return;
    setActiveReelIndex(0);
    const id = requestAnimationFrame(() => {
      const container = reelsScrollRef.current;
      if (!container) return;
      container.scrollTo({ top: 0, behavior: 'auto' });
    });
    return () => cancelAnimationFrame(id);
  }, [reelsMode, mediaReelItems.length]);

  useEffect(() => {
    if (!isMobileReels && reelsMode) {
      setReelsMode(false);
    }
  }, [isMobileReels, reelsMode]);

  useEffect(() => {
    if (!reelsMode) return;
    mediaReelItems.forEach((_, idx) => {
      const videoEl = reelVideoRefs.current[idx];
      if (!videoEl) return;
      if (idx === activeReelIndex) {
        const playPromise = videoEl.play();
        if (playPromise && typeof playPromise.catch === 'function') {
          playPromise.catch(() => {});
        }
      } else {
        videoEl.pause();
      }
    });
  }, [reelsMode, activeReelIndex, mediaReelItems]);

  const markVideoSrcFailed = (videoSrc) => {
    if (!videoSrc) return;
    setFailedVideoSrcs((prev) => ({ ...prev, [videoSrc]: true }));
  };

  const normalizeIndex = (index, count) => {
    if (!count || count <= 0) return 0;
    return ((index % count) + count) % count;
  };

  const getActiveImageIndex = (postKey, count) => {
    const savedIndex = Number(imageIndexByPost[postKey] || 0);
    return normalizeIndex(savedIndex, count);
  };

  const setActiveImageIndex = (postKey, nextIndex, count) => {
    if (!postKey || !count) return;
    setImageIndexByPost((prev) => ({
      ...prev,
      [postKey]: normalizeIndex(nextIndex, count),
    }));
  };

  const goToNextImage = (postKey, count) => {
    const current = getActiveImageIndex(postKey, count);
    setActiveImageIndex(postKey, current + 1, count);
  };

  const goToPreviousImage = (postKey, count) => {
    const current = getActiveImageIndex(postKey, count);
    setActiveImageIndex(postKey, current - 1, count);
  };

  const handleImageTouchStart = (postKey, event) => {
    const point = event?.touches?.[0] || event?.changedTouches?.[0];
    touchStartXByPostRef.current[postKey] = point?.clientX ?? null;
  };

  const handleImageTouchEnd = (postKey, count, event) => {
    const startX = touchStartXByPostRef.current[postKey];
    const point = event?.changedTouches?.[0] || event?.touches?.[0];
    const endX = point?.clientX;
    touchStartXByPostRef.current[postKey] = null;
    if (!Number.isFinite(startX) || !Number.isFinite(endX)) return;

    const deltaX = endX - startX;
    if (Math.abs(deltaX) < 40) return;
    if (deltaX < 0) goToNextImage(postKey, count);
    else goToPreviousImage(postKey, count);
  };

  useEffect(() => {
    let mounted = true;
    const runId = ++requestRunRef.current;
    const cacheKey = String(leagueId ?? 'all');

    const loadNewsFeed = async () => {
      try {
        setLoading(true);
        const requestPayload = {
          user_id: userPreferences?.user_id || null,
          followed_teams: followedTeams,
          followed_leagues: followedLeagues,
          league_id: leagueId,
          limit: 60,
        };
        const result = await getNewsFeed(requestPayload);

        if (!mounted || runId !== requestRunRef.current) return;

        if (result?.data?.success) {
          let news = Array.isArray(result.data.news) ? result.data.news : [];
          if (leagueId) {
            const targetLeagueId = Number(leagueId);
            news = news.filter((item) => Number(item?.league_id) === targetLeagueId);
          }
          // Keep a per-league memory cache so fast league switching doesn't wipe known-good feeds.
          if (news.length > 0) {
            perLeagueCacheRef.current[cacheKey] = news;
          } else if (perLeagueCacheRef.current[cacheKey]?.length) {
            news = perLeagueCacheRef.current[cacheKey];
          }
          setNewsItems(news);
          return;
        }

        if (perLeagueCacheRef.current[cacheKey]?.length) {
          setNewsItems(perLeagueCacheRef.current[cacheKey]);
        } else {
          setNewsItems([]);
        }
      } catch (error) {
        console.error('Error loading news feed:', error);
        if (!mounted || runId !== requestRunRef.current) return;
        if (perLeagueCacheRef.current[cacheKey]?.length) {
          setNewsItems(perLeagueCacheRef.current[cacheKey]);
        } else {
          setNewsItems([]);
        }
      } finally {
        if (mounted && runId === requestRunRef.current) setLoading(false);
      }
    };

    if (leagueId) {
      loadNewsFeed();
    } else {
      setLoading(false);
      setNewsItems([]);
    }

    return () => {
      mounted = false;
    };
  }, [
    leagueId,
    userPreferences?.user_id,
    followedTeams,
    followedLeagues,
    followedTeamsKey,
    followedLeaguesKey,
  ]);

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
        <RugbyBallLoader size={100} color="#10b981" compact label="Loading feed..." />
      </Box>
    );
  }

  return (
    <Box sx={{ width: '100%', px: { xs: 0, sm: 1.25, md: 2 }, pb: 4, boxSizing: 'border-box' }}>
      <Box sx={{ width: '100%', maxWidth: '100%', mx: 'auto' }}>
        <Paper
          elevation={0}
          sx={{
            p: { xs: 1.25, sm: 1.6 },
            mb: 1.5,
            borderRadius: 3,
            border: '1px solid rgba(214,185,122,0.32)',
            background:
              'linear-gradient(165deg, rgba(15,23,42,0.94) 0%, rgba(17,24,39,0.96) 48%, rgba(2,6,23,0.98) 100%)',
            boxShadow:
              '0 2px 0 rgba(255,240,212,0.12), 0 12px 28px rgba(2,6,23,0.45), inset 0 1px 0 rgba(255,250,236,0.08)',
            position: 'relative',
            overflow: 'hidden',
            '&::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: 3,
              background:
                'linear-gradient(90deg, rgba(214,185,122,0.08), rgba(245,225,170,0.7), rgba(214,185,122,0.08))',
            },
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: { xs: 0.9, sm: 1.1 },
              flexWrap: 'nowrap',
              minWidth: 0,
            }}
          >
            <Box sx={{ display: 'grid', placeItems: 'center', width: { xs: 24, sm: 28 }, height: { xs: 34, sm: 38 }, mr: { xs: 0.1, sm: 0.42 } }}>
              <RugbyPoleGlyph />
            </Box>
            <Box
              sx={{
                minWidth: 0,
                height: { xs: 34, sm: 'auto' },
                display: 'flex',
                flexDirection: 'column',
                justifyContent: { xs: 'center', sm: 'flex-start' },
              }}
            >
              <Typography sx={{ color: '#f8fafc', fontWeight: 900, fontSize: { xs: '0.98rem', sm: '1.1rem' }, letterSpacing: 0.2, lineHeight: 1.2 }}>
                Rugby Feed
              </Typography>
              <Typography sx={{ color: '#a7b2c7', fontSize: { xs: '0.72rem', sm: '0.78rem' }, mt: { xs: 0.05, sm: 0.15 }, lineHeight: 1.15 }}>
                Latest updates and social highlights
              </Typography>
            </Box>
            <Chip
              icon={<SportsIcon sx={{ fontSize: '0.9rem !important' }} />}
              label={displayLeagueChipLabel}
              size="small"
              sx={{
                ml: 'auto',
                mt: 0,
                flexShrink: 0,
                background:
                  'linear-gradient(135deg, rgba(193,154,79,0.2), rgba(245,225,170,0.14))',
                border: '1px solid rgba(214,185,122,0.45)',
                color: '#f4e4bc',
                fontWeight: 700,
                '& .MuiChip-label': {
                  whiteSpace: 'nowrap',
                },
                '& .MuiChip-icon': {
                  color: '#f4e4bc',
                },
              }}
            />
            {isMobileReels ? (
              <Chip
                label={reelsMode ? 'Reels On' : 'Reels Off'}
                size="small"
                onClick={() => setReelsMode((prev) => !prev)}
                sx={{
                  ml: 0.8,
                  mt: 0,
                  flexShrink: 0,
                  cursor: 'pointer',
                  background: reelsMode
                    ? 'linear-gradient(135deg, rgba(16,185,129,0.22), rgba(56,189,248,0.2))'
                    : 'linear-gradient(135deg, rgba(148,163,184,0.16), rgba(71,85,105,0.22))',
                  border: reelsMode
                    ? '1px solid rgba(52,211,153,0.55)'
                    : '1px solid rgba(148,163,184,0.35)',
                  color: reelsMode ? '#d1fae5' : '#e2e8f0',
                  fontWeight: 800,
                  '& .MuiChip-label': {
                    whiteSpace: 'nowrap',
                  },
                }}
              />
            ) : null}
          </Box>
        </Paper>

        {sortedItems.length === 0 ? (
          <Paper
            elevation={0}
            sx={{
              p: 3,
              borderRadius: 3,
              border: '1px solid rgba(255,255,255,0.1)',
              backgroundColor: 'rgba(15, 23, 42, 0.9)',
            }}
          >
            <Typography sx={{ color: '#f8fafc', fontWeight: 700, mb: 0.5 }}>No posts yet</Typography>
            <Typography sx={{ color: '#94a3b8' }}>
              Nothing new for {displayLeagueName}. New posts will appear here in a single-feed layout.
            </Typography>
          </Paper>
        ) : (reelsMode && isMobileReels) ? (
          mediaReelItems.length === 0 ? (
            <Paper
              elevation={0}
              sx={{
                p: 3,
                borderRadius: 3,
                border: '1px solid rgba(255,255,255,0.1)',
                backgroundColor: 'rgba(15, 23, 42, 0.9)',
              }}
            >
              <Typography sx={{ color: '#f8fafc', fontWeight: 700, mb: 0.5 }}>No media posts yet</Typography>
              <Typography sx={{ color: '#94a3b8' }}>
                Reels mode needs posts with image or video media.
              </Typography>
            </Paper>
          ) : (
            <Box
              ref={reelsScrollRef}
              onScroll={(event) => {
                const container = event.currentTarget;
                if (!container?.clientHeight) return;
                const nextIndex = Math.round(container.scrollTop / container.clientHeight);
                if (nextIndex !== activeReelIndex) setActiveReelIndex(nextIndex);
              }}
              sx={{
                width: '100%',
                maxWidth: { xs: '100%', md: 920, lg: 1040 },
                mx: 'auto',
                height: { xs: 'calc(100svh - 190px)', sm: 'calc(100vh - 210px)', lg: 'calc(100vh - 170px)' },
                minHeight: { xs: 420, sm: 520 },
                borderRadius: 3,
                overflowY: 'auto',
                overflowX: 'hidden',
                scrollSnapType: 'y mandatory',
                scrollBehavior: 'smooth',
                WebkitOverflowScrolling: 'touch',
                border: '1px solid rgba(214,185,122,0.34)',
                backgroundColor: '#020617',
                boxShadow: '0 20px 44px rgba(2,6,23,0.55)',
              }}
            >
              {mediaReelItems.map((reelItem, idx) => {
                const isActiveReel = idx === activeReelIndex;
                const titleLine = reelItem.title || '';
                const contentLine = String(reelItem.content || '').trim();
                return (
                  <Box
                    key={reelItem.itemKey}
                    sx={{
                      height: '100%',
                      minHeight: { xs: 'calc(100svh - 190px)', sm: 'calc(100vh - 210px)', lg: 'calc(100vh - 170px)' },
                      position: 'relative',
                      scrollSnapAlign: 'start',
                      overflow: 'hidden',
                      background:
                        'radial-gradient(circle at 50% 30%, rgba(15,23,42,0.58), rgba(2,6,23,0.98))',
                    }}
                  >
                    <Box
                      sx={{
                        position: 'absolute',
                        inset: 0,
                        display: 'grid',
                        placeItems: 'center',
                        px: { xs: 0, sm: 1.5, md: 2.5 },
                      }}
                    >
                      <Box
                        sx={{
                          width: '100%',
                          maxWidth: { xs: '100%', md: 760, lg: 860 },
                          height: '100%',
                          maxHeight: '100%',
                          borderRadius: { xs: 0, md: 2.5 },
                          overflow: 'hidden',
                          backgroundColor: '#020617',
                          boxShadow: { xs: 'none', md: '0 22px 40px rgba(0,0,0,0.5)' },
                          display: 'grid',
                          placeItems: 'center',
                        }}
                      >
                        {reelItem.videoSrc ? (
                          <video
                            ref={(el) => {
                              reelVideoRefs.current[idx] = el;
                            }}
                            src={reelItem.videoSrc}
                            playsInline
                            muted
                            loop
                            autoPlay={isActiveReel}
                            preload="metadata"
                            controls={isActiveReel}
                            onError={() => {
                              markVideoSrcFailed(reelItem.videoSrc);
                            }}
                            style={{
                              width: '100%',
                              maxWidth: '100%',
                              height: '100%',
                              maxHeight: '100%',
                              objectFit: 'contain',
                              display: 'block',
                              backgroundColor: '#020617',
                            }}
                          >
                            Your browser cannot play this video.
                          </video>
                        ) : (
                          <Box
                            component="img"
                            src={reelItem.imageUrl}
                            alt={reelItem.title || 'Post media'}
                            loading="lazy"
                            sx={{
                              width: '100%',
                              maxWidth: '100%',
                              height: '100%',
                              maxHeight: '100%',
                              objectFit: 'contain',
                              display: 'block',
                              backgroundColor: '#020617',
                            }}
                          />
                        )}
                      </Box>
                    </Box>

                    <Box
                      sx={{
                        position: 'absolute',
                        left: 0,
                        right: 0,
                        bottom: 0,
                        px: { xs: 1.2, sm: 1.8, md: 2.2 },
                        pb: { xs: 1.25, sm: 1.45 },
                        pt: { xs: 4, sm: 5 },
                        background:
                          'linear-gradient(180deg, rgba(2,6,23,0) 0%, rgba(2,6,23,0.64) 38%, rgba(2,6,23,0.9) 100%)',
                        pointerEvents: 'none',
                      }}
                    >
                      <Box
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 0.9,
                          mb: 0.65,
                        }}
                      >
                        <Box
                          component="img"
                          src={reelItem.authorAvatar}
                          alt={reelItem.authorName}
                          onError={(event) => {
                            event.currentTarget.src = DEFAULT_AVATAR_URL;
                          }}
                          sx={{
                            width: 34,
                            height: 34,
                            borderRadius: '50%',
                            objectFit: 'cover',
                            border: '1px solid rgba(255,255,255,0.35)',
                            boxShadow: '0 6px 18px rgba(0,0,0,0.45)',
                          }}
                        />
                        <Typography sx={{ color: '#f8fafc', fontWeight: 800, fontSize: '0.94rem' }}>
                          {reelItem.authorName}
                          {reelItem.authorHandle ? (
                            <Box component="span" sx={{ color: '#bfdbfe', ml: 0.5, fontWeight: 700 }}>
                              @{reelItem.authorHandle}
                            </Box>
                          ) : null}
                        </Typography>
                      </Box>
                      {titleLine ? (
                        <Typography sx={{ color: '#f8fafc', fontWeight: 800, fontSize: { xs: '0.95rem', sm: '1rem' }, mb: 0.3 }}>
                          {titleLine}
                        </Typography>
                      ) : null}
                      {contentLine ? (
                        <Typography
                          sx={{
                            color: '#e2e8f0',
                            fontSize: { xs: '0.88rem', sm: '0.93rem' },
                            lineHeight: 1.4,
                            display: '-webkit-box',
                            WebkitLineClamp: 3,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                          }}
                        >
                          {contentLine}
                        </Typography>
                      ) : null}
                    </Box>

                  </Box>
                );
              })}
            </Box>
          )
        ) : (
          <Stack spacing={0}>
            {sortedItems.map((item, index) => {
              const itemKey = item?.id || `${item?.timestamp}-${item?.title}`;
              const isLast = index === sortedItems.length - 1;
              const { imageUrls, videoCandidates } = getPostMedia(item);
              const sourceUrl = item?.embedded_content?.url || item?.source_url || item?.url || null;
              const tweetUrl = isTwitterUrl(sourceUrl)
                ? sourceUrl
                : (isTwitterUrl(item?.embedded_content?.url) ? item?.embedded_content?.url : null);
              const openOnXUrl = tweetUrl || sourceUrl;
              const playableSources = videoCandidates
                .flatMap((candidateUrl) => getPlayableVideoSources(candidateUrl))
                .filter((src) => !failedVideoSrcs[src]);
              const videoSrc = playableSources[0] || null;
              const canUseNativeVideo = Boolean(videoSrc);
              const activeImageIndex = getActiveImageIndex(itemKey, imageUrls.length);
              const activeImageUrl = imageUrls[activeImageIndex] || imageUrls[0] || null;
              const hasImageCarousel = imageUrls.length > 1;
              const rawHandle = String(item?.author_handle || item?.source_handle || '').trim();
              const inferredHandle = extractHandleFromUrl(tweetUrl || sourceUrl || '');
              const authorHandle = (rawHandle.replace(/^@+/, '') || inferredHandle || '').trim();
              const authorNameCandidates = [item?.author_name, item?.source_name, item?.publisher]
                .map((value) => String(value || '').trim())
                .filter(Boolean);
              const blockedAuthorNames = new Set(['verified', 'unverified', 'official']);
              const cleanedAuthorName = authorNameCandidates.find((value) => {
                const normalized = value.toLowerCase();
                if (!normalized || blockedAuthorNames.has(normalized)) return false;
                if (/^@/.test(value)) return false;
                return true;
              });
              const authorName = cleanedAuthorName || (authorHandle ? `@${authorHandle}` : 'Rugby Source');
              const authorAvatar =
                item?.author_avatar ||
                item?.profile_image_url ||
                (authorHandle ? `https://unavatar.io/x/${authorHandle}` : DEFAULT_AVATAR_URL);
              const authorVerified = Boolean(item?.author_verified);
              const timeAgo = formatTimeAgo(item?.timestamp);
              const cleanTitle = String(item?.title || '').trim();
              const cleanContent = removeRedundantTrailingLinks(
                sanitizePostContent(item?.content, { authorName, authorHandle }),
                { openOnXUrl }
              );
              const hideGenericTitle = /-\s*x\s*update$/i.test(cleanTitle);
              return (
                <Box key={itemKey} sx={{ mb: isLast ? 0 : 1.15 }}>
                  <Paper
                    elevation={0}
                    sx={{
                      px: { xs: 1.5, sm: 2 },
                      py: { xs: 1.4, sm: 1.65 },
                      width: '100%',
                      borderRadius: 3,
                      border: '1px solid rgba(214,185,122,0.34)',
                      background:
                        'linear-gradient(165deg, rgba(15,23,42,0.96) 0%, rgba(17,24,39,0.96) 52%, rgba(2,6,23,0.98) 100%)',
                      boxShadow:
                        '0 2px 0 rgba(255,240,212,0.18), 0 14px 28px rgba(0,0,0,0.42), 0 26px 46px rgba(2,6,23,0.52), inset 0 1px 0 rgba(255,250,236,0.15), inset 0 -1px 0 rgba(0,0,0,0.38)',
                      backdropFilter: 'blur(10px)',
                      overflow: 'hidden',
                      position: 'relative',
                      '&::before': {
                        content: '""',
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        height: '3px',
                        background:
                          'linear-gradient(90deg, rgba(214,185,122,0.08), rgba(245,225,170,0.74), rgba(214,185,122,0.08))',
                      },
                      '&::after': {
                        content: '""',
                        position: 'absolute',
                        inset: 0,
                        borderRadius: 3,
                        pointerEvents: 'none',
                        boxShadow: 'inset 0 0 0 1px rgba(255,243,217,0.18)',
                      },
                    }}
                  >
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25, alignItems: 'flex-start', width: '100%' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.35, width: '100%' }}>
                      <Box
                        sx={{
                          width: 48,
                          height: 48,
                          p: '2px',
                          borderRadius: '50%',
                          flexShrink: 0,
                          position: 'relative',
                          background:
                            'conic-gradient(from 220deg, rgba(238,243,250,0.98) 0deg, rgba(119,128,142,0.95) 52deg, rgba(33,38,47,0.98) 122deg, rgba(202,211,225,0.95) 208deg, rgba(66,74,87,0.98) 284deg, rgba(240,246,255,0.96) 360deg)',
                          boxShadow:
                            '0 0 0 1px rgba(7,9,12,0.98), 0 0 0 4px rgba(72,81,96,0.68), 0 12px 24px rgba(0,0,0,0.58), inset 0 1px 0 rgba(255,255,255,0.42), inset 0 -1px 0 rgba(14,17,22,0.92)',
                          '&::before': {
                            content: '""',
                            position: 'absolute',
                            inset: 1,
                            borderRadius: '50%',
                            pointerEvents: 'none',
                            background:
                              'linear-gradient(165deg, rgba(255,255,255,0.38) 0%, rgba(255,255,255,0) 42%, rgba(255,255,255,0.2) 82%, rgba(255,255,255,0.04) 100%)',
                            mixBlendMode: 'screen',
                          },
                        }}
                      >
                        <Box
                          component="img"
                          src={authorAvatar}
                          alt={authorName}
                          onError={(event) => {
                            event.currentTarget.src = DEFAULT_AVATAR_URL;
                          }}
                          sx={{
                            width: '100%',
                            height: '100%',
                            borderRadius: '50%',
                            objectFit: 'cover',
                            display: 'block',
                            border: '1px solid rgba(12,15,20,0.92)',
                            backgroundColor: '#0f172a',
                          }}
                        />
                      </Box>
                      <Box sx={{ minWidth: 0, width: '100%', py: 0.15 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, width: '100%' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.7, rowGap: 0.45, flexWrap: 'wrap', minWidth: 0 }}>
                            <Typography sx={{ color: '#f8fafc', fontWeight: 800, fontSize: { xs: '0.92rem', sm: '0.97rem' }, lineHeight: 1.25 }}>
                              {authorName}
                            </Typography>
                            {authorHandle ? (
                              <Link
                                href={`https://x.com/${authorHandle}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                underline="none"
                                sx={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: 0.45,
                                  whiteSpace: 'nowrap',
                                  '&:hover .author-handle': {
                                    color: '#bfdbfe',
                                  },
                                }}
                              >
                                {authorVerified ? (
                                  <Box component="img" src={VERIFIED_BADGE_URL} alt="verified" sx={{ width: { xs: 15, sm: 16 }, height: { xs: 15, sm: 16 }, flexShrink: 0 }} />
                                ) : null}
                                <Typography className="author-handle" sx={{ color: '#94a3b8', fontSize: { xs: '0.92rem', sm: '0.97rem' }, lineHeight: 1.25, fontWeight: 700 }}>
                                  @{authorHandle}
                                </Typography>
                              </Link>
                            ) : authorVerified ? (
                              <Box component="img" src={VERIFIED_BADGE_URL} alt="verified" sx={{ width: { xs: 15, sm: 16 }, height: { xs: 15, sm: 16 } }} />
                            ) : null}
                            {timeAgo ? (
                              <Typography sx={{ color: '#64748b', fontSize: '0.8rem', lineHeight: 1.25 }}>
                                · {timeAgo}
                              </Typography>
                            ) : null}
                          </Box>
                          {openOnXUrl ? (
                            <Link
                              href={openOnXUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              underline="none"
                              sx={{
                                ml: 'auto',
                                alignSelf: 'center',
                                color: '#f8fafc',
                                fontSize: '0.76rem',
                                fontWeight: 800,
                                px: 1.2,
                                py: 0.55,
                                borderRadius: 999,
                                border: '1px solid rgba(255,255,255,0.26)',
                                background:
                                  'linear-gradient(135deg, rgba(31,41,55,0.95), rgba(15,23,42,0.96))',
                                transition: 'all 0.18s ease',
                                whiteSpace: 'nowrap',
                                '&:hover': {
                                  borderColor: 'rgba(255,255,255,0.45)',
                                  background:
                                    'linear-gradient(135deg, rgba(51,65,85,0.95), rgba(15,23,42,0.98))',
                                },
                              }}
                            >
                              Open on X
                            </Link>
                          ) : null}
                        </Box>
                      </Box>
                    </Box>

                    <Box sx={{ minWidth: 0, width: '100%', mt: 0.9 }}>

                      {cleanTitle && !hideGenericTitle ? (
                        <Typography sx={{ color: '#f8fafc', fontWeight: 700, mt: 0.45, mb: 0.4, fontSize: '1rem', letterSpacing: 0.1, width: '100%' }}>
                          {cleanTitle}
                        </Typography>
                      ) : null}

                      <Typography
                        sx={{
                          color: '#e2e8f0',
                          lineHeight: 1.45,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontSize: { xs: '0.95rem', sm: '0.98rem' },
                          width: '100%',
                        }}
                      >
                        {linkifyText(cleanContent)}
                      </Typography>

                      {canUseNativeVideo ? (
                        <Box
                          sx={{
                            mt: 1.1,
                            borderRadius: 2,
                            overflow: 'hidden',
                            border: '1px solid rgba(255,255,255,0.12)',
                            backgroundColor: '#020617',
                            width: '100%',
                            maxHeight: '70vh',
                            position: 'relative',
                            display: 'grid',
                            placeItems: 'center',
                          }}
                        >
                          <video
                            src={videoSrc || undefined}
                            controls
                            preload="metadata"
                            playsInline
                            onError={() => {
                              if (videoSrc) markVideoSrcFailed(videoSrc);
                            }}
                            style={{
                              width: '100%',
                              minWidth: '100%',
                              maxWidth: '100%',
                              height: 'auto',
                              maxHeight: '70vh',
                              display: 'block',
                              objectFit: 'contain',
                              backgroundColor: '#020617',
                            }}
                          >
                            Your browser cannot play this video.
                          </video>
                        </Box>
                      ) : null}

                      {!canUseNativeVideo && imageUrls.length > 0 ? (
                        <Box
                          sx={{
                            mt: 1.1,
                            borderRadius: 2,
                            overflow: 'hidden',
                            border: '1px solid rgba(255,255,255,0.12)',
                            backgroundColor: '#020617',
                            width: '100%',
                            maxHeight: '70vh',
                            position: 'relative',
                            display: 'grid',
                            placeItems: 'center',
                          }}
                          onTouchStart={(event) => handleImageTouchStart(itemKey, event)}
                          onTouchEnd={(event) => handleImageTouchEnd(itemKey, imageUrls.length, event)}
                        >
                          {activeImageUrl ? (
                            <Box
                              key={`${item?.id || item?.timestamp}-${activeImageUrl}`}
                              component="img"
                              src={activeImageUrl}
                              alt={item?.title || 'Post media'}
                              loading="lazy"
                              sx={{
                                width: '100%',
                                height: 'auto',
                                maxHeight: '70vh',
                                objectFit: 'contain',
                                display: 'block',
                                backgroundColor: '#020617',
                              }}
                            />
                          ) : null}

                          {hasImageCarousel ? (
                            <>
                              <IconButton
                                size="small"
                                onClick={() => goToPreviousImage(itemKey, imageUrls.length)}
                                aria-label="Previous image"
                                sx={{
                                  position: 'absolute',
                                  left: 8,
                                  top: '50%',
                                  transform: 'translateY(-50%)',
                                  color: '#f8fafc',
                                  backgroundColor: 'rgba(15,23,42,0.58)',
                                  border: '1px solid rgba(148,163,184,0.35)',
                                  '&:hover': {
                                    backgroundColor: 'rgba(30,41,59,0.78)',
                                  },
                                }}
                              >
                                <ChevronLeftIcon fontSize="small" />
                              </IconButton>
                              <IconButton
                                size="small"
                                onClick={() => goToNextImage(itemKey, imageUrls.length)}
                                aria-label="Next image"
                                sx={{
                                  position: 'absolute',
                                  right: 8,
                                  top: '50%',
                                  transform: 'translateY(-50%)',
                                  color: '#f8fafc',
                                  backgroundColor: 'rgba(15,23,42,0.58)',
                                  border: '1px solid rgba(148,163,184,0.35)',
                                  '&:hover': {
                                    backgroundColor: 'rgba(30,41,59,0.78)',
                                  },
                                }}
                              >
                                <ChevronRightIcon fontSize="small" />
                              </IconButton>
                              <Box
                                sx={{
                                  position: 'absolute',
                                  bottom: 8,
                                  left: '50%',
                                  transform: 'translateX(-50%)',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 0.7,
                                  px: 1,
                                  py: 0.45,
                                  borderRadius: 999,
                                  backgroundColor: 'rgba(2,6,23,0.65)',
                                  border: '1px solid rgba(148,163,184,0.25)',
                                }}
                              >
                                {imageUrls.map((img, dotIndex) => {
                                  const isActive = dotIndex === activeImageIndex;
                                  return (
                                    <Box
                                      key={`${itemKey}-${img}-dot`}
                                      component="button"
                                      type="button"
                                      aria-label={`Go to image ${dotIndex + 1}`}
                                      onClick={() => setActiveImageIndex(itemKey, dotIndex, imageUrls.length)}
                                      sx={{
                                        width: 8,
                                        height: 8,
                                        borderRadius: '50%',
                                        p: 0,
                                        border: 0,
                                        cursor: 'pointer',
                                        backgroundColor: isActive ? '#f8fafc' : 'rgba(148,163,184,0.65)',
                                      }}
                                    />
                                  );
                                })}
                              </Box>
                            </>
                          ) : null}
                        </Box>
                      ) : null}

                    </Box>
                  </Box>
                  </Paper>
                  {!isLast ? (
                    <Box
                      aria-hidden
                      sx={{
                        mt: 1.8,
                        mb: 1.45,
                        minHeight: 24,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        position: 'relative',
                        px: { xs: 0.5, sm: 1 },
                        '&::before': {
                          content: '""',
                          width: '100%',
                          height: 2,
                          borderRadius: 999,
                          background:
                            'linear-gradient(90deg, rgba(148,163,184,0) 0%, rgba(56,189,248,0.25) 20%, rgba(148,163,184,0.42) 50%, rgba(56,189,248,0.25) 80%, rgba(148,163,184,0) 100%)',
                          boxShadow:
                            '0 0 16px rgba(56,189,248,0.14), 0 1px 0 rgba(255,255,255,0.05)',
                        },
                        '&::after': {
                          content: '""',
                          width: 54,
                          height: 16,
                          borderRadius: 999,
                          background:
                            'radial-gradient(circle at center, rgba(125,211,252,0.95) 0 1.5px, rgba(15,23,42,0.96) 2px 100%)',
                          border: '1px solid rgba(56,189,248,0.3)',
                          boxShadow:
                            '0 0 0 1px rgba(2,6,23,0.85), 0 6px 16px rgba(2,132,199,0.2), inset 0 1px 0 rgba(255,255,255,0.14)',
                          zIndex: 1,
                        },
                      }}
                    />
                  ) : null}
                </Box>
              );
            })}
          </Stack>
        )}
      </Box>
    </Box>
  );
};

export default NewsFeed;

