#!/usr/bin/env python3
"""Assert that team names resolve to the right side in each competition.

Guards the split that `fix_team_identity.py` performed: a bare name such as
"Bulls" or "Sharks" means a different team in the Currie Cup than it does in
the URC, and "Fijian Drua" means the club in Super Rugby but Fiji everywhere
else.

    python scripts/check_team_identity.py
"""

from __future__ import annotations

import argparse
import io
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))

from prediction.team_identity import resolve_team_id  # noqa: E402

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# (league_id, name as the feed sends it, team the database should return)
CASES = [
    # Currie Cup provinces stay clear of the franchises that share their name.
    (5069, "Bulls", "Blue Bulls"),
    (5069, "Blue Bulls", "Blue Bulls"),
    (5069, "Lions", "Golden Lions"),
    (5069, "Sharks", "Sharks XV"),
    (5069, "Cheetahs", "Free State Cheetahs"),
    (5069, "Stormers", "Western Province"),
    (5069, "Stormers XXIII", "Western Province"),
    (5069, "Western Province", "Western Province"),
    (5069, "Pumas", "Pumas"),
    # The same names in the senior competitions.
    (4446, "Bulls", "Bulls"),
    (4446, "Lions", "Lions"),
    (4446, "Sharks", "Sharks"),
    (4446, "Stormers", "Stormers"),
    (4446, "Cheetahs", "Cheetahs"),
    (4551, "Bulls", "Bulls"),
    # Renamed clubs keep one history.
    (4446, "Cardiff Blues", "Cardiff Rugby"),
    (4446, "Cardiff Rugby", "Cardiff Rugby"),
    (4446, "Treviso", "Benetton"),
    (4414, "Harlequins Football Club", "Harlequins"),
    (4414, "Newcastle Red Bulls", "Newcastle Falcons"),
    (4430, "RC Toulon", "RC Toulonnais"),
    (4430, "La Rochelle", "Stade Rochelais"),
    (4430, "Stade Français Paris", "Stade Francais Paris"),
    (4551, "Force", "Western Force"),
    # Fiji versus the Super Rugby club, in both directions.
    (4551, "Fijian Drua", "Fijian Drua"),
    (4551, "Fiji", "Fijian Drua"),
    (4574, "Fijian Drua", "Fiji"),
    (4574, "Fiji", "Fiji"),
    (5480, "Fijian Drua", "Fiji"),
    # Second national sides, labelled "A" in one feed and "B" in another.
    (5479, "New Zealand B", "New Zealand A"),
    (5479, "New Zealand", "New Zealand"),
    (5479, "Australia B", "Australia A"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data.sqlite"))
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    names = {int(r[0]): str(r[1]) for r in conn.execute("SELECT id, name FROM team")}

    failures = 0
    for league_id, feed_name, expected in CASES:
        team_id = resolve_team_id(conn, feed_name, league_id, create=False)
        actual = names.get(team_id, f"<unresolved:{team_id}>")
        if actual == expected:
            print(f"  ok   league {league_id:<5} {feed_name!r:<28} -> {actual!r}")
        else:
            failures += 1
            print(
                f"  FAIL league {league_id:<5} {feed_name!r:<28} -> {actual!r}"
                f"   expected {expected!r}"
            )

    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    conn.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
