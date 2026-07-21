#!/usr/bin/env python3
# Notify-to-post: when a new episode goes live, push the operator a ready-to-post r/TheBigPicture
# comment + a one-tap link to search the sub for that episode's thread. HUMAN-IN-THE-LOOP by design —
# the operator taps and posts it themselves in a normal browser. No Reddit API, no automation on
# Reddit's side (Reddit's 2026 API gating makes the sanctioned poster impractical, and headless
# auto-posting violates their User Agreement / risks the account — see the reddit-autocomment issue).
#
# Push goes via ntfy.sh (free, no account — subscribe to the topic in the ntfy app) when NTFY_TOPIC
# is set in .env; otherwise it falls back to a GitHub issue via alert.sh. Fires once per episode.
#
# Usage: reddit_notify.py <slug>
import sys, os, re, json, subprocess, urllib.parse, urllib.request

REPO = "/srv/the-full-picture"
SUBREDDIT = "TheBigPicture"   # r/TheBigPicture — change here if the sub name differs
def env(k):
    try:
        for line in open(f"{REPO}/.env"):
            if line.startswith(k + "="):
                return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: reddit_notify.py <slug>")
    slug = sys.argv[1]
    if not re.fullmatch(r"[a-z0-9-]{1,60}", slug):   # matches the pipeline's slug() — no path traversal
        sys.exit(f"bad slug: {slug!r}")
    marker = f"{REPO}/out/{slug}/.reddit-notified"
    if os.path.exists(marker):   # already notified for this episode — don't double-ping on a re-publish
        print(f"reddit-notify: already notified for {slug}, skipping")
        return

    jpath = f"{REPO}/web/src/data/episodes/{slug}.json"
    title = slug
    if os.path.exists(jpath):
        try: title = json.load(open(jpath)).get("title", slug)
        except Exception: pass

    ep_url = f"https://thefullpicture.app/ep/{slug}"
    comment = f"This episode is now available on The Full Picture 🎞️\n\n{ep_url}"
    thread_search = f"https://www.reddit.com/r/{SUBREDDIT}/search/?" + urllib.parse.urlencode(
        {"q": title, "restrict_sr": "1", "sort": "new"})

    topic = env("NTFY_TOPIC")
    if topic:
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{topic}", data=comment.encode("utf-8"),
                headers={
                    "Title": f"New episode live - post to r/{SUBREDDIT}",
                    "Click": thread_search,   # tap the notification -> the thread search; long-press the body to copy the comment
                    "Tags": "clapper",
                })
            urllib.request.urlopen(req, timeout=15).read()
            open(marker, "w").close()
            print(f"reddit-notify: pushed via ntfy for {slug}")
            return
        except Exception as e:
            print(f"reddit-notify: ntfy failed ({type(e).__name__}: {e}) — falling back to GitHub issue")

    # Fallback: a GitHub issue (operator already gets those). Body carries the comment + thread link.
    body = (f"New episode is live: {ep_url}\n\n"
            f"**Post this comment** to the r/{SUBREDDIT} episode thread:\n\n"
            f"> This episode is now available on The Full Picture 🎞️\n>\n> {ep_url}\n\n"
            f"Find the thread: {thread_search}\n\n"
            f"(Set `NTFY_TOPIC` in .env for a phone push instead of an issue.)")
    try:
        subprocess.run(["/home/kdor/backfill/alert.sh", f"reddit-post:{slug}",
                        f"Post {slug} to r/{SUBREDDIT}", body], timeout=60)
        open(marker, "w").close()
        print(f"reddit-notify: raised GitHub issue for {slug}")
    except Exception as e:
        print(f"reddit-notify: FAILED for {slug} ({type(e).__name__}: {e})")

if __name__ == "__main__":
    main()
