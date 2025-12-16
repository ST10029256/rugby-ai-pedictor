import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
} from '@mui/material';
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents';
import { getLeagueStandings } from '../firebase';
import RugbyBallLoader from './RugbyBallLoader';

// League ID mapping: Our league ID -> Highlightly league ID
const LEAGUE_ID_MAPPING = {
  4986: 73119, // Rugby Championship
  4446: 65460, // United Rugby Championship
  5069: 32271, // Currie Cup
  4574: 59503, // Rugby World Cup (no standings)
  4551: 61205, // Super Rugby
  4430: 14400, // French Top 14
  4414: 11847, // English Premiership Rugby (CORRECTED: was 5039 which was Austrian league)
  4714: 44185, // Six Nations Championship
  5479: 72268, // Rugby Union International Friendlies (Friendly International - no standings as friendlies don't have league tables)
};

const LeagueStandings = ({ leagueId, leagueName }) => {
  const [standings, setStandings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Prevent body scroll when loading
  useEffect(() => {
    if (loading) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [loading]);

  useEffect(() => {
    const loadStandings = async () => {
      if (!leagueId) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        
        const highlightlyLeagueId = LEAGUE_ID_MAPPING[leagueId];
        if (!highlightlyLeagueId) {
          setError('Standings not available for this league');
          setLoading(false);
          return;
        }
        
        // Special handling for International Friendlies - they don't have standings
        if (leagueId === 5479) {
          setError('Standings are not available for International Friendlies. Friendlies are exhibition matches and do not have league tables.');
          setLoading(false);
          return;
        }

        const data = await getLeagueStandings(highlightlyLeagueId);
        
        if (data && data.success && data.standings) {
          setStandings(data.standings);
        } else {
          setError(data?.error || 'No standings data available');
        }
      } catch (err) {
        console.error('Error loading standings:', err);
        setError('Failed to load standings');
      } finally {
        setLoading(false);
      }
    };

    loadStandings();
  }, [leagueId]);

  if (!leagueId) {
    return null;
  }

  if (loading) {
    return (
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        minHeight: 'calc(100vh - 200px)', 
        height: '100vh',
        width: '100%',
        position: 'relative',
        margin: { xs: '-16px', sm: '-24px', md: '-32px' },
      }}>
        <Box sx={{
          transform: { xs: 'translateX(16px)', sm: 'translate(32px, -69px)' },
        }}>
          <RugbyBallLoader size={120} color="#10b981" />
        </Box>
      </Box>
    );
  }

  if (error) {
    return (
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Alert severity="info">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  if (!standings || !standings.groups || standings.groups.length === 0) {
    return (
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Alert severity="info">No standings data available for {leagueName || 'this league'}</Alert>
        </CardContent>
      </Card>
    );
  }

  // Get the first group (most leagues have one group)
  const group = standings.groups[0];
  const teams = group.standings || group.teams || [];

  if (teams.length === 0) {
    return (
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Alert severity="info">No teams found in standings</Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card sx={{ mb: 3, background: 'linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%)' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <EmojiEventsIcon sx={{ mr: 1, color: '#fbbf24' }} />
          <Typography variant="h5" sx={{ fontWeight: 'bold', color: 'white' }}>
            {leagueName || 'League'} Standings
          </Typography>
          {standings.league?.season && (
            <Chip
              label={`Season ${standings.league.season}`}
              size="small"
              sx={{ ml: 2, backgroundColor: 'rgba(255, 255, 255, 0.2)', color: 'white' }}
            />
          )}
        </Box>

        <TableContainer component={Paper} sx={{ backgroundColor: 'rgba(255, 255, 255, 0.05)', backdropFilter: 'blur(10px)', maxHeight: 'none', overflow: 'visible' }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ backgroundColor: 'rgba(0, 0, 0, 0.2)' }}>
                <TableCell sx={{ color: 'white', fontWeight: 'bold', width: '50px' }}>Pos</TableCell>
                <TableCell sx={{ color: 'white', fontWeight: 'bold' }}>Team</TableCell>
                <TableCell align="center" sx={{ color: 'white', fontWeight: 'bold' }}>P</TableCell>
                <TableCell align="center" sx={{ color: 'white', fontWeight: 'bold' }}>W</TableCell>
                <TableCell align="center" sx={{ color: 'white', fontWeight: 'bold' }}>D</TableCell>
                <TableCell align="center" sx={{ color: 'white', fontWeight: 'bold' }}>L</TableCell>
                <TableCell align="center" sx={{ color: 'white', fontWeight: 'bold' }}>Pts</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {teams.map((team, index) => {
                const teamData = team.team || team;
                const teamName = teamData.name || teamData.team_name || 'Unknown';
                const position = team.position || index + 1;
                const points = team.points || 0;
                const wins = team.wins || 0;
                const draws = team.draws || 0;
                const loses = team.loses || team.losses || 0;
                const gamesPlayed = team.gamesPlayed || (wins + draws + loses);

                return (
                  <TableRow
                    key={teamData.id || index}
                    sx={{
                      '&:hover': { backgroundColor: 'rgba(255, 255, 255, 0.1)' },
                      backgroundColor: position <= 3 ? 'rgba(251, 191, 36, 0.1)' : 'transparent',
                    }}
                  >
                    <TableCell sx={{ color: 'white', fontWeight: position <= 3 ? 'bold' : 'normal' }}>
                      {position <= 3 && <EmojiEventsIcon sx={{ fontSize: 16, mr: 0.5, color: '#fbbf24', verticalAlign: 'middle' }} />}
                      {position}
                    </TableCell>
                    <TableCell sx={{ color: 'white', fontWeight: position <= 3 ? 'bold' : 'normal' }}>
                      {teamName}
                    </TableCell>
                    <TableCell align="center" sx={{ color: 'white' }}>{gamesPlayed}</TableCell>
                    <TableCell align="center" sx={{ color: 'white' }}>{wins}</TableCell>
                    <TableCell align="center" sx={{ color: 'white' }}>{draws}</TableCell>
                    <TableCell align="center" sx={{ color: 'white' }}>{loses}</TableCell>
                    <TableCell align="center" sx={{ color: 'white', fontWeight: 'bold' }}>{points}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
};

export default LeagueStandings;

