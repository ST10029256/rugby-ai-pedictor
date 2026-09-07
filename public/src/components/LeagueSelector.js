import React, { memo, useRef, useState } from 'react';
import {
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  useMediaQuery,
  Chip,
  Box,
  Typography,
} from '@mui/material';

const MOBILE_BREAKPOINT = '(max-width:899.95px)';

const chipSx = (tone) => ({
  height: 22,
  maxWidth: '100%',
  fontSize: '0.7rem',
  fontWeight: 700,
  letterSpacing: '0.01em',
  backgroundColor:
    tone === 'upcoming' ? 'rgba(16, 185, 129, 0.18)' : 'rgba(59, 130, 246, 0.18)',
  color: tone === 'upcoming' ? '#6ee7b7' : '#93c5fd',
  border:
    tone === 'upcoming'
      ? '1px solid rgba(16, 185, 129, 0.35)'
      : '1px solid rgba(59, 130, 246, 0.35)',
  '& .MuiChip-label': {
    px: 0.9,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
});

const LeagueSelector = memo(function LeagueSelector({ leagues, selectedLeague, onLeagueChange }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuWidth, setMenuWidth] = useState(null);
  const [menuMaxHeight, setMenuMaxHeight] = useState(360);
  const controlRef = useRef(null);
  const isMobile = useMediaQuery(MOBILE_BREAKPOINT);

  const openMenu = () => {
    const node = controlRef.current;
    if (node) {
      const width = node.offsetWidth;
      if (width) setMenuWidth(width);
      const rect = node.getBoundingClientRect();
      // Always open downward: size menu to remaining space under the field
      const spaceBelow = Math.floor(window.innerHeight - rect.bottom - 12);
      const preferred = isMobile ? 420 : 480;
      setMenuMaxHeight(Math.max(140, Math.min(preferred, spaceBelow)));
    }
    setMenuOpen(true);
  };

  if (!leagues || leagues.length === 0) {
    return (
      <FormControl fullWidth>
        <InputLabel sx={{ color: '#fafafa' }}>Select League</InputLabel>
        <Select value="" label="Select League" disabled sx={{ color: '#fafafa' }}>
          <MenuItem value="">No leagues available</MenuItem>
        </Select>
      </FormControl>
    );
  }

  const paperWidth = menuWidth
    ? Math.max(menuWidth, isMobile ? 220 : 232)
    : isMobile
      ? 'min(100%, calc(100vw - 48px))'
      : 232;

  return (
    <FormControl
      ref={controlRef}
      fullWidth
      className="league-selector-control"
      sx={{
        maxWidth: '100%',
        width: '100%',
        minWidth: 0,
        cursor: 'pointer',
        '& .MuiInputLabel-root': { pointerEvents: 'none' },
        '& .MuiOutlinedInput-notchedOutline': { pointerEvents: 'none' },
        '& .MuiSelect-icon': { pointerEvents: 'none' },
      }}
    >
      <InputLabel
        id="league-select-label"
        shrink={Boolean(selectedLeague) || menuOpen}
        sx={{
          color: '#94a3b8',
          pointerEvents: 'none',
          '&.Mui-focused': { color: '#10b981' },
          '&.MuiInputLabel-shrink': { color: '#10b981' },
        }}
      >
        Select League
      </InputLabel>
      <Select
        labelId="league-select-label"
        value={selectedLeague ? String(selectedLeague) : ''}
        open={menuOpen}
        onOpen={openMenu}
        onClose={() => setMenuOpen(false)}
        onChange={(e) => {
          const next = parseInt(e.target.value, 10);
          if (!Number.isNaN(next)) onLeagueChange(next);
          setMenuOpen(false);
        }}
        label="Select League"
        renderValue={(value) => {
          if (!value) return '';
          const league = leagues.find((l) => String(l.id) === String(value));
          return league ? league.name : 'Select League';
        }}
        MenuProps={{
          disablePortal: false,
          disableScrollLock: true,
          keepMounted: false,
          // Never flip upward when viewport height is short
          marginThreshold: null,
          transitionDuration: { enter: 120, exit: 90 },
          sx: { zIndex: 2400 },
          slotProps: {
            root: {
              onTouchMove: (event) => event.stopPropagation(),
            },
          },
          PaperProps: {
            className: 'league-selector-menu-paper',
            sx: {
              width: paperWidth,
              maxWidth: isMobile ? 'calc(100vw - 32px)' : paperWidth,
              maxHeight: menuMaxHeight,
              mt: 0.5,
              py: 0.5,
              backgroundColor: '#111827',
              backgroundImage: 'none',
              border: '1px solid rgba(16, 185, 129, 0.28)',
              borderRadius: '14px',
              boxShadow: '0 16px 40px rgba(0, 0, 0, 0.55)',
              overflowX: 'hidden',
              overflowY: 'auto',
              WebkitOverflowScrolling: 'touch',
              overscrollBehavior: 'contain',
              scrollbarWidth: 'none',
              msOverflowStyle: 'none',
              '&::-webkit-scrollbar': {
                display: 'none',
                width: 0,
                height: 0,
              },
              zIndex: 2401,
              '& .MuiList-root': {
                py: 0.25,
              },
              '& .MuiMenuItem-root': {
                display: 'flex',
                justifyContent: 'center',
                px: 1.5,
                py: 1.15,
                mx: 0.5,
                my: 0.25,
                borderRadius: '10px',
                color: '#f1f5f9',
                minHeight: 0,
                whiteSpace: 'normal',
                textAlign: 'center',
                alignItems: 'center',
                '&.Mui-selected': {
                  backgroundColor: 'rgba(16, 185, 129, 0.2)',
                  '&:hover': {
                    backgroundColor: 'rgba(16, 185, 129, 0.28)',
                  },
                },
                '&:hover': {
                  backgroundColor: 'rgba(148, 163, 184, 0.1)',
                },
                '&.Mui-focusVisible': {
                  backgroundColor: 'rgba(16, 185, 129, 0.16)',
                },
              },
            },
          },
          MenuListProps: {
            autoFocusItem: false,
            dense: false,
            disablePadding: false,
          },
          anchorOrigin: { vertical: 'bottom', horizontal: 'left' },
          transformOrigin: { vertical: 'top', horizontal: 'left' },
          disableAutoFocusItem: true,
        }}
        sx={{
          color: '#fafafa',
          width: '100%',
          cursor: 'pointer',
          backgroundColor: 'rgba(31, 41, 55, 0.85)',
          borderRadius: '12px',
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: menuOpen ? '#10b981' : 'rgba(16, 185, 129, 0.25)',
            borderWidth: menuOpen ? '2px' : '1.5px',
            pointerEvents: 'none',
          },
          '&:hover .MuiOutlinedInput-notchedOutline': {
            borderColor: 'rgba(16, 185, 129, 0.5)',
          },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: '#10b981',
            borderWidth: '2px',
          },
          '& .MuiSelect-select': {
            width: '100%',
            cursor: 'pointer',
            py: 1.5,
            pl: 1.75,
            pr: '44px !important',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            fontWeight: 600,
            fontSize: '0.9375rem',
            lineHeight: 1.35,
            minHeight: 24,
          },
          '& .MuiSelect-icon': {
            color: '#10b981',
            right: 12,
            pointerEvents: 'none',
            transition: 'transform 0.18s ease',
            transform: menuOpen ? 'rotate(180deg)' : 'none',
          },
        }}
      >
        {leagues.map((league) => {
          const upcoming = league.upcoming_matches || 0;
          const recent = league.recent_matches || 0;
          const hasMeta = upcoming > 0 || recent > 0;
          const muted = !(league.has_news || hasMeta);

          return (
            <MenuItem
              key={league.id}
              value={String(league.id)}
              sx={{ opacity: muted ? 0.55 : 1 }}
            >
              <Box
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: hasMeta ? 0.75 : 0,
                  width: '100%',
                  minWidth: 0,
                  textAlign: 'center',
                }}
              >
                <Typography
                  component="span"
                  sx={{
                    display: 'block',
                    width: '100%',
                    color: 'inherit',
                    fontSize: '0.9rem',
                    fontWeight: 600,
                    lineHeight: 1.35,
                    textAlign: 'center',
                    whiteSpace: 'normal',
                    overflowWrap: 'anywhere',
                    wordBreak: 'break-word',
                  }}
                >
                  {league.name}
                </Typography>
                {hasMeta ? (
                  <Box
                    sx={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: 0.6,
                      justifyContent: 'center',
                      width: '100%',
                      minWidth: 0,
                    }}
                  >
                    {upcoming > 0 ? (
                      <Chip
                        size="small"
                        label={`${upcoming} upcoming`}
                        sx={chipSx('upcoming')}
                      />
                    ) : null}
                    {recent > 0 ? (
                      <Chip
                        size="small"
                        label={`${recent} recent`}
                        sx={chipSx('recent')}
                      />
                    ) : null}
                  </Box>
                ) : null}
              </Box>
            </MenuItem>
          );
        })}
      </Select>
    </FormControl>
  );
});

export default LeagueSelector;
