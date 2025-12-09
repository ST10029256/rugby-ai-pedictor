import React from 'react';
import { FormControl, InputLabel, Select, MenuItem } from '@mui/material';

function LeagueSelector({ leagues, selectedLeague, onLeagueChange }) {
  console.log('LeagueSelector received leagues:', leagues);
  console.log('LeagueSelector selectedLeague:', selectedLeague);
  
  if (!leagues || leagues.length === 0) {
    return (
      <FormControl fullWidth>
        <InputLabel sx={{ color: '#fafafa' }}>Select League</InputLabel>
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
    <FormControl fullWidth>
      <InputLabel sx={{ color: '#fafafa' }}>Select League</InputLabel>
      <Select
        value={selectedLeague ? String(selectedLeague) : ''}
        onChange={(e) => {
          console.log('League changed to:', e.target.value);
          onLeagueChange(parseInt(e.target.value));
        }}
        label="Select League"
        sx={{
          color: '#fafafa',
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: '#4b5563',
          },
          '&:hover .MuiOutlinedInput-notchedOutline': {
            borderColor: '#6b7280',
          },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: '#10b981',
          },
        }}
      >
        {leagues.map((league) => {
          console.log('Rendering league option:', league);
          return (
            <MenuItem key={league.id} value={String(league.id)}>
              {league.name}
            </MenuItem>
          );
        })}
      </Select>
    </FormControl>
  );
}

export default LeagueSelector;
