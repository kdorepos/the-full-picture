// Build-time index of every film mentioned across all episodes, plus episode metadata.
// One source of truth for search (#43) and the /movies + /movie/<id> pages (#60).
// Films are deduped by TMDb id (fallback: normalized title) so a film is ONE entry
// no matter how many episodes reference it or how it was spelled.
const modules = import.meta.glob('../data/episodes/*.json', { eager: true });
const episodesRaw = Object.values(modules).map((m) => m.default);

export const norm = (s) =>
  (s || '').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'x';

// segment kind -> how the film appeared (shown as context in results/pages)
const CONTEXT = {
  review: 'Reviewed', ranking: 'Ranked', topfive: 'Top five', halloffame: 'Hall of Fame',
  discussion: 'Discussed', interview: 'Interview', list: 'Pick', roundtable: 'Pick',
  draft: 'Drafted', auction: 'Auctioned', awards: 'Nominated',
};

// title -> context label for one episode, walking every film-bearing structure
// (mirrors pipeline/enrich_tmdb.py's traversal).
function titleContexts(ep) {
  const ctx = {};
  const put = (title, label) => { if (title && !(title in ctx)) ctx[title] = label; };
  for (const s of ep.segments ?? []) {
    const label = CONTEXT[s.kind] ?? 'Mentioned';
    (s.films ?? []).forEach((f) => put(f.title, label));
    (s.picks ?? []).forEach((p) => put(p.title, label));
    (s.teams ?? []).forEach((t) => (t.picks ?? []).forEach((p) => put(p.title, 'Drafted')));
    (s.slates ?? []).forEach((sl) => (sl.picks ?? []).forEach((p) => put(p.title, 'Auctioned')));
    (s.januarySlate ?? []).forEach((sl) => (sl.picks ?? []).forEach((p) => put(p.title, 'Auctioned')));
    (s.categories ?? []).forEach((c) => (c.nominees ?? []).forEach((n) => put(n.title, 'Nominated')));
    (s.undrafted ?? []).forEach((t) => put(t, 'Undrafted'));
  }
  for (const g of ep.referenced ?? []) (g.films ?? []).forEach((t) => put(t, 'Referenced'));
  return ctx;
}

let _index = null;
export function mentionIndex() {
  if (_index) return _index;
  const films = new Map();
  const episodes = [];
  for (const ep of episodesRaw) {
    const ctx = titleContexts(ep);
    const tmdb = ep.tmdb ?? {};
    // The tmdb map is the authoritative FILM list (enrich_tmdb only adds real films —
    // year-less draft picks like ships/characters are excluded). Key off it, use the
    // walk only to attach context.
    for (const title of Object.keys(tmdb)) {
      const meta = tmdb[title] || null;
      const id = meta?.id ?? null;
      const key = id ? `t${id}` : `n${norm(title)}`;
      if (!films.has(key)) {
        films.set(key, {
          key,
          slug: id ? String(id) : norm(title), // /movie/<slug>
          id,
          title: meta?.title ?? title,
          year: meta?.year ?? null,
          poster: meta?.poster ?? null,
          mentions: [],
        });
      }
      films.get(key).mentions.push({
        slug: ep.slug, episodeTitle: ep.title, date: ep.published, context: ctx[title] ?? 'Mentioned',
      });
    }
    episodes.push({ slug: ep.slug, title: ep.title, date: ep.published });
  }
  const byTitle = (a, b) => a.title.localeCompare(b.title, 'en', { sensitivity: 'base' });
  const newestFirst = (a, b) => (a.date < b.date ? 1 : -1);
  const filmList = [...films.values()].sort(byTitle);
  filmList.forEach((f) => f.mentions.sort(newestFirst));
  episodes.sort(newestFirst);
  _index = { films: filmList, episodes };
  return _index;
}
