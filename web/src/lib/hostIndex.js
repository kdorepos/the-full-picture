// Build-time index of every host/guest across all episodes, for the /hosts + /host/<slug> pages
// and the clickable host names in episode credits. Mirrors mentionIndex.js. Source = each episode's
// hosts[] (already includes guests who co-host a segment).
const modules = import.meta.glob('../data/episodes/*.json', { eager: true });
const episodesRaw = Object.values(modules).map((m) => m.default);

const slugify = (s) =>
  (s || '').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'host';

// Fold known misspellings / name-form variants onto one canonical name so a host isn't split
// across two pages with divided counts. The four misspellings are ALSO fixed in the source JSONs,
// so they're no-ops today — kept as regression insurance because these are recurring Whisper
// mishears of names ("Sean Fennessy" x124, "Adam Naiman" x28) that will resurface in a new episode
// before a human corrects it. Tim/Juliette variants are alias-only. Add new variants as found.
const ALIASES = {
  'Sean Fennessy': 'Sean Fennessey',
  'Adam Naiman': 'Adam Nayman',
  'Yasi Salik': 'Yasi Salek',
  'Zach Barron': 'Zach Baron',
  'Tim Simons': 'Timothy Simons',
  'Juliette Littman': 'Juliet Litman',
  'Juliette Lim': 'Juliet Litman',
};
const canonical = (name) => ALIASES[name] ?? name;

// Canonical URL slug for a host name — shared with episode credits so a variant spelling still
// links to the right person's page.
export const hostSlug = (name) => slugify(canonical(name));

let _index = null;
export function hostIndex() {
  if (_index) return _index;
  const hosts = new Map(); // canonical name -> { name, slug, episodes: [] }
  for (const ep of episodesRaw) {
    const seen = new Set(); // guard against a variant + its canonical both appearing in one episode
    for (const raw of ep.hosts ?? []) {
      const name = canonical(raw);
      if (seen.has(name)) continue;
      seen.add(name);
      if (!hosts.has(name)) hosts.set(name, { name, slug: slugify(name), episodes: [] });
      hosts.get(name).episodes.push({ slug: ep.slug, title: ep.title, date: ep.published });
    }
  }
  const list = [...hosts.values()];
  list.forEach((h) => {
    h.count = h.episodes.length;
    h.episodes.sort((a, b) => (a.date < b.date ? 1 : -1)); // newest first
  });
  // Descending by appearances, then alphabetical.
  list.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));
  _index = { hosts: list };
  return _index;
}
