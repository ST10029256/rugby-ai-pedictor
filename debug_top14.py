#!/usr/bin/env python3
import requests
import time
import json

def check_top14_endpoints():
    print("Checking French Top 14 (League ID: 4430) API endpoints...")
    
    endpoints_to_check = [
        "https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id=4430",
        "https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id=4430&s=2025-2026",
        "https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id=4430&s=2025",
        "https://www.thesportsdb.com/api/v1/json/123/eventsleague.php?id=4430",
        "https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id=4430&r=1&s=2025-2026",
        "https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id=4430&r=2&s=2025-2026",
        "https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id=4430&r=3&s=2025-2026",
        "https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id=4430&r=4&s=2025-2026",
        "https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id=4430&r=5&s=2025-2026",
        "https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id=4430&r=6&s=2025-2026",
        "https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id=4430&r=7&s=2025-2026",
        "https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id=4430&r=8&s=2025-2026",
    ]
    
    for i, url in enumerate(endpoints_to_check):
        try:
            print(f"\n{i+1}. Checking: {url}")
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'events' in data and data['events']:
                    print(f"   [OK] Found {len(data['events'])} events")
                    # Show first few events
                    for j, event in enumerate(data['events'][:3]):
                        if 'strEvent' in event and 'dateEvent' in event:
                            print(f"      {event['dateEvent']}: {event['strEvent']}")
                else:
                    print(f"   [NO] No events found")
            else:
                print(f"   [ERROR] HTTP {response.status_code}")
                
            time.sleep(1)  # Rate limiting
            
        except Exception as e:
            print(f"   [ERROR] {e}")

if __name__ == "__main__":
    check_top14_endpoints()
