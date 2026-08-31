import React, { useEffect, useMemo, useState } from 'react';
import { Box } from '@mui/material';
import { buildTeamLogoCandidates } from '../utils/teamLogos';

/**
 * Shared team crest — tries standings URL then static fallbacks before initial avatar.
 */
const TeamLogoImage = ({
  teamName,
  leagueId = null,
  logoMap = {},
  explicitLogo = null,
  size = { xs: 64, sm: 80 },
  alt,
}) => {
  const name = teamName || alt || '';
  const candidates = useMemo(
    () => buildTeamLogoCandidates(name, { leagueId, logoMap, explicitLogo }),
    [name, leagueId, logoMap, explicitLogo]
  );

  const [candidateIndex, setCandidateIndex] = useState(0);
  const candidateKey = candidates.join('|');

  useEffect(() => {
    setCandidateIndex(0);
  }, [name, candidateKey]);

  const src = candidates[candidateIndex] || null;
  const w = size;
  const h = size;

  if (!src || candidateIndex >= candidates.length) {
    return (
      <Box
        sx={{
          width: w,
          height: h,
          borderRadius: '50%',
          display: 'grid',
          placeItems: 'center',
          bgcolor: 'rgba(16,185,129,0.12)',
          border: '2px solid rgba(16,185,129,0.28)',
          fontWeight: 900,
          color: '#fff',
          fontSize: { xs: '1.35rem', sm: '1.65rem' },
          flexShrink: 0,
        }}
      >
        {(name || '?').charAt(0)}
      </Box>
    );
  }

  return (
    <Box
      component="img"
      src={src}
      alt={alt || name}
      referrerPolicy="no-referrer"
      loading="lazy"
      onError={() => {
        setCandidateIndex((prev) => (prev + 1 < candidates.length ? prev + 1 : candidates.length));
      }}
      sx={{
        width: w,
        height: h,
        objectFit: 'contain',
        flexShrink: 0,
        filter: 'drop-shadow(0 10px 20px rgba(0,0,0,0.45))',
      }}
    />
  );
};

export default TeamLogoImage;
