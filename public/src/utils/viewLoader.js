import React from 'react';
import { Box } from '@mui/material';
import RugbyBallLoader from '../components/RugbyBallLoader';

/** Centered full-viewport loader container — matches Standings tab. */
export const VIEW_LOADER_SX = {
  width: '100%',
  minHeight: { xs: 'calc(100svh - 160px)', sm: 'calc(100vh - 180px)' },
  display: 'grid',
  placeItems: 'center',
  boxSizing: 'border-box',
};

/** Outer padding wrapper for News / Standings / Lineups / History tabs. */
export const VIEW_CONTENT_WRAPPER_SX = {
  width: '100%',
  maxWidth: '100%',
  mx: 0,
  p: { xs: 1.5, sm: 2.5, md: 3.5 },
  position: 'relative',
  minHeight: { xs: 'calc(100svh - 180px)', sm: 'calc(100vh - 200px)' },
  overflowX: 'visible',
  overflowY: 'visible',
  boxSizing: 'border-box',
};

export const TabLoadingScreen = ({ label = 'Loading...' }) => (
  <Box sx={VIEW_LOADER_SX}>
    <RugbyBallLoader size={100} color="#10b981" compact label={label} />
  </Box>
);
