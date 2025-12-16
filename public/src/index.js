import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import './App.css';
import App from './App';

// Media assets are loaded via video elements with preload="auto" attribute
// and via CSS background-image for images, which the browser handles automatically.
// No manual preloading needed - the browser's native preloading is more efficient.

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Prevent zooming on mobile devices
if (typeof window !== 'undefined') {
  // Prevent double-tap zoom
  let lastTouchEnd = 0;
  document.addEventListener('touchend', (event) => {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) {
      event.preventDefault();
    }
    lastTouchEnd = now;
  }, false);

  // Prevent pinch zoom
  document.addEventListener('gesturestart', (e) => {
    e.preventDefault();
  });

  document.addEventListener('gesturechange', (e) => {
    e.preventDefault();
  });

  document.addEventListener('gestureend', (e) => {
    e.preventDefault();
  });
}

// Register service worker for PWA (only if service-worker.js exists)
if ('serviceWorker' in navigator && process.env.NODE_ENV === 'production') {
  window.addEventListener('load', () => {
    // Check if service worker file exists before registering
    fetch('/service-worker.js', { method: 'HEAD' })
      .then(response => {
        if (response.ok) {
          return navigator.serviceWorker.register('/service-worker.js', { scope: '/' });
        } else {
          throw new Error('Service worker file not found');
        }
      })
      .then((registration) => {
        console.log('✅ Service Worker registered successfully');
        
        // Check for updates
        registration.addEventListener('updatefound', () => {
          console.log('Service Worker update found');
        });
      })
      .catch((registrationError) => {
        // Silently fail - service worker is optional
        // Only log if it's not a "file not found" error
        if (!registrationError.message.includes('not found')) {
          console.debug('Service Worker not available:', registrationError.message);
        }
      });
  });
}

