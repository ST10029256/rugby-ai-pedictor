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
  Alert,
  useMediaQuery,
  useTheme,
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
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

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
        <Box sx={{ display: 'flex', alignItems: { xs: 'flex-start', sm: 'center' }, flexDirection: { xs: 'column', sm: 'row' }, gap: { xs: 1, sm: 0 }, mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <EmojiEventsIcon sx={{ mr: 1, color: '#fbbf24' }} />
            <Typography variant="h5" sx={{ fontWeight: 'bold', color: 'white', fontSize: { xs: '1.1rem', sm: '1.5rem' } }}>
              {leagueName || 'League'} Standings
            </Typography>
          </Box>
          {standings.league?.season && (
            <Chip
              label={`Season ${standings.league.season}`}
              size="small"
              sx={{
                ml: { xs: 0, sm: 2 },
                backgroundColor: 'rgba(255, 255, 255, 0.2)',
                color: 'white',
                alignSelf: { xs: 'flex-start', sm: 'center' },
              }}
            />
          )}
        </Box>

        {isMobile ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
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
                <Paper
                  key={teamData.id || index}
                  sx={{
                    p: 1.25,
                    borderRadius: 2,
                    backgroundColor: position <= 3 ? 'rgba(251, 191, 36, 0.08)' : 'rgba(255, 255, 255, 0.06)',
                    border: '1px solid rgba(255, 255, 255, 0.12)',
                    backdropFilter: 'blur(10px)',
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography sx={{ color: 'white', fontWeight: 800, fontSize: '0.95rem', lineHeight: 1.2 }} noWrap>
                        {position}. {teamName}
                      </Typography>
                      <Typography sx={{ color: 'rgba(255,255,255,0.75)', fontSize: '0.8rem', mt: 0.25 }}>
                        P {gamesPlayed} • W {wins} • D {draws} • L {loses}
                      </Typography>
                    </Box>
                    <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                      <Typography sx={{ color: '#fbbf24', fontWeight: 900, fontSize: '1.15rem', lineHeight: 1 }}>
                        {points}
                      </Typography>
                      <Typography sx={{ color: 'rgba(255,255,255,0.75)', fontSize: '0.75rem' }}>
                        Pts
                      </Typography>
                    </Box>
                  </Box>
                </Paper>
              );
            })}
          </Box>
        ) : (
          <TableContainer
            component={Paper}
            sx={{
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              backdropFilter: 'blur(10px)',
              maxHeight: 'none',
              overflowX: 'auto',
              overflowY: 'hidden',
              '&::-webkit-scrollbar': { height: 8 },
              '&::-webkit-scrollbar-thumb': { backgroundColor: 'rgba(255,255,255,0.18)', borderRadius: 8 },
            }}
          >
            <Table size="small" sx={{ minWidth: 600 }}>
              <TableHead>
                <TableRow sx={{ backgroundColor: 'rgba(0, 0, 0, 0.2)' }}>
                  <TableCell sx={{ color: 'white', fontWeight: 'bold', width: '60px' }}>Pos</TableCell>
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
        )}
      </CardContent>
    </Card>
  );
};

export default LeagueStandings;

