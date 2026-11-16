const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { test, before, after } = require("node:test");
const { chromium } = require("playwright");

const docs = path.resolve(__dirname, "..");
const repo = path.resolve(docs, "..");
const pages = ["index.html", "get-started.html", "learn.html", "investigation.html"];
const sourcePrefix = "https://github.com/Coding-Forge/Fabric/blob/main/";
const treePrefix = "https://github.com/Coding-Forge/Fabric/tree/main/";
const tracked = new Set(execFileSync("git", ["ls-files", "-z"], { cwd: repo, encoding: "utf8" }).split("\0"));
const mime = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".png": "image/png", ".mp4": "video/mp4" };
let server;
let browser;
let origin;

before(async () => {
  server = http.createServer((request, response) => {
    const url = new URL(request.url, "http://localhost");
    let relative;
    try { relative = decodeURIComponent(url.pathname.slice("/Fabric/".length)); }
    catch { response.writeHead(400).end(); return; }
    if (!url.pathname.startsWith("/Fabric/")) { response.writeHead(404).end(); return; }
    if (!relative || relative.endsWith("/")) relative += "index.html";
    const target = path.resolve(docs, relative);
    if (!target.startsWith(`${docs}${path.sep}`) || relative.includes("node_modules") || relative.includes("output/") || !mime[path.extname(target)] || !fs.existsSync(target)) {
      response.writeHead(404).end(); return;
    }
    const size = fs.statSync(target).size;
    const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range || "");
    let start = 0;
    let end = size - 1;
    const headers = { "Content-Type": mime[path.extname(target)], "Accept-Ranges": "bytes" };
    if (range) {
      start = Number(range[1]);
      end = range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
      if (start > end) { response.writeHead(416).end(); return; }
      headers["Content-Range"] = `bytes ${start}-${end}/${size}`;
    }
    headers["Content-Length"] = end - start + 1;
    response.writeHead(range ? 206 : 200, headers);
    if (request.method === "HEAD") { response.end(); return; }
    const stream = fs.createReadStream(target, { start, end });
    response.on("close", () => stream.destroy());
    stream.pipe(response);
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
});

after(async () => {
  await browser?.close();
  await new Promise(resolve => {
    if (!server?.listening) return resolve();
    server.close(resolve);
    server.closeAllConnections();
  });
});

test("New pages work at the project-site prefix on desktop and narrow screens", async () => {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  try {
    for (const width of [1440, 820, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      for (const name of pages) {
        await page.goto(`${origin}/Fabric/${name}`);
        assert.equal(await page.locator("main h1").count(), 1);
        assert.equal(await page.locator("main").isVisible(), true);
        assert.equal(await page.locator(".menu-toggle").isVisible(), width <= 820);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${name}: horizontal overflow at ${width}px`);
        assert.deepEqual(await page.locator("img").evaluateAll(images => images.filter(image => !image.hasAttribute("alt")).map(image => image.src)), []);
        const duplicates = await page.locator("[id]").evaluateAll(elements => {
          const seen = new Set();
          return elements.map(element => element.id).filter(id => seen.has(id) || !seen.add(id));
        });
        assert.deepEqual(duplicates, [], `${name}: duplicate anchor IDs`);
        if (name === "index.html") {
          const preview = page.locator(".report-preview img");
          await preview.evaluate(async image => { image.loading = "eager"; await image.decode(); });
          const dimensions = await preview.evaluate(image => ({
            displayed: image.clientWidth / image.clientHeight,
            natural: image.naturalWidth / image.naturalHeight,
          }));
          assert(Math.abs(dimensions.displayed - dimensions.natural) < 0.02, "Report preview must retain its aspect ratio");
        }
        if (process.env.SITE_SCREENSHOT_DIR && name === "index.html" && [1440, 390].includes(width)) {
          fs.mkdirSync(process.env.SITE_SCREENSHOT_DIR, { recursive: true });
          await page.screenshot({ path: path.join(process.env.SITE_SCREENSHOT_DIR, `fabric-monitor-${width}.png`), fullPage: true });
        }
      }
    }
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test("Project-site links, anchors, assets and canonical source targets resolve", async () => {
  const page = await browser.newPage();
  const documents = [...pages, "catalog-pbip.html", "blog/fabric-monitor-solution.html", "demo/index.html", ...Array.from({ length: 7 }, (_, index) => `video/episode-0${index + 1}.html`)];
  const checked = new Set();
  try {
    for (const name of documents) {
      await page.goto(`${origin}/Fabric/${name}`);
      const links = await page.locator("a[href], img[src], script[src], link[href], source[src]").evaluateAll(elements =>
        elements.map(element => element.getAttribute("href") || element.getAttribute("src")));
      for (const link of links) {
        const url = new URL(link, page.url());
        if (url.href.startsWith(sourcePrefix)) {
          const relative = decodeURIComponent(url.pathname.slice(new URL(sourcePrefix).pathname.length));
          assert(tracked.has(relative), `Source is not tracked: ${link}`);
        } else if (url.href.startsWith(treePrefix)) {
          const relative = decodeURIComponent(url.pathname.slice(new URL(treePrefix).pathname.length));
          assert([...tracked].some(file => file.startsWith(`${relative}/`)), `Missing source directory: ${link}`);
        } else if (url.origin === origin) {
          assert(url.pathname.startsWith("/Fabric/"), `Escapes project-site prefix: ${name} -> ${link}`);
          const key = `${url.pathname}${url.hash}`;
          if (checked.has(key)) continue;
          checked.add(key);
          const response = await page.request.get(`${origin}${url.pathname}`, { method: url.pathname.endsWith(".mp4") ? "HEAD" : "GET" });
          assert.equal(response.status(), 200, `Missing published target: ${name} -> ${link}`);
          if (url.hash) {
            const id = decodeURIComponent(url.hash.slice(1));
            const html = await response.text();
            assert(html.includes(`id="${id}"`), `Missing anchor: ${name} -> ${link}`);
          }
          await response.dispose();
        }
      }
    }
  } finally { await page.close(); }
});

test("Library search combines words and category, announces counts and handles no results", async () => {
  const page = await browser.newPage();
  try {
    await page.goto(`${origin}/Fabric/learn.html`);
    const visible = page.locator("[data-resource]:visible");
    const total = await visible.count();
    assert(total > 10);
    await page.locator("#resource-search").fill("gold query");
    assert.equal(await visible.count(), 1);
    assert.match(await visible.textContent(), /Gold query examples/);
    await page.locator("#resource-category").selectOption("operate");
    assert.equal(await visible.count(), 0);
    assert.equal(await page.locator("#no-results").isVisible(), true);
    assert.match(await page.locator("#result-count").textContent(), /^0 resources/);
    await page.locator("#resource-search").fill("  AZURE  ");
    assert((await visible.count()) > 0);
    for (const category of await visible.evaluateAll(cards => cards.map(card => card.dataset.category))) assert.equal(category, "operate");
    await page.locator("#resource-category").selectOption("all");
    await page.locator("#resource-search").fill("");
    assert.equal(await visible.count(), total);
    assert.equal(await page.locator("#no-results").isVisible(), false);
  } finally { await page.close(); }
});

test("Mobile navigation works with keyboard, Escape and anchor navigation", async () => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    await page.goto(`${origin}/Fabric/`);
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.textContent), "Skip to content");
    const menu = page.getByRole("button", { name: /Menu/ });
    assert.equal(await page.locator("#nav-links").isVisible(), false);
    await menu.focus();
    await page.keyboard.press("Enter");
    assert.equal(await menu.getAttribute("aria-expanded"), "true");
    assert.equal(await page.locator("#nav-links").isVisible(), true);
    await page.keyboard.press("Escape");
    assert.equal(await menu.getAttribute("aria-expanded"), "false");
    assert.equal(await menu.evaluate(element => element === document.activeElement), true);
    await menu.click();
    await page.locator("#nav-links a[href='#architecture']").click();
    assert.match(page.url(), /#architecture$/);
    assert.equal(await menu.getAttribute("aria-expanded"), "false");
  } finally { await page.close(); }
});

test("Navigation, guide links and FAQs remain available without JavaScript", async () => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  try {
    await page.goto(`${origin}/Fabric/`);
    assert.equal(await page.locator("#nav-links").isVisible(), true);
    await page.getByText("Do I need a Fabric capacity to run the collector?", { exact: true }).click();
    assert.equal(await page.locator("details[open]").count(), 1);
    await page.goto(`${origin}/Fabric/learn.html`);
    assert.equal(await page.locator(".library-tools").isVisible(), false);
    assert.equal(await page.locator("[data-resource]:visible").count(), await page.locator("[data-resource]").count());
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  } finally { await context.close(); }
});

test("Media is opt-in, plays from the published path and has a visible failure alternative", async () => {
  const page = await browser.newPage();
  const requestedVideo = [];
  page.on("request", request => { if (request.url().endsWith(".mp4")) requestedVideo.push(request.url()); });
  try {
    await page.goto(`${origin}/Fabric/`);
    const video = page.locator("video");
    assert.equal(await video.getAttribute("preload"), "none");
    assert.equal(await video.getAttribute("autoplay"), null);
    assert.equal(await video.getAttribute("controls"), "");
    assert.deepEqual(requestedVideo, []);
    const poster = await video.getAttribute("poster");
    assert.equal((await page.request.head(`${origin}/Fabric/${poster}`)).status(), 200);
    const range = await page.request.get(`${origin}/Fabric/demo/fabric-monitor-demo.mp4`, { headers: { Range: "bytes=0-4095" } });
    assert.equal(range.status(), 206);
    assert.equal((await range.body()).length, 4096);
    await range.dispose();
    await video.evaluate(element => { element.muted = true; element.load(); });
    await page.waitForFunction(() => document.querySelector("video").readyState >= 2, null, { timeout: 20000 });
    await video.evaluate(element => element.play());
    await page.waitForFunction(() => document.querySelector("video").currentTime > 0.1);
    await video.evaluate(element => element.pause());
    await page.route("**/fabric-monitor-demo.mp4", route => route.abort());
    await video.evaluate(element => element.load());
    await page.locator(".video-error").waitFor({ state: "visible" });
    assert.equal(await page.locator(".video-error a").getAttribute("href"), "demo/fabric-monitor-demo.mp4");
    await page.goto(`${origin}/Fabric/video/episode-01.html`);
    assert.equal(await page.locator("audio").isVisible(), false);
    assert.equal(await page.locator("audio").getAttribute("src"), null);
  } finally { await page.close(); }
});
