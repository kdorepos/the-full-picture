# The Full Picture — house style ("Deep Pine & Gold")

The site has ONE visual identity. New pages, episode types, and components must render in
it — do not reinvent the look per episode or per session. When building UI here, treat the
tokens and rules below as fixed, and paste the theme block at the bottom into your working
prompt. (Adapted from Anthropic's frontend-aesthetics cookbook: lock a theme across
generations; call out the AI-default anti-patterns explicitly.)

## Concept
A green "screening room" — The Big Picture's emerald primary (~#009060) taken several
shades darker — lit by warm gold. Restrained, editorial, poster-forward. The register is a
fine auction/exhibition catalogue, not a dashboard.

## Tokens (source of truth: `src/styles/global.css :root`)
| role | var | value |
|---|---|---|
| page ground (deep pine) | `--ink` | `#0a1611` |
| deep surface | `--curtain` | `#0f1f18` |
| raised card | `--velvet` | `#172b21` |
| primary text (warm ivory) | `--ivory` | `#ece4d3` |
| secondary (sage) | `--muted` | `#93a49a` |
| tertiary / numerals | `--faint` | `#607269` |
| accent — gold | `--brass` | `#c7a667` |
| emphasis figures | `--brass-lit` | `#e6cd92` |
| the one red (SOLD, used once) | `--oxblood` | `#b4433b` |
| hairline | `--line` / `--line-lit` | `#21332a` / `#2e4638` |
| paddles (gold / dusty-blue / rose) | `--paddle-1/2/3` | `#c9a86a` / `#83b0c4` / `#cf6a60` |

Dominant ground + sharp gold accent — never a timid, evenly-distributed palette. Every
color comes from a variable; no one-off hex in components.

## Type (three roles, non-negotiable)
- **Display** — `Bodoni Moda` (Didone), large and sparing: episode titles, film titles, hosts.
- **Body/labels** — `Archivo` (grotesque).
- **Figures/data** — `IBM Plex Mono`: every price, year, paddle number, tally. Tabular.

Self-hosted via `@fontsource`. Never Inter / Roboto / Arial / Space Grotesk / system stacks.

## Backgrounds — atmosphere, not a flat fill
Deep-pine radial gradient + a fixed **film-grain** SVG-noise layer (opacity ~0.045) + a
**vignette** (`body::before` / `::after`, behind content so type stays crisp). Grain is the
subject's own material — keep it subtle.

## Motion
One orchestrated page-load: the hero rises with staggered `animation-delay` (`rise`
keyframe). No scattered micro-interactions. Always honor `prefers-reduced-motion`.

## Structure = information
- **Auction** episodes: numbered **paddles** (draft order, the three tones) + a hammer-price
  **ledger** ranked by price, with a right-aligned gold money column and one **"Sold"** stamp.
- **List / roundtable** episodes: poster-forward **pick cards** (one critic, one film — no
  ranks or prices), an interview block, a host's ranked top-five.
- Posters + TMDb links throughout. A confirmed-but-unreleased film shows a hatched placeholder.

## Never (AI-default anti-patterns)
Inter/Roboto/Arial/system fonts · Space Grotesk · purple-or-blue gradients on white · flat
solid backgrounds · timid evenly-distributed palettes · rounded-card SaaS templating ·
reinventing the look for a new episode type instead of extending this one.

## Paste this when building new UI here
```
<the_full_picture_theme>
Match the existing "Deep Pine & Gold" identity exactly — do not invent a new look.
Ground: deep pine green (#0a1611) with a film-grain + vignette (never a flat fill).
Accent: warm gold (#c7a667); one muted red (#b4433b) used sparingly. Text: warm ivory.
Type: Bodoni Moda (display), Archivo (body), IBM Plex Mono (all figures) — never Inter/
Roboto/system/Space Grotesk. All color via the CSS variables in src/styles/global.css.
Motion: one staggered page-load reveal, reduced-motion safe. Poster-forward, catalogue
register. Structure encodes real info (paddles/ranks), never decoration.
</the_full_picture_theme>
```
