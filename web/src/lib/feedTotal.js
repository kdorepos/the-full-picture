// Live episode total, fetched from the podcast RSS feed once at build time (ESM modules are
// evaluated once, so this fires a single fetch no matter how many pages import it). The site
// rebuilds on every publish/deploy, so the number stays current with no pipeline wiring.
// Falls back to the committed snapshot in feed-count.json if the feed is unreachable, so a
// flaky feed never breaks a build. Deliberately build-time only — no runtime infra.
import snapshot from '../data/feed-count.json';

const FEED = 'https://feeds.megaphone.fm/the-big-picture';

async function fetchTotal() {
  try {
    const res = await fetch(FEED, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new Error(`feed responded ${res.status}`);
    const xml = await res.text();
    const n = (xml.match(/<\/item>/g) || []).length;   // one </item> per episode (closing tags don't appear in free-text descriptions)
    if (n > 0) return n;
    throw new Error('no <item> elements found');
  } catch (e) {
    console.warn(`[feedTotal] live fetch failed (${e.message}); using snapshot ${snapshot.total}`);
    return snapshot.total;
  }
}

export const feedTotal = await fetchTotal();
