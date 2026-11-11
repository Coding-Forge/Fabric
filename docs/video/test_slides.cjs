const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { test, before, after } = require("node:test");
const { chromium } = require("playwright");

let browser;
before(async () => {
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
});
after(async () => { await browser?.close(); });

for (const [episode, count] of [["01", 8], ["02", 10], ["03", 9], ["04", 9], ["05", 11], ["06", 10], ["07", 12]]) {
  test(`Episode ${episode}: navigation, notes and direct links`, async () => {
    const page = await browser.newPage();
    try {
      const url = pathToFileURL(path.join(__dirname, `episode-${episode}.html`)).href;
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(url);
      assert.equal(await page.locator(".slide").count(), count);
      assert.equal(await page.locator("#previous").isDisabled(), true);
      await page.keyboard.press("ArrowLeft");
      assert.equal(await page.locator(".slide:visible").count(), 1);
      await page.locator("#next").click();
      await page.locator("#toggle-notes").click();
      assert.equal(await page.locator("#toggle-notes").getAttribute("aria-expanded"), "true");
      assert((await page.locator("#notes").textContent()).length > 100);
      for (let index = 2; index < count; index++) await page.locator("#next").click();
      assert.equal(await page.locator("#next").isDisabled(), true);
      await page.locator("body").click({ position: { x: 1, y: 1 } });
      await page.keyboard.press("ArrowRight");
      assert.equal(await page.locator("#counter").textContent(), `${String(count).padStart(2, "0")} / ${String(count).padStart(2, "0")}`);
      await page.goto("about:blank");
      await page.goto(`${url}#slide-3`);
      assert.equal(await page.locator("#counter").textContent(), `03 / ${String(count).padStart(2, "0")}`);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

for (const [episode, count] of [["02", 10], ["03", 9], ["04", 9], ["05", 11], ["06", 10], ["07", 12]]) {
  test(`Episode ${episode}: capture layout, narrow viewport and local source links`, async () => {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    try {
      const url = pathToFileURL(path.join(__dirname, `episode-${episode}.html`)).href;
      await page.goto(`${url}?capture=1`);
      assert.equal(await page.locator(".review").isVisible(), false);
      for (let index = 0; index < count; index++) {
        const overflow = await page.locator(".slide:visible").evaluate(slide => {
          const bounds = slide.getBoundingClientRect();
          return Array.from(slide.querySelectorAll("h1,h2,h3,p,pre,.callout,.card")).filter(element => {
            const box = element.getBoundingClientRect();
            return box.right > bounds.right + 1 || box.bottom > bounds.bottom - 35 || element.scrollWidth > element.clientWidth + 1;
          }).map(element => element.textContent.trim().slice(0, 60));
        });
        assert.deepEqual(overflow, [], `Slide ${index + 1} overflows`);
        await page.keyboard.press("ArrowRight");
      }
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(url);
      for (let index = 1; index <= count; index++) {
        assert.equal(await page.locator("#counter").textContent(), `${String(index).padStart(2, "0")} / ${String(count).padStart(2, "0")}`);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Slide ${index} narrow overflow`);
        await page.keyboard.press("ArrowRight");
      }
      const fs = require("node:fs");
      for (const href of await page.locator("a").evaluateAll(links => links.map(link => link.getAttribute("href")))) {
        assert(fs.existsSync(path.resolve(__dirname, href)), `Missing source link: ${href}`);
      }
    } finally { await page.close(); }
  });
}
