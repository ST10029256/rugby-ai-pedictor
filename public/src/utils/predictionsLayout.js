/** Shared max-width for predictions page widgets (metrics, odds, generate, results). */
export const predictionsWidgetSx = {
  width: '100%',
  maxWidth: { xs: 420, sm: '100%', md: 900, lg: '1600px' },
  boxSizing: 'border-box',
  mx: 'auto',
  '@media (min-width: 1440px)': {
    maxWidth: '1800px',
  },
  '@media (min-width: 1920px)': {
    maxWidth: '2000px',
  },
};
