import React from 'react';
import { Box } from '@mui/material';

const RugbyBallLoader = ({ size = 120, color = '#10b981' }) => {
  // Calculate post positions - ball needs to go through the gap
  const postWidth = 6;
  const gapWidth = size * 0.5; // Gap between posts (wider for better visibility)
  const containerCenter = '50%';
  const leftPostLeft = `calc(${containerCenter} - ${gapWidth / 2}px)`;
  const rightPostLeft = `calc(${containerCenter} + ${gapWidth / 2}px)`;
  const crossbarTop = '50%'; // Position crossbar (matching HTML)
  const ballSize = size * 0.25;
  const height = 120; // Fixed height (matching HTML goal-posts-container)
  
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100%', // Take full height of parent
        minHeight: '400px', // Ensure minimum height for proper centering
        position: 'relative',
        // Match HTML container exactly - centers content both horizontally and vertically
        // Global keyframes - Smooth diagonal arc from bottom-left to top-right, going HIGHER through crossbar
        '@keyframes rugbyBallKick': {
          '0%': {
            transform: 'translate(-250%, 150%) rotate(0deg) scale(0.8)',
            opacity: 0.7,
          },
          '20%': {
            transform: 'translate(-150%, 20%) rotate(-216deg) scale(0.95)',
            opacity: 0.85,
          },
          '40%': {
            transform: 'translate(-50%, -60%) rotate(-432deg) scale(1.05)',
            opacity: 1,
          },
          '50%': {
            transform: 'translate(0%, -130%) rotate(-540deg) scale(1.1)',
            opacity: 1,
          },
          '60%': {
            transform: 'translate(50%, -150%) rotate(-648deg) scale(1.1)',
            opacity: 1,
          },
          '80%': {
            transform: 'translate(100%, -180%) rotate(-864deg) scale(1.0)',
            opacity: 0.9,
          },
          '100%': {
            transform: 'translate(150%, -200%) rotate(-1080deg) scale(0.8)',
            opacity: 0.7,
          },
        },
        '@keyframes postGlow': {
          '0%, 100%': { opacity: 0.7 },
          '50%': { opacity: 1 },
        },
        '@keyframes pulse': {
          '0%, 100%': { opacity: 0.6 },
          '50%': { opacity: 1 },
        },
      }}
    >
      {/* Wrapper to match HTML structure - centers goal posts and loading text */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '32px',
          transform: 'translateY(-5%)', // Move up slightly for better centering
        }}
      >
        {/* Goal Posts Container */}
        <Box
          sx={{
            position: 'relative',
            width: `${size * 1.5}px`,
            height: `${height}px`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
        {/* Left Post - Vertical */}
        <Box
          sx={{
            position: 'absolute',
            left: leftPostLeft,
            width: `${postWidth}px`,
            height: '100%',
            background: `linear-gradient(180deg, 
              #ffffff 0%, 
              #f8f9fa 20%, 
              #ffffff 40%,
              #f0f0f0 60%,
              #ffffff 80%,
              #e8e8e8 100%
            )`,
            borderRadius: '3px',
            boxShadow: `
              0 0 20px rgba(255, 255, 255, 0.8),
              inset 2px 0 4px rgba(255, 255, 255, 0.9),
              inset -2px 0 4px rgba(0, 0, 0, 0.1),
              0 4px 8px rgba(0, 0, 0, 0.2)
            `,
            zIndex: 5, // Left post z-index
            border: '1px solid rgba(255, 255, 255, 0.9)',
            '&::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: `linear-gradient(180deg, transparent 0%, ${color}20 50%, transparent 100%)`,
              borderRadius: '3px',
              animation: 'postGlow 2s ease-in-out infinite',
            },
          }}
        />
        
        {/* Right Post - Vertical */}
        <Box
          sx={{
            position: 'absolute',
            left: rightPostLeft,
            width: `${postWidth}px`,
            height: '100%',
            background: `linear-gradient(180deg, 
              #ffffff 0%, 
              #f8f9fa 20%, 
              #ffffff 40%,
              #f0f0f0 60%,
              #ffffff 80%,
              #e8e8e8 100%
            )`,
            borderRadius: '3px',
            boxShadow: `
              0 0 20px rgba(255, 255, 255, 0.8),
              inset 2px 0 4px rgba(255, 255, 255, 0.9),
              inset -2px 0 4px rgba(0, 0, 0, 0.1),
              0 4px 8px rgba(0, 0, 0, 0.2)
            `,
            zIndex: 8, // Highest z-index so ball can go behind it
            border: '1px solid rgba(255, 255, 255, 0.9)',
            '&::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: `linear-gradient(180deg, transparent 0%, ${color}20 50%, transparent 100%)`,
              borderRadius: '3px',
              animation: 'postGlow 2s ease-in-out infinite 0.5s',
            },
          }}
        />
        
        {/* Crossbar - Horizontal - Centered between posts, crosses OVER the ball */}
        <Box
          sx={{
            position: 'absolute',
            top: crossbarTop,
            left: leftPostLeft,
            width: `calc(${gapWidth}px + ${postWidth}px)`,
            height: `${postWidth}px`,
            background: `linear-gradient(90deg, 
              #ffffff 0%, 
              #f8f9fa 20%, 
              #ffffff 40%,
              #f0f0f0 60%,
              #ffffff 80%,
              #e8e8e8 100%
            )`,
            borderRadius: '3px',
            boxShadow: `
              0 0 20px rgba(255, 255, 255, 0.8),
              inset 0 2px 4px rgba(255, 255, 255, 0.9),
              inset 0 -2px 4px rgba(0, 0, 0, 0.1),
              0 4px 8px rgba(0, 0, 0, 0.2),
              0 -2px 4px rgba(0, 0, 0, 0.1)
            `,
            zIndex: 6, // Crossbar z-index
            border: '1px solid rgba(255, 255, 255, 0.9)',
            '&::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: `linear-gradient(90deg, transparent 0%, ${color}20 50%, transparent 100%)`,
              borderRadius: '3px',
              animation: 'postGlow 2s ease-in-out infinite 0.25s',
            },
          }}
        />
        
        {/* Rugby Ball - Goes through the gap UNDER the crossbar */}
        <Box
          sx={{
            position: 'absolute',
            width: `${ballSize}px`,
            height: `${ballSize * 0.65}px`,
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 6, // Between crossbar (6) and right post (8) so it can go behind right post
            animation: 'rugbyBallKick 2s linear infinite',
          }}
        >
          {/* Ball Shape */}
          <Box
            sx={{
              width: '100%',
              height: '100%',
              background: `radial-gradient(ellipse at 30% 30%, 
                #ffffff 0%, 
                #f8f9fa 15%,
                #e5e7eb 30%,
                #d1d5db 50%,
                #9ca3af 70%,
                #6b7280 100%
              )`,
              borderRadius: '50%',
              position: 'relative',
              boxShadow: `
                0 6px 12px rgba(0, 0, 0, 0.4),
                inset -3px -3px 6px rgba(0, 0, 0, 0.3),
                inset 3px 3px 6px rgba(255, 255, 255, 0.4),
                0 0 20px rgba(255, 255, 255, 0.2)
              `,
              border: '2px solid rgba(255, 255, 255, 0.3)',
              '&::before': {
                content: '""',
                position: 'absolute',
                top: '15%',
                left: '8%',
                width: '65%',
                height: '70%',
                border: '2.5px solid #6b7280',
                borderRadius: '50%',
                opacity: 0.7,
                boxShadow: 'inset 0 0 4px rgba(0, 0, 0, 0.3)',
              },
              '&::after': {
                content: '""',
                position: 'absolute',
                top: '25%',
                left: '20%',
                width: '55%',
                height: '50%',
                border: '2px solid #9ca3af',
                borderRadius: '50%',
                opacity: 0.5,
                boxShadow: 'inset 0 0 3px rgba(0, 0, 0, 0.2)',
              },
            }}
          />
        </Box>
        
        {/* Trailing Effect - Multiple layers for depth */}
        {[1, 2, 3].map((layer, idx) => {
          // Convert hex color to rgba
          const hexToRgba = (hex, alpha) => {
            const r = parseInt(hex.slice(1, 3), 16);
            const g = parseInt(hex.slice(3, 5), 16);
            const b = parseInt(hex.slice(5, 7), 16);
            return `rgba(${r}, ${g}, ${b}, ${alpha})`;
          };
          
          const trailConfigs = [
            { opacity: 0.075, zIndex: 0, blur: 10, colorAlpha: 0.35 },
            { opacity: 0.05, zIndex: -1, blur: 15, colorAlpha: 0.2 },
            { opacity: 0.0375, zIndex: -2, blur: 20, colorAlpha: 0.05 },
          ];
          const config = trailConfigs[idx];
          return (
            <Box
              key={idx}
              sx={{
                position: 'absolute',
                width: `${ballSize}px`,
                height: `${ballSize * 0.65}px`,
                left: '50%',
                top: '50%',
                transform: 'translate(-50%, -50%)',
                zIndex: config.zIndex,
                animation: `rugbyBallKick 2s cubic-bezier(0.4, 0, 0.2, 1) infinite`,
                animationDelay: `${(idx + 1) * 0.08}s`, // 0.08s, 0.16s, 0.24s
                opacity: config.opacity,
                '&::before': {
                  content: '""',
                  position: 'absolute',
                  width: '100%',
                  height: '100%',
                  background: `radial-gradient(ellipse, ${hexToRgba(color, config.colorAlpha)} 0%, transparent 70%)`,
                  borderRadius: '50%',
                  filter: `blur(${config.blur}px)`,
                },
              }}
            />
          );
        })}
        </Box>
        
        {/* Loading Text */}
        <Box
          sx={{
            color: color,
            fontSize: '0.875rem',
            fontWeight: 500,
            letterSpacing: '0.05em',
            animation: 'pulse 2s ease-in-out infinite',
            transform: 'translate(10%, 20%)',
          }}
        >
          Loading...
        </Box>
      </Box>
    </Box>
  );
};

export default RugbyBallLoader;
