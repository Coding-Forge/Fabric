# Fabric Monitor video series

The series follows collection through the semantic-model foundation, with a
production operations and troubleshooting extension. It does not demonstrate
dashboards or report visuals. See the
[storyboard](storyboard.md) for episode order, scope and recording safeguards.

## Watch the Episode 1 production pilot

Open the [captioned pilot player](output/episode-01-pilot.html) locally, or play
the [MP4](output/episode-01-pilot.mp4) in a media player. These links require the
generated files in this checkout; they are not published or present in Git.

The pilot contains all eight slides with full offline **Microsoft Zira Desktop**
narration at rate -1. It runs **5 minutes 34.2 seconds**, at **1920x1080, 25 fps**,
and is approximately **6.94 MiB**. Audio is mono AAC from 16 kHz, 16-bit PCM.
The MP4 includes an English subtitle track; the HTML player loads matching
WebVTT captions. Captions are selectable, not burned into the images.
[SRT](output/episode-01-pilot.srt) and [WebVTT](output/episode-01-pilot.vtt)
sidecars are also available.

Word offsets come from the offline speech engine, not estimated reading speed.
Each slide has a half-second lead and at least a one-second tail, padded to
whole video frames. Caption grouping preserves the narration and uses at most
two lines. The Windows builder uses 16 kHz to avoid the word-offset drift
observed with Zira's sample-rate conversion at 24 kHz. Invalid/out-of-range
timing fails the build rather than silently stretching captions.

**Review gate:** listen and watch the full pilot for voice, pronunciation,
pace, caption alignment and legibility before approving production of the
other episodes. Automated checks and selected-frame inspection do not replace
that review. Nothing has been uploaded or released.

### Rebuild the pilot

Use Node.js with the video-only dependencies installed in this directory:

```bash
npm ci --prefix docs/video
```

This installs Playwright and a local FFmpeg binary; it does not change the
collector's Python dependencies or install a system-wide encoder. Use a working
Playwright browser or set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an approved local
Chromium executable. The current WSL installation uses `/snap/bin/chromium`.

From the repository root in WSL:

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/snap/bin/chromium \
  node docs/video/build_episode.cjs prepare 01

powershell.exe -NoProfile -NonInteractive \
  -File "$(wslpath -w "$PWD/docs/video/build_episode_narration.ps1")" -Episode 01

node docs/video/build_episode.cjs render 01

PLAYWRIGHT_CHROMIUM_EXECUTABLE=/snap/bin/chromium \
  npm run verify:pilot --prefix docs/video
```

Native Windows can use the same Node commands and invoke narration with
`.\docs\video\build_episode_narration.ps1 -Episode 01`. Use a working Windows
Playwright browser instead of the WSL executable path.

If Windows blocks the unsigned script, follow the approved signing/execution
process. The pilot narration here used an explicitly operator-approved,
one-process override for `build_episode_narration.ps1`; no saved execution
policy was changed. That approval is not standing permission for other runs.

Preparation exports screenshots and narration to
`output/episode-01-pilot/scenes.json`. Windows synthesis produces per-slide
WAVs and measured word timing. Rendering verifies that the deck and narration
still match, then assembles continuous audio, caption sidecars, slide timing,
the MP4 and a local review player. Rebuild preparation and narration after
editing the deck. `FFMPEG_EXECUTABLE` can select an existing encoder instead of
the bundled one.

The commands overwrite only their named generated pilot artifacts under
`output/`, not the original root-level demo video or voice audition.
Dependencies and media are ignored by Git. Keep draft generated captions local;
promote accepted scripts/captions as sources only after review.

### Pilot validation

All **18 focused tests** pass: thirteen deck checks and five PCM/caption/timing
tests. The separate rendered-media verifier decoded the complete MP4 without
errors, checked the expected slide before and after every transition, confirmed
browser playback and all 76 loaded captions, and checked an active caption on
every slide. All measured boundary-image similarities exceeded 0.997.
Audio mean/peak levels were -20.4/-1.8 dB, with no detected clipping.
Selected captioned frames from slides 1, 5 and 8 were also inspected visually.

The machine-readable result is
`output/episode-01-pilot-verification.json`; its listening review remains
explicitly pending. No API collection, Fabric access, deployment or cloud
changes were involved.

## Review Episode 1

Open [episode-01.html](episode-01.html) in a browser directly from this checkout.
Use **Previous**, **Next**, or the left/right arrow keys. **Speaker notes**
shows the draft narration for the current slide.

The audio control below the slides plays an offline Microsoft Zira audition,
not synchronized episode narration. The current local preview is approximately
49 seconds. The generated WAV and eight 1080p slide screenshots are under
`output/`, which is ignored by Git and will not be present in a fresh clone.
Do not treat this deck or audition as a completed video.

The slides cover architecture, Windows/Linux/WSL2 execution options, the raw
evidence handoff, authorization boundaries and interpretation of coverage.
The closing slide introduces Episode 2's local PoC.

## Review Episode 2

Open [episode-02.html](episode-02.html) directly in a browser. Its ten slides and
speaker notes cover native Windows PowerShell, Linux and optional WSL2;
dependency setup; local output; private configuration; deliberate module
selection; retained evidence/state; and the distinction between standalone
Python and the local Functions host.

All commands and the output tree are illustrative, not recordings of live
collection. No new audio was generated, and Episode 1's voice audition is not
reused as Episode 2 narration. The closing slide directs viewers to the
Function App or notebook production path, or to analytics when evidence is
already available in the Lakehouse.

Episode 2's presentation styles and navigation are in `slides.css` and
`slides.js`. Keep those files beside the HTML when sharing the review deck.
The ten 1080p review screenshots and exported narration transcript are under
`output/episode-02-slide-*.png` and `output/episode-02-narration.txt`. These
generated files are ignored by Git.

All three focused browser tests pass, covering both decks' navigation and
Episode 2's ten desktop/narrow layouts. The Windows setup and cross-platform
destination slides were also inspected visually. The examples were checked
against the repository's operating guides; they were not executed as a live PoC.

## Review Episode 3

Open [episode-03.html](episode-03.html) directly in a browser, keeping
`slides.css` and `slides.js` beside it. Nine slides and speaker notes cover the
Function App production path: runtime/data storage, separate API and managed
identities, private settings, the current timer/startup behavior, deployment
packaging, verification, operational recovery, retention and the Lakehouse
handoff.

The timer is checked against `function_app.py`: daily at 02:00 UTC,
`run_on_startup=True`, and `use_monitor=False`. The deck explicitly distinguishes
that source from the older four-hour example in the deployment guide. It also
distinguishes infrastructure compile validation from live production acceptance.

Commands and architecture are illustrative. No resources were provisioned,
settings changed, code deployed or collection triggered. This is a review
deck with narration notes, not a narrated MP4. Episode 4 is the alternative
notebook-hosted production path; Episode 5 follows after the Lakehouse evidence
handoff is validated.

All five focused browser tests pass across Episodes 1-3. Episode 3's nine 1080p
screenshots and narration transcript are under `output/episode-03-slide-*.png`
and `output/episode-03-narration.txt`, ignored by Git. The identity and timer
slides were also inspected visually.

## Review Episode 4

Open [episode-04.html](episode-04.html) directly in a browser, keeping
`slides.css` and `slides.js` beside it. Nine slides and speaker notes cover
collector-notebook code/dependencies, private asynchronous helper settings,
the mounted default Lakehouse, destination precedence, an illustrative pipeline
pattern, the separate analytics orchestrator and scheduled-run acceptance.

The deck distinguishes API collection from the self-contained numbered
transformation notebooks. Its matched example uses `PATH_IN_LAKEHOUSE=monitor`
and analytics root `/lakehouse/default/Files/monitor`; repository example names
are not claims about the signed-in workspace. It also distinguishes execution
dependencies from collection-quality gates, which are not implemented by the
supplied analytics orchestrator.

No notebooks, pipelines, schedules, permissions or cloud resources were changed
or executed. No new audio was generated. This is a review deck with narration
notes, not a completed video. Episode 5 continues with analytics preview,
publication and controlled validation.

All seven focused browser tests pass across Episodes 1-4. Episode 4's nine
1080p screenshots and narration transcript are under
`output/episode-04-slide-*.png` and `output/episode-04-narration.txt`, ignored by
Git. The destination and pipeline-pattern slides were also inspected visually.

## Review Episode 5

Open [episode-05.html](episode-05.html) directly in a browser, keeping
`slides.css` and `slides.js` beside it. Eleven slides and speaker notes cover
self-contained notebook import, default Lakehouse/runtime preparation, domain
selection, preview/coverage, insert-only Delta publication, serial orchestration,
validation scopes and the capture/rerun/compare experiment.

The deck preserves the distinction between historical observation grain and
current inventory. It explains 10/25/48-table validation scope, immutable
baselines, required Delta history and the meanings of PASS, NOT_COMPARABLE and
UNVERIFIED. These labels describe the contract, not fabricated run results.
No notebook, table, baseline, collector or retention setting was executed,
created or changed for the deck. No new audio was generated.

Episode 6 continues at the semantic-model foundation, not dashboarding or
report visuals. This remains a slide/script review artifact, not a narrated MP4.

All nine focused browser tests pass across Episodes 1-5. Episode 5's eleven
1080p screenshots and narration transcript are under
`output/episode-05-slide-*.png` and `output/episode-05-narration.txt`, ignored by
Git. The validation-scope and capture/rerun/compare slides were also inspected
visually.

## Review Episode 6

Open [episode-06.html](episode-06.html) directly in a browser, keeping
`slides.css` and `slides.js` beside it. Ten slides and speaker notes cover
collected estate schema versus a Monitor semantic model, curated/derived
sources, observation-context relationships, scope/grain, date and permission
roles, explicit measures, readiness guards, refresh order and access acceptance.
No dashboard or report pages are shown.

The inspected example is the **local exploration** model under
`pbip-local/Monitor/Monitor.SemanticModel/definition/`, with its local operating
guide at `pbip-local/Monitor/README.md`. These are read-only source references,
not video distribution dependencies or permission to commit the exploration
files. No files under `pbip-local/` were changed or copied as video assets.

Evidence for the explanation includes `model.tmdl` (Direct Lake configuration),
`relationships.tmdl` (observation-context joins), `tables/Job History.tmdl`
(curated source mapping), `tables/Observation Context.tmdl` and
`tables/Estate Measures.tmdl` (readiness and explicit measures). The local guide
describes 20 separate derived lookup/context tables and their guarded rebuild.
This layer is additional to the 48 curated notebook datasets, not automatically
created by them. It is not presented as the only possible modeling design.

Desktop evaluation and DAX acceptance remain unverified in the local guide;
the episode does not claim to resolve that limitation. No model was deployed,
opened remotely, refreshed or modified, and no lookup publication or DAX/data
query was run. No new audio was generated. This is the sixth slide/script
review deck, not a completed video series.

All eleven focused browser tests pass across Episodes 1-6. Episode 6's ten
1080p screenshots and narration transcript are under
`output/episode-06-slide-*.png` and `output/episode-06-narration.txt`, ignored by
Git. The relationship and refresh-order slides were also inspected visually.

## Review Episode 7

Open [episode-07.html](episode-07.html) directly in a browser, keeping
`slides.css` and `slides.js` beside it. Twelve slides and speaker notes cover
the operating contract, layer-by-layer fault isolation, invocation outcomes,
host cadence versus module eligibility, API authorization boundaries,
legacy versus durable cooldowns, blocked-request investigation, the Lakehouse
handoff, partial publication, retention and model readiness.

The deck distinguishes a successful invocation from completed collection.
It preserves successful-empty, failed, deferred and unknown evidence; does not
prescribe ledger resets; and warns that module-folder lifecycle rules can match
durable controls as well as dated observations. Episode 6 now transitions to
this operations extension of the original six-episode foundation.

Sources include `function_app.py`, `env/audit.py`, the configuration reference,
collector operating guidance, deployment retention caveats and the notebook
operator runbook. The model discussion refers back to Episode 6's inspected
local pattern, without changing or distributing local exploration files.
No live incident was diagnosed, recovery executed, schedule or policy changed,
API called, or notebook/model run for this deck. Alerts and production
acceptance are requirements, not claims of installed automation. No new audio
was generated; this remains a slide/script review artifact, not a narrated MP4.

All thirteen focused browser tests pass across Episodes 1-7. Episode 7's twelve
1080p screenshots and narration transcript are under
`output/episode-07-slide-*.png` and `output/episode-07-narration.txt`, ignored by
Git. The identity, blocked-request and retention slides were also inspected
visually. Episode 6's screenshots/transcript were regenerated for its updated
transition.

## Regenerate the voice audition

Uses Windows' installed `System.Speech` engine without a cloud speech service.
The default voice is `Microsoft Zira Desktop`; Microsoft David is also supported.

Native Windows PowerShell, from the repository root:

```powershell
.\docs\video\build_narration_preview.ps1
```

From WSL, with Windows interoperability enabled:

```bash
powershell.exe -NoProfile -NonInteractive \
  -File "$(wslpath -w "$PWD/docs/video/build_narration_preview.ps1")"
```

If execution policy blocks the unsigned script, use the organization's approved
signing or execution process. Do not change saved execution policies. The local
audition in this session was generated with an explicitly operator-approved,
one-process override; that approval is not a standing instruction for other runs.

The builder overwrites only `output/narration-preview.wav`. Edit
[narration-preview.txt](narration-preview.txt) to change the audition text.

## Current validation and remaining work

Playwright rendered all eight slides at 1920x1080 with no detected content
overflow or JavaScript errors. Checks covered navigation boundaries, direct
slide links, speaker notes, a narrow viewport and browser audio playback.
The sample is non-silent mono 24 kHz, 16-bit WAV. Selected rendered slides were
also inspected visually. Voice naturalness and pronunciation still need an
operator listening review.

The cached Playwright Chromium could not launch because an audio library is
missing. The installed system Chromium worked without installing dependencies.
These checks used the existing local Playwright installation; they do not
establish that a fresh machine is ready for capture.

Episode 1 now has the separate narrated pilot described above. Its full
operator audio/video review and voice acceptance remain pending before
producing Episodes 2-7. Those episodes still have slides/scripts, not narrated
MP4s. No live Fabric recording, collection, notebook execution, Delta
publication or cloud changes were performed for these assets.

Publish accepted episode MP4s as separate GitHub Release assets. Keep the
viewing guide, scripts and captions in Git; keep large media out of Git history.
There are no published episode links yet.

## Slide checks

With Playwright installed, run `node --test docs/video/test_slides.cjs` from the
repository root. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` if using a system Chromium.
The video project's own dependencies provide Playwright under
`docs/video/node_modules`:

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/snap/bin/chromium \
node --test docs/video/test_slides.cjs
```

The executable path above is specific to the current WSL installation, not a
portable requirement. The checks exercise all seven decks' navigation and
speaker notes, plus Episodes 2-7's desktop/narrow layouts and local source links.

With the video-only dependencies installed, run the complete source test suite:

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/snap/bin/chromium npm test --prefix docs/video
```

Use `npm run verify:pilot --prefix docs/video` with the same browser setting to
check the rendered pilot separately. It requires the generated MP4, source
screenshots, timing file and captioned player, and writes review screenshots
and a verification result under `output/`.
