import { test, expect } from '@playwright/test';

// Runs on both the desktop and mobile projects (see playwright.config.ts),
// so every assertion is a usability check across both form factors.

test('home lists the episode and links through to its page', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('link', { name: /2026 Movie Auction Returns/i })).toBeVisible();
  await page.getByRole('link', { name: /2026 Movie Auction Returns/i }).click();
  await expect(page).toHaveURL(/\/ep\/2026-movie-auction-returns/);
  await expect(page.getByRole('heading', { level: 1 })).toContainText('2026 Movie Auction');
});

test('episode page shows the top lot and ledger prices', async ({ page }) => {
  await page.goto('/ep/2026-movie-auction-returns');
  // Top lot (Behemoth! $715) appears in both the hero summary and the ledger — scope to the ledger row.
  const topLot = page.locator('.lot--top');
  await expect(topLot.locator('.lot__title')).toContainText('Behemoth!');
  await expect(topLot.locator('.lot__price')).toHaveText('$715');
  await expect(page.getByText('Whalefall')).toBeVisible();
  await expect(page.getByText(/at the hammer/)).toBeVisible();
});

test('episode embeds Spotify, TMDb links, and posters', async ({ page }) => {
  await page.goto('/ep/2026-movie-auction-returns');
  await expect(page.locator('iframe[src*="open.spotify.com/embed/episode"]')).toHaveCount(1);
  await expect(page.locator('.lot__title a[href*="themoviedb.org/movie"]').first()).toBeVisible();
  await expect(page.locator('.lot__poster img').first()).toBeVisible();
});

test('roundtable episode renders its segments (picks, interview, top five)', async ({ page }) => {
  await page.goto('/ep/the-10-best-movies-of-2026-so-far');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('10 Best Movies');
  // list segment: per-critic picks with a "Picked by" byline
  await expect(page.locator('.pick-card__by').filter({ hasText: 'Picked by' }).first()).toBeVisible();
  // interview segment: the guest byline surfaces as a card
  await expect(page.getByText(/John Early/).first()).toBeVisible();
  // top-five segment: its heading and ranked bylines ("No. 1")
  await expect(page.getByText("Sean's running top five")).toBeVisible();
  await expect(page.locator('.pick-card__by').filter({ hasText: 'No. 1' }).first()).toBeVisible();
  await expect(page.locator('iframe[src*="open.spotify.com/embed/episode"]')).toHaveCount(1);
  // no auction furniture leaked into a non-auction episode
  await expect(page.locator('.board')).toHaveCount(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test('no horizontal overflow (responsive fits the viewport)', async ({ page }) => {
  await page.goto('/ep/2026-movie-auction-returns');
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test('tap targets: episode links are large enough to tap', async ({ page }) => {
  await page.goto('/');
  const box = await page.getByRole('link', { name: /2026 Movie Auction Returns/i }).boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(44); // iOS min tap target
});

test('processing panel reveals for an in-flight episode and hides once published', async ({ page }) => {
  // In-flight, not-yet-published episode → panel shows with live progress.
  await page.route('**/api/progress*', (r) => r.fulfill({
    json: { active: true, phase: 'transcribing', slug: 'some-upcoming-episode',
            title: 'Some Upcoming Episode', done: 4, total: 10, pct: 40 },
  }));
  await page.goto('/');
  await expect(page.locator('#processing')).toBeVisible();
  await expect(page.locator('#proc-title')).toHaveText('Some Upcoming Episode');
  await expect(page.locator('#proc-status')).toContainText('4/10 chunks');

  // Same payload but the slug is already on the site → panel stays hidden (no stale card).
  await page.unroute('**/api/progress*');
  await page.route('**/api/progress*', (r) => r.fulfill({
    json: { active: true, phase: 'transcribing', slug: '2026-movie-auction-returns', pct: 90 },
  }));
  await page.reload();
  await expect(page.locator('#processing')).toBeHidden();
});
