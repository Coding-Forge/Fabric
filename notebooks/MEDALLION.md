# Silver and Gold event investigation

For a plain-language explanation of the layers, transformations, your preview
and what remains unfinished, start with [Understanding Bronze, Silver and Gold](MEDALLION_EXPLAINED.md).

Notebooks 24 and 25 implement the **first slice** of the plan in [TODO.md](../TODO.md):
event -> scoped artifact -> exact execution -> retained activity/child run.
They do not implement dependency-impact closure, effective permissions,
additional runtime endpoint collection or a new semantic model.

Existing `Files/monitor` and `dbo.monitor_*` evidence is treated as Bronze.
Nothing is moved or renamed. Outputs are new, owned Delta snapshots in the
same schema-enabled Lakehouse. Workspace folders and Lakehouse schemas are
different: folders organize notebooks; qualified output names select schemas.

## Upload and run

| Workspace folder | Upload | Output |
|---|---|---|
| Silver | `24_monitor_silver_events.ipynb` | `lh_monitor.silver.*` |
| Gold | `25_monitor_gold_event_cases.ipynb` | `lh_monitor.gold.*` |
| Gold | `26_monitor_gold_investigation.ipynb` | Read-only queries against published Gold; no new tables |

1. Create the `silver` and `gold` schemas and attach **lh_monitor as the default
   Lakehouse** to both notebooks. If its name differs, set `LAKEHOUSE_NAME`.
2. In 24, leave `AUTO_DISCOVER_TENANT=True` and `TENANT_ID=""` for automatic
   discovery from the Fabric execution identity. For a manual override, set
   `TENANT_ID` to the evidence owner's tenant UUID; a nonempty value takes
   precedence. Set `AUTO_DISCOVER_TENANT=False` to require manual configuration.
   The tenant UUID is not a credential.
   Keep `WRITE_TABLES=False` and `INCLUDE_SENSITIVE_VALUES=False`.
3. Run 24. Inspect coverage/counts, missing inputs and quarantine. It uses raw
   Admin activity files for event IDs, actor/IP keys and correlation IDs.
4. After reviewing access, evidence scope and preview results, set
   `WRITE_TABLES=True` in 24 and rerun to publish Silver.
5. Run 25 with `WRITE_TABLES=False`. A ready, persisted Silver build is required;
   a Silver preview alone is not an input to the separate Gold notebook.
6. Set `EVENT_ID` to a reported provider event ID to display its case/trace.
   The default output shows aggregate operation/correlation counts only.
7. Review the result, then explicitly enable Gold publication if desired.
8. Optionally import 26, attach the same Lakehouse, choose `EVENTS_SQL`, and run
   its self-contained setup/event loop. See [Gold query examples](GOLD_QUERIES.md).

No schema, permission, collector, schedule, FM report/model or other Fabric item
is created or changed by preview. Publication changes only owned layer tables.
The existing `nb_orchestrator` remains unchanged and does not run 24 or 25.
No shell application credentials or collection API calls are used.

Automatic tenant discovery reads the `tid` claim from a token obtained directly
through [`notebookutils.credentials.getToken("pbi")`](https://learn.microsoft.com/en-us/fabric/data-engineering/notebookutils/notebookutils-credentials).
The token and other claims are never displayed or persisted. This is execution
identity metadata, not an independent cryptographic token validation or proof
that copied Bronze evidence belongs to that tenant. Use the manual override for
evidence collected from another tenant. Discovery failures stop before evidence
reads or writes, with instructions for manual configuration; no tenant is guessed.
Token acquisition uses the existing Fabric execution identity and adds no
collector permissions or REST data requests.

## Sources and execution identity

Silver reads version-pinned, owned `dbo.monitor_` tables:

`inventory`, `catalog_items`, `collection_health`, `job_resources`,
`job_observations`, `pipeline_activity_resources`, and
`pipeline_activity_observations`.

It also reads the retained `Files/monitor/activity/YYYY/MM/DD/YYYYMMDD_page.json`
scope. Raw file hashes and file availability/scope are rechecked.
Missing tables are represented as missing, not successful empty tables. An
existing source with incompatible Monitor ownership is rejected, not guessed.
Jobs are supplied by notebook 03; optional pipeline activities by notebook 22.
Publishing those contracts does not prove their collection is populated.

The signed-in Fabric execution identity needs Bronze table/raw-file read access,
and layer write access only for explicit publication. Gold needs Silver read
access and optionally Gold write access. Schema-enabled, three-part Spark names
are used; these schemas are not created automatically.

**Non-Admin scope:** retained jobs and pipeline activities originate from
workspace/item-scoped Fabric APIs under the collector's caller permissions.
Recent history, polling gaps and activity query windows limit coverage.
These notebooks introduce no new API permissions and cannot broaden the
original collection scope. See [configuration reference](../docs/configuration-reference.md)
and [notebook contracts](README.md).

## Silver contracts

All tables carry `build_id`, source path/hash, source observation ID, observation
time, coverage, collection module/mode/run ID and a normalized record hash.
Collector run IDs are not execution IDs. Typed timestamps are normalized to UTC;
the Spark session is set to UTC. Provider audit CreationTime is defined as UTC.
Naive string timestamps from other evidence are rejected.

| Table | Grain / interpretation |
|---|---|
| `audit_event` | One provider event, or explicitly labelled canonical full-record hash when ID is absent. Conflicts remain visible as minimal conflict events. |
| `event_source` | Distinct retained source files for each event, including duplicate observations across files. |
| `actor_identity`, `client_ip` | Scoped keys; reported values suppressed by default. |
| `artifact_observation` | Historical workspace/item observations, names and types. Names are not keys or current-state claims. |
| `event_artifact` | Event/reference role with scoped, not-in-inventory or unresolved resolution. |
| `execution_observation` | Retained job observations, not a live status table. |
| `execution_latest` | One usable scoped execution. Conflicting latest/unknown-order states are quarantined. Activity-only parents retain unknown job status/timing. |
| `pipeline_activity` | Latest usable activity per scoped run/activity, with nullable reported metrics, polling coverage and explicit destination gaps. |
| `event_correlation_id` | Canonical audit ActivityId/RequestId values and source fields. |
| `correlation_candidate` | Exact ID matches with scope mismatch/unresolved/ambiguity states. No time/name proximity inference. |
| `event_execution_link` | One exact, unambiguous, artifact-compatible event/execution pair. |
| `child_run_link` | Explicit child-run ID resolved only against one uniquely scoped observed execution, or an unresolved/ambiguous gap. |
| `reported_location` | Redacted provider object/source references, not physical pipeline endpoints. |
| `quarantine` | Entity key and reason; no conflicting raw payloads or identity values. |
| `evidence_coverage` | Missing/present sources, retained row counts, source versions and privacy setting. |
| `build` | One readiness gate, source signature, version and sensitive-value setting. |

Identities use tenant/workspace/item scope and execution/activity IDs, never
artifact names. Event IDs are tenant-scoped. JSON key ordering does not create
event conflicts. Different content for the same provider ID is not silently
chosen; Gold retains a conflict case without promoting its actor or execution.

Inventory absence does not prove deletion or nonexistence. Explicit scoped IDs
can link to a matching observed execution even when inventory did not retain
the item, with the inventory gap remaining visible.

Latest failed/empty/unknown-order poll states accompany retained historical
statuses and activity metrics. They never certify old successes as live status.
Unknown metrics stay null; actual reported zeros remain zeros.

## Gold contracts and interpretation

| Table | Grain |
|---|---|
| `event_case` | One event, reference/link counts, historical label hints, correlation state and trace-limit flag. |
| `event_trace_edge` | One event-scoped typed evidence edge, with role/matched fields, provenance and stable edge key. Gaps have null targets. |
| `execution_fact` | One scoped execution; metrics/status are not multiplied by audit references. |
| `pipeline_activity_fact` | One scoped activity with latest reported metrics. |
| `event_execution_bridge` | Explicit event/execution links for downstream semantic models. |
| `reported_location` | Redacted audit references, linked from cases without presenting them as runtime sinks. |
| `evidence_coverage` | Silver source/scope limitations carried into Gold. |
| `build` | Gold readiness and source signature, tied to `source_build_id`. |

Artifact reference counts and execution links are calculated independently.
Metrics stay at execution/activity grain: do not sum them across correlated
events or chained activities as distinct end-to-end movement.

Gold label hints distinguish last observed before the event, later-observed,
undated, unknown-event-time and conflicting hints. Even a prior name is a
historical observation, not proof it remained valid until the event.

Exact ID/scope links establish correlation, **not causality or the initiating
actor**. Actor/IP keys belong to the audit event. Zero supported links does not
prove zero executions. Activity metrics do not establish physical sources/sinks;
both remain null with `NOT_RETAINED_BY_CURRENT_CONTRACT` trace gaps.
Reported ObjectId/ImportSource strings remain separately labelled references
in Silver and Gold, never physical destination evidence.

Child traversal is cycle-safe and depth-capped (default/max 32). The case
explicitly flags capped traces. Dependency impact is not substituted for
runtime movement and is still pending in TODO.md.

## Privacy

`INCLUDE_SENSITIVE_VALUES=False` preserves actor/IP keys but suppresses actual
reported values. Enable it only after reviewing layer/model Build/export access
and the intended audience. Gold does not copy these raw values into cases/facts.
This is **not anonymization**: keys can be linkable, and item names, IDs, locations,
source paths and detail outputs can still be sensitive.

Schema separation does not create an access boundary. No RLS, OLS, grant change
or automatic export restriction is introduced. Default displays are aggregate
counts/coverage; explicit `EVENT_ID` preview can show sensitive operational detail.
Clear notebook outputs before sharing or committing.

## Bounds and publication safety

This is a **bounded driver-side first implementation**, not a distributed
production-scale correlation engine. Spark reads Delta snapshots, but normalized
rows are materialized in Python. Defaults cap each source at 250,000 rows and
total inputs at 500,000 for Silver / 1,000,000 for Gold. Raw defaults cap 10,000
files, 128 MiB total and 8 MiB per file. Candidate construction and Gold traces
also have hard 500,000 limits. Limits fail instead of publishing truncated data.
`MAX_PREVIEW_ROWS` only limits explicit detail display, not the published build.

Run after Bronze publication with upstream and medallion writers idle; do not
overlap Silver/Gold writers. Existing layer ownership and exact schemas are
preflighted before writes. A contract change needs an explicit migration/version
decision, not automatic schema evolution.

Publication marks `build` as `building`, overwrites only owned derived snapshots,
verifies persisted rows in both directions, rechecks all inputs, then marks
the build ready. Bronze is never overwritten. A failure leaves the gate non-ready;
consumers must honor readiness/build IDs, not read partially replaced tables.
Delta history is retained by the engine; no VACUUM or retention changes are made.
There is no distributed lock or cross-table transaction. If creation fails before
ownership properties are set, the unowned table is rejected on rerun rather than
silently claimed.

Gold pins the Silver gate before reading data, validates matching build IDs
and rechecks source versions. Rebuilding layers is different from model
framing refresh. No semantic-model deployment is performed.

## Validation

Synthetic tests cover exact/scoped and ambiguous links, duplicate/conflicting
events, fan-out, latest metrics, polling failure, historical labels, child
scope/cycles/depth caps, privacy/redaction, source readiness and publication guards.

```bash
.venv/bin/python -m unittest tests.test_monitor_medallion \
  tests.test_monitor_notebooks.UploadableNotebookTests -v
ruff check --target-version py310 notebooks/monitor_medallion.py \
  notebooks/monitor_medallion_runtime.py notebooks/build_monitor_notebooks.py \
  tests/test_monitor_medallion.py
ruff format --check notebooks/monitor_medallion.py \
  notebooks/monitor_medallion_runtime.py notebooks/build_monitor_notebooks.py \
  tests/test_monitor_medallion.py
.venv/bin/python notebooks/build_monitor_notebooks.py
```

Upload artifacts are generated from Python sources, self-contained, Python 3.10
compatible, with parameter cells and cleared outputs. No tenant data or API
credentials are embedded. Offline tests do not establish Fabric Spark namespace,
Delta publication, access or live DAX behavior. Perform preview and controlled
Silver/Gold publication acceptance in Fabric before scheduling/sharing.
