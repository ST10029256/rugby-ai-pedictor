"""
Check RapidAPI subscription status and find correct API endpoints
"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

def check_rapidapi_key(api_key: str):
    """Check if RapidAPI key is valid and what APIs are available"""
    
    print("="*80)
    print("RAPIDAPI KEY DIAGNOSTIC")
    print("="*80)
    print(f"API Key: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else '***'}")
    print()
    
    # Test different possible SportDevs API names on RapidAPI
    rapidapi_apis = [
        {
            "name": "SportDevs Rugby API",
            "host": "rugby.sportdevs.com",
            "base_url": "https://rugby.sportdevs.com"
        },
        {
            "name": "Rugby Highlights API (Highlightly)",
            "host": "rugby-highlights-api.p.rapidapi.com",
            "base_url": "https://rugby-highlights-api.p.rapidapi.com"
        },
        {
            "name": "SportDevs API",
            "host": "sportdevs.p.rapidapi.com",
            "base_url": "https://sportdevs.p.rapidapi.com"
        },
    ]
    
    print("Testing RapidAPI endpoints...")
    print()
    
    for api_info in rapidapi_apis:
        name = api_info["name"]
        host = api_info["host"]
        base_url = api_info["base_url"]
        
        headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": host
        }
        
        # Try a simple endpoint
        test_endpoints = ["leagues", "matches", ""]
        
        for endpoint in test_endpoints:
            url = f"{base_url}/{endpoint}" if endpoint else base_url
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    print(f"✅ {name}")
                    print(f"   Host: {host}")
                    print(f"   Endpoint: {endpoint or 'root'}")
                    print(f"   Status: {response.status_code}")
                    print(f"   ✅ YOU ARE SUBSCRIBED TO THIS API!")
                    print()
                    return api_info
                elif response.status_code == 403:
                    error_msg = response.json().get("message", "") if response.headers.get("content-type", "").startswith("application/json") else response.text[:100]
                    if "not subscribed" in str(error_msg).lower():
                        print(f"⚠️  {name}")
                        print(f"   Host: {host}")
                        print(f"   Status: 403 - Not subscribed")
                        print(f"   💡 You need to subscribe to this API on RapidAPI")
                        print()
                    else:
                        print(f"❌ {name}")
                        print(f"   Host: {host}")
                        print(f"   Status: 403 - {error_msg[:100]}")
                        print()
                elif response.status_code == 401:
                    print(f"❌ {name}")
                    print(f"   Host: {host}")
                    print(f"   Status: 401 - Invalid API key")
                    print()
                else:
                    print(f"❌ {name}")
                    print(f"   Host: {host}")
                    print(f"   Status: {response.status_code}")
                    print()
                    
            except Exception as e:
                # Only show error if it's not a connection error (which is expected for wrong hosts)
                if "not subscribed" not in str(e).lower():
                    pass  # Skip connection errors for wrong hosts
    
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print("If you see 'not subscribed' messages:")
    print("  1. Go to https://rapidapi.com")
    print("  2. Search for 'SportDevs' or 'Rugby'")
    print("  3. Subscribe to the SportDevs Rugby API")
    print("  4. Get your RapidAPI key from your dashboard")
    print()
    print("If all APIs return 401:")
    print("  - Your RapidAPI key may be invalid")
    print("  - Check your RapidAPI dashboard")
    print()
    print("If you get 521 errors on SportDevs direct API:")
    print("  - The API service may be down")
    print("  - Or you need to use RapidAPI instead")
    
    return None

if __name__ == "__main__":
    api_key = os.getenv("SPORTDEVS_API_KEY", "qwh9orOkZESulf4QBhf0IQ")
    
    if not api_key:
        print("❌ No API key found!")
        print("Set SPORTDEVS_API_KEY environment variable")
    else:
        result = check_rapidapi_key(api_key)
        
        if result:
            print("\n" + "="*80)
            print("✅ FOUND WORKING API!")
            print("="*80)
            print(f"API Name: {result['name']}")
            print(f"Host: {result['host']}")
            print(f"Base URL: {result['base_url']}")
            print("\nYou can use this configuration in SportDevsClient!")

