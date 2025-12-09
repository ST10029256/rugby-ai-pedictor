#!/bin/bash
# Script to set environment variables for Cloud Functions
# For 2nd Gen functions, we use secrets

echo "Setting environment variables for Cloud Functions..."

# Set MODEL_STORAGE_BUCKET (can be a regular env var)
echo -n "rugby-ai-61fd0.firebasestorage.app" | firebase functions:secrets:set MODEL_STORAGE_BUCKET

# Set API keys as secrets (more secure)
echo "Enter your SPORTDEVS_API_KEY (or press Enter to skip):"
read -s SPORTDEVS_KEY
if [ ! -z "$SPORTDEVS_KEY" ]; then
    echo -n "$SPORTDEVS_KEY" | firebase functions:secrets:set SPORTDEVS_API_KEY
fi

echo "Enter your HIGHLIGHTLY_API_KEY (or press Enter to skip):"
read -s HIGHLIGHTLY_KEY
if [ ! -z "$HIGHLIGHTLY_KEY" ]; then
    echo -n "$HIGHLIGHTLY_KEY" | firebase functions:secrets:set HIGHLIGHTLY_API_KEY
fi

echo "Done! Now redeploy functions:"
echo "  firebase deploy --only functions"

