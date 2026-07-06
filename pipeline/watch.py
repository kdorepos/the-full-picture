#!/usr/bin/env python3
"""Watch the podcast RSS feed for episodes newer than what's on the site.

Compares the feed's newest items against the published dates already in
web/src/data/episodes/. Prints (or emits JSON for) episodes to ingest. It only
looks at items NEWER than the newest on-site episode, so it flags genuinely new
drops — not the older backlog you deliberately skipped.

Usage: ./pipeline/watch.py [--json] [--feed URL] [--episodes-dir DIR]
Exit 10 if there are new episodes, 0 if none (so a scheduler can branch on it).
"""
import re, os, sys, json, argparse, urllib.request, unicodedata
from email.utils import parsedate_to_datetime

FEED = "https://feeds.megaphone.fm/the-big-picture"
UA = "Mozilla/5.0"


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "episode"


def feed_items(url):
    body = urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30
    ).read().decode("utf-8", "replace")
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
        title = t.group(1).strip()
        out.append({"index": i, "title": title, "date": date, "url": au.group(1), "slug": slug(title)})
    return out


def newest_on_site(d):
    dates = []
    for f in os.listdir(d):
        if f.endswith(".json"):
            try:
                dates.append(json.load(open(os.path.join(d, f))).get("published", ""))
            except Exception:
                pass
    return max(dates) if dates else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default=FEED)
    ap.add_argument("--episodes-dir", default="web/src/data/episodes")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    items = feed_items(a.feed)
    have_slug = {os.path.splitext(f)[0] for f in os.listdir(a.episodes_dir) if f.endswith(".json")}
    cutoff = newest_on_site(a.episodes_dir)
    # New = published after the newest episode on the site, and not already added.
    new = [it for it in items if it["date"] > cutoff and it["slug"] not in have_slug]

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
