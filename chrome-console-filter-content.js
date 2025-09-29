// Chrome Extension Content Script for Streamlit Console Filtering
(function() {
    'use strict';
    
    // List of warning patterns to filter
    const filterPatterns = [
        'Unrecognized feature:',
        'ambient-light-sensor',
        'battery',
        'document-domain',
        'layout-animations',
        'legacy-image-formats',
        'oversized-images',
        'vr',
        'wake-lock',
        'iframe which has both allow-scripts and allow-same-origin'
    ];
    
    // Override console methods early
    const originalWarn = console.warn;
    const originalError = console.error;
    
    console.warn = function(...args) {
        const message = args.join(' ');
        if (filterPatterns.some(pattern => message.includes(pattern))) {
            return; // Suppress this warning
        }
        originalWarn.apply(console, args);
    };
    
    console.error = function(...args) {
        const message = args.join(' ');
        if (filterPatterns.some(pattern => message.includes(pattern))) {
            return; // Suppress this error
        }
        originalError.apply(console, args);
    };
    
    // Also filter for logs that might match our patterns
    const originalLog = console.log;
    console.log = function(...args) {
        const message = args.join(' ');
        if (filterPatterns.some(pattern => message.includes(pattern))) {
            return; // Suppress this log
        }
        originalLog.apply(console, args);
    };
    
    console.info('🔧 Streamlit Console Filter: Active');
    
})();
