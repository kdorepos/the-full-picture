#!/usr/bin/env python3
"""Enrich an episode JSON with TMDb ids + poster paths.

Adds a top-level "tmdb" map: title -> {id, poster, title, year} (or null if no
confident match). The site resolves poster thumbnails and TMDb links by title.

Year-aware matching fixes Whisper's title collisions: a pick tagged year 2026
won't match "Werewolf by Night (2022)" — if TMDb has no 2026 entry, it's left
null (too-new indie) rather than mislinked.

Usage: TMDB_KEY=... ./pipeline/enrich_tmdb.py web/src/data/episodes/<slug>.json
"""
import json, os, re, sys, time, urllib.parse, urllib.request

KEY = os.environ["TMDB_KEY"]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def ry(r):
    return int((r.get("release_date") or "0")[:4] or 0)


def search(title, year):
    """Require an EXACT (normalized) title match — a mere year-proximity hit links
    the wrong film (a coincidental 2026 release, a same-name reboot). With a year in
    hand, also require the match to be within a year of it (or have an unknown date),
    so a title reused decades apart (Jack of Spades 1960) is rejected as null."""
    q = urllib.parse.urlencode({"query": title, "api_key": KEY})
    try:
        results = json.load(urllib.request.urlopen(
            f"https://api.themoviedb.org/3/search/movie?{q}", timeout=15))["results"]
    except Exception:
        return None
    exact = [r for r in results if norm(r["title"]) == norm(title)]
    if not exact:
        return None
    if year:
        exact = [r for r in exact if ry(r) == 0 or abs(ry(r) - year) <= 1]
        if not exact:
            return None
    pick = exact[0]
    return {
        "id": pick["id"],
        "poster": pick.get("poster_path"),
        "title": pick["title"],
        "year": ry(pick) or None,
    }


def clean(t):
    return re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()  # drop trailing "(director)" notes


def main():
    path = sys.argv[1]
    ep = json.load(open(path))

    # (title, year) for everything linkable, across episode types. Excluded (TV/games/ads) skipped.
    # `picks` = films a host actually chose (high value); an unmatched pick is a red flag worth review.
    items, picks = {}, set()
    def pick(title, year):
        items[title] = year
        picks.add(title)
    for s in ep.get("slates", []):            # auction episodes
        for p in s["picks"]:
            pick(p["title"], p.get("year"))
    for p in ep.get("picks", []):             # list / roundtable episodes
        pick(p["title"], p.get("year"))
    if ep.get("interview"):
        iv = ep["interview"]
        pick(iv["title"], iv.get("year", 2026))
    for t in ep.get("seansTopFive", []):      # a host's running top list — 2026 releases
        pick(t, 2026)
    for s in ep.get("januarySlate", []):      # first-half slate — all 2026 releases
        for p in s["picks"]:
            pick(p["title"], 2026)
    for t in ep.get("undrafted", []):         # discussed upcoming films — 2026 context
        items.setdefault(t, 2026)
    for g in ep.get("referenced", []):        # mix of 2026 + older; no reliable year -> exact-title only
        for t in g["films"]:
            items.setdefault(t, None)

    tmdb, hits = {}, 0
    for title, year in items.items():
        m = search(clean(title), year)
        tmdb[title] = m
        hits += 1 if m else 0
        time.sleep(0.05)

    ep["tmdb"] = tmdb
    json.dump(ep, open(path, "w"), ensure_ascii=False, indent=2)
    print(f"{hits}/{len(items)} titles matched -> {path}")

    # Tripwire: unmatched PICKS are usually a mishear (a wrong exact match can't be caught here).
    # Either way the review step is required — flag it loudly so it isn't skipped.
    missing = sorted(t for t in picks if not tmdb.get(t))
    if missing:
        print(f"\n⚠  {len(missing)} pick(s) UNMATCHED — likely a title mishear:")
        for t in missing:
            print(f"     - {t}")
    print("\nNEXT (required): run the film-title-reviewer agent on this episode before publishing.")


if __name__ == "__main__":
    main()
