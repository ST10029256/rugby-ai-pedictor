// Script to resize logo.png to icon sizes
// Run with: node resize-logo.js
// Requires: npm install canvas

const fs = require('fs');
const path = require('path');

try {
  const { createCanvas, loadImage } = require('canvas');
  
  async function resizeLogo() {
    const publicDir = path.join(__dirname, 'public');
    const logoPath = path.join(publicDir, 'logo.png');
    
    if (!fs.existsSync(logoPath)) {
      console.error('❌ logo.png not found in public/public/ folder');
      process.exit(1);
    }
    
    console.log('📸 Loading logo.png...');
    const logo = await loadImage(logoPath);
    
    // Resize to 192x192
    console.log('🔄 Resizing to 192x192...');
    const canvas192 = createCanvas(192, 192);
    const ctx192 = canvas192.getContext('2d');
    ctx192.drawImage(logo, 0, 0, 192, 192);
    const icon192 = canvas192.toBuffer('image/png');
    fs.writeFileSync(path.join(publicDir, 'icon-192.png'), icon192);
    console.log('✅ Created icon-192.png');
    
    // Resize to 512x512
    console.log('🔄 Resizing to 512x512...');
    const canvas512 = createCanvas(512, 512);
    const ctx512 = canvas512.getContext('2d');
    ctx512.drawImage(logo, 0, 0, 512, 512);
    const icon512 = canvas512.toBuffer('image/png');
    fs.writeFileSync(path.join(publicDir, 'icon-512.png'), icon512);
    console.log('✅ Created icon-512.png');
    
    console.log('\n🎉 Icons created successfully from logo.png!');
    console.log('Icons saved to:', publicDir);
  }
  
  resizeLogo().catch(error => {
    console.error('❌ Error:', error.message);
    console.log('\n💡 Make sure you have canvas installed: npm install canvas');
    process.exit(1);
  });
  
} catch (error) {
  console.error('❌ Canvas library not available.');
  console.log('💡 Install it with: npm install canvas');
  console.log('💡 Or use resize-logo.html in your browser instead.');
  process.exit(1);
}

