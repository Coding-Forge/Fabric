const assert = require("node:assert/strict");
const { test } = require("node:test");
const { readPcm, wave, makeCues, timeline, subtitles } = require("./build_episode.cjs");

function audio(seconds) {
  const pcm = Buffer.alloc(seconds * 16000 * 2);
  pcm.writeInt16LE(2000);
  return wave(pcm);
}

test("PCM narration preserves samples and rejects silent, truncated or wrong-rate WAVs", () => {
  const wav = audio(1);
  assert.equal(readPcm(wav).length, 32000);
  assert.throws(() => readPcm(wave(Buffer.alloc(32000))), /silent/);
  assert.throws(() => readPcm(wav.subarray(0, wav.length - 1)), /Truncated/);
  wav.writeUInt32LE(48000, 24);
  assert.throws(() => readPcm(wav), /16 kHz/);
});

test("captions preserve punctuation and use speech offsets rather than estimated reading speed", () => {
  const text = "Hello, Fabric. Next episode!";
  const words = [
    { start: 0.1, position: 0, length: 5 },
    { start: 0.6, position: 7, length: 6 },
    { start: 1.4, position: 15, length: 4 },
    { start: 1.8, position: 20, length: 7 }
  ];
  const cues = makeCues(text, words, 2.5, 10);
  assert.deepEqual(cues, [
    { start: 10.1, end: 11.4, text: "Hello, Fabric." },
    { start: 11.4, end: 12.5, text: "Next episode!" }
  ]);
  assert.match(subtitles(cues), /^WEBVTT\n\n1\n00:00:10.100 --> 00:00:11.400/);
  assert.match(subtitles(cues, true), /^1\n00:00:10,100 --> 00:00:11,400/);
  assert.throws(() => makeCues(text, [...words].reverse(), 2.5, 0), /timing/);
  assert.throws(() => makeCues(text, [{ ...words[0], start: 3 }], 2.5, 0), /timing/);
});

test("long captions wrap without losing text and remain ordered within narration", () => {
  const text = "Keep the complete observation context when examining historical evidence and distinguish missing collection from an explicit successful empty result.";
  let position = 0;
  const words = text.split(" ").map((word, index) => {
    const result = { start: index * 0.4, position, length: word.length };
    position += word.length + 1;
    return result;
  });
  const cues = makeCues(text, words, 10, 0.5);
  assert(cues.length > 1);
  assert.equal(cues.map(cue => cue.text.replace(/\n/g, " ")).join(" "), text);
  for (const [index, cue] of cues.entries()) {
    assert(cue.text.split("\n").length <= 2);
    assert(cue.text.split("\n").every(line => line.length <= 42));
    assert(cue.end <= 10.5);
    if (index) assert(cues[index - 1].end <= cue.start);
  }
});

test("caption grouping respects word wrapping, not just total character count", () => {
  const text = "Directory collection uses separate Microsoft Graph application permissions and consent.";
  let position = 0;
  const words = text.split(" ").map((word, index) => {
    const result = { start: index * 0.4, position, length: word.length };
    position += word.length + 1;
    return result;
  });
  const cues = makeCues(text, words, 5, 0);
  assert.equal(cues.map(cue => cue.text.replace(/\n/g, " ")).join(" "), text);
  assert(cues.every(cue => cue.text.split("\n").length <= 2));
});

test("scene timing pads audio to exact video frames and offsets each slide's captions", () => {
  const manifest = { slides: [
    { index: 1, title: "First", image: "slide-01.png", text: "First." },
    { index: 2, title: "Second", image: "slide-02.png", text: "Second." }
  ] };
  const speech = { slides: manifest.slides.map(slide => ({
    index: slide.index, words: [{ start: 0.1, position: 0, length: slide.text.length }]
  })) };
  const result = timeline(manifest, speech, [audio(1), audio(2)]);
  assert.equal(result.frames, 63 + 88);
  assert.equal(result.duration, 6.04);
  assert.equal(result.pcm.length / (16000 * 2), result.duration);
  assert.equal(result.slides[1].start, 2.52);
  assert.equal(result.cues[1].start, 3.12);
  assert.equal(result.pcm.readInt16LE(16000), 2000);
  assert.throws(() => timeline(manifest, { slides: [] }, []), /counts/);
  assert.throws(() => timeline(manifest, { slides: [...speech.slides].reverse() }, [audio(1), audio(2)]), /order/);
});
