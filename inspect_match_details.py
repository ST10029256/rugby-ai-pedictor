"""
Inspect match details structure to find lineups and news
"""

import os
import sys
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'prediction'))

from prediction.highlightly_client import HighlightlyRugbyAPI
import json

def inspect_match_details():
    """Inspect actual match details structure"""
    
    api_key = os.getenv("HIGHLIGHTLY_API_KEY", "9c27c5f8-9437-4d42-8cc9-5179d3290a5b")
    api = HighlightlyRugbyAPI(api_key)
    
    # Get a match
    today = datetime.now().strftime('%Y-%m-%d')
    matches = api.get_matches(date=today, limit=1)
    
    if not matches.get('data'):
        print("No matches found for today")
        return
    
    match = matches['data'][0]
    match_id = match.get('id')
    
    print("="*80)
    print(f"INSPECTING MATCH DETAILS FOR MATCH {match_id}")
    print("="*80)
    print(f"Match: {match.get('homeTeam', {}).get('name')} vs {match.get('awayTeam', {}).get('name')}")
    print()
    
    # Get match details
    details = api.get_match_details(match_id)
    
    print("MATCH DETAILS STRUCTURE:")
    print("="*80)
    print(json.dumps(details, indent=2, default=str)[:5000])  # First 5000 chars
    print()
    
    print("="*80)
    print("SEARCHING FOR LINEUPS...")
    print("="*80)
    
    def find_lineups(obj, path="", depth=0):
        """Recursively search for lineup-related fields"""
        if depth > 5:  # Limit depth
            return []
        
        findings = []
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_lower = str(key).lower()
                if any(term in key_lower for term in ['lineup', 'squad', 'players', 'roster', 'team', 'starting']):
                    findings.append(f"{path}.{key} (type: {type(value).__name__})")
                    if isinstance(value, (dict, list)) and len(str(value)) < 500:
                        findings.append(f"  -> {value}")
                
                if isinstance(value, (dict, list)):
                    findings.extend(find_lineups(value, f"{path}.{key}", depth+1))
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:3]):  # Check first 3 items
                if isinstance(item, (dict, list)):
                    findings.extend(find_lineups(item, f"{path}[{i}]", depth+1))
        
        return findings
    
    lineup_findings = find_lineups(details)
    if lineup_findings:
        print("Found potential lineup fields:")
        for finding in lineup_findings[:20]:  # First 20 findings
            print(f"  {finding}")
    else:
        print("No lineup-related fields found")
    
    print()
    print("="*80)
    print("SEARCHING FOR NEWS...")
    print("="*80)
    
    def find_news(obj, path="", depth=0):
        """Recursively search for news-related fields"""
        if depth > 5:
            return []
        
        findings = []
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_lower = str(key).lower()
                if any(term in key_lower for term in ['news', 'article', 'update', 'media', 'press', 'preview', 'report', 'story']):
                    findings.append(f"{path}.{key} (type: {type(value).__name__})")
                    if isinstance(value, str) and len(value) < 200:
                        findings.append(f"  -> {value[:100]}")
                
                if isinstance(value, (dict, list)):
                    findings.extend(find_news(value, f"{path}.{key}", depth+1))
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:3]):
                if isinstance(item, (dict, list)):
                    findings.extend(find_news(item, f"{path}[{i}]", depth+1))
        
        return findings
    
    news_findings = find_news(details)
    if news_findings:
        print("Found potential news fields:")
        for finding in news_findings[:20]:
            print(f"  {finding}")
    else:
        print("No news-related fields found")
    
    print()
    print("="*80)
    print("ALL TOP-LEVEL KEYS:")
    print("="*80)
    if isinstance(details, dict):
        for key in details.keys():
            value = details[key]
            value_type = type(value).__name__
            if isinstance(value, (dict, list)):
                size = len(value)
                print(f"  {key}: {value_type} (size: {size})")
            else:
                print(f"  {key}: {value_type} = {str(value)[:100]}")

if __name__ == "__main__":
    inspect_match_details()

