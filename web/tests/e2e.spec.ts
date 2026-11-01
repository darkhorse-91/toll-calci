import { test, expect } from '@playwright/test';

test.describe('India Toll Calculator MVP Web Experience', () => {
  test('Autocomplete shows suggestions when typing in origin and destination', async ({ page }) => {
    // Mock the places endpoint to avoid external network flakiness in testing
    await page.route('**/v1/places*', async (route) => {
      const url = new URL(route.request().url());
      const query = url.searchParams.get('q') || '';
      if (query.toLowerCase().includes('luck')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'luck-1', name: 'Lucknow', detail: 'Uttar Pradesh, India', lat: 26.8467, lng: 80.9462 },
            { id: 'luck-2', name: 'Lucknow Airport (LKO)', detail: 'Amausi, Lucknow', lat: 26.7606, lng: 80.8893 },
          ]),
        });
      } else if (query.toLowerCase().includes('ayo')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'ayo-1', name: 'Ayodhya', detail: 'Uttar Pradesh, India', lat: 26.7922, lng: 82.1998 },
          ]),
        });
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      }
    });

    await page.goto('/');

    // Type in origin field
    const fromInput = page.locator('#from-input');
    await fromInput.fill('Lucknow');

    // Wait for dropdown suggestion
    const firstOrigin = page.getByText('Lucknow', { exact: true }).first();
    await expect(firstOrigin).toBeVisible({ timeout: 5000 });
    await firstOrigin.click();

    // Verify input populated
    await expect(fromInput).toHaveValue('Lucknow');

    // Type in destination field
    const toInput = page.locator('#to-input');
    await toInput.fill('Ayodhya');

    const firstDest = page.getByText('Ayodhya', { exact: true }).first();
    await expect(firstDest).toBeVisible({ timeout: 5000 });
    await firstDest.click();

    await expect(toInput).toHaveValue('Ayodhya');
  });

  test('Submitting valid route renders quote card, headline, pass recommendation, and breakdown table', async ({ page }) => {
    // Mock places and quote responses
    await page.route('**/v1/places*', async (route) => {
      const url = new URL(route.request().url());
      const q = (url.searchParams.get('q') || '').toLowerCase();
      if (q.includes('luck')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{ id: 'lko', name: 'Lucknow', lat: 26.8467, lng: 80.9462 }]),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{ id: 'ayo', name: 'Ayodhya', lat: 26.7922, lng: 82.1998 }]),
        });
      }
    });

    await page.route('**/v1/quote', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rates_as_of: '2026-04-01',
          pass_product: {
            effective_year: 2026,
            amount_inr: 3075,
            max_trips: 200,
            valid_days: 365,
          },
          routes: [
            {
              label: 'USUAL',
              distance_km: 135.2,
              est_duration_min: 140,
              geometry: {
                type: 'LineString',
                coordinates: [
                  [80.9462, 26.8467],
                  [81.24, 26.87],
                  [82.1998, 26.7922],
                ],
              },
              toll_with_pass_inr: 0,
              toll_without_pass_inr: 100,
              complete: true,
              pass: {
                eligible: true,
                points_covered: 1,
                points_total: 1,
                trips_used: 1,
                trips_left_after: 199,
                break_even_journeys: 31,
              },
              points: [
                {
                  id: 101,
                  name: 'Nawabganj Toll Plaza',
                  kind: 'PLAZA',
                  operator: 'NHAI',
                  road: 'NH-27',
                  lat: 26.87,
                  lng: 81.24,
                  amount_without_pass_inr: 100,
                  amount_inr: 100,
                  pass_applied: false,
                  trips_used: 0,
                  reason: null,
                },
              ],
              insights: [
                {
                  key: 'revenue',
                  text: 'Nawabganj Toll Plaza collects ~₹1.20 crore per month.',
                  period: '2026-03',
                  source: 'IHMCL',
                },
              ],
            },
          ],
        }),
      });
    });

    await page.goto('/');

    // Select places
    await page.locator('#from-input').fill('Lucknow');
    await page.getByText('Lucknow', { exact: true }).first().click();

    await page.locator('#to-input').fill('Ayodhya');
    await page.getByText('Ayodhya', { exact: true }).first().click();

    // Click submit
    await page.locator('button[type="submit"]').click();

    // Verify headline price in quote total
    const quoteAmt = page.locator('.quote-total .amt');
    await expect(quoteAmt).toBeVisible({ timeout: 5000 });
    await expect(quoteAmt).toContainText('₹100');

    // Verify breakdown table / point list
    await expect(page.locator('.quote-points')).toBeVisible();
    await expect(page.getByText('Nawabganj Toll Plaza', { exact: true })).toBeVisible();

    // Verify pass decision box
    await expect(page.locator('.quote-pass-box')).toBeVisible();
  });

  test('Responsive layout behaves correctly on 360px viewport', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto('/');

    // Check that header and form card exist and are visible
    await expect(page.locator('header.hero')).toBeVisible();
    await expect(page.locator('form.card')).toBeVisible();

    // Verify decorative milestone is hidden on mobile viewport to prioritize calculator
    await expect(page.locator('.stone')).toBeHidden();

    // Verify no unintended horizontal scroll on page body
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2); // allowance for fractional pixel rounding
  });


});
