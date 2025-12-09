import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import './App.css';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Register service worker for PWA
if ('serviceWorker' in navigator) {
  // Register immediately, don't wait for load
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
      .then((registration) => {
        console.log('✅ Service Worker registered successfully:', registration);
        console.log('Scope:', registration.scope);
        
        // Check for updates
        registration.addEventListener('updatefound', () => {
          console.log('Service Worker update found');
        });
      })
      .catch((registrationError) => {
        console.error('❌ Service Worker registration failed:', registrationError);
        console.error('Error details:', {
          message: registrationError.message,
          stack: registrationError.stack,
          name: registrationError.name
        });
      });
  });
  
  // Also try registering on page load (faster)
  if (document.readyState === 'complete') {
    navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
      .then((registration) => {
        console.log('✅ Service Worker registered (early):', registration);
      })
      .catch((error) => {
        console.log('Service Worker early registration failed (will retry on load):', error);
      });
  }
}

