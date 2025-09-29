// Console warning filter for Streamlit applications
(function() {
    'use strict';
    
    // List of blocked features that generate warnings
    const blockedFeatures = [
        'ambient-light-sensor',
        'battery',
        'document-domain', 
        'layout-animations',
        'legacy-image-formats',
        'oversized-images',
        'vr',
        'wake-lock'
    ];
    
    // Store original console methods
    const originalConsoleWarn = console.warn;
    const originalConsoleError = console.error;
    
    // Override console.warn to filter out browser API warnings
    console.warn = function(message, ...args) {
        if (typeof message === 'string') {
            // Check if message contains any blocked features
            const containsBlockedFeature = blockedFeatures.some(feature => 
                message.toLowerCase().includes(feature.toLowerCase())
            );
            
            if (containsBlockedFeature) {
                return; // Suppress this warning
            }
            
            // Check for "Unrecognized feature" pattern
            if (message.includes('Unrecognized feature') && 
                args.length > 0 && typeof args[0] === 'string') {
                const featureName = args[0];
                if (blockedFeatures.includes(featureName)) {
                    return; // Suppress this warning
                }
            }
        }
        
        // Call original console.warn for non-blocked messages
        originalConsoleWarn.apply(console, arguments);
    };
    
    // Override console.error to filter iframe security warnings
    console.error = function(message, ...args) {
        if (typeof message === 'string') {
            // Suppress iframe sandbox warnings
            if (message.includes('iframe') && message.includes('sandbox') && 
                message.includes('allow-scripts') && message.includes('allow-same-origin')) {
                return; // Suppress iframe security warning
            }
        }
        
        // Call original console.error for non-blocked messages
        originalConsoleError.apply(console, arguments);
    };
    
    // Prevent browser from detecting certain APIs
    const noop = function() { return Promise.resolve({state: 'denied'}); };
    
    // Override problematic API methods
    if (navigator.permissions && navigator.permissions.query) {
        const originalQuery = navigator.permissions.query.bind(navigator.permissions);
        
        navigator.permissions.query = function(permission) {
            if (typeof permission === 'object' && permission.name && 
                blockedFeatures.includes(permission.name)) {
                return Promise.resolve({state: 'denied'});
            }
            return originalQuery(permission);
        };
    }
    
    // Suppress performance warnings
    if (window.performance && window.performance.constructor) {
        try {
            const originalMark = window.performance.mark;
            window.performance.mark = function(...args) {
                // Only allow essential performance marks
                const allowedMarks = ['navigationStart', 'loadEventEnd', 'domContentLoaded'];
                if (args.length > 0 && typeof args[0] === 'string') {
                    if (!allowedMarks.includes(args[0])) {
                        return;
                    }
                }
                return originalMark.apply(window.performance, arguments);
            };
        } catch (e) {
            // Ignore errors
        }
    }
    
    // Prevent certain feature detection
    window.addEventListener('load', function() {
        // Override feature detection for blocked APIs
        blockedFeatures.forEach(feature => {
            if (feature in window || feature in navigator) {
                try {
                    Object.defineProperty(window, feature, {
                        get: function() { return undefined; },
                        set: function() { return undefined; },
                        configurable: false
                    });
                } catch (e) {
                    // Ignore if property cannot be overridden
                }
            }
        });
    });
    
})();
