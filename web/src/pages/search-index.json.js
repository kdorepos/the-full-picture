// Static endpoint: Astro emits this as /search-index.json at build.
// Slim payload (short keys) the header search lazy-loads on first focus.
import { mentionIndex } from '../lib/mentionIndex.js';

export function GET() {
  const { films, episodes } = mentionIndex();
  const payload = {
    films: films.map((f) => ({
      t: f.title,
      s: f.slug,
      y: f.year,
      e: f.mentions.length,
    })),
    episodes: episodes.map((e) => ({ s: e.slug, t: e.title, d: e.date })),
  };
  return new Response(JSON.stringify(payload), {
    headers: { 'content-type': 'application/json' },
  });
}
