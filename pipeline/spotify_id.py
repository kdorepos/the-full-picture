#!/usr/bin/env python3
"""Resolve an episode's Spotify id deterministically and write it into the episode JSON.

The MCP/app search is fuzzy and won't surface plain-titled back-catalog episodes
(e.g. "The 2026 Movie Auction" is shadowed by the "…Returns!" one). Instead this lists
the show's episodes via the Spotify Web API and matches by exact title (or release date),
which is deterministic.

Setup (one-time): create a free app at developer.spotify.com/dashboard (no redirect URI
needed — client-credentials only) and put its Client ID/Secret in .env:
    SPOTIFY_CLIENT_ID=...
    SPOTIFY_CLIENT_SECRET=...

Usage: SPOTIFY_CLIENT_ID=… SPOTIFY_CLIENT_SECRET=… ./pipeline/spotify_id.py <episode.json> [--show <id>]
Reads `title` + `published` from the JSON, finds the episode, writes `spotifyEpisodeId`.
"""
import base64, json, os, re, sys, time, unicodedata, urllib.request

SHOW = "6mTel3azvnK8isLs4VujvF"  # The Big Picture (The Ringer)


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def token():
    cid, secret = os.environ["SPOTIFY_CLIENT_ID"], os.environ["SPOTIFY_CLIENT_SECRET"]
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    return json.load(urllib.request.urlopen(req, timeout=15))["access_token"]


def find_episode(show, title, date, tok):
    """Episodes come newest-first; match on normalized title (strongest) or exact date,
    and stop paging once we're safely older than the target date."""
    nt, offset = norm(title), 0
    while offset < 1200:
        req = urllib.request.Request(
            f"https://api.spotify.com/v1/shows/{show}/episodes?market=US&limit=50&offset={offset}",
            headers={"Authorization": f"Bearer {tok}"})
        items = json.load(urllib.request.urlopen(req, timeout=20)).get("items", [])
        if not items:
            return None
        for ep in items:
            if ep and (norm(ep["name"]) == nt or ep.get("release_date") == date):
                return ep
        if (items[-1].get("release_date") or "") < date:  # paged past the target
            return None
        offset += 50
        time.sleep(0.1)
    return None


def main():
    path = sys.argv[1]
    show = sys.argv[sys.argv.index("--show") + 1] if "--show" in sys.argv else SHOW
    ep = json.load(open(path))
    match = find_episode(show, ep["title"], ep["published"], token())
    if not match:
        sys.exit(f"No Spotify match for '{ep['title']}' ({ep['published']})")
    # Unconditional write — must overwrite an empty placeholder if extraction pre-seeded
    # `spotifyEpisodeId: ""` (setdefault/insert-after-type silently no-op'd in that case).
    ep["spotifyEpisodeId"] = match["id"]
    json.dump(ep, open(path, "w"), ensure_ascii=False, indent=2)
    print(f"matched: {match['name']} ({match.get('release_date')}) -> {match['id']}")


if __name__ == "__main__":
    main()
