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
        'iframe which has both allow-scripts and allow-same-origin',
        'An iframe which has both allow-scripts and allow-same-origin for its sandbox attribute can escape its sandboxing',
        'INITIAL ->',
        'RUNNING',
        'Pe @ index-B59N3yFD.js',
        'ambient-light-sensor'.toLowerCase(),
        'battery'.toLowerCase(),
        'document-domain'.toLowerCase(),
        'layout-animations'.toLowerCase(),
        'legacy-image-formats'.toLowerCase(),
        'oversized-images'.toLowerCase(),
        'vr'.toLowerCase(),
        'wake-lock'.toLowerCase()
    ];
    
    // Override console methods early with improved filtering
    const originalWarn = console.warn;
    const originalError = console.error;
    const originalLog = console.log;
    
    function shouldFilterMessage(args) {
        const message = args.join(' ').toLowerCase();
        
        // Check for exact patterns
        if (filterPatterns.some(pattern => 
            typeof pattern === 'string' && message.includes(pattern.toLowerCase()))) {
            return true;
        }
        
        // Additional specific patterns from your error log
        const specificPatterns = [
            'unrecognized feature:',
            'index-b59n3yfd.js',  // case insensitive file pattern
            'initial ->',
            'running',
            'pe @',
            'ambient-light-sensor',
            'document-domain',
            'layout-animations',
            'legacy-image-formats',
            'oversized-images',
            'iframe.*allow-scripts.*allow-same-origin'
        ];
        
        return specificPatterns.some(pattern => {
            const regex = new RegExp(pattern, 'i');
            return regex.test(message);
        });
    }
    
    console.warn = function(...args) {
        if (shouldFilterMessage(args)) {
            return; // Suppress this warning
        }
        originalWarn.apply(console, args);
    };
    
    console.error = function(...args) {
        if (shouldFilterMessage(args)) {
            return; // Suppress this error
        }
        originalError.apply(console, args);
    };
    
    console.log = function(...args) {
        if (shouldFilterMessage(args)) {
            return; // Suppress this log
        }
        originalLog.apply(console, args);
    };
    
    console.info('🔧 Streamlit Console Filter: Active');
    
})();
