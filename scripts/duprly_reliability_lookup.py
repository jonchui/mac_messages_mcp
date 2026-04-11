#!/usr/bin/env python3
"""
Look up DUPR players and print Doubles rating + Doubles Reliability %.
Uses DuprClient from the duprly repo (default: ~/code/duprly). Override with DUPRLY_PATH.

  python3 scripts/duprly_reliability_lookup.py
  python3 scripts/duprly_reliability_lookup.py data/4.0_open_play_attendees.csv

  # or from anywhere:
  DUPRLY_PATH=~/code/duprly python3 /path/to/duprly_reliability_lookup.py /path/to/data/4.0_open_play_attendees.csv
"""
import csv
import json
import os
import re
import sys
import time

# Optional: disable SSL warnings if duprly does
try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass
try:
    import requests
    _orig_post = requests.post
    _orig_get = requests.get
    def _p(*a, **kw):
        kw.setdefault("verify", False)
        return _orig_post(*a, **kw)
    def _g(*a, **kw):
        kw.setdefault("verify", False)
        return _orig_get(*a, **kw)
    requests.post = _p
    requests.get = _g
except Exception:
    pass

# Add duprly repo to path for DuprClient (default: ~/code/duprly)
DUPRLY_PATH = os.environ.get("DUPRLY_PATH", os.path.expanduser("~/code/duprly"))
if os.path.isdir(DUPRLY_PATH):
    sys.path.insert(0, os.path.abspath(DUPRLY_PATH))
try:
    from dupr_client import DuprClient
except ImportError:
    print("Error: DuprClient not found. Run from duprly repo or set DUPRLY_PATH.", file=sys.stderr)
    sys.exit(1)


def _doubles_reliability_from_player(player_data: dict) -> str:
    """
    Extract doubles reliability from full player data (get_player response).
    search_players hits do NOT include reliability — must call get_player(duprId).
    """
    if not player_data:
        return "—"
    ratings = player_data.get("ratings") or {}
    if isinstance(ratings, dict):
        rel = (
            ratings.get("doublesReliabilityScore")
            or ratings.get("doublesVerified")
            or ratings.get("reliability")
        )
    else:
        rel = None
    if rel is None:
        rel = (
            player_data.get("doublesReliabilityScore")
            or player_data.get("doublesVerified")
            or player_data.get("reliability")
        )
    if rel is not None:
        try:
            return f"{int(float(rel))}%"
        except (ValueError, TypeError):
            return str(rel)
    return "—"


# Scale for reliability-based DUPR range (Elo-style: uncertainty ∝ 100 - reliability).
# Half-width in rating points = DUPR_RANGE_SCALE * (100 - reliability_pct) / 100.
# Try 0.7 (tighter), 1.0, 1.1 (e.g. Richard 4.74@26% → 3.9-5.6), 1.2 (wider).
DUPR_RANGE_SCALE = 1.1


def _dupr_margin(doubles_rating: float | None, reliability_pct: int | None) -> float | None:
    """Uncertainty half-width in rating points (Elo-style). None if no rating or reliability."""
    if doubles_rating is None or reliability_pct is None or reliability_pct < 0:
        return None
    return DUPR_RANGE_SCALE * (100 - reliability_pct) / 100.0


def _dupr_range_str(doubles_rating: float | None, reliability_pct: int | None) -> str:
    """
    Compute a DUPR range (low - high) from point rating and reliability %, Elo-style.
    Low reliability → larger uncertainty → wider interval. High reliability → narrow.
    """
    if doubles_rating is None or reliability_pct is None or reliability_pct < 0:
        return "—"
    margin = DUPR_RANGE_SCALE * (100 - reliability_pct) / 100.0
    lo = max(0.0, doubles_rating - margin)
    hi = doubles_rating + margin
    return f"{lo:.1f} - {hi:.1f}"


def _doubles_display(doubles_str: str, doubles_num: float | None, margin: float | None) -> str:
    """Display DUPR as '4.7 ± 0.8' when margin available, else raw doubles_str."""
    if doubles_num is not None and margin is not None:
        return f"{doubles_num:.1f} ± {margin:.1f}"
    return doubles_str


def _first_last_from_csv_row(row: dict) -> str:
    first = (row.get("First Name") or "").strip().strip('"')
    last = (row.get("Last Name") or "").strip()
    # Strip waiver suffix for search e.g. "Sasseville W4.5" -> "Sasseville"
    last = re.sub(r"\s*W\s*\d+\.?\d*\s*$", "", last, flags=re.I).strip()
    return f"{first} {last}".strip()


def _print_results_table(rows: list) -> None:
    """Print collected results as a table. Call at end or on cancel/exception."""
    if not rows:
        return
    print()
    print(
        f'{"Search Name":<26} {"Full Name":<28} {"DUPR ID":<12} {"Doubles":<14} {"Rel%":<6} '
        f'{"DUPR range":<14} {"Location":<22}'
    )
    print("=" * 125)
    for r in rows:
        if r.get("error"):
            print(f"{r.get('search_name', '?'):<26} ERROR: {r['error']}")
        else:
            print(
                f"{r.get('search_name', ''):<26} {r.get('full', 'N/A'):<28} "
                f"{r.get('dupr_id', 'N/A'):<12} {r.get('doubles_display', r.get('doubles_str', 'NR')):<14} "
                f"{r.get('reliability', '—'):<6} {r.get('dupr_range', '—'):<14} {r.get('addr', 'N/A'):<22}"
            )


def main():
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        players = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = _first_last_from_csv_row(row)
                if name:
                    players.append(name)
    else:
        players = [
            "Chris Murphy", "Taylor Osieczanek", "Ryan Ingram", "Garrett Loria",
            "Colby Smith", "Jen Osieczanek", "Justin Floyd", "Scott Jackson",
            "Tom Midanier", "Leslie Markley", "Kevin Smith", "Luke Eha",
            "Linh Ton", "Dustin Kitson", "Jonathan Chui", "Lindsay Clark",
            "Natalie G", "Drew Boston", "Demian Mallo", "Steve Lopez",
        ]

    client = DuprClient()
    rows = []

    try:
        for name in players:
            try:
                status, result = client.search_players(name, limit=5)
                if status == 200 and result and result.get("hits"):
                    hit = result["hits"][0]
                    full = hit.get("fullName", "N/A")
                    dupr_id = hit.get("duprId", "N/A")
                    ratings = hit.get("ratings") or {}
                    doubles = ratings.get("doubles", "NR")
                    if isinstance(doubles, dict) and "rating" in doubles:
                        doubles = doubles.get("rating", "NR")
                    doubles_str = str(doubles) if doubles is not None else "NR"
                    addr = (hit.get("shortAddress") or "N/A")[:22]
                    # Reliability is NOT in search hit — fetch full player via get_player(duprId)
                    reliability = "—"
                    reliability_pct = None
                    if dupr_id and dupr_id != "N/A":
                        time.sleep(0.15)
                        rc, player_data = client.get_player(dupr_id)
                        if rc == 200 and player_data:
                            reliability = _doubles_reliability_from_player(player_data)
                            try:
                                reliability_pct = int(float(re.search(r"\d+", reliability).group()))
                            except (ValueError, TypeError, AttributeError):
                                pass
                    doubles_num = None
                    try:
                        doubles_num = float(doubles_str)
                    except (ValueError, TypeError):
                        pass
                    margin = _dupr_margin(doubles_num, reliability_pct)
                    dupr_range = _dupr_range_str(doubles_num, reliability_pct)
                    doubles_display = _doubles_display(doubles_str, doubles_num, margin)
                    rows.append({
                        "search_name": name,
                        "full": full,
                        "dupr_id": str(dupr_id),
                        "doubles_str": doubles_str,
                        "doubles_display": doubles_display,
                        "reliability": reliability,
                        "reliability_pct": reliability_pct,
                        "dupr_range": dupr_range,
                        "addr": addr,
                    })
                else:
                    rows.append({
                        "search_name": name,
                        "full": "--- NOT FOUND ---",
                        "dupr_id": "N/A",
                        "doubles_str": "NR",
                        "doubles_display": "NR",
                        "reliability": "—",
                        "dupr_range": "—",
                        "addr": "N/A",
                    })
                time.sleep(0.3)
            except Exception as e:
                rows.append({"search_name": name, "error": str(e)})
    finally:
        _print_results_table(rows)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("\n[Interrupted]", file=sys.stderr)
        sys.exit(130)
