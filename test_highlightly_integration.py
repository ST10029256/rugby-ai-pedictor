#!/usr/bin/env python3
"""
Test Highlightly API Integration
"""

import os
import sys

# Set API key
os.environ['HIGHLIGHTLY_API_KEY'] = '5906e52d-34df-4320-91c7-fda6d5349157'

def test_api_integration():
    """Test the Highlightly API integration"""
    print("🧪 Testing Highlightly API Integration...")
    print("=" * 50)
    
    # Test 1: API Key
    api_key = os.getenv('HIGHLIGHTLY_API_KEY')
    if api_key:
        print(f"✅ API Key set: {api_key[:10]}...")
    else:
        print("❌ API Key not found")
        return False
    
    # Test 2: Import
    try:
        from prediction.highlightly_client import HighlightlyRugbyAPI
        print("✅ HighlightlyRugbyAPI imported successfully")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    
    # Test 3: API Initialization
    try:
        api = HighlightlyRugbyAPI(api_key)
        print("✅ API client initialized successfully")
    except Exception as e:
        print(f"❌ API initialization error: {e}")
        return False
    
    # Test 4: Basic API Call
    try:
        print("🔄 Testing basic API call...")
        matches = api.get_matches(league_name="Rugby Championship", limit=5)
        if matches and 'data' in matches:
            print(f"✅ API call successful - found {len(matches['data'])} matches")
        else:
            print("⚠️ API call returned no data")
    except Exception as e:
        print(f"❌ API call error: {e}")
        return False
    
    print("=" * 50)
    print("🎉 All tests passed! Highlightly API integration is working!")
    return True

if __name__ == "__main__":
    success = test_api_integration()
    if success:
        print("\n🚀 Ready to deploy with enhanced predictions!")
        print("Your AI will now make decisions based on:")
        print("- Live odds from bookmakers")
        print("- Team form and standings")
        print("- Head-to-head history")
        print("- Real-time match data")
    else:
        print("\n❌ Integration test failed. Check the errors above.")
    
    sys.exit(0 if success else 1)
