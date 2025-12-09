// Simple script to generate PWA icons
// Run with: node generate-icons.js
// Requires: npm install canvas (optional, will use HTML5 canvas API if available)

const fs = require('fs');
const path = require('path');

// Create a simple SVG icon that can be converted to PNG
const createSVGIcon = (size) => {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#10b981;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#059669;stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect width="${size}" height="${size}" fill="url(#grad)" rx="${size * 0.1}"/>
  <text x="50%" y="50%" font-family="Arial, sans-serif" font-size="${size * 0.6}" font-weight="bold" text-anchor="middle" dominant-baseline="central" fill="#ffffff">🏉</text>
  <rect width="${size}" height="${size}" fill="none" stroke="#ffffff" stroke-width="${size * 0.02}" rx="${size * 0.1}"/>
</svg>`;
};

// Try to use canvas if available, otherwise create SVG
try {
  const { createCanvas } = require('canvas');
  
  function generatePNGIcon(size) {
    const canvas = createCanvas(size, size);
    const ctx = canvas.getContext('2d');
    
    // Background gradient
    const gradient = ctx.createLinearGradient(0, 0, size, size);
    gradient.addColorStop(0, '#10b981');
    gradient.addColorStop(1, '#059669');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
    
    // Draw rugby ball emoji (as text)
    ctx.fillStyle = '#ffffff';
    ctx.font = `bold ${size * 0.6}px Arial`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('🏉', size / 2, size / 2);
    
    // Border
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = size * 0.02;
    ctx.strokeRect(size * 0.1, size * 0.1, size * 0.8, size * 0.8);
    
    return canvas.toBuffer('image/png');
  }
  
  const publicDir = path.join(__dirname, 'public');
  if (!fs.existsSync(publicDir)) {
    fs.mkdirSync(publicDir, { recursive: true });
  }
  
  // Generate 192x192 icon
  const icon192 = generatePNGIcon(192);
  fs.writeFileSync(path.join(publicDir, 'icon-192.png'), icon192);
  console.log('✅ Generated icon-192.png');
  
  // Generate 512x512 icon
  const icon512 = generatePNGIcon(512);
  fs.writeFileSync(path.join(publicDir, 'icon-512.png'), icon512);
  console.log('✅ Generated icon-512.png');
  
  console.log('\n🎉 Icons generated successfully!');
  console.log('Icons saved to:', publicDir);
  
} catch (error) {
  console.log('Canvas library not available. Generating SVG icons instead...');
  console.log('To generate PNG icons, run: npm install canvas');
  console.log('Or use the generate-icons.html file in the public folder.\n');
  
  const publicDir = path.join(__dirname, 'public');
  if (!fs.existsSync(publicDir)) {
    fs.mkdirSync(publicDir, { recursive: true });
  }
  
  // Generate SVG icons as fallback
  fs.writeFileSync(path.join(publicDir, 'icon-192.svg'), createSVGIcon(192));
  fs.writeFileSync(path.join(publicDir, 'icon-512.svg'), createSVGIcon(512));
  
  console.log('✅ Generated SVG icons (icon-192.svg, icon-512.svg)');
  console.log('Note: You need PNG files for PWA. Use generate-icons.html or install canvas.');
}

