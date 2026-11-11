const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { pathToFileURL } = require("node:url");
const { chromium } = require("playwright");

async function verify(episode) {
  const output = path.join(__dirname, "output");
  const name = `episode-${episode}-pilot`;
  const video = path.join(output, `${name}.mp4`);
  const timing = JSON.parse(fs.readFileSync(path.join(output, `${name}-timing.json`)));
  const encoder = process.env.FFMPEG_EXECUTABLE || require("ffmpeg-static");
  function run(args) {
    const result = spawnSync(encoder, ["-hide_banner", "-threads", "2", ...args], { encoding: "utf8" });
    if (result.error) throw result.error;
    assert.equal(result.status, 0, result.stderr);
    return result.stderr;
  }
  run(["-v", "error", "-xerror", "-i", video, "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"]);
  const levels = run(["-i", video, "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"]);
  const mean = Number(/mean_volume: ([-\d.]+) dB/.exec(levels)?.[1]);
  const peak = Number(/max_volume: ([-\d.]+) dB/.exec(levels)?.[1]);
  assert(Number.isFinite(mean) && mean > -45, "Narration is silent or too quiet.");
  assert(Number.isFinite(peak) && peak < 0, "Narration is clipped.");
  let minimumSsim = 1;
  for (const slide of timing.slides) {
    for (const seconds of [slide.start + 0.12, slide.end - 0.12]) {
      const score = run(["-ss", String(seconds), "-i", video,
        "-i", path.join(output, name, slide.image), "-filter_complex", "[0:v][1:v]ssim[score]",
        "-map", "[score]", "-frames:v", "1", "-f", "null", "-"]);
      const ssim = Number(/All:([\d.]+)/.exec(score)?.[1]);
      assert(ssim > 0.98, `Slide ${slide.index} is wrong at ${seconds}s (SSIM ${ssim}).`);
      minimumSsim = Math.min(minimumSsim, ssim);
    }
  }
  for (const [index, cue] of timing.cues.entries()) {
    assert(cue.start >= 0 && cue.end > cue.start && cue.end <= timing.duration);
    assert(cue.text.split("\n").length <= 2, `Caption ${index + 1} exceeds two lines.`);
    assert(cue.text.split("\n").every(line => line.length <= 42), `Caption ${index + 1} exceeds line width.`);
    if (index) assert(timing.cues[index - 1].end <= cue.start, "Caption overlap.");
  }
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {})
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(pathToFileURL(path.join(output, `${name}.html`)).href);
    await page.waitForFunction(() => {
      const video = document.querySelector("video");
      const track = document.querySelector("track");
      return video.readyState >= 2 && track.track.cues?.length > 0;
    });
    const metadata = await page.locator("video").evaluate(video => ({
      width: video.videoWidth, height: video.videoHeight, duration: video.duration
    }));
    assert.equal(metadata.width, 1920);
    assert.equal(metadata.height, 1080);
    assert(Math.abs(metadata.duration - timing.duration) < 0.15);
    assert.equal(await page.locator("track").evaluate(track => track.track.cues.length), timing.cues.length);
    await page.locator("video").evaluate(video => video.play());
    await page.waitForFunction(() => document.querySelector("video").currentTime > 0.2);
    await page.locator("video").evaluate(video => video.pause());
    for (const slide of timing.slides) {
      const cue = timing.cues.find(cue => cue.start >= slide.start && cue.end <= slide.end);
      assert(cue, `Slide ${slide.index} lacks captions.`);
      await page.locator("video").evaluate(async (video, time) => {
        await new Promise(resolve => {
          video.addEventListener("seeked", resolve, { once: true });
          video.currentTime = time;
        });
      }, (cue.start + cue.end) / 2);
      await page.waitForFunction(expected => {
        const cues = document.querySelector("track").track.activeCues;
        return cues?.length === 1 && cues[0].text === expected;
      }, cue.text);
      if ([1, 5, 8].includes(slide.index)) {
        await page.locator("video").screenshot({
          path: path.join(output, `${name}-review-${String(slide.index).padStart(2, "0")}.png`)
        });
      }
    }
    assert.deepEqual(errors, []);
    const report = {
      ...metadata, bytes: fs.statSync(video).size, slides: timing.slides.length,
      captions: timing.cues.length, meanVolumeDb: mean, peakVolumeDb: peak,
      minimumBoundarySsim: minimumSsim, fullDecode: true, browserPlayback: true,
      captionsActiveOnEverySlide: true, humanListeningReview: "pending"
    };
    fs.writeFileSync(path.join(output, `${name}-verification.json`), JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify(report, null, 2));
  } finally { await browser.close(); }
}

const episode = process.argv[2] || "01";
if (!/^\d{2}$/.test(episode)) {
  console.error("Usage: node verify_episode.cjs [01]");
  process.exitCode = 1;
} else {
  verify(episode).catch(error => { console.error(error); process.exitCode = 1; });
}
