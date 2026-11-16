# Fabric Monitor website

The public site is <https://coding-forge.github.io/Fabric/>. GitHub Pages
publishes the `docs/` directory on `main` using the repository's existing
branch-based configuration. Changes on a feature branch are not live until
merged and the Pages deployment succeeds. No collector, API, Fabric runtime
or tenant connection is used by this static site.

## Content map

| File | Purpose |
|---|---|
| `index.html` | Positioning, collection architecture, scope, demo and FAQs |
| `get-started.html` | Guided runtime, authorization, collection and analytics path |
| `investigation.html` | Synthetic event-to-evidence walkthrough and explicit limits |
| `learn.html` | Searchable guide library and draft learning decks |
| `assets/site/` | Shared local CSS, progressive-enhancement JavaScript and brand mark |
| `catalog-pbip.html`, `blog/`, `demo/` | Existing report guide, earlier story and demo |

Technical Markdown remains canonical in GitHub's rendered reader. Link to it
with explicit `https://github.com/Coding-Forge/Fabric/blob/main/...` URLs.
Repository files outside `docs/` are not published under the Pages site.
Avoid relative `.md`, `.py` or `.ipynb` links that work in a checkout but fail
or show unrendered source on Pages. There is no duplicated Markdown build,
client-side Markdown renderer, CDN, tracking script or frontend framework.

For a new library guide, copy one `data-resource` article in `learn.html`.
Set `data-category` to one of the existing select values and add optional
`data-keywords`. The count and filtering derive from the articles. Without
JavaScript, all guide links and the full navigation remain available.

## Add videos

Only the existing tracked introductory MP4 is featured. Local files in
`video/output/` are draft/generated assets, ignored by Git, and must not be
linked from the public site. The seven episode links are explicitly labelled
draft slide decks, not finished narrated episodes. Episode 1's unpublished
voice audition is available only when the deck is opened through `file:`.

For additional videos:

1. Review the complete recording for credentials, tenant names, identifiers,
   user details, raw evidence and private endpoints. Publish only approved
   synthetic or sanitized material. The website is public.
2. Choose a stable public host. Small approved assets can live under
   `docs/demo/`; for a growing library, prefer externally hosted video
   (for example an approved YouTube/Vimeo channel or a public release asset).
   Do not add large recordings to Git by default or hotlink private storage
   with an expiring access token.
3. Add a descriptive learning card in `learn.html`. Use a normal watch link
   for an external host: it makes no third-party player request until chosen.
   Do not present an unrecorded deck or a local pilot as a published episode.
4. For a self-hosted player, copy the homepage's native `<video controls
   playsinline preload="none">` pattern. Add the approved poster, MP4 source
   and text alternative. Do not autoplay.
5. Add reviewed WebVTT captions using a `<track kind="captions" srclang="en"
   label="English" src="...vtt">` element and a readable transcript link.
   Verify timestamps and terminology. The existing introductory demo has no
   supplied caption track; the page discloses this and links a text overview,
   not a claimed word-for-word transcript.
6. Test the final published URL and playback, captions, keyboard controls and
   mobile layout. A local file's existence is not publication acceptance.

Keep the marketing distinction precise: external collection to local/Blob
does not require a Fabric notebook; optional notebook-hosted collection,
Lakehouse transformations, Silver/Gold and the separate JSONL export notebook
do use Fabric compute. Do not claim zero cost, universal API access, complete
lineage or causality. Keep implemented, example, draft and planned states clear.

## Preview and validate

From the repository root, an optional loopback-only preview is:

```bash
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8000/`. Stop the preview when finished. No secret files
should be copied into `docs/`.

Browser tests reuse the existing video tooling, without adding site dependencies:

```bash
npm ci --prefix docs/video
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/snap/bin/chromium \
  npm run test:site --prefix docs/video
```

Use an approved installed Chromium path, or omit the environment variable when
Playwright's browser is available. The test server is loopback-only, uses an
ephemeral port, emulates the `/Fabric/` project-site prefix and stops afterward.
Tests check responsive overflow, navigation, no-JavaScript access, combined
library filters, media behavior, published resource paths and source links.
Run the existing deck tests when changing decks:

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/snap/bin/chromium npm test --prefix docs/video
```

After merging, check the repository's Pages deployment and the actual public
site. Local browser tests do not establish remote publishing or live API
acceptance.
