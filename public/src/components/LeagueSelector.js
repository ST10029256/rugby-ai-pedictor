import React, { memo, useState, useEffect } from 'react';
import { FormControl, InputLabel, Select, MenuItem, useMediaQuery, Chip, Box } from '@mui/material';

const LeagueSelector = memo(function LeagueSelector({ leagues, selectedLeague, onLeagueChange }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const isMobile = useMediaQuery('(max-width:768px)');

  // Prevent main content scrolling when menu is open (mobile only)
  useEffect(() => {
    if (!menuOpen || !isMobile) return;

    const body = document.body;
    const mainContent = document.querySelector('main') || document.querySelector('.main-content-wrapper');
    
    // Store original scroll position
    const scrollY = window.scrollY;
    const mainScrollTop = mainContent ? mainContent.scrollTop : 0;
    
    // Disable scrolling
    body.classList.add('menu-open');
    body.style.overflow = 'hidden';
    body.style.position = 'fixed';
    body.style.top = `-${scrollY}px`;
    body.style.width = '100%';
    
    if (mainContent) {
      mainContent.style.overflow = 'hidden';
    }

    return () => {
      // Restore scrolling when menu closes
      body.classList.remove('menu-open');
      body.style.overflow = '';
      body.style.position = '';
      body.style.top = '';
      body.style.width = '';
      
      // Restore scroll position
      window.scrollTo(0, scrollY);
      
      if (mainContent) {
        mainContent.style.overflow = '';
        mainContent.scrollTop = mainScrollTop;
      }
    };
  }, [menuOpen, isMobile]);
  if (!leagues || leagues.length === 0) {
    return (
      <FormControl fullWidth>
        <InputLabel 
          sx={{ 
            color: '#fafafa',
            '@media (min-width: 769px)': {
              overflow: 'visible',
              whiteSpace: 'nowrap',
              maxWidth: '100%',
            },
          }}
        >
          Select League
        </InputLabel>
        <Select
          value=""
          label="Select League"
          disabled
          sx={{
            color: '#fafafa',
            '& .MuiOutlinedInput-notchedOutline': {
              borderColor: '#4b5563',
            },
          }}
        >
          <MenuItem value="">No leagues available</MenuItem>
        </Select>
      </FormControl>
    );
  }
  
  return (
    <FormControl 
      fullWidth
      sx={{
        '@media (min-width: 769px)': {
          maxWidth: '232px', // Fixed width on desktop
          width: '100%',
        },
      }}
    >
      <InputLabel 
        id="league-select-label"
        shrink={!!selectedLeague}
        sx={{ 
          color: '#fafafa',
          '@media (min-width: 769px)': {
            overflow: 'visible',
            whiteSpace: 'nowrap',
            maxWidth: '100%',
          },
        }}
      >
        Select League
      </InputLabel>
      <Select
        labelId="league-select-label"
        value={selectedLeague ? String(selectedLeague) : ''}
        onChange={(e) => {
          onLeagueChange(parseInt(e.target.value));
        }}
        onOpen={() => setMenuOpen(true)}
        onClose={() => setMenuOpen(false)}
        label="Select League"
        displayEmpty={false}
        renderValue={(value) => {
          if (!value) return '';
          const league = leagues.find(l => String(l.id) === String(value));
          return league ? league.name : 'Select League';
        }}
        MenuProps={{
          disablePortal: false, // Use portal to prevent layout shifts
          disableScrollLock: true, // Prevent scroll lock on desktop
          PaperProps: {
            sx: {
              maxHeight: 'none', // Show all leagues without scrolling
              width: 'auto',
              minWidth: '200px',
              maxWidth: '280px', // Never exceed control panel width (280px)
              boxSizing: 'border-box',
              zIndex: 1400, // Higher than drawer (1200) and default menu (1300)
              mt: 0.5,
              backgroundColor: '#1f2937',
              backgroundImage: 'linear-gradient(135deg, #1f2937 0%, #111827 100%)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              borderRadius: '12px',
              boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(16, 185, 129, 0.1)',
              position: 'absolute', // Ensure absolute positioning
              overflow: 'visible', // Allow all items to show
              '& .MuiMenuItem-root': {
                px: 2.5,
                py: 1.25,
                color: '#fafafa',
                fontSize: '0.875rem',
                fontWeight: 500,
                borderRadius: '8px',
                margin: '2px 8px',
                transition: 'all 0.2s ease',
                '&:hover': {
                  backgroundColor: 'rgba(16, 185, 129, 0.15)',
                  transform: 'translateX(4px)',
                  boxShadow: '0 2px 8px rgba(16, 185, 129, 0.2)',
                },
                '&.Mui-selected': {
                  backgroundColor: 'rgba(16, 185, 129, 0.25)',
                  color: '#10b981',
                  fontWeight: 600,
                  '&:hover': {
                    backgroundColor: 'rgba(16, 185, 129, 0.35)',
                  },
                  '&::before': {
                    content: '""',
                    position: 'absolute',
                    left: 0,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: '3px',
                    height: '60%',
                    backgroundColor: '#10b981',
                    borderRadius: '0 2px 2px 0',
                  },
                },
              },
            },
          },
          anchorOrigin: {
            vertical: 'bottom',
            horizontal: 'left',
          },
          transformOrigin: {
            vertical: 'top',
            horizontal: 'left',
          },
          // Prevent menu from affecting layout
          disableAutoFocusItem: true,
        }}
        sx={{
          color: '#fafafa',
          width: '100%',
          maxWidth: '100%',
          minWidth: 0,
          boxSizing: 'border-box',
          flexShrink: 1,
          flexGrow: 0,
          flexBasis: 'auto',
          backgroundColor: 'rgba(31, 41, 55, 0.6)',
          borderRadius: '12px',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '@media (min-width: 769px)': {
            maxWidth: '232px', // Fixed width: 280px drawer - 48px padding
            width: '100%',
          },
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: 'rgba(16, 185, 129, 0.2)',
            borderWidth: '1.5px',
            transition: 'all 0.3s ease',
          },
          '&:hover .MuiOutlinedInput-notchedOutline': {
            borderColor: 'rgba(16, 185, 129, 0.4)',
            boxShadow: '0 0 0 3px rgba(16, 185, 129, 0.1)',
          },
          '&.Mui-focused': {
            backgroundColor: 'rgba(31, 41, 55, 0.8)',
            boxShadow: '0 4px 16px rgba(16, 185, 129, 0.2), inset 0 0 0 1px rgba(16, 185, 129, 0.3)',
          },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: '#10b981',
            borderWidth: '2px',
            boxShadow: '0 0 0 4px rgba(16, 185, 129, 0.15)',
          },
          '& .MuiSelect-select': {
            width: '100%',
            maxWidth: '100%',
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            paddingRight: '24px',
            paddingLeft: '14px',
            paddingTop: '14px',
            paddingBottom: '14px',
            boxSizing: 'border-box',
            display: 'block',
            flex: '0 0 auto',
            flexShrink: 1,
            flexGrow: 0,
            fontWeight: 500,
            fontSize: '0.9375rem',
            '@media (min-width: 769px)': {
              maxWidth: 'calc(232px - 24px)',
            },
          },
          '& .MuiSelect-icon': {
            color: '#10b981',
            fontSize: '1.5rem',
            right: '12px',
            transition: 'transform 0.3s ease',
          },
          '&.Mui-focused .MuiSelect-icon': {
            transform: 'rotate(180deg)',
          },
          '& .MuiOutlinedInput-root': {
            width: '100%',
            maxWidth: '100%',
            minWidth: 0,
            boxSizing: 'border-box',
            overflow: 'hidden',
            flexShrink: 1,
            flexGrow: 0,
            flexBasis: 'auto',
            '@media (min-width: 769px)': {
              maxWidth: '232px',
            },
          },
          '& .MuiInputBase-root': {
            width: '100%',
            maxWidth: '100%',
            minWidth: 0,
            boxSizing: 'border-box',
            flexShrink: 1,
            flexGrow: 0,
            '@media (min-width: 769px)': {
              maxWidth: '232px',
            },
          },
        }}
      >
        {leagues.map((league) => {
          const upcoming = league.upcoming_matches || 0;
          const recent = league.recent_matches || 0;
          const hasNews = league.has_news || (upcoming > 0 || recent > 0);
          const totalNews = upcoming + recent;
          
          return (
            <MenuItem 
              key={league.id} 
              value={String(league.id)}
              sx={{
                opacity: hasNews ? 1 : 0.6,
                '&:hover': {
                  opacity: 1,
                },
              }}
            >
              <Box sx={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'space-between',
                width: '100%',
                gap: 1,
              }}>
                <Box component="span" sx={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {league.name}
                </Box>
                {hasNews && (
                  <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', flexShrink: 0 }}>
                    {upcoming > 0 && (
                      <Chip
                        label={`${upcoming} upcoming`}
                        size="small"
                        sx={{
                          height: '20px',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          backgroundColor: 'rgba(16, 185, 129, 0.2)',
                          color: '#10b981',
                          border: '1px solid rgba(16, 185, 129, 0.3)',
                          '& .MuiChip-label': {
                            padding: '0 6px',
                          },
                        }}
                      />
                    )}
                    {recent > 0 && (
                      <Chip
                        label={`${recent} recent`}
                        size="small"
                        sx={{
                          height: '20px',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          backgroundColor: 'rgba(59, 130, 246, 0.2)',
                          color: '#3b82f6',
                          border: '1px solid rgba(59, 130, 246, 0.3)',
                          '& .MuiChip-label': {
                            padding: '0 6px',
                          },
                        }}
                      />
                    )}
                  </Box>
                )}
              </Box>
            </MenuItem>
          );
        })}
      </Select>
    </FormControl>
  );
});

export default LeagueSelector;
