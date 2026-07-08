import { expect, test } from "@playwright/test";

/**
 * Visual regression for an agent-generated Elementor page.
 *
 * KNOWN BLOCKER: `_elementor_data` only persists over the WP REST API once
 * the companion WordPress plugin registers it with `show_in_rest` (see
 * project-structure.md and the Sprint 5 notes in progress-tracker.md).
 * Until that plugin ships, WordPress silently drops the meta and the target
 * page renders blank — this suite is expected to need a new baseline (or
 * simply fail) until that dependency lands. It runs only in the gated
 * eval-live workflow, never as a merge-blocking check.
 *
 * WP_ELEMENTOR_PAGE_SLUG should point at a page already created via
 * wp_create_elementor_page (e.g. by the gated live integration eval) — this
 * spec only screenshots and diffs, it does not generate the page itself.
 */

const PAGE_SLUG = process.env.WP_ELEMENTOR_PAGE_SLUG ?? "eval-elementor-page";

test("agent-generated Elementor page renders without visual regressions", async ({ page }) => {
  await page.goto(`/${PAGE_SLUG}/`);
  await expect(page).toHaveScreenshot("elementor-page.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.02,
  });
});
