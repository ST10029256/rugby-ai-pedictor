import React, { memo, useState, useEffect } from 'react';
import { FormControl, InputLabel, Select, MenuItem } from '@mui/material';

const LeagueSelector = memo(function LeagueSelector({ leagues, selectedLeague, onLeagueChange }) {
  const [menuOpen, setMenuOpen] = useState(false);

  // Prevent main content scrolling when menu is open
  useEffect(() => {
    if (!menuOpen) return;

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
  }, [menuOpen]);
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
        value={selectedLeague ? String(selectedLeague) : ''}
        onChange={(e) => {
          console.log('League changed to:', e.target.value);
          onLeagueChange(parseInt(e.target.value));
        }}
        onOpen={() => setMenuOpen(true)}
        onClose={() => setMenuOpen(false)}
        label="Select League"
        MenuProps={{
          disablePortal: true, // Keep menu within drawer DOM to constrain it
          container: () => document.querySelector('.MuiDrawer-paper'), // Explicitly set container to drawer paper
          PaperProps: {
            sx: {
              maxHeight: 'none', // Show all options without scrolling
              width: '100%', // Match container width
              maxWidth: '280px', // Never exceed control panel width (280px)
              boxSizing: 'border-box',
              zIndex: 1400, // Higher than drawer (1200) and default menu (1300)
              mt: 0.5,
              backgroundColor: '#262730',
              border: '1px solid #4b5563',
              boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
              left: '0 !important', // Force left alignment
              right: 'auto !important',
              transformOrigin: 'top left !important',
              '& .MuiMenuItem-root': {
                px: 2,
                py: 1.5,
                color: '#fafafa',
                fontSize: '0.875rem', // Smaller text (14px instead of default 16px)
                '&:hover': {
                  backgroundColor: 'rgba(255, 255, 255, 0.1)',
                },
                '&.Mui-selected': {
                  backgroundColor: 'rgba(16, 185, 129, 0.2)',
                  '&:hover': {
                    backgroundColor: 'rgba(16, 185, 129, 0.3)',
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
          '@media (min-width: 769px)': {
            maxWidth: '232px', // Fixed width: 280px drawer - 48px padding
            width: '100%',
          },
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: '#4b5563',
          },
          '&:hover .MuiOutlinedInput-notchedOutline': {
            borderColor: '#6b7280',
          },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: '#10b981',
          },
          '& .MuiSelect-select': {
            width: '100%',
            maxWidth: '100%',
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            paddingRight: '24px', // Reduced from 32px to give more text space
            boxSizing: 'border-box',
            display: 'block',
            flex: '0 0 auto',
            flexShrink: 1,
            flexGrow: 0,
            '@media (min-width: 769px)': {
              maxWidth: 'calc(232px - 24px)', // Account for padding-right (reduced)
            },
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
        {leagues.map((league) => (
          <MenuItem key={league.id} value={String(league.id)}>
            {league.name}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
});

export default LeagueSelector;
