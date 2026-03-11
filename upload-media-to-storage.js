/**
 * Script to upload media files to Firebase Storage
 * Run: node upload-media-to-storage.js
 */

const admin = require('firebase-admin');
const path = require('path');
const fs = require('fs');

// Initialize Firebase Admin (you'll need to set up service account)
// For now, this script uses the Firebase CLI approach

console.log('📦 Firebase Storage Media Upload Script');
console.log('========================================\n');

const mediaFiles = [
  { local: 'public/public/video_rugby.mov', remote: 'media/video_rugby.mov' },
  { local: 'public/public/video_rugby_ball.mov', remote: 'media/video_rugby_ball.mov' },
  { local: 'public/public/login_video.mov', remote: 'media/login_video.mov' },
  { local: 'public/public/image_rugby.jpeg', remote: 'media/image_rugby.jpeg' },
];

console.log('Media files to upload:');
mediaFiles.forEach((file, idx) => {
  const exists = fs.existsSync(file.local);
  console.log(`${idx + 1}. ${file.remote} ${exists ? '✅' : '❌ (file not found)'}`);
});

console.log('\n📋 Upload Instructions:');
console.log('======================');
console.log('\nOption 1: Using Firebase Console (Easiest)');
console.log('1. Go to https://console.firebase.google.com/project/rugby-ai-61fd0/storage');
console.log('2. Create a folder called "media"');
console.log('3. Upload each file to the media folder');
console.log('4. Make files publicly accessible (click on file > Permissions > Add "allUsers" with "Reader" role)');

console.log('\nOption 2: Using Firebase CLI');
console.log('1. Install: npm install -g firebase-tools');
console.log('2. Login: firebase login');
console.log('3. Run these commands:');
console.log('');
mediaFiles.forEach(file => {
  if (fs.existsSync(file.local)) {
    console.log(`   firebase storage:upload "${file.local}" "${file.remote}" --project rugby-ai-61fd0`);
  }
});

console.log('\nOption 3: Using gsutil (Google Cloud SDK)');
console.log('1. Install Google Cloud SDK');
console.log('2. Authenticate: gcloud auth login');
console.log('3. Run these commands:');
console.log('');
mediaFiles.forEach(file => {
  if (fs.existsSync(file.local)) {
    const bucket = 'rugby-ai-61fd0.firebasestorage.app';
    console.log(`   gsutil cp "${file.local}" gs://${bucket}/${file.remote}`);
    console.log(`   gsutil acl ch -u AllUsers:R gs://${bucket}/${file.remote}`);
  }
});

console.log('\n✅ After uploading, update the code to use Storage URLs');
console.log('   Storage URLs format: https://firebasestorage.googleapis.com/v0/b/rugby-ai-61fd0.firebasestorage.app/o/media%2F[filename]?alt=media');

