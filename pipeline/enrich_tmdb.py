#!/usr/bin/env python3
"""Enrich an episode JSON with TMDb ids + poster paths.

Adds a top-level "tmdb" map: title -> {id, poster, title, year} (or null if no
confident match). The site resolves poster thumbnails and TMDb links by title.

Year-aware matching fixes Whisper's title collisions: a pick tagged year 2026
won't match "Werewolf by Night (2022)" — if TMDb has no 2026 entry, it's left
null (too-new indie) rather than mislinked.

Usage: TMDB_KEY=... ./pipeline/enrich_tmdb.py web/src/data/episodes/<slug>.json
"""
import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

KEY = os.environ["TMDB_KEY"]


def norm(s):
    # Fold accents (Amélie -> amelie) instead of dropping them, so an exact match
    # survives inconsistent diacritics between the pick and the TMDb title.
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def ry(r):
    return int((r.get("release_date") or "0")[:4] or 0)


def search(title, year):
    """Require an EXACT (normalized) title match — a mere year-proximity hit links
    the wrong film (a coincidental 2026 release, a same-name reboot). With a year in
    hand, also require the match to be within a year of it (or have an unknown date),
    so a title reused decades apart (Jack of Spades 1960) is rejected as null.

    Returns (match, candidates). `match` is the provisional pick (most-popular exact
    title, TMDb's ordering) or None. `candidates` is the list of exact-title matches
    when there is MORE THAN ONE — an ambiguous case (a remake, a reused title) the
    provisional pick guesses at; the review step gets these to pick the right id."""
    q = urllib.parse.urlencode({"query": title, "api_key": KEY})
    try:
        results = json.load(urllib.request.urlopen(
            f"https://api.themoviedb.org/3/search/movie?{q}", timeout=15))["results"]
    except Exception:
        return None, []
    exact = [r for r in results if norm(r["title"]) == norm(title)]
    if not exact:
        return None, []
    if year:
        exact = [r for r in exact if ry(r) == 0 or abs(ry(r) - year) <= 1]
        if not exact:
            return None, []
    pick = exact[0]
    match = {"id": pick["id"], "poster": pick.get("poster_path"),
             "title": pick["title"], "year": ry(pick) or None}
    # Doubtful only when the pick had NO year to go on AND the exact matches span multiple distinct
    # years — a remake / reused title (Ghostbusters 1984 vs 2016) the most-popular pick just guesses
    # at. A year-having pick is already era-disambiguated; same-year duplicate entries aren't a real
    # ambiguity. Give the reviewer each candidate's {id, year} so it can pick from the transcript's era.
    span = len({ry(r) for r in exact if ry(r)}) > 1
    # id + year only (no overview): the reviewer disambiguates by matching the transcript's era to a
    # candidate year. Cap at 8 (TMDb popularity order) — the intended film is near the top.
    # ponytail: 8-cap ceiling; a correct match ranked lower keeps the provisional pick.
    cands = [{"id": r["id"], "year": ry(r) or None}
             for r in exact[:8]] if (not year and span) else []
    return match, cands


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
    args = sys.argv[1:]
    cand_path = None
    if "--candidates" in args:  # optional sidecar of ambiguous same-title matches, for the review step
        i = args.index("--candidates")
        if i + 1 >= len(args):
            sys.exit("--candidates needs a path")
        cand_path = args[i + 1]
        args = args[:i] + args[i + 2:]
    path = args[0]
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

    tmdb, ambiguous = {}, {}
    for title, year in items.items():
        tmdb[title], cands = search(clean(title), year)
        if cands:
            ambiguous[title] = cands
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

    # Ambiguous = >1 same-title film; the provisional pick guessed. Drop any the reviewer already
    # pinned via override, write the rest to the sidecar for the review step to disambiguate.
    overridden = set(ep.get("tmdbOverrides", {}))
    ambiguous = {t: c for t, c in ambiguous.items() if t not in overridden}
    if cand_path:
        json.dump(ambiguous, open(cand_path, "w"), ensure_ascii=False, indent=2)
    if ambiguous:
        print(f"\nℹ  {len(ambiguous)} title(s) with MULTIPLE same-title TMDb matches (provisional pick may be wrong):")
        for t, c in ambiguous.items():
            opts = ", ".join(f"{x['year']}#{x['id']}" for x in c)
            print(f"     - {t}: {opts}")

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
