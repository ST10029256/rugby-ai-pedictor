from __future__ import annotations

import os
from pydantic import BaseModel
from dotenv import load_dotenv


class AppConfig(BaseModel):
    api_key: str
    base_url: str = "https://www.thesportsdb.com/api/v1/json"
    rate_limit_rpm: int = 30


# League mappings for TheSportsDB
LEAGUE_MAPPINGS = {
    4986: "Rugby Championship",
    4446: "United Rugby Championship",
    5069: "Currie Cup",
    4574: "Rugby World Cup",
    4551: "Super Rugby",
    4430: "French Top 14",
    4414: "English Premiership Rugby",
    4714: "Six Nations Championship",
    5479: "Rugby Union International Friendlies",
    5480: "Nations Championship",
}


# Maps a normalized standings team name -> list of normalized alternative names
# to try when resolving a TheSportsDB logo. Our match results use sponsor /
# full club names (e.g. "Vodacom Bulls"), but TheSportsDB indexes the short
# names (e.g. "Bulls"), so without these aliases the logo lookup misses and the
# UI falls back to a plain initial. Keys/values must be normalized the same way
# as the standings logo resolver: lowercase, non-alphanumeric collapsed to
# single spaces, trimmed.
STANDINGS_TEAM_OVERRIDES = {
    # United Rugby Championship (South African franchises carry sponsor names)
    "vodacom bulls": ["bulls", "blue bulls"],
    "bulls": ["vodacom bulls", "blue bulls"],
    "dhl stormers": ["stormers", "western province"],
    "stormers": ["dhl stormers"],
    "hollywoodbets sharks": ["sharks", "cell c sharks"],
    "cell c sharks": ["sharks", "hollywoodbets sharks"],
    "sharks": ["hollywoodbets sharks", "cell c sharks"],
    "fidelity securedrive lions": ["lions", "emirates lions", "golden lions"],
    "emirates lions": ["lions", "golden lions"],
    "lions": ["emirates lions", "golden lions", "fidelity securedrive lions"],
    "cardiff rugby": ["cardiff", "cardiff blues"],
    "cardiff": ["cardiff rugby", "cardiff blues"],
    "dragons rfc": ["dragons", "newport gwent dragons"],
    "dragons": ["dragons rfc", "newport gwent dragons"],
    "benetton rugby": ["benetton", "benetton treviso", "treviso"],
    "benetton": ["benetton treviso", "treviso"],
    "zebre parma": ["zebre", "zebre rugby", "zebre parma"],
    "zebre": ["zebre parma", "zebre rugby"],
    "glasgow warriors": ["glasgow"],
    "edinburgh rugby": ["edinburgh"],
    "leinster rugby": ["leinster"],
    "munster rugby": ["munster"],
    "ulster rugby": ["ulster"],
    "connacht rugby": ["connacht"],
    # Super Rugby (state/region prefixes)
    "western force": ["force"],
    "force": ["western force"],
    "nsw waratahs": ["waratahs"],
    "waratahs": ["nsw waratahs", "new south wales waratahs"],
    "act brumbies": ["brumbies"],
    "brumbies": ["act brumbies"],
    "queensland reds": ["reds"],
    "reds": ["queensland reds"],
    "fijian drua": ["fiji drua", "drua"],
    "fiji drua": ["fijian drua", "drua"],
    "auckland blues": ["blues"],
    "blues": ["auckland blues"],
}


# Curated, verified logo URLs for teams that Highlightly does NOT host an image
# for (its `logo` field is null and the deterministic URL 404s). These are stable
# Wikipedia/Wikimedia upload URLs (each verified to return a real image). Keys are
# normalized the same way as the standings logo resolver (lowercase, non-alphanumeric
# collapsed to single spaces, trimmed) and include sponsor / short-name aliases so
# we match whatever name Highlightly returns. This is the guaranteed last-resort
# fallback so every team in a league table shows a crest even without a paid
# TheSportsDB key. Priority order in main.py: Highlightly -> TheSportsDB -> this map.
STATIC_TEAM_LOGOS = {
    # --- United Rugby Championship ---
    "leinster": "https://upload.wikimedia.org/wikipedia/en/thumb/a/a4/LeinsterRugby_logo_2019.svg/500px-LeinsterRugby_logo_2019.svg.png",
    "leinster rugby": "https://upload.wikimedia.org/wikipedia/en/thumb/a/a4/LeinsterRugby_logo_2019.svg/500px-LeinsterRugby_logo_2019.svg.png",
    "munster": "https://upload.wikimedia.org/wikipedia/en/thumb/f/fb/Munster_Rugby_logo.svg/500px-Munster_Rugby_logo.svg.png",
    "munster rugby": "https://upload.wikimedia.org/wikipedia/en/thumb/f/fb/Munster_Rugby_logo.svg/500px-Munster_Rugby_logo.svg.png",
    "ulster": "https://upload.wikimedia.org/wikipedia/en/thumb/c/c0/Ulster_Rugby_logo.svg/500px-Ulster_Rugby_logo.svg.png",
    "ulster rugby": "https://upload.wikimedia.org/wikipedia/en/thumb/c/c0/Ulster_Rugby_logo.svg/500px-Ulster_Rugby_logo.svg.png",
    "connacht": "https://upload.wikimedia.org/wikipedia/en/thumb/6/67/ConnachtRugby_2017logo.svg/500px-ConnachtRugby_2017logo.svg.png",
    "connacht rugby": "https://upload.wikimedia.org/wikipedia/en/thumb/6/67/ConnachtRugby_2017logo.svg/500px-ConnachtRugby_2017logo.svg.png",
    "glasgow warriors": "https://upload.wikimedia.org/wikipedia/en/thumb/0/06/Glasgow_Warriors_Logo.svg/330px-Glasgow_Warriors_Logo.svg.png",
    "glasgow": "https://upload.wikimedia.org/wikipedia/en/thumb/0/06/Glasgow_Warriors_Logo.svg/330px-Glasgow_Warriors_Logo.svg.png",
    "edinburgh": "https://upload.wikimedia.org/wikipedia/en/thumb/e/e3/Edinburgh_Rugby_logo_2018.svg/500px-Edinburgh_Rugby_logo_2018.svg.png",
    "edinburgh rugby": "https://upload.wikimedia.org/wikipedia/en/thumb/e/e3/Edinburgh_Rugby_logo_2018.svg/500px-Edinburgh_Rugby_logo_2018.svg.png",
    "cardiff rugby": "https://upload.wikimedia.org/wikipedia/en/1/1f/Cardiff_Rugby_logo_%282021%29.jpg",
    "cardiff": "https://upload.wikimedia.org/wikipedia/en/1/1f/Cardiff_Rugby_logo_%282021%29.jpg",
    "ospreys": "https://upload.wikimedia.org/wikipedia/en/thumb/2/2c/Ospreys_Rugby_logo.svg/500px-Ospreys_Rugby_logo.svg.png",
    "scarlets": "https://upload.wikimedia.org/wikipedia/en/thumb/0/07/Scarlets_logo.svg/330px-Scarlets_logo.svg.png",
    "dragons": "https://upload.wikimedia.org/wikipedia/en/9/9b/Dragons_RFC_logo.png",
    "dragons rfc": "https://upload.wikimedia.org/wikipedia/en/9/9b/Dragons_RFC_logo.png",
    "benetton": "https://upload.wikimedia.org/wikipedia/en/thumb/a/ac/Benetton_rugby.svg/500px-Benetton_rugby.svg.png",
    "benetton rugby": "https://upload.wikimedia.org/wikipedia/en/thumb/a/ac/Benetton_rugby.svg/500px-Benetton_rugby.svg.png",
    "benetton treviso": "https://upload.wikimedia.org/wikipedia/en/thumb/a/ac/Benetton_rugby.svg/500px-Benetton_rugby.svg.png",
    "zebre": "https://upload.wikimedia.org/wikipedia/en/5/5d/Zebre_parma_logo23.png",
    "zebre parma": "https://upload.wikimedia.org/wikipedia/en/5/5d/Zebre_parma_logo23.png",
    "bulls": "https://upload.wikimedia.org/wikipedia/en/c/cf/Bulls_rugby_logo.jpg",
    "vodacom bulls": "https://upload.wikimedia.org/wikipedia/en/c/cf/Bulls_rugby_logo.jpg",
    "blue bulls": "https://upload.wikimedia.org/wikipedia/en/c/cf/Bulls_rugby_logo.jpg",
    "stormers": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/16/StormersRugbyClubLogo2025.svg/500px-StormersRugbyClubLogo2025.svg.png",
    "dhl stormers": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/16/StormersRugbyClubLogo2025.svg/500px-StormersRugbyClubLogo2025.svg.png",
    "sharks": "https://upload.wikimedia.org/wikipedia/en/9/9f/Sharks_rugby_union_logo.png",
    "hollywoodbets sharks": "https://upload.wikimedia.org/wikipedia/en/9/9f/Sharks_rugby_union_logo.png",
    "cell c sharks": "https://upload.wikimedia.org/wikipedia/en/9/9f/Sharks_rugby_union_logo.png",
    "lions": "https://upload.wikimedia.org/wikipedia/en/e/e6/Lions_rugby_logo_2007.png",
    "emirates lions": "https://upload.wikimedia.org/wikipedia/en/e/e6/Lions_rugby_logo_2007.png",
    "golden lions": "https://upload.wikimedia.org/wikipedia/en/e/e6/Lions_rugby_logo_2007.png",
    "fidelity securedrive lions": "https://upload.wikimedia.org/wikipedia/en/e/e6/Lions_rugby_logo_2007.png",
    # --- Super Rugby ---
    "blues": "https://upload.wikimedia.org/wikipedia/en/c/cd/Auckland_Blues_rugby_logo.webp",
    "auckland blues": "https://upload.wikimedia.org/wikipedia/en/c/cd/Auckland_Blues_rugby_logo.webp",
    "chiefs": "https://upload.wikimedia.org/wikipedia/en/8/87/Chiefs_rugby_union_logo.jpg",
    "crusaders": "https://upload.wikimedia.org/wikipedia/en/thumb/b/bd/Crusaders_%28rugby_union%29_logo.png/330px-Crusaders_%28rugby_union%29_logo.png",
    "highlanders": "https://upload.wikimedia.org/wikipedia/en/thumb/a/a7/Highlanders_NZ_rugby_union_team_logo.svg/330px-Highlanders_NZ_rugby_union_team_logo.svg.png",
    "hurricanes": "https://upload.wikimedia.org/wikipedia/en/thumb/2/28/Wellington_Hurricanes_logo.png/330px-Wellington_Hurricanes_logo.png",
    "brumbies": "https://upload.wikimedia.org/wikipedia/en/thumb/5/53/Brumbies_Rugby_logo.svg/500px-Brumbies_Rugby_logo.svg.png",
    "act brumbies": "https://upload.wikimedia.org/wikipedia/en/thumb/5/53/Brumbies_Rugby_logo.svg/500px-Brumbies_Rugby_logo.svg.png",
    "reds": "https://upload.wikimedia.org/wikipedia/en/thumb/e/e1/QLD_reds_logo.svg/500px-QLD_reds_logo.svg.png",
    "queensland reds": "https://upload.wikimedia.org/wikipedia/en/thumb/e/e1/QLD_reds_logo.svg/500px-QLD_reds_logo.svg.png",
    "waratahs": "https://upload.wikimedia.org/wikipedia/en/thumb/6/6f/Waratahs_logo.svg/500px-Waratahs_logo.svg.png",
    "nsw waratahs": "https://upload.wikimedia.org/wikipedia/en/thumb/6/6f/Waratahs_logo.svg/500px-Waratahs_logo.svg.png",
    "new south wales waratahs": "https://upload.wikimedia.org/wikipedia/en/thumb/6/6f/Waratahs_logo.svg/500px-Waratahs_logo.svg.png",
    "rebels": "https://upload.wikimedia.org/wikipedia/en/thumb/a/a3/Melbourne_Rebels_logo.svg/330px-Melbourne_Rebels_logo.svg.png",
    "melbourne rebels": "https://upload.wikimedia.org/wikipedia/en/thumb/a/a3/Melbourne_Rebels_logo.svg/330px-Melbourne_Rebels_logo.svg.png",
    "western force": "https://upload.wikimedia.org/wikipedia/en/0/01/Western_force_rugby_logo.png",
    "force": "https://upload.wikimedia.org/wikipedia/en/0/01/Western_force_rugby_logo.png",
    "fijian drua": "https://upload.wikimedia.org/wikipedia/en/thumb/9/9c/FijianDruaLogo.svg/250px-FijianDruaLogo.svg.png",
    "fiji drua": "https://upload.wikimedia.org/wikipedia/en/thumb/9/9c/FijianDruaLogo.svg/250px-FijianDruaLogo.svg.png",
    "drua": "https://upload.wikimedia.org/wikipedia/en/thumb/9/9c/FijianDruaLogo.svg/250px-FijianDruaLogo.svg.png",
    "moana pasifika": "https://upload.wikimedia.org/wikipedia/en/2/20/Moana_Pasifika_logo.jpg",
    # --- English Premiership ---
    "newcastle red bulls": "https://upload.wikimedia.org/wikipedia/en/8/80/Newcastle_Red_Bulls_logo.png",
    "newcastle falcons": "https://upload.wikimedia.org/wikipedia/en/8/80/Newcastle_Red_Bulls_logo.png",
}


def load_config() -> AppConfig:
    # Load .env if present
    load_dotenv()

    api_key = os.getenv("THESPORTSDB_API_KEY", "123")
    base_url = os.getenv("THESPORTSDB_BASE_URL", "https://www.thesportsdb.com/api/v1/json")
    rate_limit_rpm = int(os.getenv("RATE_LIMIT_RPM", "30"))

    return AppConfig(api_key=api_key, base_url=base_url, rate_limit_rpm=rate_limit_rpm)
