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
    # United Rugby Championship (South African franchises carry sponsor names).
    # These deliberately do NOT alias across to the Currie Cup provinces
    # (Blue Bulls, Golden Lions, Sharks XV, Western Province): those are
    # separate sides and carry their own crest.
    "vodacom bulls": ["bulls"],
    "bulls": ["vodacom bulls"],
    "dhl stormers": ["stormers"],
    "stormers": ["dhl stormers"],
    "hollywoodbets sharks": ["sharks", "cell c sharks"],
    "cell c sharks": ["sharks", "hollywoodbets sharks"],
    "sharks": ["hollywoodbets sharks", "cell c sharks"],
    "fidelity securedrive lions": ["lions", "emirates lions"],
    "emirates lions": ["lions"],
    "lions": ["emirates lions", "fidelity securedrive lions"],
    "cardiff rugby": ["cardiff", "cardiff blues"],
    "cardiff": ["cardiff rugby", "cardiff blues"],
    "dragons rfc": ["dragons", "newport gwent dragons"],
    "dragons": ["dragons rfc", "newport gwent dragons"],
    "benetton rugby": ["benetton", "benetton treviso", "treviso"],
    "benetton": ["benetton treviso", "treviso"],
    "portugal rugby": ["portugal"],
    "portugal": ["portugal rugby"],
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
    "stormers": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/16/StormersRugbyClubLogo2025.svg/500px-StormersRugbyClubLogo2025.svg.png",
    "dhl stormers": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/16/StormersRugbyClubLogo2025.svg/500px-StormersRugbyClubLogo2025.svg.png",
    "sharks": "https://upload.wikimedia.org/wikipedia/en/9/9f/Sharks_rugby_union_logo.png",
    "hollywoodbets sharks": "https://upload.wikimedia.org/wikipedia/en/9/9f/Sharks_rugby_union_logo.png",
    "cell c sharks": "https://upload.wikimedia.org/wikipedia/en/9/9f/Sharks_rugby_union_logo.png",
    "lions": "https://upload.wikimedia.org/wikipedia/en/e/e6/Lions_rugby_logo_2007.png",
    "emirates lions": "https://upload.wikimedia.org/wikipedia/en/e/e6/Lions_rugby_logo_2007.png",
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
    # --- English Premiership (Highlightly CDN — Wikimedia thumb URLs often 404) ---
    "northampton saints": "https://highlightly.net/rugby/images/teams/56099.png",
    "bath rugby": "https://highlightly.net/rugby/images/teams/50142.png",
    "bath": "https://highlightly.net/rugby/images/teams/50142.png",
    "exeter chiefs": "https://highlightly.net/rugby/images/teams/51844.png",
    "exeter rc chiefs": "https://highlightly.net/rugby/images/teams/51844.png",
    "leicester tigers": "https://highlightly.net/rugby/images/teams/54397.png",
    "saracens": "https://highlightly.net/rugby/images/teams/57801.png",
    "saracens fc": "https://highlightly.net/rugby/images/teams/57801.png",
    "bristol bears": "https://highlightly.net/rugby/images/teams/50993.png",
    "bristol": "https://highlightly.net/rugby/images/teams/50993.png",
    "sale sharks": "https://highlightly.net/rugby/images/teams/56950.png",
    "gloucester rugby": "https://highlightly.net/rugby/images/teams/52695.png",
    "gloucester": "https://highlightly.net/rugby/images/teams/52695.png",
    "harlequins": "https://highlightly.net/rugby/images/teams/53546.png",
    "harlequins fc": "https://highlightly.net/rugby/images/teams/53546.png",
    "newcastle red bulls": "https://highlightly.net/rugby/images/teams/789661.png",
    "newcastle falcons": "https://highlightly.net/rugby/images/teams/69715.png",
    # --- French Top 14 ---
    "stade toulousain": "https://highlightly.net/rugby/images/teams/91841.png",
    "montpellier herault rugby": "https://highlightly.net/rugby/images/teams/87586.png",
    "montpellier": "https://highlightly.net/rugby/images/teams/87586.png",
    "stade francais paris": "https://highlightly.net/rugby/images/teams/90990.png",
    "section paloise": "https://highlightly.net/rugby/images/teams/90139.png",
    "racing 92": "https://highlightly.net/rugby/images/teams/89288.png",
    "stade rochelais": "https://highlightly.net/rugby/images/teams/85884.png",
    "asm clermont auvergne": "https://highlightly.net/rugby/images/teams/85033.png",
    "clermont": "https://highlightly.net/rugby/images/teams/85033.png",
    "union bordeaux begles": "https://highlightly.net/rugby/images/teams/82480.png",
    "bordeaux begles": "https://highlightly.net/rugby/images/teams/82480.png",
    "rc toulonnais": "https://highlightly.net/rugby/images/teams/88437.png",
    "rc toulon": "https://highlightly.net/rugby/images/teams/88437.png",
    "castres olympique": "https://highlightly.net/rugby/images/teams/84182.png",
    "lyon ou": "https://highlightly.net/rugby/images/teams/86735.png",
    "lyon": "https://highlightly.net/rugby/images/teams/86735.png",
    "aviron bayonne": "https://highlightly.net/rugby/images/teams/81629.png",
    "aviron bayonnais": "https://highlightly.net/rugby/images/teams/81629.png",
    "usa perpignan": "https://highlightly.net/rugby/images/teams/102904.png",
    "us montalbanaise": "https://highlightly.net/rugby/images/teams/99500.png",
    "montauban": "https://highlightly.net/rugby/images/teams/99500.png",
    # --- URC / Currie aliases ---
    "the sharks": "https://highlightly.net/rugby/images/teams/257786.png",
    "ford pumas": "https://highlightly.net/rugby/images/teams/260339.png",
    "pumas": "https://highlightly.net/rugby/images/teams/260339.png",
    "sharks xv": "https://highlightly.net/rugby/images/teams/257786.png",
    "stormers xxii": "https://highlightly.net/rugby/images/teams/529255.png",
    "golden lions": "https://highlightly.net/rugby/images/teams/253531.png",
    "blue bulls": "https://highlightly.net/rugby/images/teams/250978.png",
    "boland cavaliers": "https://highlightly.net/rugby/images/teams/250127.png",
    "cheetahs": "https://highlightly.net/rugby/images/teams/251829.png",
    "free state cheetahs": "https://highlightly.net/rugby/images/teams/251829.png",
    "griquas": "https://highlightly.net/rugby/images/teams/259488.png",
    "benetton treviso": "https://highlightly.net/rugby/images/teams/334376.png",
    # --- International / RWC (API-Sports CDN — stable when search quota exhausted) ---
    "argentina": "https://media.api-sports.io/rugby/teams/460.png",
    "australia": "https://media.api-sports.io/rugby/teams/461.png",
    "chile": "https://media.api-sports.io/rugby/teams/639.png",
    "england": "https://media.api-sports.io/rugby/teams/386.png",
    "fiji": "https://media.api-sports.io/rugby/teams/28.png",
    "france": "https://media.api-sports.io/rugby/teams/387.png",
    "georgia": "https://media.api-sports.io/rugby/teams/410.png",
    "ireland": "https://media.api-sports.io/rugby/teams/388.png",
    "italy": "https://media.api-sports.io/rugby/teams/389.png",
    "japan": "https://media.api-sports.io/rugby/teams/463.png",
    "namibia": "https://media.api-sports.io/rugby/teams/464.png",
    "new zealand": "https://media.api-sports.io/rugby/teams/465.png",
    "portugal": "https://media.api-sports.io/rugby/teams/411.png",
    "romania": "https://media.api-sports.io/rugby/teams/412.png",
    "samoa": "https://media.api-sports.io/rugby/teams/466.png",
    "scotland": "https://media.api-sports.io/rugby/teams/390.png",
    "south africa": "https://media.api-sports.io/rugby/teams/467.png",
    "tonga": "https://media.api-sports.io/rugby/teams/468.png",
    "uruguay": "https://media.api-sports.io/rugby/teams/470.png",
    "wales": "https://media.api-sports.io/rugby/teams/391.png",
    # --- Additional international (API-Sports) ---
    "canada": "https://media.api-sports.io/rugby/teams/462.png",
    "usa": "https://media.api-sports.io/rugby/teams/469.png",
    "united states": "https://media.api-sports.io/rugby/teams/469.png",
    "eagles": "https://media.api-sports.io/rugby/teams/469.png",
    "spain": "https://media.api-sports.io/rugby/teams/414.png",
    "belgium": "https://media.api-sports.io/rugby/teams/562.png",
    "brazil": "https://media.api-sports.io/rugby/teams/638.png",
    "russia": "https://media.api-sports.io/rugby/teams/413.png",
    "zimbabwe": "https://media.api-sports.io/rugby/teams/320.png",
    "kenya": "https://media.api-sports.io/rugby/teams/641.png",
    "hong kong": "https://media.api-sports.io/rugby/teams/720.png",
    "germany": "https://media.api-sports.io/rugby/teams/415.png",
    "netherlands": "https://media.api-sports.io/rugby/teams/417.png",
    "czech republic": "https://media.api-sports.io/rugby/teams/748.png",
    "colombia": "https://media.api-sports.io/rugby/teams/784.png",
    "poland": "https://media.api-sports.io/rugby/teams/418.png",
    "uganda": "https://media.api-sports.io/rugby/teams/694.png",
    "cook islands": "https://media.api-sports.io/rugby/teams/690.png",
    "papua new guinea": "https://media.api-sports.io/rugby/teams/369.png",
    "south korea": "https://media.api-sports.io/rugby/teams/760.png",
    "paraguay": "https://media.api-sports.io/rugby/teams/658.png",
    "barbarians": "https://media.api-sports.io/rugby/teams/653.png",
    "french barbarians": "https://media.api-sports.io/rugby/teams/640.png",
    "maori all blacks": "https://media.api-sports.io/rugby/teams/642.png",
    "portugal rugby": "https://media.api-sports.io/rugby/teams/411.png",
    # --- Premiership / Super Rugby historical ---
    "wasps": "https://media.api-sports.io/rugby/teams/68.png",
    "london irish": "https://media.api-sports.io/rugby/teams/64.png",
    "london welsh": "https://media.api-sports.io/rugby/teams/510.png",
    "worcester warriors": "https://media.api-sports.io/rugby/teams/69.png",
    "yorkshire": "https://media.api-sports.io/rugby/teams/83.png",
    "jaguares": "https://media.api-sports.io/rugby/teams/559.png",
    "sunwolves": "https://media.api-sports.io/rugby/teams/768.png",
    "southern kings": "https://media.api-sports.io/rugby/teams/767.png",
    # --- Currie Cup (API-Sports) ---
    "western province": "https://media.api-sports.io/rugby/teams/303.png",
    "griffons": "https://media.api-sports.io/rugby/teams/316.png",
    "border bulldogs": "https://media.api-sports.io/rugby/teams/311.png",
    "leopards": "https://media.api-sports.io/rugby/teams/317.png",
    "eastern province kings": "https://media.api-sports.io/rugby/teams/313.png",
    "welwitschias": "https://media.api-sports.io/rugby/teams/319.png",
    "cheetahs": "https://media.api-sports.io/rugby/teams/295.png",
    "pumas": "https://media.api-sports.io/rugby/teams/305.png",
    "griquas": "https://media.api-sports.io/rugby/teams/304.png",
    "boland cavaliers": "https://media.api-sports.io/rugby/teams/293.png",
    # --- French Top 14 short-name aliases (Highlightly) ---
    "la rochelle": "https://highlightly.net/rugby/images/teams/85884.png",
    "stade francais": "https://highlightly.net/rugby/images/teams/90990.png",
    "toulouse": "https://highlightly.net/rugby/images/teams/91841.png",
    "castres": "https://highlightly.net/rugby/images/teams/84182.png",
    "perpignan": "https://highlightly.net/rugby/images/teams/102904.png",
    "bordeaux": "https://highlightly.net/rugby/images/teams/82480.png",
    "bayonne": "https://highlightly.net/rugby/images/teams/81629.png",
    "montauban": "https://highlightly.net/rugby/images/teams/99500.png",
    "pau": "https://highlightly.net/rugby/images/teams/90139.png",
    "section paloise": "https://highlightly.net/rugby/images/teams/90139.png",
    "treviso": "https://highlightly.net/rugby/images/teams/334376.png",
    "aironi": "https://highlightly.net/rugby/images/teams/334376.png",
    # --- French Top 14 / Pro D2 (API-Sports) ---
    "agen": "https://media.api-sports.io/rugby/teams/94.png",
    "biarritz olympique": "https://media.api-sports.io/rugby/teams/111.png",
    "biarritz": "https://media.api-sports.io/rugby/teams/111.png",
    "ca brive": "https://media.api-sports.io/rugby/teams/97.png",
    "grenoble fc": "https://media.api-sports.io/rugby/teams/114.png",
    "grenoble": "https://media.api-sports.io/rugby/teams/114.png",
    "union sportive oyonnax": "https://media.api-sports.io/rugby/teams/121.png",
    "us oyonnax": "https://media.api-sports.io/rugby/teams/121.png",
    "us dax": "https://media.api-sports.io/rugby/teams/516.png",
    "vannes": "https://media.api-sports.io/rugby/teams/123.png",
    "provence rugby": "https://media.api-sports.io/rugby/teams/118.png",
    "provence": "https://media.api-sports.io/rugby/teams/118.png",
    "united arab emirates": "https://media.api-sports.io/rugby/teams/889.png",
    # --- Representative / composite sides (parent nation crests) ---
    "north island": "https://media.api-sports.io/rugby/teams/465.png",
    "south island": "https://media.api-sports.io/rugby/teams/465.png",
    "pacific islands": "https://media.api-sports.io/rugby/teams/466.png",
    "rfu championship xv": "https://media.api-sports.io/rugby/teams/386.png",
    "south american xv": "https://media.api-sports.io/rugby/teams/460.png",
    "yamaha jubilo": "https://media.api-sports.io/rugby/teams/463.png",
    "falcons": "https://media.api-sports.io/rugby/teams/69715.png",
    "cs bourgoin jallieu": "https://media.api-sports.io/rugby/teams/112.png",
    "mont de marsan": "https://upload.wikimedia.org/wikipedia/fr/thumb/8/8e/Stade_montois_logo.svg/330px-Stade_montois_logo.svg.png",
}


def load_config() -> AppConfig:
    # Load .env if present
    load_dotenv()

    api_key = os.getenv("THESPORTSDB_API_KEY", "123")
    base_url = os.getenv("THESPORTSDB_BASE_URL", "https://www.thesportsdb.com/api/v1/json")
    rate_limit_rpm = int(os.getenv("RATE_LIMIT_RPM", "30"))

    return AppConfig(api_key=api_key, base_url=base_url, rate_limit_rpm=rate_limit_rpm)
