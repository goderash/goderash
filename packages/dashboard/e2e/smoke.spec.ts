/**
 * Dashboard smoke tests — verify each page loads without crashing.
 *
 * These tests do NOT require a live Goderash control plane. Every page
 * handles fetch errors gracefully (showing an error card or empty state),
 * so the smoke just confirms the page renders at all and the <h1> is present.
 *
 * Set GODERASH_ENDPOINT to a real instance to test against live data.
 */

import { expect, test } from '@playwright/test'

const PAGES = [
  { path: '/', heading: 'Overview' },
  { path: '/events', heading: 'Events' },
  { path: '/verify', heading: 'Verify' },
  { path: '/packs', heading: 'Compliance packs' },
  { path: '/whatif', heading: 'What-If' },
  { path: '/settings', heading: 'Settings' },
]

for (const { path, heading } of PAGES) {
  test(`${path} — renders heading "${heading}"`, async ({ page }) => {
    await page.goto(path)
    await expect(page.locator('h1')).toContainText(heading)
  })
}

test('nav links are all present', async ({ page }) => {
  await page.goto('/')
  const nav = page.locator('nav')
  await expect(nav).toBeVisible()
  for (const { heading } of PAGES) {
    if (heading === 'Overview') continue
    await expect(nav.locator(`text=${heading}`)).toBeVisible()
  }
})

test('settings page shows connection info', async ({ page }) => {
  await page.goto('/settings')
  await expect(page.locator('text=GODERASH_ENDPOINT')).toBeVisible()
  await expect(page.locator('text=GODERASH_API_KEY')).toBeVisible()
  await expect(page.locator('text=GODERASH_TENANT')).toBeVisible()
})

test('events page shows empty state or table rows', async ({ page }) => {
  await page.goto('/events')
  const table = page.locator('table')
  const emptyMsg = page.locator('text=no events yet')
  // One of the two must be visible — either data or empty state.
  await expect(table.or(emptyMsg)).toBeVisible({ timeout: 15_000 })
})

test('verify page shows chain status or error', async ({ page }) => {
  await page.goto('/verify')
  const status = page.locator('text=Chain status').or(page.locator('text=Error'))
  await expect(status).toBeVisible({ timeout: 15_000 })
})

test('packs page shows regulation cards or empty state', async ({ page }) => {
  await page.goto('/packs')
  const content = page
    .locator('text=SOC 2')
    .or(page.locator('text=No packs registered'))
    .or(page.locator('text=HIPAA'))
  await expect(content).toBeVisible({ timeout: 15_000 })
})
