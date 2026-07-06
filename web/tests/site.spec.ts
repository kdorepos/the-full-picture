import { test, expect } from '@playwright/test';

// Runs on both the desktop and mobile projects (see playwright.config.ts),
// so every assertion is a usability check across both form factors.

test('home lists the episode and links through to its page', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('link', { name: /2026 Movie Auction/i })).toBeVisible();
  await page.getByRole('link', { name: /2026 Movie Auction/i }).click();
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
  await expect(page.locator('.sale-line')).toContainText('at the hammer');
});

test('episode embeds Spotify, TMDb links, and posters', async ({ page }) => {
  await page.goto('/ep/2026-movie-auction-returns');
  await expect(page.locator('iframe[src*="open.spotify.com/embed/episode"]')).toHaveCount(1);
  await expect(page.locator('.lot__title a[href*="themoviedb.org/movie"]').first()).toBeVisible();
  await expect(page.locator('.lot__poster img').first()).toBeVisible();
});

test('roundtable episode renders pick cards, byline, and interview', async ({ page }) => {
  await page.goto('/ep/the-10-best-movies-of-2026-so-far');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('10 Best Movies');
  await expect(page.locator('.pick-card')).toHaveCount(11);
  await expect(page.locator('.pick-card__by').first()).toContainText('Picked by');
  await expect(page.locator('.interview')).toContainText('John Early');
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
  const box = await page.getByRole('link', { name: /2026 Movie Auction/i }).boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(44); // iOS min tap target
});
