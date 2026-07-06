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

test('episode page shows draft picks with prices', async ({ page }) => {
  await page.goto('/ep/2026-movie-auction-returns');
  await expect(page.getByText('Behemoth!')).toBeVisible();
  await expect(page.getByText('$715')).toBeVisible();
  await expect(page.getByText('Whalefall')).toBeVisible();
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
