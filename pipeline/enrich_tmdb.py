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


def by_id(mid):
    """Fetch a specific TMDb movie by id — used to pin reviewer-confirmed matches that
    exact-title search gets wrong (a same-title collision)."""
    try:
        d = json.load(urllib.request.urlopen(
            f"https://api.themoviedb.org/3/movie/{mid}?api_key={KEY}", timeout=15))
    except Exception:
        return None
    return {"id": d["id"], "poster": d.get("poster_path"), "title": d["title"], "year": ry(d) or None}


def clean(t):
    return re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()  # drop trailing "(director)" notes


def main():
    path = sys.argv[1]
    ep = json.load(open(path))

    # (title, year) for everything linkable, walking each segment by kind. Excluded skipped.
    # `picks` = films a host actually chose (high value); an unmatched pick is a red flag worth review.
    items, picks = {}, set()
    # Prior first-half slate + undrafted current-year films share the episode's year,
    # not a fixed 2026 (older back-catalog episodes are 2024/2025).
    ep_year = int((ep.get("published") or "0")[:4]) or None
    def pick(title, year):
        items[title] = year
        picks.add(title)
    for seg in ep.get("segments", []):
        for f in seg.get("films", []):        # review / ranking / topfive / halloffame / discussion / interview
            pick(f["title"], f.get("year"))
        for p in seg.get("picks", []):        # list / roundtable
            pick(p["title"], p.get("year"))
        for t in seg.get("teams", []):        # draft — film picks carry a year; year-less
            for p in t["picks"]:              # picks are non-films (a character/ship/wild card), skip them
                if p.get("year"):
                    pick(p["title"], p["year"])
        for s in seg.get("slates", []):       # auction
            for p in s["picks"]:
                pick(p["title"], p.get("year"))
        if seg.get("kind") == "awards":       # awards — nominees (draft's `categories` are label strings)
            for c in seg["categories"]:
                for n in c["nominees"]:
                    pick(n["title"], n.get("year"))
        for s in seg.get("januarySlate", []):  # auction's prior first-half slate — same year as the episode
            for p in s["picks"]:
                pick(p["title"], ep_year)
        # undrafted = current-year films in an auction (disambiguate by year), historical classics in a draft.
        undrafted_year = None if seg.get("kind") == "draft" else ep_year
        for t in seg.get("undrafted", []):
            items.setdefault(t, undrafted_year)
    for g in ep.get("referenced", []):        # mix of 2026 + older; no reliable year -> exact-title only
        for t in g["films"]:
            items.setdefault(t, None)

    tmdb = {}
    for title, year in items.items():
        tmdb[title] = search(clean(title), year)
        time.sleep(0.05)

    # Reviewer-confirmed overrides win over exact-title search (pin the right same-title film,
    # or null to force "no match" when a title collides with a real but wrong film — e.g. a song
    # nominee whose name is also a movie).
    for title, mid in ep.get("tmdbOverrides", {}).items():
        if mid is None:
            tmdb[title] = None
            continue
        m = by_id(mid)
        if m:
            tmdb[title] = m

    hits = sum(1 for v in tmdb.values() if v)
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
