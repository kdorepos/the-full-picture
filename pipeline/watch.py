#!/usr/bin/env python3
"""Watch the podcast RSS feed for episodes newer than what's on the site.

Compares the feed's newest items against the published dates already in
web/src/data/episodes/. Prints (or emits JSON for) episodes to ingest. It only
looks at items NEWER than the newest on-site episode, so it flags genuinely new
drops — not the older backlog you deliberately skipped.

Usage: ./pipeline/watch.py [--json] [--feed URL] [--episodes-dir DIR]
Exit 10 if there are new episodes, 0 if none (so a scheduler can branch on it).
"""
import re, os, sys, json, html, argparse, urllib.request, unicodedata
from email.utils import parsedate_to_datetime

FEED = "https://feeds.megaphone.fm/the-big-picture"
UA = "Mozilla/5.0"


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "episode"


def unique_slug(title, date, existing):
    """slug(title), disambiguated with the publish YEAR when the base already exists — the
    show reuses annual titles with no year in them ("The Summer Movie Mailbag", "The Epic
    Movie Draft", Hall of Fame inductions), which would otherwise collide onto one file/URL
    and silently overwrite last year's episode. Stable: an already-published year-suffixed
    episode keeps returning its own slug (base is taken, so it re-derives -<year>).
    # ponytail: assumes at most one same-title episode per year (true for an annual show);
    # a same-year repeat would still collide — revisit only if the cadence changes."""
    base = slug(title)
    if base not in existing:
        return base
    year = (date or "")[:4]
    return f"{base}-{year}" if year else base


def feed_items(url, episodes_dir="web/src/data/episodes"):
    body = urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30
    ).read().decode("utf-8", "replace")
    try:  # existing slugs so recurring-title episodes get a year suffix, not a collision
        existing = {f[:-5] for f in os.listdir(episodes_dir) if f.endswith(".json")}
    except OSError:
        existing = set()
    out = []
    for i, chunk in enumerate(body.split("<item>")[1:]):
        b = chunk.split("</item>")[0]
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", b, re.S)
        au = re.search(r'<enclosure[^>]+url="([^"]+)"', b, re.I)
        pub = re.search(r"<pubDate>([^<]+)</pubDate>", b)
        if not (t and au and pub):
            continue
        try:
            date = parsedate_to_datetime(pub.group(1)).date().isoformat()
        except Exception:
            continue
        title = html.unescape(t.group(1).strip())  # &amp; -> & before slug/display
        # Strip Megaphone's ?updated= cache-buster so the URL is a stable id for pinning
        # (the query param changes over time and breaks exact-URL matching).
        url = au.group(1).split("?")[0]
        out.append({"index": i, "title": title, "date": date, "url": url,
                    "slug": unique_slug(title, date, existing)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default=FEED)
    ap.add_argument("--episodes-dir", default="web/src/data/episodes")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    items = feed_items(a.feed, a.episodes_dir)
    # Identify already-published episodes by (published-date, base title-slug) read from the JSONs —
    # NOT the on-disk filename. unique_slug's year suffix isn't stable for a bare-published episode:
    # its own file makes the base look "taken", so on re-check unique_slug re-derives base-<year>,
    # which no filename matches, and the episode looks falsely "new". (date, slug(title)) uniquely
    # identifies an episode and survives that re-derivation; two same-title episodes differ by date.
    have = set()
    for f in os.listdir(a.episodes_dir):
        if not f.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(a.episodes_dir, f)))
            have.add((d.get("published", ""), slug(d.get("title", ""))))
        except Exception:
            pass
    cutoff = max((p for p, _ in have), default="")
    # New = on/after the newest on-site date (skips the deliberately-skipped older backlog) and not
    # already published. `>=` (not `>`) catches a same-day second drop.
    new = [it for it in items if it["date"] >= cutoff and (it["date"], slug(it["title"])) not in have]

    if a.json:
        print(json.dumps(new, indent=2))
    elif not new:
        print(f"No new episodes (site current through {cutoff or 'never'}).")
    else:
        print(f"{len(new)} new episode(s) since {cutoff}:")
        for it in new:
            print(f"  --item {it['index']}  {it['date']}  {it['title']}")
    sys.exit(10 if new else 0)


if __name__ == "__main__":
    main()
