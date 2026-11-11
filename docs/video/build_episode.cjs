const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const { pathToFileURL } = require("node:url");

const FPS = 25;
const RATE = 16000;
const LEAD = 0.5;
const TAIL = 1;
const sha256 = value => crypto.createHash("sha256").update(value).digest("hex");
const readJson = file => JSON.parse(fs.readFileSync(file, "utf8").replace(/^\uFEFF/, ""));

function wrapCaption(text) {
  const lines = [""];
  for (const token of text.split(/\s+/)) {
    if (lines[lines.length - 1] && lines[lines.length - 1].length + token.length + 1 > 42) lines.push("");
    lines[lines.length - 1] += (lines[lines.length - 1] ? " " : "") + token;
  }
  return lines.join("\n");
}

function readPcm(wav) {
  if (wav.toString("ascii", 0, 4) !== "RIFF" || wav.toString("ascii", 8, 12) !== "WAVE") {
    throw new Error("Expected a RIFF WAV narration file.");
  }
  let format;
  let pcm;
  for (let offset = 12; offset + 8 <= wav.length;) {
    const type = wav.toString("ascii", offset, offset + 4);
    const size = wav.readUInt32LE(offset + 4);
    const start = offset + 8;
    if (start + size > wav.length) throw new Error("Truncated WAV chunk.");
    if (type === "fmt ") {
      if (size < 16) throw new Error("Truncated WAV format.");
      format = [wav.readUInt16LE(start), wav.readUInt16LE(start + 2), wav.readUInt32LE(start + 4), wav.readUInt16LE(start + 14)];
    }
    if (type === "data") pcm = wav.subarray(start, start + size);
    offset = start + size + size % 2;
  }
  if (JSON.stringify(format) !== JSON.stringify([1, 1, RATE, 16]) || !pcm?.length || pcm.length % 2) {
    throw new Error("Narration must be nonempty mono 16 kHz, 16-bit PCM.");
  }
  if (!pcm.some(byte => byte !== 0)) throw new Error("Narration is silent.");
  return pcm;
}

function wave(pcm) {
  const header = Buffer.alloc(44);
  header.write("RIFF");
  header.writeUInt32LE(36 + pcm.length, 4);
  header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(RATE, 24);
  header.writeUInt32LE(RATE * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([header, pcm]);
}

function makeCues(text, words, duration, offset) {
  if (!words.length || words[0].position !== 0) throw new Error("Missing speech word timing.");
  let previousPosition = -1;
  let previousStart = -1;
  for (const word of words) {
    if (!Number.isInteger(word.position) || !Number.isInteger(word.length) || word.length < 1 ||
        word.position <= previousPosition || word.position + word.length > text.length ||
        !Number.isFinite(word.start) || word.start < previousStart || word.start < 0 || word.start >= duration) {
      throw new Error("Invalid speech word timing.");
    }
    previousPosition = word.position;
    previousStart = word.start;
  }
  const cues = [];
  let first = 0;
  for (let index = 0; index < words.length; index++) {
    const nextPosition = words[index + 1]?.position ?? text.length;
    const fragment = text.slice(words[first].position, nextPosition).trim();
    const sentenceEnd = /[.!?]$/.test(fragment);
    const nextLong = index + 1 < words.length && (
      wrapCaption(text.slice(words[first].position, words[index + 1].position + words[index + 1].length)).split("\n").length > 2 ||
      words[index + 1].start - words[first].start > 6.5
    );
    if (sentenceEnd || nextLong || index - first >= 13 || index === words.length - 1) {
      const start = words[first].start;
      const end = Math.min(words[index + 1]?.start ?? duration, start + 7);
      if (end <= start) throw new Error("Empty caption interval.");
      cues.push({ start: offset + start, end: offset + end, text: wrapCaption(fragment) });
      first = index + 1;
    }
  }
  return cues;
}

function timeline(manifest, speech, audio) {
  if (!manifest.slides?.length || speech.slides?.length !== manifest.slides.length) {
    throw new Error("Scene/narration counts differ.");
  }
  const slides = [];
  const cues = [];
  const chunks = [];
  let frames = 0;
  for (const [index, slide] of manifest.slides.entries()) {
    const narration = speech.slides[index];
    if (slide.index !== index + 1 || narration.index !== slide.index) throw new Error("Scene/narration order differs.");
    const pcm = readPcm(audio[index]);
    const seconds = pcm.length / (RATE * 2);
    const count = Math.ceil((LEAD + seconds + TAIL) * FPS);
    const start = frames / FPS;
    const leadSamples = LEAD * RATE;
    const totalSamples = count * RATE / FPS;
    chunks.push(Buffer.alloc(leadSamples * 2), pcm, Buffer.alloc((totalSamples - leadSamples - pcm.length / 2) * 2));
    cues.push(...makeCues(slide.text, narration.words, seconds, start + LEAD));
    frames += count;
    slides.push({ index: slide.index, title: slide.title, start, end: frames / FPS, image: slide.image });
  }
  return { slides, cues, frames, duration: frames / FPS, pcm: Buffer.concat(chunks) };
}

function timestamp(seconds, separator = ".") {
  const milliseconds = Math.round(seconds * 1000);
  const pad = (value, length = 2) => String(value).padStart(length, "0");
  return `${pad(Math.floor(milliseconds / 3600000))}:${pad(Math.floor(milliseconds / 60000) % 60)}:${pad(Math.floor(milliseconds / 1000) % 60)}${separator}${pad(milliseconds % 1000, 3)}`;
}

function subtitles(cues, srt = false) {
  return (srt ? "" : "WEBVTT\n\n") + cues.map((cue, index) =>
    `${index + 1}\n${timestamp(cue.start, srt ? "," : ".")} --> ${timestamp(cue.end, srt ? "," : ".")}\n${cue.text}\n`
  ).join("\n");
}

async function prepare(episode, directory) {
  const { chromium } = require("playwright");
  const source = path.join(__dirname, `episode-${episode}.html`);
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {})
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    await page.goto(`${pathToFileURL(source).href}?capture=1`);
    await page.evaluate(() => document.fonts.ready);
    const slides = await page.locator(".slide").evaluateAll(elements => elements.map((slide, index) => ({
      index: index + 1,
      title: slide.querySelector("h1,h2").innerText.replace(/\s+/g, " ").trim(),
      text: slide.querySelector(".speaker-notes").content.textContent.replace(/\s+/g, " ").trim(),
      image: `slide-${String(index + 1).padStart(2, "0")}.png`
    })));
    if (!slides.length || slides.some(slide => !slide.text)) throw new Error("Every slide needs narration.");
    for (const slide of slides) {
      await page.screenshot({ path: path.join(directory, slide.image) });
      await page.keyboard.press("ArrowRight");
    }
    fs.writeFileSync(path.join(directory, "scenes.json"), JSON.stringify({
      episode, sourceSha256: sha256(fs.readFileSync(source)), slides
    }, null, 2) + "\n");
    console.log(`Prepared episode ${episode}: ${slides.length} slides. Next, run build_episode_narration.ps1.`);
  } finally { await browser.close(); }
}

function render(episode, directory) {
  const input = fs.readFileSync(path.join(directory, "scenes.json"));
  const manifest = JSON.parse(input);
  const speech = readJson(path.join(directory, "speech.json"));
  if (manifest.sourceSha256 !== sha256(fs.readFileSync(path.join(__dirname, `episode-${episode}.html`))) ||
      speech.inputSha256 !== sha256(input)) {
    throw new Error("Deck or narration changed; prepare and synthesize again before rendering.");
  }
  const result = timeline(manifest, speech, speech.slides.map(slide => {
    if (slide.audio !== `slide-${String(slide.index).padStart(2, "0")}.wav`) throw new Error("Unexpected audio filename.");
    return fs.readFileSync(path.join(directory, slide.audio));
  }));
  const name = `episode-${episode}-pilot`;
  const output = path.dirname(directory);
  fs.writeFileSync(path.join(directory, "narration.wav"), wave(result.pcm));
  const concat = ["ffconcat version 1.0"];
  for (const slide of result.slides) {
    if (!/^slide-\d{2}\.png$/.test(slide.image)) throw new Error("Unexpected slide filename.");
    concat.push(`file '${slide.image}'`, `duration ${(slide.end - slide.start).toFixed(6)}`);
  }
  concat.push(`file '${result.slides.at(-1).image}'`);
  fs.writeFileSync(path.join(directory, "slides.ffconcat"), concat.join("\n") + "\n");
  const vtt = subtitles(result.cues);
  fs.writeFileSync(path.join(output, `${name}.vtt`), vtt);
  fs.writeFileSync(path.join(output, `${name}.srt`), subtitles(result.cues, true));
  fs.writeFileSync(path.join(output, `${name}-timing.json`), JSON.stringify({
    episode, voice: speech.voice, rate: speech.rate, fps: FPS,
    duration: result.duration, slides: result.slides, cues: result.cues
  }, null, 2) + "\n");
  const encoder = process.env.FFMPEG_EXECUTABLE || require("ffmpeg-static");
  const args = ["-hide_banner", "-y", "-threads", "2",
    "-f", "concat", "-safe", "0", "-i", path.join(directory, "slides.ffconcat"),
    "-i", path.join(directory, "narration.wav"), "-i", path.join(output, `${name}.srt`),
    "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0", "-t", String(result.duration),
    "-vf", `fps=${FPS}`, "-c:v", "libx264", "-threads", "2", "-preset", "fast",
    "-tune", "stillimage", "-crf", "23", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "64k", "-c:s", "mov_text",
    "-metadata:s:s:0", "language=eng", "-disposition:s:0", "default",
    "-metadata", `title=Fabric Monitor - Episode ${Number(episode)} pilot`,
    "-movflags", "+faststart", path.join(output, `${name}.mp4`)];
  const encoded = spawnSync(encoder, args, { stdio: "inherit" });
  if (encoded.error) throw encoded.error;
  if (encoded.status !== 0) throw new Error(`Encoder failed: ${encoded.status}`);
  fs.writeFileSync(path.join(output, `${name}.html`), `<!doctype html>
<html lang="en"><meta charset="utf-8"><title>Fabric Monitor Episode ${Number(episode)} pilot</title>
<style>body{margin:24px;background:#080f1c;color:#edf5fc;font:18px "Segoe UI",sans-serif}video{width:100%;max-width:1280px}a{color:#61dfcc}video::cue{font-size:28px;background:#080f1ce6}</style>
<h1>Episode ${Number(episode)} production pilot</h1>
<p>Offline ${speech.voice}. Review voice, pacing, slide transitions and captions before release.</p>
<video controls preload="metadata" src="${name}.mp4"><track kind="captions" label="English" srclang="en" default></video>
<p><a href="${name}.mp4">MP4</a> / <a href="${name}.srt">SRT captions</a> / <a href="${name}.vtt">WebVTT captions</a></p>
<script>document.querySelector("track").src=URL.createObjectURL(new Blob([${JSON.stringify(vtt).replaceAll("<", "\\u003c")}],{type:"text/vtt"}));</script>
</html>\n`);
  console.log(`Rendered ${name}: ${result.duration.toFixed(2)} seconds, ${result.cues.length} captions.`);
}

if (require.main === module) {
  const [action, episode = "01"] = process.argv.slice(2);
  if (!["prepare", "render"].includes(action) || !/^\d{2}$/.test(episode)) {
    console.error("Usage: node build_episode.cjs prepare|render [01]");
    process.exitCode = 1;
  } else {
    const directory = path.join(__dirname, "output", `episode-${episode}-pilot`);
    fs.mkdirSync(directory, { recursive: true });
    Promise.resolve().then(() => action === "prepare" ? prepare(episode, directory) : render(episode, directory))
      .catch(error => { console.error(error.message); process.exitCode = 1; });
  }
}

module.exports = { readPcm, wave, makeCues, timeline, subtitles };
