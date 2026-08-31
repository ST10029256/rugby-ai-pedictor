import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Chip, IconButton, Link, Paper, Stack, Typography, useMediaQuery } from '@mui/material';
import SportsIcon from '@mui/icons-material/Sports';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import VolumeOffIcon from '@mui/icons-material/VolumeOff';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import RugbyBallLoader from './RugbyBallLoader';
import { TabLoadingScreen } from '../utils/viewLoader';
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
  5480: { name: 'Nations Championship' },
};

const URL_PATTERN = /(https?:\/\/[^\s]+)/g;
const PLAYABLE_VIDEO_EXT_PATTERN = /\.(mp4|webm|ogg|m3u8)(\?.*)?$/i;
const IMAGE_EXT_PATTERN = /\.(jpg|jpeg|png|gif|webp|avif)(\?.*)?$/i;
const URL_EXACT_PATTERN = /^https?:\/\/[^\s]+$/i;
const DEFAULT_AVATAR_URL = 'https://abs.twimg.com/sticky/default_profile_images/default_profile_400x400.png';
const VERIFIED_BADGE_URL = 'https://abs.twimg.com/icons/apple-touch-icon-192x192.png';
const VIDEO_PROXY_ENDPOINT = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/proxy_video_http';
const REEL_CONTROLS_HIDE_DELAY_MS = 2000;
const MOBILE_NAV_TOP = 'var(--app-mobile-nav-offset)';

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

function formatMediaTime(seconds) {
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  const mins = Math.floor(safeSeconds / 60);
  const secs = safeSeconds % 60;
  return `${mins}:${String(secs).padStart(2, '0')}`;
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

function getPlayableVideoSources(url, options = {}) {
  if (!url) return [];
  const forReels = Boolean(options.forReels);
  const directSrc = String(url);
  const proxySrc = buildPlayableVideoSrc(url);
  const host = typeof window !== 'undefined'
    ? String(window.location?.hostname || '').toLowerCase()
    : '';
  const isLocalDevHost = host === 'localhost' || host === '127.0.0.1';
  // Reels: try direct MP4 first (fast when allowed), then proxy fallback via onError.
  const ordered = (forReels || isLocalDevHost)
    ? [directSrc, proxySrc]
    : [proxySrc, directSrc];
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
  const vidsMatch = value.match(/\/vids\/(\d{2,5})x(\d{2,5})\//);
  if (vidsMatch) {
    return {
      width: Number(vidsMatch[1]) || 0,
      height: Number(vidsMatch[2]) || 0,
    };
  }
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

function getPostMedia(item, options = {}) {
  const forReels = Boolean(options.forReels);
  const candidates = getMediaCandidates(item);
  const videoCandidates = candidates
    .map((value) => normalizeVideoCandidate(value))
    .filter((candidate) => candidate.url && isLikelyVideoUrl(candidate.url))
    .filter((candidate, index, arr) => arr.findIndex((itemCandidate) => itemCandidate.url === candidate.url) === index)
    .sort((a, b) => {
      if (forReels) {
        // Smallest file first — starts playback much faster on mobile.
        const brA = a.bitrate || (a.width * a.height) || 999_999_999;
        const brB = b.bitrate || (b.width * b.height) || 999_999_999;
        if (brA !== brB) return brA - brB;
      } else {
        const bitrateDelta = (b.bitrate || 0) - (a.bitrate || 0);
        if (bitrateDelta !== 0) return bitrateDelta;
      }
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
  const embedded = item?.embedded_content || {};
  const mediaBag = item?.media || {};
  const related = item?.related_stats || {};
  const posterUrl =
    mediaBag.preview_image_url ||
    related.preview_image_url ||
    item?.thumbnail_url ||
    item?.image_url ||
    related?.image_url ||
    embedded.thumbnail_url ||
    embedded.preview_image_url ||
    embedded.poster_url ||
    imageUrls[0] ||
    null;
  return { videoUrl, imageUrls, videoCandidates, posterUrl };
}

function linkifyText(text) {
  const value = String(text || '');
  if (!value) return null;
  const parts = value.split(URL_PATTERN);
  const HASHTAG_OR_MENTION_PATTERN = /(^|[^A-Za-z0-9_])(@[A-Za-z0-9_]{1,15})|(#[A-Za-z][A-Za-z0-9_]*)/g;

  const renderSocialTokens = (segment, keyPrefix) => {
    const nodes = [];
    let lastIndex = 0;
    let match;

    while ((match = HASHTAG_OR_MENTION_PATTERN.exec(segment)) !== null) {
      const fullMatch = match[0];
      const boundary = match[1] || '';
      const mention = match[2] || '';
      const hashtag = match[3] || '';
      const matchStart = match.index;
      const tokenOffset = boundary ? boundary.length : 0;
      const tokenStart = matchStart + tokenOffset;

      if (matchStart > lastIndex) {
        nodes.push(
          <React.Fragment key={`${keyPrefix}-text-${lastIndex}`}>
            {segment.slice(lastIndex, matchStart)}
          </React.Fragment>
        );
      }

      if (boundary) {
        nodes.push(
          <React.Fragment key={`${keyPrefix}-boundary-${matchStart}`}>
            {boundary}
          </React.Fragment>
        );
      }

      if (mention) {
        const handle = mention.replace(/^@/, '');
        nodes.push(
          <Link
            key={`${keyPrefix}-mention-${tokenStart}`}
            href={`https://x.com/${handle}`}
            target="_blank"
            rel="noopener noreferrer"
            underline="hover"
            sx={{ color: '#93c5fd', fontWeight: 700 }}
          >
            {mention}
          </Link>
        );
      } else if (hashtag) {
        const tag = hashtag.replace(/^#/, '');
        nodes.push(
          <Link
            key={`${keyPrefix}-hashtag-${tokenStart}`}
            href={`https://x.com/hashtag/${encodeURIComponent(tag)}`}
            target="_blank"
            rel="noopener noreferrer"
            underline="hover"
            sx={{ color: '#60a5fa', fontWeight: 700 }}
          >
            {hashtag}
          </Link>
        );
      } else {
        nodes.push(
          <React.Fragment key={`${keyPrefix}-fallback-${matchStart}`}>
            {fullMatch}
          </React.Fragment>
        );
      }

      lastIndex = matchStart + fullMatch.length;
    }

    if (lastIndex < segment.length) {
      nodes.push(
        <React.Fragment key={`${keyPrefix}-tail-${lastIndex}`}>
          {segment.slice(lastIndex)}
        </React.Fragment>
      );
    }

    return nodes.length > 0
      ? nodes
      : [<React.Fragment key={`${keyPrefix}-plain`}>{segment}</React.Fragment>];
  };

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

    return renderSocialTokens(part, `segment-${idx}`);
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
  const [reelPlaybackByPost, setReelPlaybackByPost] = useState({});
  const [reelControlsVisibleByPost, setReelControlsVisibleByPost] = useState({});
  const [activeReelIndex, setActiveReelIndex] = useState(0);
  const [reelsMuted, setReelsMuted] = useState(true);
  const [reelBufferingByPost, setReelBufferingByPost] = useState({});
  const requestRunRef = useRef(0);
  const perLeagueCacheRef = useRef({});
  const touchStartXByPostRef = useRef({});
  const reelsScrollRef = useRef(null);
  const reelVideoRefs = useRef({});
  const reelControlsTimeoutsRef = useRef({});
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
        const media = getPostMedia(item, { forReels: true });
        const videoSources = media.videoCandidates
          .flatMap((candidateUrl) => getPlayableVideoSources(candidateUrl, { forReels: true }))
          .filter((src) => !failedVideoSrcs[src]);
        const videoSrc = videoSources[0] || null;
        const sourceUrl = item?.embedded_content?.url || item?.source_url || item?.url || null;
        const tweetUrl = isTwitterUrl(sourceUrl)
          ? sourceUrl
          : (isTwitterUrl(item?.embedded_content?.url) ? item?.embedded_content?.url : null);
        const openOnXUrl = tweetUrl || sourceUrl;
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
        const title = String(item?.title || '').trim();
        const content = removeRedundantTrailingLinks(
          sanitizePostContent(item?.content, { authorName, authorHandle }),
          { openOnXUrl }
        );
        return {
          itemKey,
          item,
          videoSrc,
          posterUrl: media.posterUrl,
          imageUrls: media.imageUrls,
          authorName,
          authorHandle,
          authorAvatar,
          authorVerified,
          timeAgo,
          openOnXUrl,
          title,
          content,
        };
      })
      .filter((entry) => Boolean(entry.videoSrc || entry.imageUrls?.length));
  }, [sortedItems, failedVideoSrcs]);

  useEffect(() => {
    if (!isMobileReels) return;
    setActiveReelIndex(0);
    const id = requestAnimationFrame(() => {
      const container = reelsScrollRef.current;
      if (!container) return;
      container.scrollTo({ top: 0, behavior: 'auto' });
    });
    return () => cancelAnimationFrame(id);
  }, [isMobileReels, mediaReelItems.length]);

  useEffect(() => {
    if (!isMobileReels) return;
    const active = mediaReelItems[activeReelIndex];
    if (active?.videoSrc && active?.itemKey) {
      setReelBuffering(active.itemKey, true);
    }
  }, [isMobileReels, activeReelIndex, mediaReelItems]);

  useEffect(() => {
    if (!isMobileReels) return;
    mediaReelItems.forEach((_, idx) => {
      const videoEl = reelVideoRefs.current[idx];
      if (!videoEl) return;
      videoEl.muted = reelsMuted;
      if (idx === activeReelIndex) {
        const playPromise = videoEl.play();
        if (playPromise && typeof playPromise.catch === 'function') {
          playPromise.catch(() => {});
        }
      } else {
        videoEl.pause();
        videoEl.currentTime = 0;
      }
    });
  }, [isMobileReels, activeReelIndex, mediaReelItems, reelsMuted]);

  const toggleReelsMuted = () => {
    setReelsMuted((prev) => !prev);
  };

  const advanceToNextReel = (currentIdx) => {
    const container = reelsScrollRef.current;
    if (!container) return;
    const nextIdx = currentIdx + 1;
    if (nextIdx >= mediaReelItems.length) return;
    container.scrollTo({ top: nextIdx * container.clientHeight, behavior: 'smooth' });
    setActiveReelIndex(nextIdx);
  };

  const setReelBuffering = (postKey, buffering) => {
    if (!postKey) return;
    setReelBufferingByPost((prev) => {
      if (Boolean(prev[postKey]) === Boolean(buffering)) return prev;
      return { ...prev, [postKey]: Boolean(buffering) };
    });
  };

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

  const clearReelControlsTimer = (postKey) => {
    if (!postKey) return;
    const timeoutId = reelControlsTimeoutsRef.current[postKey];
    if (timeoutId) {
      clearTimeout(timeoutId);
      delete reelControlsTimeoutsRef.current[postKey];
    }
  };

  const setReelControlsVisible = (postKey, visible) => {
    if (!postKey) return;
    setReelControlsVisibleByPost((prev) => {
      if (Boolean(prev[postKey]) === Boolean(visible)) return prev;
      return { ...prev, [postKey]: Boolean(visible) };
    });
  };

  const showReelControlsTemporarily = (postKey) => {
    if (!postKey) return;
    clearReelControlsTimer(postKey);
    setReelControlsVisible(postKey, true);
    reelControlsTimeoutsRef.current[postKey] = setTimeout(() => {
      setReelControlsVisible(postKey, false);
      delete reelControlsTimeoutsRef.current[postKey];
    }, REEL_CONTROLS_HIDE_DELAY_MS);
  };

  const updateReelPlayback = (postKey, nextState) => {
    if (!postKey) return;
    setReelPlaybackByPost((prev) => {
      const current = prev[postKey] || {};
      const resolved = typeof nextState === 'function' ? nextState(current) : nextState;
      const merged = { ...current, ...resolved };
      const currentTimeChanged = Math.abs((merged.currentTime || 0) - (current.currentTime || 0)) >= 0.2;
      const durationChanged = Math.abs((merged.duration || 0) - (current.duration || 0)) >= 0.2;
      const pausedChanged = Boolean(merged.paused) !== Boolean(current.paused);
      if (!currentTimeChanged && !durationChanged && !pausedChanged) return prev;
      return { ...prev, [postKey]: merged };
    });
  };

  const handleReelMetadata = (postKey, event) => {
    const video = event?.currentTarget;
    if (!video) return;
    updateReelPlayback(postKey, {
      currentTime: Number(video.currentTime) || 0,
      duration: Number(video.duration) || 0,
      paused: Boolean(video.paused),
    });
  };

  const handleReelTimeUpdate = (postKey, event) => {
    const video = event?.currentTarget;
    if (!video) return;
    updateReelPlayback(postKey, {
      currentTime: Number(video.currentTime) || 0,
      duration: Number(video.duration) || 0,
      paused: Boolean(video.paused),
    });
  };

  const handleReelPlayState = (postKey, paused) => {
    updateReelPlayback(postKey, { paused });
    if (paused) {
      clearReelControlsTimer(postKey);
      setReelControlsVisible(postKey, true);
    } else {
      showReelControlsTemporarily(postKey);
    }
  };

  const toggleReelPlayback = (reelIndex, postKey) => {
    const videoEl = reelVideoRefs.current[reelIndex];
    if (!videoEl) return;
    if (videoEl.paused) {
      const playPromise = videoEl.play();
      if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(() => {});
      }
    } else {
      videoEl.pause();
    }
    updateReelPlayback(postKey, {
      currentTime: Number(videoEl.currentTime) || 0,
      duration: Number(videoEl.duration) || 0,
      paused: Boolean(videoEl.paused),
    });
  };

  const handleReelSeek = (reelIndex, postKey, nextValue) => {
    const videoEl = reelVideoRefs.current[reelIndex];
    if (!videoEl) return;
    const duration = Number(videoEl.duration) || 0;
    const clampedValue = Math.max(0, Math.min(duration || 0, Number(nextValue) || 0));
    videoEl.currentTime = clampedValue;
    if (videoEl.paused) {
      clearReelControlsTimer(postKey);
      setReelControlsVisible(postKey, true);
    } else {
      showReelControlsTemporarily(postKey);
    }
    updateReelPlayback(postKey, {
      currentTime: clampedValue,
      duration,
      paused: Boolean(videoEl.paused),
    });
  };

  useEffect(() => {
    return () => {
      Object.values(reelControlsTimeoutsRef.current).forEach((timeoutId) => clearTimeout(timeoutId));
      reelControlsTimeoutsRef.current = {};
    };
  }, []);

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
    return <TabLoadingScreen label="Loading feed..." />;
  }

  if (isMobileReels) {
    return (
      <Box
        sx={{
          position: 'fixed',
          top: MOBILE_NAV_TOP,
          left: 0,
          right: 0,
          bottom: 0,
          width: '100%',
          zIndex: 1500,
          backgroundColor: '#000',
          boxSizing: 'border-box',
        }}
      >
        {sortedItems.length === 0 ? (
          <Box sx={{ height: '100%', display: 'grid', placeItems: 'center', px: 2 }}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography sx={{ color: '#f8fafc', fontWeight: 700, mb: 0.5 }}>No posts yet</Typography>
              <Typography sx={{ color: '#94a3b8' }}>
                Nothing new for {displayLeagueName}. New posts will appear here.
              </Typography>
            </Box>
          </Box>
        ) : mediaReelItems.length === 0 ? (
          <Box sx={{ height: '100%', display: 'grid', placeItems: 'center', px: 2 }}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography sx={{ color: '#f8fafc', fontWeight: 700, mb: 0.5 }}>No media posts yet</Typography>
              <Typography sx={{ color: '#94a3b8' }}>
                Waiting for image or video posts from {displayLeagueName}.
              </Typography>
            </Box>
          </Box>
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
              height: '100%',
              overflowY: 'auto',
              overflowX: 'hidden',
              scrollSnapType: 'y mandatory',
              scrollBehavior: 'smooth',
              scrollSnapStop: 'always',
              overscrollBehavior: 'contain',
              WebkitOverflowScrolling: 'touch',
              backgroundColor: '#000',
            }}
          >
            {mediaReelItems.map((reelItem, idx) => {
              const isActiveReel = idx === activeReelIndex;
              const shouldLoadReelVideo = isActiveReel && Boolean(reelItem.videoSrc);
              const shouldLoadReelImages = isActiveReel || Math.abs(idx - activeReelIndex) === 1;
              const titleLine = reelItem.title || '';
              const contentLine = String(reelItem.content || '').trim();
              const hideGenericTitle = /-\s*x\s*update$/i.test(titleLine);
              const reelImageUrls = Array.isArray(reelItem.imageUrls) ? reelItem.imageUrls : [];
              const activeReelImageIndex = getActiveImageIndex(reelItem.itemKey, reelImageUrls.length);
              const hasReelImageCarousel = reelImageUrls.length > 1;
              const reelPlayback = reelPlaybackByPost[reelItem.itemKey] || {};
              const reelDuration = Number(reelPlayback.duration) || 0;
              const reelCurrentTime = Math.min(Number(reelPlayback.currentTime) || 0, reelDuration || Number.MAX_SAFE_INTEGER);
              const reelProgress = reelDuration > 0 ? (reelCurrentTime / reelDuration) * 100 : 0;
              const isReelBuffering = Boolean(reelBufferingByPost[reelItem.itemKey]);
              return (
                <Box
                  key={reelItem.itemKey}
                  sx={{
                    height: '100%',
                    minHeight: '100%',
                    position: 'relative',
                    scrollSnapAlign: 'start',
                    scrollSnapStop: 'always',
                    overflow: 'hidden',
                    backgroundColor: '#000',
                  }}
                >
                  {reelItem.videoSrc && isActiveReel && reelDuration > 0 ? (
                    <Box
                      sx={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        zIndex: 4,
                        height: 3,
                        backgroundColor: 'rgba(255,255,255,0.22)',
                      }}
                    >
                      <Box
                        sx={{
                          height: '100%',
                          width: `${reelProgress}%`,
                          backgroundColor: '#fff',
                          transition: 'width 120ms linear',
                        }}
                      />
                    </Box>
                  ) : null}

                  <Box sx={{ position: 'absolute', inset: 0, backgroundColor: '#000' }}>
                    {reelItem.videoSrc ? (
                      <>
                        {reelItem.posterUrl && (isReelBuffering || !shouldLoadReelVideo) ? (
                          <Box
                            sx={{
                              position: 'absolute',
                              inset: 0,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              backgroundColor: '#000',
                              pointerEvents: 'none',
                            }}
                          >
                            <Box
                              component="img"
                              src={reelItem.posterUrl}
                              alt=""
                              aria-hidden
                              sx={{
                                maxWidth: '100%',
                                maxHeight: '100%',
                                width: 'auto',
                                height: 'auto',
                                objectFit: 'contain',
                                objectPosition: 'center',
                              }}
                            />
                          </Box>
                        ) : null}
                        <video
                          ref={(el) => {
                            reelVideoRefs.current[idx] = el;
                          }}
                          src={shouldLoadReelVideo ? reelItem.videoSrc : undefined}
                          poster={reelItem.posterUrl || undefined}
                          playsInline
                          muted={reelsMuted}
                          loop={false}
                          autoPlay={shouldLoadReelVideo}
                          preload={shouldLoadReelVideo ? 'auto' : 'none'}
                          controls={false}
                          onLoadedMetadata={(event) => handleReelMetadata(reelItem.itemKey, event)}
                          onTimeUpdate={(event) => handleReelTimeUpdate(reelItem.itemKey, event)}
                          onPlay={() => handleReelPlayState(reelItem.itemKey, false)}
                          onPause={() => handleReelPlayState(reelItem.itemKey, true)}
                          onWaiting={() => setReelBuffering(reelItem.itemKey, true)}
                          onCanPlay={() => setReelBuffering(reelItem.itemKey, false)}
                          onPlaying={() => setReelBuffering(reelItem.itemKey, false)}
                          onEnded={() => advanceToNextReel(idx)}
                          onError={() => {
                            markVideoSrcFailed(reelItem.videoSrc);
                          }}
                          onClick={() => toggleReelPlayback(idx, reelItem.itemKey)}
                          style={{
                            position: 'absolute',
                            inset: 0,
                            width: '100%',
                            height: '100%',
                            objectFit: 'cover',
                            objectPosition: 'center',
                            display: 'block',
                            backgroundColor: '#000',
                            cursor: 'pointer',
                          }}
                        >
                          Your browser cannot play this video.
                        </video>
                        {isActiveReel && isReelBuffering ? (
                          <Box
                            sx={{
                              position: 'absolute',
                              inset: 0,
                              zIndex: 2,
                              display: 'grid',
                              placeItems: 'center',
                              pointerEvents: 'none',
                              backgroundColor: 'rgba(0,0,0,0.18)',
                            }}
                          >
                            <RugbyBallLoader size={48} color="#ffffff" compact label="" />
                          </Box>
                        ) : null}
                      </>
                    ) : (
                      <Box
                        sx={{ width: '100%', height: '100%', position: 'relative', overflow: 'hidden' }}
                        onTouchStart={(event) => handleImageTouchStart(reelItem.itemKey, event)}
                        onTouchEnd={(event) => handleImageTouchEnd(reelItem.itemKey, reelImageUrls.length, event)}
                      >
                        <Box
                          sx={{
                            display: 'flex',
                            width: '100%',
                            height: '100%',
                            transform: `translateX(-${activeReelImageIndex * 100}%)`,
                            transition: 'transform 320ms cubic-bezier(0.22, 1, 0.36, 1)',
                            willChange: 'transform',
                          }}
                        >
                          {reelImageUrls.map((img, imageIndex) => (
                            <Box
                              key={`${reelItem.itemKey}-${img}-${imageIndex}`}
                              sx={{
                                minWidth: '100%',
                                width: '100%',
                                height: '100%',
                                flexShrink: 0,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                backgroundColor: '#000',
                              }}
                            >
                              <Box
                                component="img"
                                src={shouldLoadReelImages ? img : undefined}
                                alt={reelItem.title || 'Post media'}
                                loading="lazy"
                                draggable={false}
                                sx={{
                                  maxWidth: '100%',
                                  maxHeight: '100%',
                                  width: 'auto',
                                  height: 'auto',
                                  objectFit: 'contain',
                                  objectPosition: 'center',
                                  display: 'block',
                                  userSelect: 'none',
                                  WebkitUserDrag: 'none',
                                }}
                              />
                            </Box>
                          ))}
                        </Box>
                        {hasReelImageCarousel ? (
                          <>
                            <IconButton
                              size="small"
                              onClick={() => goToPreviousImage(reelItem.itemKey, reelImageUrls.length)}
                              aria-label="Previous image"
                              sx={{
                                position: 'absolute',
                                left: 10,
                                top: '50%',
                                transform: 'translateY(-50%)',
                                zIndex: 2,
                                color: '#f8fafc',
                                backgroundColor: 'rgba(15,23,42,0.58)',
                                border: '1px solid rgba(148,163,184,0.35)',
                              }}
                            >
                              <ChevronLeftIcon fontSize="small" />
                            </IconButton>
                            <IconButton
                              size="small"
                              onClick={() => goToNextImage(reelItem.itemKey, reelImageUrls.length)}
                              aria-label="Next image"
                              sx={{
                                position: 'absolute',
                                right: 10,
                                top: '50%',
                                transform: 'translateY(-50%)',
                                zIndex: 2,
                                color: '#f8fafc',
                                backgroundColor: 'rgba(15,23,42,0.58)',
                                border: '1px solid rgba(148,163,184,0.35)',
                              }}
                            >
                              <ChevronRightIcon fontSize="small" />
                            </IconButton>
                          </>
                        ) : null}
                      </Box>
                    )}
                  </Box>

                  {reelItem.videoSrc ? (
                    <IconButton
                      aria-label={reelsMuted ? 'Unmute reel' : 'Mute reel'}
                      onClick={toggleReelsMuted}
                      sx={{
                        position: 'absolute',
                        right: 12,
                        bottom: 'calc(168px + env(safe-area-inset-bottom, 0px))',
                        zIndex: 6,
                        color: '#fff',
                        backgroundColor: 'rgba(15,23,42,0.55)',
                        border: '1px solid rgba(255,255,255,0.25)',
                        '&:hover': { backgroundColor: 'rgba(30,41,59,0.78)' },
                      }}
                    >
                      {reelsMuted ? <VolumeOffIcon /> : <VolumeUpIcon />}
                    </IconButton>
                  ) : null}

                  <Box
                    sx={{
                      position: 'absolute',
                      left: 0,
                      right: 0,
                      bottom: 0,
                      zIndex: 5,
                      px: 1.5,
                      pt: 6,
                      pb: 'calc(14px + env(safe-area-inset-bottom, 0px))',
                      background:
                        'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.45) 28%, rgba(0,0,0,0.92) 100%)',
                      pointerEvents: 'none',
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, mb: 0.75, pointerEvents: 'auto' }}>
                      <Box
                        sx={{
                          width: 40,
                          height: 40,
                          p: '2px',
                          borderRadius: '50%',
                          flexShrink: 0,
                          background:
                            'conic-gradient(from 220deg, rgba(238,243,250,0.98) 0deg, rgba(119,128,142,0.95) 52deg, rgba(33,38,47,0.98) 122deg, rgba(202,211,225,0.95) 208deg, rgba(66,74,87,0.98) 284deg, rgba(240,246,255,0.96) 360deg)',
                          boxShadow: '0 0 0 1px rgba(7,9,12,0.98), 0 0 0 3px rgba(72,81,96,0.68)',
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
                            width: '100%',
                            height: '100%',
                            borderRadius: '50%',
                            objectFit: 'cover',
                            display: 'block',
                            border: '1px solid rgba(12,15,20,0.92)',
                          }}
                        />
                      </Box>
                      <Box sx={{ minWidth: 0, flex: 1 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.55, flexWrap: 'wrap', minWidth: 0 }}>
                            <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', lineHeight: 1.25 }}>
                              {reelItem.authorName}
                            </Typography>
                            {reelItem.authorHandle ? (
                              <Link
                                href={`https://x.com/${reelItem.authorHandle}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                underline="none"
                                sx={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: 0.4,
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {reelItem.authorVerified ? (
                                  <Box
                                    component="img"
                                    src={VERIFIED_BADGE_URL}
                                    alt="verified"
                                    sx={{ width: 15, height: 15, flexShrink: 0 }}
                                  />
                                ) : null}
                                <Typography sx={{ color: '#cbd5e1', fontSize: '0.88rem', fontWeight: 700, lineHeight: 1.25 }}>
                                  @{reelItem.authorHandle}
                                </Typography>
                              </Link>
                            ) : reelItem.authorVerified ? (
                              <Box component="img" src={VERIFIED_BADGE_URL} alt="verified" sx={{ width: 15, height: 15 }} />
                            ) : null}
                            {reelItem.timeAgo ? (
                              <Typography sx={{ color: '#94a3b8', fontSize: '0.78rem', lineHeight: 1.25 }}>
                                · {reelItem.timeAgo}
                              </Typography>
                            ) : null}
                          </Box>
                          {reelItem.openOnXUrl ? (
                            <Link
                              href={reelItem.openOnXUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              underline="none"
                              sx={{
                                flexShrink: 0,
                                color: '#f8fafc',
                                fontSize: '0.74rem',
                                fontWeight: 800,
                                px: 1.15,
                                py: 0.5,
                                borderRadius: 999,
                                border: '1px solid rgba(255,255,255,0.26)',
                                background: 'linear-gradient(135deg, rgba(31,41,55,0.95), rgba(15,23,42,0.96))',
                                whiteSpace: 'nowrap',
                                '&:hover': {
                                  borderColor: 'rgba(255,255,255,0.45)',
                                  background: 'linear-gradient(135deg, rgba(51,65,85,0.95), rgba(15,23,42,0.98))',
                                },
                              }}
                            >
                              Open on X
                            </Link>
                          ) : null}
                        </Box>
                      </Box>
                    </Box>
                    {!hideGenericTitle && titleLine ? (
                      <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: '0.88rem', mb: 0.35, pointerEvents: 'auto' }}>
                        {titleLine}
                      </Typography>
                    ) : null}
                    {contentLine ? (
                      <Typography
                        sx={{
                          color: '#e2e8f0',
                          fontSize: '0.84rem',
                          lineHeight: 1.4,
                          display: '-webkit-box',
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                          pointerEvents: 'auto',
                        }}
                      >
                        {linkifyText(contentLine)}
                      </Typography>
                    ) : null}
                    {!reelItem.videoSrc && hasReelImageCarousel ? (
                      <Box sx={{ mt: 0.85, display: 'flex', justifyContent: 'center', pointerEvents: 'auto' }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.7 }}>
                          {reelImageUrls.map((img, dotIndex) => {
                            const isActive = dotIndex === activeReelImageIndex;
                            return (
                              <Box
                                key={`${reelItem.itemKey}-${img}-reel-dot`}
                                component="button"
                                type="button"
                                aria-label={`Go to image ${dotIndex + 1}`}
                                onClick={() => setActiveImageIndex(reelItem.itemKey, dotIndex, reelImageUrls.length)}
                                sx={{
                                  width: isActive ? 18 : 7,
                                  height: 7,
                                  borderRadius: 999,
                                  p: 0,
                                  border: 'none',
                                  cursor: 'pointer',
                                  backgroundColor: isActive ? '#fff' : 'rgba(255,255,255,0.45)',
                                  transition: 'all 180ms ease',
                                }}
                              />
                            );
                          })}
                        </Box>
                      </Box>
                    ) : null}
                  </Box>
                </Box>
              );
            })}
          </Box>
        )}
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
                {isSmallScreen ? 'News Feed' : 'Rugby Feed'}
              </Typography>
              {!isSmallScreen ? (
                <Typography sx={{ color: '#a7b2c7', fontSize: { xs: '0.72rem', sm: '0.78rem' }, mt: { xs: 0.05, sm: 0.15 }, lineHeight: 1.15 }}>
                  Latest updates and social highlights
                </Typography>
              ) : null}
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
                        <Box sx={{ mt: 1.1, width: '100%' }}>
                          <Box
                            sx={{
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
                            <Box
                              sx={{
                                display: 'flex',
                                width: '100%',
                                transform: `translateX(-${activeImageIndex * 100}%)`,
                                transition: 'transform 320ms cubic-bezier(0.22, 1, 0.36, 1)',
                                willChange: 'transform',
                              }}
                            >
                              {imageUrls.map((img, imageIndex) => (
                                <Box
                                  key={`${itemKey}-${img}-${imageIndex}`}
                                  sx={{
                                    minWidth: '100%',
                                    width: '100%',
                                    flexShrink: 0,
                                    display: 'grid',
                                    placeItems: 'center',
                                    backgroundColor: '#020617',
                                  }}
                                >
                                  <Box
                                    component="img"
                                    src={img}
                                    alt={item?.title || 'Post media'}
                                    loading="lazy"
                                    sx={{
                                      width: '100%',
                                      height: 'auto',
                                      maxHeight: '70vh',
                                      objectFit: 'contain',
                                      objectPosition: 'center',
                                      display: 'block',
                                      backgroundColor: '#020617',
                                      userSelect: 'none',
                                    }}
                                  />
                                </Box>
                              ))}
                            </Box>

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
                              </>
                            ) : null}
                          </Box>

                          {hasImageCarousel ? (
                            <Box sx={{ mt: 1.05, display: 'flex', justifyContent: 'center' }}>
                              <Box
                                sx={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 0.9,
                                  px: 1.25,
                                  py: 0.6,
                                  borderRadius: 999,
                                  background: 'linear-gradient(135deg, rgba(15,23,42,0.92), rgba(30,41,59,0.86))',
                                  border: '1px solid rgba(255,255,255,0.2)',
                                  boxShadow: '0 10px 26px rgba(2,6,23,0.2), inset 0 1px 0 rgba(255,255,255,0.08)',
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
                                        width: isActive ? 22 : 10,
                                        height: 10,
                                        borderRadius: 999,
                                        p: 0,
                                        border: isActive ? '1px solid rgba(255,255,255,0.72)' : '1px solid rgba(255,255,255,0.18)',
                                        cursor: 'pointer',
                                        background: isActive
                                          ? 'linear-gradient(90deg, #f8fafc 0%, #38bdf8 100%)'
                                          : 'rgba(148,163,184,0.5)',
                                        boxShadow: isActive ? '0 0 18px rgba(56,189,248,0.4)' : 'none',
                                        transition: 'all 220ms ease',
                                      }}
                                    />
                                  );
                                })}
                              </Box>
                            </Box>
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

