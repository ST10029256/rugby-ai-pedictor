import React, { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import CleaningServicesIcon from '@mui/icons-material/CleaningServices';
import { scanFirestoreMatches } from '../firebase';

function SummaryChip({ label, value, tone = 'default' }) {
  const palette = {
    default: { bg: 'rgba(255,255,255,0.06)', color: '#e5e7eb', border: 'rgba(255,255,255,0.12)' },
    warning: { bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: 'rgba(251,191,36,0.24)' },
    danger: { bg: 'rgba(239,68,68,0.12)', color: '#f87171', border: 'rgba(239,68,68,0.24)' },
    success: { bg: 'rgba(16,185,129,0.12)', color: '#34d399', border: 'rgba(16,185,129,0.24)' },
  }[tone];

  return (
    <Chip
      label={`${label}: ${value}`}
      size="small"
      sx={{
        backgroundColor: palette.bg,
        color: palette.color,
        border: `1px solid ${palette.border}`,
        fontWeight: 700,
      }}
    />
  );
}

const MatchDataHealth = () => {
  const [scanning, setScanning] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const hasIssues = useMemo(() => {
    if (!result) return false;
    return (
      (result.duplicate_docs || 0) > 0 ||
      (result.id_mismatches || 0) > 0 ||
      (result.missing_fixture_key_docs || 0) > 0 ||
      (result.duplicate_id_field_groups || 0) > 0
    );
  }, [result]);

  const runScan = async (removeDuplicates = false) => {
    const setBusy = removeDuplicates ? setCleaning : setScanning;
    setBusy(true);
    setError('');

    try {
      const response = await scanFirestoreMatches({
        remove_duplicates: removeDuplicates,
        confirm_remove: removeDuplicates,
      });
      setResult(response?.data || null);
    } catch (err) {
      setError(err?.message || 'Failed to scan Firestore matches.');
      setResult(null);
    } finally {
      setBusy(false);
      if (removeDuplicates) {
        setConfirmOpen(false);
      }
    }
  };

  return (
    <Box
      sx={{
        mt: 2,
        p: 2,
        borderRadius: 2,
        border: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(15, 23, 42, 0.45)',
      }}
    >
      <Typography
        variant="subtitle2"
        sx={{ color: '#f3f4f6', fontWeight: 800, mb: 0.5 }}
      >
        Match Data Health
      </Typography>
      <Typography variant="caption" sx={{ color: '#9ca3af', display: 'block', mb: 1.5 }}>
        Scan the Firestore <code>matches</code> collection for duplicate fixtures, ID mismatches, and missing fields.
      </Typography>

      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Button
          size="small"
          variant="contained"
          startIcon={scanning ? <CircularProgress size={14} color="inherit" /> : <SearchIcon />}
          disabled={scanning || cleaning}
          onClick={() => runScan(false)}
          sx={{
            textTransform: 'none',
            fontWeight: 700,
            backgroundColor: '#2563eb',
            '&:hover': { backgroundColor: '#1d4ed8' },
          }}
        >
          {scanning ? 'Scanning...' : 'Scan Matches'}
        </Button>

        <Button
          size="small"
          variant="outlined"
          startIcon={cleaning ? <CircularProgress size={14} color="inherit" /> : <CleaningServicesIcon />}
          disabled={scanning || cleaning || !result || !(result.duplicate_docs > 0)}
          onClick={() => setConfirmOpen(true)}
          sx={{
            textTransform: 'none',
            fontWeight: 700,
            borderColor: 'rgba(239,68,68,0.35)',
            color: '#fca5a5',
            '&:hover': {
              borderColor: 'rgba(239,68,68,0.55)',
              backgroundColor: 'rgba(239,68,68,0.08)',
            },
          }}
        >
          Remove Duplicates
        </Button>
      </Box>

      {error ? (
        <Alert severity="error" sx={{ mt: 1.5 }}>
          {error}
        </Alert>
      ) : null}

      <Collapse in={Boolean(result)}>
        {result ? (
          <Box sx={{ mt: 1.5 }}>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
              <SummaryChip label="Total docs" value={result.total_docs ?? 0} />
              <SummaryChip
                label="Duplicate docs"
                value={result.duplicate_docs ?? 0}
                tone={(result.duplicate_docs || 0) > 0 ? 'danger' : 'success'}
              />
              <SummaryChip
                label="Duplicate groups"
                value={result.duplicate_fixture_groups ?? 0}
                tone={(result.duplicate_fixture_groups || 0) > 0 ? 'warning' : 'default'}
              />
              <SummaryChip
                label="ID mismatches"
                value={result.id_mismatches ?? 0}
                tone={(result.id_mismatches || 0) > 0 ? 'warning' : 'default'}
              />
              <SummaryChip
                label="Missing fields"
                value={result.missing_fixture_key_docs ?? 0}
                tone={(result.missing_fixture_key_docs || 0) > 0 ? 'warning' : 'default'}
              />
              {result.removed_docs ? (
                <SummaryChip label="Removed" value={result.removed_docs} tone="success" />
              ) : null}
            </Box>

            <Typography variant="caption" sx={{ color: hasIssues ? '#fbbf24' : '#34d399', display: 'block' }}>
              {hasIssues
                ? 'Issues found. Review the sample groups below before removing duplicates.'
                : 'No duplicate fixtures or structural issues detected.'}
            </Typography>

            {(result.sample_duplicate_groups || []).length > 0 ? (
              <Box sx={{ mt: 1.5 }}>
                <Typography variant="caption" sx={{ color: '#d1d5db', fontWeight: 700 }}>
                  Sample duplicate fixture groups
                </Typography>
                <Box
                  sx={{
                    mt: 0.75,
                    maxHeight: 220,
                    overflowY: 'auto',
                    borderRadius: 1.5,
                    border: '1px solid rgba(255,255,255,0.08)',
                    backgroundColor: 'rgba(0,0,0,0.2)',
                    p: 1,
                  }}
                >
                  {result.sample_duplicate_groups.map((group) => (
                    <Box key={group.fixture_key} sx={{ mb: 1.25 }}>
                      <Typography variant="caption" sx={{ color: '#93c5fd', display: 'block', fontWeight: 700 }}>
                        {group.fixture_key} ({group.count} docs)
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#9ca3af', display: 'block' }}>
                        Keep: {group.keeper_doc_id}
                        {group.delete_doc_ids?.length ? ` | Remove: ${group.delete_doc_ids.join(', ')}` : ''}
                      </Typography>
                      <Divider sx={{ my: 0.75, borderColor: 'rgba(255,255,255,0.06)' }} />
                    </Box>
                  ))}
                </Box>
              </Box>
            ) : null}
          </Box>
        ) : null}
      </Collapse>

      <Dialog open={confirmOpen} onClose={() => !cleaning && setConfirmOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 800 }}>Remove duplicate match docs?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ color: '#4b5563' }}>
            This will delete {result?.duplicate_docs || 0} extra Firestore documents and keep the best document in each duplicate fixture group.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)} disabled={cleaning}>
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            disabled={cleaning}
            onClick={() => runScan(true)}
          >
            {cleaning ? 'Removing...' : 'Confirm Remove'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default MatchDataHealth;
