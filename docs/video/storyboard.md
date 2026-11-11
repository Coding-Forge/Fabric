# Fabric Monitor video series: from collection to a model-ready foundation

Status: series structure and Episode 7 operations extension accepted; Episode 1-7 review decks and an offline
Microsoft Zira voice audition are available locally. No live Fabric footage recorded, cloud
resources provisioned, collectors started or notebooks executed for this series.
Live examples, final narration voice and episode durations still need acceptance.
Episode 1 also has a narrated 1080p pilot (5:34, approximately 6.94 MiB), with
measured caption timing and local playback checks. Full operator audio/video
review is pending; Episodes 2-7 remain slide/script review decks.

## Production brief

Audience: Fabric platform owners, administrators and engineers evaluating Monitor
or planning its operation.

Format: targeted episodes combining architecture slides, local terminal
demonstrations and Fabric browser footage. Cover native Windows and Linux
equally in the local PoC episode; present WSL2 as an optional best-of-both-worlds
workflow for Windows users who prefer Linux tools. Windows does not require WSL.
Stop at the semantic-model layer, with an operations extension covering the
same collection-to-model path. Dashboarding, report visuals and the
Estate & Impact application are out of scope.

Outcome: viewers can distinguish collection, storage, transformation and modeling;
choose a local PoC or production hosting approach; explain preview/publication;
and interpret results without mistaking missing evidence for a healthy estate.

Use the current implementation, not the claims in the older presentation.
In particular, avoid "real-time," "complete tenant visibility," "effective access,"
and guaranteed change-impact claims. Existing video tooling documented in
[VIDEO_BUILD_README.md](../../VIDEO_BUILD_README.md) builds a silent,
screenshot-based MP4. The new [pilot workflow](README.md#rebuild-the-pilot)
captures these HTML slides, synthesizes offline Windows narration with word
timing, and assembles a captioned MP4. It does not record live browser
demonstrations or replace the full operator audio/video acceptance review.

## Storyboard and narration

The scenes below are reusable script blocks, grouped into these episodes rather
than one shortened video. Approximate lengths include interaction and reading
pauses; confirm after rehearsal. Narration is intended to be spoken. Production
directions are not narration.
Every live scene remains conditional on workspace inspection and approval.

| Episode | Topic | Source scenes | Target |
|---|---|---|---|
| 1 | Overview, architecture and permission boundaries | 01-03 | Initial target 3-4 minutes; pilot 5:34 |
| 2 | Local PoC on Windows, Linux or WSL2 | 04, with platform-specific setup | 4-5 minutes |
| 3 | Production collection with an Azure Function App | 05 | 3-4 minutes |
| 4 | Collector notebooks and pipeline orchestration | 06, collection-to-curation handoff from 10 | 4-5 minutes |
| 5 | Analytics notebooks, serial orchestration, Delta publication and validation | 07-11, 13 | 5-6 minutes |
| 6 | Curated data and the semantic-model layer | 12, 14 | 3-4 minutes |
| 7 | Production operations and troubleshooting | 15 | 5-7 minutes |

Episodes 3 and 4 are alternative deployment paths, not mandatory sequential
steps. Each episode opens with its purpose and prerequisites, briefly summarizes
the outcome, and closes with the next relevant episode. Use an end card naming
the destination episode and a viewing-guide link; add final video URLs only
after publication. Expand demonstrations during rehearsal rather than padding
with repeated narration.

Transitions:

- 1 -> 2: "Next, explore the collector locally on Windows, Linux or WSL2."
- 2 -> 3/4: "For hosted collection, choose the Function App walkthrough or the
  notebook-and-pipeline walkthrough. If evidence is already available in your
  Lakehouse, continue to analytics."
- 3/4 -> 5: "With the collection handoff validated, turn retained evidence into
  curated Delta tables."
- 5 -> 6: "Next, use the curated foundation at the semantic-model layer,
  preserving grain, coverage and observation context."
- 6 -> 7: "This completes the collection-to-model foundation. Next, operate it
  deliberately: production checks, troubleshooting and safe recovery."
- 7: "Return to the hosting, analytics or model episode for the layer you are
  implementing. Dashboarding and report design remain outside this series."

Publish each finished MP4 as a separate versioned GitHub Release asset, not a
binary committed to Git history. Keep the approved script, captions and viewing
guide in the repository. Do not upload until the content/privacy review passes.

### 01. Start with the questions

Visual: title slide, then three large questions: "What is here?", "What needs
investigation?", and "What could depend on this?"

Narration:

> Fabric Monitor helps you explore the evidence behind your Fabric and Power BI
> estate. What workspaces and items have been observed? What do semantic models
> contain? Which operations or access assignments deserve investigation? And
> which resources may depend on something you are planning to change?
>
> In this walkthrough, we will start with a local proof of concept, compare two
> production execution approaches, and follow collected metadata into Delta
> tables and the semantic-model layer. Throughout, we will keep
> one distinction visible: what the evidence tells us, and what it cannot prove.

Capture: opening slide only; do not imply that every question has an automated
finding or recommendation in the current dashboard.

Source: [solution overview](../../README.md).

### 02. The architecture in one picture

Visual: animate this flow one layer at a time:

```text
Authorized Power BI / Fabric / Microsoft Graph APIs
                         |
              Python collection runtime
          local process | Function App | collector notebook
                         |
            Retained raw evidence and controls
           local files | Blob / ADLS | Lakehouse Files
                         |
       Explicitly arrange Lakehouse availability if needed
                         |
         Numbered analytics notebooks, run serially
                         |
                 Curated Delta tables
                         |
         Semantic-model layer: grain and relationships
```

Narration:

> Think of Monitor as separate layers. Collectors call the APIs you have
> authorized and preserve the returned evidence. Storage retains those raw
> observations and the controls needed for later runs. Analytics notebooks
> transform the retained files into curated Delta tables. Reporting tools then
> help you investigate those tables.
>
> Changing where the collector runs does not change the meaning of its evidence.
> A local process, an Azure Function, and a collector notebook are different
> execution hosts, not different levels of permission.
>
> There is also an important handoff. The analytics notebooks expect files in
> the Lakehouse. If collection writes locally or to Blob Storage, you must
> explicitly arrange and validate how the required files become available there.
> This diagram does not represent an automatic transfer implemented by Monitor.

Capture: architecture slide. Keep "collect" and "transform" visually distinct.
Do not silently substitute a shortcut, copy job or ingestion mechanism.

Source: [overview](../../README.md),
[storage configuration](../configuration-reference.md#storage-settings),
[notebook workflow](../../notebooks/notebook-guide.md).

### 03. Scope and permission boundaries

Visual: permission-boundary slide with four separate boxes: API authorization,
resource access, storage access, and notebook/report execution identity.

Narration:

> Before collecting, choose the modules and scope deliberately. Monitor is not
> an Admin-API-only solution. Catalog uses Admin Scanner APIs, but some features
> use non-Admin Fabric or Power BI endpoints, and directory collection uses
> separate Microsoft Graph permissions.
>
> For example, item job history reads only explicitly configured supported items.
> Connections are caller-visible, not a complete tenant inventory. Definition
> collection discovers active notebooks and data pipelines across the tenant,
> then requires item read-write access to export their definitions. Contributor
> is the least workspace role supplying that access, even though collection
> itself does not execute or update those workloads.
>
> Deployment history needs deployment-pipeline Admin. Refresh history needs
> dataset Write permission. These rights are not supplied simply by enabling
> Admin API access. Storage permissions and the identity that runs analytics
> must also be considered separately. Start with the minimum approved modules,
> protect the evidence, and expand only when the additional permissions and
> collection boundaries are understood.

On-screen companion card, held long enough to read:

| Non-Admin or separate family | Scope and permission boundary |
|---|---|
| Job history | 1-100 configured supported items; actual item/job-history access; recent history only; never starts jobs |
| Connections | Caller-visible connections; connection permission; not tenant-complete; paths/credentials excluded |
| Definitions | Tenant-discovered active notebooks/data pipelines; item read/write; potentially sensitive source; static inference, not runtime proof |
| Deployment operations | Caller-visible deployment pipelines; pipeline Admin; up to 20 recent deployments; never deploys |
| Refresh history | Discovered refreshable datasets; dataset Write; bounded API history; never triggers refresh |
| Gateway | Caller-admin supported gateways; Gateway Admin; endpoint-specific identity support; no VNet gateway support; sensitive details may be retained |
| Capacity Metrics | Configured semantic model; Read + Build and Execute Queries settings; consuming the Metrics app model is unsupported by Microsoft |
| Graph | Separate application permissions/admin consent; directory/licensing scope; groups optional and bounded; sensitive identifiers |

Include a visible reference to the full scope matrix rather than presenting
these summaries as a complete authorization checklist.

Source: [API scope and authorization boundaries](../configuration-reference.md#api-scope-and-authorization-boundaries).

### 04. Explore locally before deploying

Visual: local PoC slide showing native Windows, Linux and optional WSL2. Give
Windows PowerShell and Linux shell examples equal prominence, then show a
sanitized terminal and approved output folder. Show commands as prepared text
unless a real API run has been approved.

Windows PowerShell, from the repository root with Python installed:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Example only: configure credentials privately, outside the recording.
$env:LOCAL_OUTPUT_PATH = "$HOME\monitor-poc-output"
python -m app.monitor --modules Activity,Catalog
```

Linux or a Linux distribution in WSL2, from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Example only: configure credentials privately, outside the recording.
export LOCAL_OUTPUT_PATH="$HOME/monitor-poc-output"
python -m app.monitor --modules Activity,Catalog
```

Narration:

> For a proof of concept, run the Python application locally on Windows or Linux
> and direct its output to a local folder. Windows users can run natively in
> PowerShell; Linux is not required.
>
> WSL2 is an optional best-of-both-worlds approach: keep your Windows desktop
> while using a Linux development environment. Use the same collection workflow
> with the shell commands appropriate to your environment.
>
> Create a Python virtual environment, install the repository requirements,
> configure credentials privately and choose a small approved set of modules.
> Then inspect the resulting evidence before introducing cloud hosting.
>
> Local does not mean offline. This command still calls real Microsoft APIs
> using the configured identity. The local output setting changes the
> destination; it does not restrict every collector to a chosen workspace.
> Different modules have different discovery boundaries.
>
> Keep credentials off screen and out of source control. Keep the output
> protected too: metadata, identities and exported definitions can be sensitive.
> Preserve collection state so incremental operation and quota controls remain
> intact. Do not delete checkpoints or cooldowns to force another run.
>
> You can also exercise the Functions host locally, but it runs on startup.
> Neither starting that host nor selecting dry-run should be treated as a
> guarantee that no API calls occur.

Capture: emphasize module selection, output layout and state without exposing
payloads, credentials or private paths. Do not open `local.settings.json`,
`.env`, a real credential profile or raw logs. Standalone Python does not need
Azurite; the local Functions-host path does need its runtime storage configured.
Keep Windows and WSL Python environments separate; do not reuse one `.venv`
across operating systems. Explain PowerShell activation policy troubleshooting
only if needed, using the existing Windows setup guide. Commands are examples,
not instructions to change execution policy or start collection during filming.

Source: [local PoC mode](../local-development.md#local-folder-poc-mode),
[CLI implementation](../../app/monitor.py),
[configuration](../configuration-reference.md),
[Windows setup](../windows-development.md).

### 05. Production option A: Azure Function App

Visual: architecture slide: timer -> collector -> protected storage, with
identity/Key Vault and monitoring shown separately.

Narration:

> An Azure Function App provides a hosted way to invoke the collector on a
> timer. Configure the approved modules, API credentials, storage destination
> and operational monitoring for that environment.
>
> In the current code, the timer is daily at two AM UTC, and startup execution
> is enabled. A deployment or host start can therefore cause collection before
> the next scheduled time. Review that behavior, invocation duration, hosting
> limits and overlap before production use.
>
> The documented approach can use managed identity for Blob Storage and a
> Key Vault reference for the API client secret. Storage identity does not
> automatically replace the collector's API credentials or grant Fabric access.
>
> Treat this as a deployment option requiring environment acceptance, not proof
> that the supplied infrastructure has already been deployed and validated.
> Verify network access, permission scope, retention, recovery and alerts. Then
> inspect collection outcomes, not just whether the outer invocation finished.

Capture: slides by default. Portal footage only if an approved deployed app
exists. Do not provision resources, publish code, reveal settings values or
trigger collection for this scene without separate approval.

Accuracy note: `function_app.py` is authoritative for the timer. The deployment
guide contains an older four-hour example; do not reproduce it as the default.
The source also sets `use_monitor=False`; do not claim durable timer schedule
monitoring or non-overlap is established by this trigger.

Source: [trigger implementation](../../function_app.py),
[deployment guide](../deployment.md).

### 06. Production option B: a collector notebook

Visual: slide contrasting "collector notebook" and "analytics notebook"; then,
if available, an approved collector setup cell with secret retrieval concealed.

Prepared code excerpt, not a runnable credential setup:

```python
from env.notebook import run

# settings is prepared privately using an approved secret store.
await run(settings)
```

Narration:

> A notebook can host the collector too. The repository provides an asynchronous
> helper that runs the Python monitoring code with explicit settings. Unlike
> the generated analytics notebooks, this collector notebook needs the repository
> code and its dependencies available in the runtime.
>
> Resolve secrets through an approved secret store rather than embedding them
> in notebook source or displayed output. Configure the workspace, Lakehouse
> and destination path deliberately, and verify that the collected files land
> where the analytics notebooks will read them.
>
> For production, a pipeline can orchestrate collector execution followed by
> transformation. That pipeline must be configured and accepted in your
> environment; the collector helper does not create it. Validate the actual
> scheduled identity, permissions, runtime and failure behavior before enabling
> a schedule.

Capture: no claim that a production collection pipeline exists until inspected.
Use slides if no approved collector notebook is available. Match the collector
destination to the analytics raw root; do not reuse the README's different
example folder without explanation. This Fabric/OneLake walkthrough is Commercial;
do not imply sovereign-cloud Fabric parity.

Source: [Fabric collector helper](../../env/notebook.py),
[collector setup](../../README.md),
[Lakehouse settings](../configuration-reference.md#option-c--fabric-lakehouse).

### 07. Find the evidence in the Lakehouse

Visual: Fabric workspace -> intended Lakehouse -> Files -> approved raw root;
then show Tables as a separate destination.

Narration:

> Now follow the handoff from collection to analytics. In this example,
> Lakehouse Files holds the retained Monitor evidence, while Tables holds the
> curated Delta datasets.
>
> Before running a transformation, confirm the default Lakehouse and raw root.
> The analytics default is Files slash monitor. The folder existing is not
> enough: check that the required modules actually produced usable observations
> and that the execution identity can read them.
>
> A dated folder is not necessarily an exact collection timestamp. Older
> snapshots can be useful evidence without establishing a complete, current
> picture of the tenant.

Capture: verify actual workspace/Lakehouse names before scripting clicks.
`FabricMonitor` and `lh_monitor` are repository examples, not discovered facts
about the signed-in workspace. Avoid expanding raw sensitive payloads.

Source: [notebook walkthrough](../../notebooks/notebook-guide.md).

### 08. Understand the notebook suite

Visual: grouped notebook index, not 21 individual opening sequences.

| Group | Role |
|---|---|
| 01-04 | Inventory/health, permissions, jobs and lineage |
| 05 | Read-only core visualizations |
| 06 | Controlled rerun validation |
| 07-11 | Activity, catalog/schema, connections, gateways and refreshes |
| 12-21 | Apps, capacity, directory/licensing, roles, settings, domains, Git, tags, sharing and deployment history |

Narration:

> There are twenty-one numbered analytics notebooks. Nineteen transform existing
> evidence into forty-eight managed datasets. Notebook five visualizes the core
> results; notebook six validates controlled reruns.
>
> These notebooks do not collect new API data. Import the generated notebook
> files, attach the intended default Lakehouse and review the parameters. Their
> transformation helpers are embedded, so this layer does not need a repository
> checkout or collector credentials.
>
> Adopt the domains you need. The numbers organize the suite; they are not one
> strict dependency chain. Core visualizations need the core tables, while the
> domain notebooks read their own collected sources.

Capture: workspace notebook list and one parameter cell. Keep imported notebook
names readable; do not assume all generated artifacts are already imported.

Source: [suite reference](../../notebooks/README.md),
[notebook guide](../../notebooks/notebook-guide.md).

### 09. Preview before writing Delta tables

Visual: notebook 01 parameter cell -> approved preview output -> publication
explanation -> existing Delta table preview.

```python
RAW_ROOT = "/lakehouse/default/Files/monitor"
TABLE_PREFIX = "monitor_"
WRITE_TABLES = False
```

Narration:

> Start in preview mode. Confirm the raw root, table prefix and, where relevant,
> the explicit Scoped or Tenant permission mode. Preview lets you inspect
> transformed counts and coverage without publishing Delta rows.
>
> Read the warnings as part of the result. A notebook can execute successfully
> while reporting missing collection or failed resources. That is not the same
> as a healthy empty estate.
>
> Once the preview and destination are accepted, enabling writes publishes
> retained observations with provenance. The tables are historical evidence,
> not a shortcut to a current-state count. Repeated observations of one resource
> must not be presented as multiple current resources.
>
> Publication has ownership and consistency safeguards. If an existing table
> fails those checks, investigate the contract and destination; do not drop
> tables or weaken checks just to make the demonstration pass.

Capture: run preview only after operator approval. Demonstrate writes using
previously accepted footage/tables unless a new publication is explicitly
approved. Do not stage a success output or hide real warnings.

Source: [preview and publication workflow](../../notebooks/notebook-guide.md#import-preview-and-publish).

### 10. Run transformations with the orchestrator

Visual: `nb_orchestrator` parameter list -> serial execution diagram -> actual
accepted run summary, if one exists.

Narration:

> The optional orchestrator gives the transformation layer one entry point.
> Its notebook list selects the domains to process, and its parameters carry
> the shared raw root, prefix, permission mode and write setting.
>
> It runs the selected transformations serially. Several notebooks share a
> coverage table, so concurrent publication to the same prefix is unsupported.
> The orchestrator attempts each selected child, reports named outcomes, and
> raises after the summary if any child failed.
>
> It does not collect API data, and it excludes visualization and controlled
> validation. A pipeline may call it after collection has completed. Configure
> that dependency and prevent overlapping writers. Finally, review coverage
> separately: a successful child execution does not prove that its source
> collection was complete or fresh.

Capture: show the parameter cell without editing or saving the live notebook.
A pipeline diagram must be labeled "deployment pattern" unless an actual
accepted pipeline has been inspected. Never start overlapping demonstration runs.

Source: [orchestrator artifact](../../notebooks/nb_orchestrator.ipynb),
[orchestrator operating guidance](../../notebooks/README.md#optional-serial-orchestrator).

### 11. Explain the Delta tables

Visual: Lakehouse table list, then approved columns from `monitor_inventory`,
`monitor_collection_health` and a lineage or model-content table.

Narration:

> The Delta layer makes retained evidence available as structured datasets.
> Inventory describes observed resources. Health and coverage explain the
> collection behind those observations. Permissions, operations, model contents
> and lineage provide domain-specific investigation paths.
>
> Keep the grain in mind. A row can represent an observation at a source version,
> a collection outcome, or a relationship, rather than a unique current item.
> Coverage and provenance are how we avoid treating failed collection as zero.
>
> These structured datasets form the handoff to the semantic-model layer.
> Before defining relationships or measures, establish each table's grain,
> source selection and coverage rules. Connection and access requirements must
> also be validated for the intended model identity.

Capture: use a small approved projection. Raw JSON, directory identifiers and
source definitions need not appear to explain table grain.

Source: [table contracts](../../notebooks/README.md#notebooks-and-output-tables).

### 12. From curated evidence to the semantic-model layer

Visual: table-grain diagram and an approved semantic model's structure, if
available. Show sources, keys and relationships, never report pages or dashboard
visuals. Otherwise use a clearly labeled modeling-pattern slide.

Narration:

> A semantic model gives curated evidence a reusable analytical structure.
> First decide what each table represents, which observation belongs in an
> analysis, and how facts and dimensions can be joined without multiplying rows.
>
> Preserve coverage and observation context. A missing collection must not
> become a zero count, and historical snapshots must not be added together as
> if every row represented a different current resource.
>
> There are two different meanings of model metadata here. Monitor can retain
> schema observations about models in the estate. Building a semantic model
> over Monitor's own curated tables is a separate design and deployment step.
> The analytics notebooks do not automatically build that reporting model.
>
> Validate the intended sources, relationships, measures and access under the
> identity that will use the model. The foundation walkthrough ends here, with
> an operations extension in Episode Seven. Dashboarding and visual report
> design are deliberately deferred.

Capture: inspect the intended semantic-model artifact before claiming an
implemented connection, relationship, measure or deployment. Do not substitute
collected estate schema for a demonstrated Monitor reporting model. Do not
create or change a model without separate approval.

Source: [table contracts](../../notebooks/README.md#notebooks-and-output-tables),
[catalog/schema notebook scope](../../notebooks/notebook-guide.md#08---estate-catalog-and-semantic-model-schema).

### 13. Validate stability, not just row counts

Visual: slide: capture baseline -> rerun unchanged writers -> compare.
Show an approved existing notebook 06 result only if available.

Narration:

> Notebook six supports a controlled rerun experiment. First publish the chosen
> scope. Keep collectors and other writers idle, capture a new metadata baseline,
> rerun the transformations against unchanged evidence, and compare.
>
> This checks exact curated contents, not only row counts. A pass establishes
> rerun stability for that experiment; it does not establish freshness or
> tenant completeness.
>
> If evidence or scope changes, the comparison is not comparable rather than
> a rerun pass or failure. If required Delta history is unavailable, the result
> is unverified. Keep baselines immutable and retain the history needed for
> comparison.

Capture: no live validation experiment while collectors or writers are active.
Do not overwrite a baseline, alter retention or run cleanup for filming.

Source: [validation procedure](../../notebooks/notebook-guide.md#validate-the-scope-you-actually-published).

### 14. Choose a path and operate it deliberately

Visual: comparison slide, then closing architecture diagram.

| Choice | Good starting point | Acceptance needed |
|---|---|---|
| Local Python | Small approved PoC and evidence exploration | Real API permissions, restricted output, module scope |
| Function App | Hosted timer-based collection | Hosting/runtime limits, startup behavior, identities, network, alerts, storage and overlap |
| Collector notebook + pipeline | Collection alongside Fabric workflows | Code/dependencies, secrets, scheduled identity, dependencies, capacity and overlap |
| Analytics notebooks + orchestrator | Curating existing Lakehouse evidence | Correct raw handoff, preview/write approval, serial publication and coverage review |

Narration:

> Begin locally when the goal is to learn what evidence is useful and what
> permissions it requires. Choose a Function App when hosted timer execution
> fits your operating model. Choose a collector notebook and pipeline when that
> is the right execution pattern for your Fabric environment.
>
> In either case, keep collection separate from transformation. Validate the
> handoff to Lakehouse Files, preview before publication, and use the serial
> orchestrator only after manual acceptance. Keep required capacities available
> for collection and analytics, and monitor failures, quotas, storage growth
> and freshness.
>
> The goal is not simply to accumulate metadata. It is to make the estate
> understandable, support informed investigation, and make the limits of the
> evidence clear before operational decisions depend on it.

Capture: end with repository guide locations, not live tenant URLs. Eventhouse,
Event Hubs and Splunk delivery are not needed for this walkthrough. Do not imply
an implemented publisher or exporter.

Source: [local operation](../local-development.md),
[deployment](../deployment.md), [notebook runbook](../../notebooks/notebook-guide.md),
[integration status](../analytics-integration.md).

### 15. Production operations and troubleshooting

Visual: [Episode 7's twelve-slide review deck](episode-07.html), with a
layer-by-layer evidence journey, invocation/coverage distinctions, request
control diagram and recovery acceptance checklist. No dashboard visuals.

Narration: the deck's speaker notes are the complete draft script. Cover:

- The operating contract: approved scope, identities, capacities, cadence,
  freshness expectations, ownership and explicitly arranged alerts.
- Fault isolation across invocation, APIs, raw persistence, Lakehouse handoff,
  curated publication and model readiness. Review/redact shared evidence.
- Succeeded, deferred and failed outcomes versus finished/complete manifests,
  whole-cycle health and explicit successful-empty observations.
- Actual Function timer/startup settings versus UTC module eligibility and
  bounded permission slices. No restart loops or overlapping schedulers.
- Endpoint-specific authentication/authorization, non-Admin scope, legacy
  retry/token behavior versus the four durable gated collectors.
- Preserve ledgers/progress when requests are pending or blocked. Establish
  safe timing before an approved repair; otherwise remain blocked and escalate.
- Serial unchanged-input publication recovery, immutable baselines, retained
  Delta history and lifecycle-prefix review for module-local controls.
- Model context/readiness and private acceptance. Close incidents with a
  bounded recovery claim, preserving API-window gaps and unresolved uncertainty.

Capture: illustrative slides only unless separate approval is obtained. No
real request, scheduler restart, control-file edit, scope replacement, table
write, policy change, model refresh or recovery experiment for filming. Do not
show actual tenant incident logs or imply an alerting system is already deployed.

Sources: [collector operation](../local-development.md#operating-the-four-fabric-collectors),
[configuration and API contracts](../configuration-reference.md),
[Function trigger](../../function_app.py), [audit outcomes](../../env/audit.py),
[retention caveats](../deployment.md#e08-optional-blob-retention),
[analytics runbook](../../notebooks/notebook-guide.md).

## Recording and acceptance gates

Before launching a recorder:

- Approve the story, intended audience, approximate length, and narration
  approach. Synthetic speech would need a locally available or explicitly
  approved service; do not send tenant information to an external voice service.
- Inspect local Playwright/browser installation and WSL GUI support without
  installing packages or changing the machine merely for inspection.
- Confirm actual Fabric workspace, Lakehouse, imported notebook names and any
  approved semantic model for structural demonstrations. Do not discover these
  by broad collection or make assumptions from repository examples.
- Open a dedicated recording browser/profile. The operator handles authentication
  privately. Start footage only after sign-in; do not record credentials, MFA,
  tokens, cookies, browser storage or an authentication-state export.
- Review visible names, URLs, IDs, table samples and outputs before capture.
  Use approved examples and mask sensitive metadata. Browser traces and network
  captures may contain sensitive data; do not enable them by default.
- Obtain separate approval for real API requests, notebook execution, Delta
  writes or pipeline changes. Navigation and viewing existing results are the
  default live scope.

During capture and editing:

- Record short per-scene clips. Codegen can produce interaction scripts, but is
  not itself the final narrated video. Configure video capture separately.
- Use slides for architecture, configuration and unavailable production paths.
  Label illustrative diagrams and distinguish prior results from live execution.
- Remove sign-in and secret-management footage rather than relying only on
  blur. Do not publish raw evidence or executed notebooks as video assets.
- Store footage, temporary browser profiles and tenant-specific assets outside
  tracked source paths. Do not overwrite the existing MP4 or PPTX.
- Add narration and captions after the scene content is accepted. Review captions
  for API names, permission statements, notebook names and uncertainty language.

Before delivery:

- Reconcile narration with the final code and demonstrated workspace state.
  Review all claims about production readiness and permissions.
- Watch the complete rendered video with audio and captions. Check text size,
  cursor visibility, legibility, pacing, clipping and audio/video synchronization.
- Inspect frames, thumbnails, captions and file metadata for sensitive content.
  Confirm each planned scene is present or explicitly replaced with a labeled slide.
- Deliver separate versioned MP4s and approved scripts/captions, with transitions
  and an ordered viewing guide. A slide deck can accompany the series, but is
  not a substitute for the agreed browser walkthrough.

## Decisions for storyboard review

These are not implementation assumptions:

| Decision | Proposed starting point |
|---|---|
| Audience and depth | Technical evaluators and platform operators; targeted episodes with per-topic depth |
| Narration | Spoken explanation with captions; voice/source to be approved |
| Local PoC | Native Windows and Linux, with WSL2 as an optional best-of-both-worlds workflow |
| Live examples | One approved workspace/Lakehouse and a semantic-model structure if accepted; no dashboarding |
| Production demonstrations | Architecture slides unless existing deployments/pipelines are approved for viewing |
| Execution during filming | View existing results; separately approve any actual collection or writes |
| Output | Separate episode files as Release assets, linked from a viewing guide; preserve previous artifacts |
