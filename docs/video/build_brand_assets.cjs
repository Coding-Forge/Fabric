const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

async function main() {
  const root = path.resolve(__dirname, "../..");
  const output = path.join(root, "docs/assets/site");
  const sources = {};
  for (const [name, file] of Object.entries({
    icon: "fabric-monitor-brand-icon.png",
    banner: "fabric-monitor-readme-banner.png",
  })) {
    sources[name] = `data:image/png;base64,${fs.readFileSync(path.join(root, "images", file)).toString("base64")}`;
  }
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  try {
    const page = await browser.newPage();
    const assets = await page.evaluate(async inputs => {
      const images = {};
      for (const [name, source] of Object.entries(inputs)) {
        const image = new Image();
        image.src = source;
        await image.decode();
        images[name] = image;
      }
      const render = (source, width, height, type, background) => {
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d");
        if (background) {
          context.fillStyle = background;
          context.fillRect(0, 0, width, height);
        }
        context.imageSmoothingQuality = "high";
        const image = images[source];
        const scale = Math.min(width / image.width, height / image.height);
        const w = image.width * scale;
        const h = image.height * scale;
        context.drawImage(image, (width - w) / 2, (height - h) / 2, w, h);
        const data = canvas.toDataURL(type, 0.9);
        if (!data.startsWith(`data:${type};base64,`)) throw new Error(`Unsupported image format: ${type}`);
        return data.split(",")[1];
      };
      return {
        "brand-icon.png": render("icon", 256, 256, "image/png"),
        "favicon.png": render("icon", 32, 32, "image/png"),
        "apple-touch-icon.png": render("icon", 180, 180, "image/png", "#001a2a"),
        "brand-banner.webp": render("banner", images.banner.width, images.banner.height, "image/webp"),
        "social-preview.jpg": render("banner", 1200, 630, "image/jpeg", "#001a2a"),
      };
    }, sources);
    fs.mkdirSync(output, { recursive: true });
    for (const [name, data] of Object.entries(assets)) {
      const bytes = Buffer.from(data, "base64");
      fs.writeFileSync(path.join(output, name), bytes);
      console.log(`${name}: ${Math.round(bytes.length / 1024)} KiB`);
    }
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
