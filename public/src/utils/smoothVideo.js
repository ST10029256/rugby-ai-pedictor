function getVideoSrc(video) {
  if (video.currentSrc) return video.currentSrc;
  if (video.src) return video.src;
  const source = video.querySelector('source');
  return source ? source.getAttribute('src') : '';
}

function looksLikeLocalFallback(src, localFallback) {
  if (!src || !localFallback) return false;
  const file = String(localFallback).split('/').pop();
  return Boolean(file) && String(src).includes(file);
}

export function attachSmoothVideo(video, { onReady, localFallback } = {}) {
  if (!video) return () => {};

  let cancelled = false;
  let revealed = false;
  let fallbackTried = false;

  video.muted = true;
  video.defaultMuted = true;
  video.playsInline = true;
  video.setAttribute('muted', '');
  video.setAttribute('playsinline', '');
  video.setAttribute('webkit-playsinline', 'true');
  video.preload = 'auto';
  video.loop = true;
  video.autoplay = true;

  const playSafe = () => {
    if (cancelled || document.hidden) return;
    const play = video.play();
    if (play && typeof play.catch === 'function') play.catch(() => {});
  };

  const reveal = () => {
    if (cancelled || revealed) return;
    revealed = true;
    onReady?.();
    playSafe();
  };

  const onCanPlay = () => reveal();
  const onLoadedData = () => {
    if (video.readyState >= 2) reveal();
  };
  const onPlaying = () => reveal();
  const onEnded = () => {
    try {
      video.currentTime = 0;
    } catch {
      /* ignore */
    }
    playSafe();
  };
  const onError = () => {
    if (cancelled || fallbackTried || !localFallback) return;
    if (looksLikeLocalFallback(getVideoSrc(video), localFallback)) return;
    fallbackTried = true;
    try {
      while (video.firstChild) video.removeChild(video.firstChild);
      video.src = localFallback;
      video.load();
      playSafe();
    } catch {
      /* ignore */
    }
  };
  const onVisibility = () => {
    if (document.hidden) {
      video.pause();
    } else {
      playSafe();
    }
  };

  video.addEventListener('canplay', onCanPlay);
  video.addEventListener('loadeddata', onLoadedData);
  video.addEventListener('playing', onPlaying);
  video.addEventListener('ended', onEnded);
  video.addEventListener('error', onError);
  document.addEventListener('visibilitychange', onVisibility);

  playSafe();
  if (video.readyState >= 2) reveal();

  const kick = window.setTimeout(() => {
    if (!revealed) reveal();
    playSafe();
  }, 1200);

  return () => {
    cancelled = true;
    window.clearTimeout(kick);
    video.removeEventListener('canplay', onCanPlay);
    video.removeEventListener('loadeddata', onLoadedData);
    video.removeEventListener('playing', onPlaying);
    video.removeEventListener('ended', onEnded);
    video.removeEventListener('error', onError);
    document.removeEventListener('visibilitychange', onVisibility);
  };
}
