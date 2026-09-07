import React, { useEffect } from 'react';
import { Box } from '@mui/material';
import RugbyBallLoader from '../components/RugbyBallLoader';

let mobileScrollLockCount = 0;

function addMobileScrollLock() {
  mobileScrollLockCount += 1;
  if (mobileScrollLockCount !== 1) return;
  const html = document.documentElement;
  const body = document.body;
  const root = document.getElementById('root');
  html.classList.add('view-loading');
  body.classList.add('view-loading');
  if (root) root.classList.add('view-loading');
  // Inline !important beats earlier page-scroll overflow:auto (prevents empty scroll while loading)
  html.style.setProperty('overflow', 'hidden', 'important');
  html.style.setProperty('overscroll-behavior', 'none', 'important');
  body.style.setProperty('overflow', 'hidden', 'important');
  body.style.setProperty('overscroll-behavior', 'none', 'important');
  if (root) root.style.setProperty('overflow', 'hidden', 'important');
}

function restorePageScrollOverflow() {
  const html = document.documentElement;
  const body = document.body;
  const root = document.getElementById('root');
  const pageScroll = html.classList.contains('news-page-scroll');
  if (pageScroll) {
    html.style.setProperty('overflow-y', 'auto', 'important');
    html.style.setProperty('overflow-x', 'hidden', 'important');
    html.style.removeProperty('overflow');
    html.style.removeProperty('overscroll-behavior');
    body.style.setProperty('overflow', 'visible', 'important');
    body.style.removeProperty('overscroll-behavior');
    if (root) root.style.setProperty('overflow', 'visible', 'important');
  } else {
    html.style.removeProperty('overflow');
    html.style.removeProperty('overflow-y');
    html.style.removeProperty('overflow-x');
    html.style.removeProperty('overscroll-behavior');
    body.style.removeProperty('overflow');
    body.style.removeProperty('overscroll-behavior');
    if (root) root.style.removeProperty('overflow');
  }
}

function removeMobileScrollLock() {
  mobileScrollLockCount = Math.max(0, mobileScrollLockCount - 1);
  if (mobileScrollLockCount > 0) return;
  const html = document.documentElement;
  const body = document.body;
  const root = document.getElementById('root');
  html.classList.remove('view-loading');
  body.classList.remove('view-loading');
  if (root) root.classList.remove('view-loading');
  restorePageScrollOverflow();
}

/**
 * Lock page rubber-band / empty scroll while a tab loader is up.
 * Applies on all viewports so short loaders can't create a fake scroll page.
 */
export function useViewLoadingScrollLock() {
  useEffect(() => {
    addMobileScrollLock();
    return () => removeMobileScrollLock();
  }, []);
}

/** Clear any stuck mobile loading lock (e.g. after nav change). */
export function clearViewLoadingScrollLock() {
  mobileScrollLockCount = 0;
  const html = document.documentElement;
  const body = document.body;
  const root = document.getElementById('root');
  html.classList.remove('view-loading');
  body.classList.remove('view-loading');
  if (root) root.classList.remove('view-loading');
  restorePageScrollOverflow();
}

/**
 * Loader overlay pinned to the main content section (not the full window).
 * On desktop this sits to the right of the 280px control panel and below the nav,
 * so the rugby-ball stays centered in the content column.
 */
export const VIEW_LOADER_SX = {
  position: 'fixed',
  top: 'var(--app-view-chrome, 0px)',
  right: 0,
  bottom: 0,
  left: 'var(--app-desktop-panel-width, 0px)',
  zIndex: 40,
  width: 'auto',
  height: 'auto',
  minHeight: 0,
  maxHeight: 'none',
  display: 'grid',
  placeItems: 'center',
  placeContent: 'center',
  boxSizing: 'border-box',
  margin: 0,
  overflow: 'hidden',
  pointerEvents: 'none',
};

/** Outer padding — clears fixed header via main pt; this adds balanced breathing room. */
export const VIEW_CONTENT_WRAPPER_SX = {
  width: '100%',
  maxWidth: '100%',
  mx: 0,
  px: { xs: 1.5, sm: 2.5, md: 3.5 },
  pb: { xs: 2, sm: 2.5, md: 3.5 },
  pt: {
    xs: 'var(--app-content-top-gap, 16px)',
    sm: 'var(--app-content-top-gap, 20px)',
    md: 'var(--app-content-top-gap, 24px)',
  },
  position: 'relative',
  minHeight: 0,
  overflowX: 'visible',
  overflowY: 'visible',
  boxSizing: 'border-box',
};

export const TabLoadingScreen = ({ label = 'Loading...' }) => {
  useViewLoadingScrollLock();

  return (
    <Box
      className="view-tab-loader"
      sx={VIEW_LOADER_SX}
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <RugbyBallLoader size={100} color="#10b981" compact label={label} />
    </Box>
  );
};
