import React, { useState } from 'react';
import {
  Box,
  Paper,
  TextField,
  Button,
  Typography,
  Grid,
  CircularProgress,
  Alert,
  Card,
  CardContent,
} from '@mui/material';
import { predictMatch } from '../firebase';
import { format } from 'date-fns';

function MatchPredictor({ leagueId }) {
  const [homeTeam, setHomeTeam] = useState('');
  const [awayTeam, setAwayTeam] = useState('');
  const [matchDate, setMatchDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [loading, setLoading] = useState(false);
  const [prediction, setPrediction] = useState(null);
  const [error, setError] = useState(null);

  const handlePredict = async () => {
    if (!homeTeam || !awayTeam || !leagueId) {
      setError('Please fill in all fields');
      return;
    }

    setLoading(true);
    setError(null);
    setPrediction(null);

    try {
      const result = await predictMatch({
        home_team: homeTeam,
        away_team: awayTeam,
        league_id: leagueId,
        match_date: matchDate,
        enhanced: false,
      });

      setPrediction(result.data);
    } catch (err) {
      setError(err.message || 'Failed to get prediction');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h5" gutterBottom>
        Match Predictor
      </Typography>

      <Grid container spacing={2} sx={{ mt: 1 }}>
        <Grid item xs={12} md={4}>
          <TextField
            fullWidth
            label="Home Team"
            value={homeTeam}
            onChange={(e) => setHomeTeam(e.target.value)}
            placeholder="e.g., South Africa"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <TextField
            fullWidth
            label="Away Team"
            value={awayTeam}
            onChange={(e) => setAwayTeam(e.target.value)}
            placeholder="e.g., New Zealand"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <TextField
            fullWidth
            type="date"
            label="Match Date"
            value={matchDate}
            onChange={(e) => setMatchDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
        </Grid>
      </Grid>

      <Box sx={{ mt: 2 }}>
        <Button
          variant="contained"
          onClick={handlePredict}
          disabled={loading}
          fullWidth
          size="large"
        >
          {loading ? <CircularProgress size={24} /> : 'Get Prediction'}
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}

      {prediction && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Prediction Result
            </Typography>
            <Typography variant="body1">
              <strong>Predicted Winner:</strong> {prediction.predicted_winner}
            </Typography>
            <Typography variant="body1">
              <strong>Predicted Score:</strong> {prediction.predicted_home_score} - {prediction.predicted_away_score}
            </Typography>
            <Typography variant="body1">
              <strong>Confidence:</strong> {(prediction.confidence * 100).toFixed(1)}%
            </Typography>
            <Typography variant="body1">
              <strong>Home Win Probability:</strong> {(prediction.home_win_prob * 100).toFixed(1)}%
            </Typography>
            <Typography variant="body1">
              <strong>Away Win Probability:</strong> {(prediction.away_win_prob * 100).toFixed(1)}%
            </Typography>
          </CardContent>
        </Card>
      )}
    </Paper>
  );
}

export default MatchPredictor;

