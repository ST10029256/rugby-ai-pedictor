import React from 'react';
import './RugbyBallLoader.css';

const RugbyBallLoader = ({ color = '#10b981', compact = false, label = 'Loading...' }) => {
  return (
    <div className={`rbl ${compact ? 'rbl--compact' : 'rbl--full'}`}>
      <div className="rbl-inner">
        <div className="rbl-posts">
          <div className="rbl-post rbl-post-left" />
          <div className="rbl-post rbl-post-right" />
          <div className="rbl-crossbar" />
          <div className="rbl-ball">
            <div className="rbl-ball-shape" />
          </div>
        </div>
        {label ? (
          <div className="rbl-label" style={{ color }}>
            {label}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default RugbyBallLoader;
