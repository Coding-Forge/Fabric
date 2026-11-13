# Fabric Monitor: understanding Bronze, Silver and Gold

## The main idea

**Bronze keeps the evidence we collected. Silver makes that evidence consistent
and connects records where identifiers support a connection. Gold organizes
those connections into investigation cases.**

We are not moving your business data through these layers. We are transforming
**monitoring evidence about Fabric**: audit events, artifact inventory, job
observations and pipeline activity observations.

For this project, you chose to treat the existing Fabric Monitor evidence as
Bronze. That includes both raw files and the existing `dbo.monitor_*` Delta
tables, even though those tables already have some cleaning and normalization.
The medallion names describe their role in this investigation design, not how
much processing they have already received.

| Layer | Main question | Location in `lh_monitor` | What produces it |
|---|---|---|---|
| Bronze | What evidence did the collectors retain? | Existing `Files/monitor/...` and `dbo.monitor_*` tables | Existing collectors and existing transformation notebooks |
| Silver | Which events, identities, artifacts and executions can we consistently identify and connect? | `silver.*` | `24_monitor_silver_events.ipynb` |
| Gold | What does the retained evidence say about this event, and where does the trace stop? | `gold.*` | `25_monitor_gold_event_cases.ipynb` |

```text
Authorized API collectors
    |
    v
Bronze: retained raw JSON
    |                         |
    | existing notebooks      | retained raw audit files
    v                         |
Bronze: dbo.monitor_* tables   |
    |                         |
    +-------------------------+
                |
                v
       Silver notebook 24
                |
       Published silver.* tables
                |
                v
        Gold notebook 25
                |
        Published gold.* tables
                |
                v
    Future semantic-model/report integration
```

**The last step is not implemented yet.** The existing FM Observability model
is a separate investigation prototype. These notebooks do not rebind or replace
that model, change its relationships, or add report visuals.

## 1. Bronze: retain what was observed

Bronze is our starting evidence, not a guaranteed complete picture of Fabric.
The existing collectors retrieve selected metadata under their configured
permissions and collection scope. Existing notebooks turn retained files into
the existing `dbo.monitor_*` tables.

For example:

| Evidence | What it can establish | What it cannot establish by itself |
|---|---|---|
| Raw audit event | The provider reported an operation, identifiers, time and possibly an actor/IP/outcome | A complete pipeline execution, physical destination or proven downstream effect |
| Inventory/catalog observation | An item with a particular identity/name/type was observed | Its exact state at every earlier or later time |
| Job observation | A particular execution and reported status/timing were retained | That all executions were collected or that the status is current |
| Pipeline activity observation | A particular activity, parent run and selected metrics were retained | The full activity input/output payload or physical source/sink |
| Resource collection outcome | A poll/query was attempted with a recorded outcome | That an execution actually occurred |

**A collection run and a pipeline run are different things.** A collector can
successfully poll an item and receive no job records. It can also retain a failed
poll outcome without retaining any executions.

### The exact Bronze inputs used by this first Silver notebook

The new Silver notebook does not read every existing Monitor table. It reads:

| Input | Purpose in Silver |
|---|---|
| `dbo.monitor_inventory` | Historical workspace/item identity and label evidence |
| `dbo.monitor_catalog_items` | Additional item identity and label evidence |
| `dbo.monitor_collection_health` | Retained collection-health evidence |
| `dbo.monitor_job_resources` | Job polling outcomes and coverage |
| `dbo.monitor_job_observations` | Retained execution IDs, root correlation IDs, status and timing |
| `dbo.monitor_pipeline_activity_resources` | Activity polling/query outcomes and coverage |
| `dbo.monitor_pipeline_activity_observations` | Retained activity IDs, parent/child run references and selected metrics |
| `Files/monitor/activity/...` | Original audit records, including reported actor/IP and correlation fields |

Jobs are transformed by notebook 03; optional pipeline activities by notebook 22.
Those notebooks transform existing collector output. **Rerunning a transformation
does not fetch missing history from an API.**

Bronze may also hold permissions, scanner lineage, definitions, connections and
other evidence. The existence of those sources does not mean this first
Silver/Gold slice consumes them.

### API scope still matters

Audit evidence comes from the retained Admin activity collection. Job and
pipeline-activity evidence comes from workspace/item-scoped, non-Admin Fabric
APIs under the original collector's permissions.

Therefore, an audit event can exist even when the collector could not retrieve
its related execution. Permissions, supported item/job types, history windows,
polling gaps and failed collection can all limit what Bronze contains.

Silver and Gold do not broaden those permissions or call the collection APIs.
See the [API scope and authorization reference](../docs/configuration-reference.md#api-scope-and-authorization-boundaries).

## 2. Silver: normalize identity and establish evidence-backed links

Silver is where we stop treating every record as an isolated file or row.
Notebook 24 performs the following transformations.

### Normalize events and preserve their history

It reads the retained audit records, normalizes identifiers and UTC timestamps,
and creates one normalized event per tenant-scoped provider event ID.

Identical repeated records do not become additional events. Their distinct
source files remain traceable. JSON property order does not create a new event.
If the same provider ID has conflicting content, Silver retains a minimal
conflict event and a quarantine reason instead of arbitrarily choosing an actor
or execution.

An event without a provider ID uses an explicitly labelled canonical
full-record hash. That is a different identity basis, not a fabricated provider ID.

### Create stable keys instead of joining by names

An artifact is identified by tenant, workspace and item IDs. Executions and
activities add their own scoped identifiers. An item named `Daily Load` in one
workspace is not joined to another item simply because both have that name.

The tenant UUID supplies the namespace for these keys. By default, Silver
discovers it from the Fabric execution identity. A manual `TENANT_ID` overrides
discovery; `AUTO_DISCOVER_TENANT=False` requires manual configuration.

This is not a credential or a grant of access. For copied evidence from another
tenant, use that evidence owner's tenant UUID. Keep it consistent across reruns:
changing the namespace changes the generated keys.

### Separate an audit reference from an observed artifact

If an event explicitly reports a workspace/item ID, Silver records the reference
and its resolution state. An identifier absent from inventory is still retained
as a reported identifier; absence is not treated as proof of deletion.

Names and types come from historical observations. Gold later labels whether
a name was observed before the event, only afterward, without a timestamp,
or with conflicting observations. A later name is a hint, not a verified
event-time name.

### Normalize executions and activities without adding up repeated polls

Silver retains job observations and selects a usable latest observation per
scoped execution. It similarly selects a usable latest activity observation.
It does not add together repeated snapshots of the same activity's metrics.

Conflicting latest observations are quarantined rather than silently selecting
a status. Failed/empty/unknown-order polling evidence remains relevant even when
an older successful observation exists.

Missing metrics remain null, not zero. A reported zero remains a reported zero.
An activity's explicit parent run can survive missing job evidence, but its job
status and timing remain unknown.

### Match an event to a run only when the evidence supports it

The implemented match compares an audit `ActivityId` or `RequestId` with a job's
`root_activity_id`, then requires compatible explicit artifact scope.

An exact identifier match alone is insufficient if the artifact scope conflicts.
Multiple compatible candidates are marked ambiguous rather than promoted.
Matching names or nearby timestamps are not substituted for exact identifiers.

Even an accepted link establishes **correlation**, not proof that the audit actor
initiated the run or caused every subsequent effect.

### Keep identity/IP and location evidence appropriately limited

Silver creates actor/IP keys, but suppresses their reported values by default
with `INCLUDE_SENSITIVE_VALUES=False`. Preserving `UserId` versus `UserKey` does
not equate those provider identities to a verified human.

Reported object/source locations are redacted and retained separately. They are
not relabelled as physical pipeline destinations. The existing pipeline-activity
collector deliberately excludes arbitrary input/output and error payloads.
Consequently, physical source and destination fields remain unknown even when
activity metrics exist.

### The 17 Silver tables

A table's **grain** means what one row represents.

| Table | One row represents / purpose |
|---|---|
| `audit_event` | A normalized provider event or explicitly labelled derived/conflict event |
| `event_source` | A distinct event/source-file association |
| `actor_identity` | A scoped reported identity key, with optional reported value |
| `client_ip` | A reported IP key, with optional reported value |
| `artifact_observation` | A historical item identity/name/type observation |
| `event_artifact` | An event's artifact reference and its source-field role |
| `execution_observation` | A retained execution observation |
| `execution_latest` | A latest usable scoped execution, including activity-referenced parents |
| `pipeline_activity` | A latest usable scoped activity with nullable metrics and coverage |
| `event_correlation_id` | A canonical correlation value and the audit field that supplied it |
| `correlation_candidate` | An exact-ID candidate with its scope/ambiguity assessment |
| `event_execution_link` | An accepted exact, unambiguous, artifact-compatible event/run pair |
| `child_run_link` | An explicit child-run reference and its resolution |
| `reported_location` | A redacted audit location/reference |
| `quarantine` | An entity key and reason why evidence was not safely promoted |
| `evidence_coverage` | Source availability, counts, versions and interpretation |
| `build` | The snapshot's identity and publication-readiness gate |

## 3. Gold: turn those links into an event investigation

Gold reads **published, ready Silver tables**, not Bronze directly and not the
temporary results of a Silver preview.

Notebook 25 organizes the evidence around a question:

> For this audit event, what artifact references, correlated executions and
> retained activities can I follow, and where does the evidence stop?

It builds one event case, independently counts artifact references and execution
links, attaches historical label hints, and creates typed trace edges.
Unmatched or conflicting events remain cases; they are not dropped to make the
results look complete.

### The 8 Gold tables

| Table | Purpose |
|---|---|
| `event_case` | One event with operation/time, actor/IP keys, reference/link counts, correlation state and trace-limit flag |
| `event_trace_edge` | Evidence links for that event: references, exact correlations, parent/child runs and explicit gaps |
| `execution_fact` | One scoped execution with retained status/timing and coverage |
| `pipeline_activity_fact` | One scoped activity with latest retained metrics |
| `event_execution_bridge` | Accepted event/run pairs for downstream analysis/model integration |
| `reported_location` | Redacted audit references, still separate from physical endpoints |
| `evidence_coverage` | Silver source limitations carried into Gold |
| `build` | Gold readiness and its connection to the source Silver build |

**Gold is not just a large joined table.** If several events reference the same
run, duplicating that run's activity metrics into every event would inflate
movement totals. Facts stay at execution/activity grain; cases and bridges
provide the connections. Do not sum the same facts repeatedly across events or
assume chained activities describe distinct end-to-end movement.

Child-run traces are cycle-safe and depth-capped. A capped trace is flagged;
the output does not silently imply that traversal was complete.

### An illustrative trace, not your current observed result

The identifiers and numbers below are fictional shorthand, not executable input
or evidence from your tenant.

| Layer | Example |
|---|---|
| Bronze | Audit event E1 reports pipeline P1 and correlation C1. A retained job R1 reports the same root correlation. A Copy activity A1 reports 42,000 copied rows. |
| Silver | Deduplicate E1, scope P1, normalize R1/A1, and accept E1-to-R1 only if identifiers and artifact scope agree without ambiguity. |
| Gold | Produce case E1 and trace E1 -> R1 -> A1, with A1's retained metrics and explicit unknown physical source/destination. |

That supports: **"E1 is exactly correlated with this observed run, which has
this observed activity and reported metric."**

It does not support: **"This person definitely initiated the run, 42,000 distinct
business rows reached this physical destination, and these downstream systems
were affected."**

## 4. What your Silver preview actually tells us

In the preview you shared on November 13, 2026:

| Input / setting | Reported count or state | Meaning |
|---|---|---|
| Inventory | 1,934 rows | Retained inventory observations, not necessarily 1,934 distinct current items |
| Catalog items | 137 rows | Retained catalog item observations |
| Collection health | 1,894 rows | Retained collection-health evidence |
| Job resources | 483 rows | Polling/outcome evidence, not 483 executions |
| Job observations | 0 rows | No retained job execution records in this input table |
| Pipeline activity resources | 132 rows | Activity collection outcomes, not 132 executed activities |
| Pipeline activity observations | 0 rows | No retained activity execution records in this input table |
| Raw activity | 29,608 records | Audit input records before Silver event deduplication |
| Actor/IP values | Suppressed; 19 keys combined | Reported values are hidden; this is not a count of distinct people or events |

The displayed table is **source coverage**, not the final Silver table counts.
For example, 29,608 raw audit records need not become 29,608 distinct Silver
events. The notebook separately prints output-table counts.

The preview establishes that the input-reading/transformation path ran. It does
not establish that every source is complete, that execution tracing is populated,
or that any Silver table was written.

**With both execution-observation inputs empty, this snapshot cannot establish
event-to-observed-run or run-to-activity traces.** Gold can still preserve events
and their artifact references, but must show missing execution links rather than
inventing them.

The next evidence question is why Bronze execution observations are empty.
Inspect the latest job/activity resource statuses and reasons. This summary
cannot distinguish empty history from unsupported requests, permission failures,
collection errors or collection-window limits. Silver matching cannot repair
evidence that was never retained.

## 5. Preview, publication and model refresh are different operations

| Operation | What happens | What does not happen |
|---|---|---|
| Silver preview (`WRITE_TABLES=False`) | Reads pinned Bronze inputs, computes Silver rows, checks safeguards and displays coverage/counts | Does not create or replace persisted Silver tables |
| Silver publication (`WRITE_TABLES=True`) | Writes owned `silver.*` snapshots, verifies persisted rows, rechecks sources and marks the build ready | Does not modify Bronze or deploy a semantic model |
| Gold preview (`WRITE_TABLES=False`) | Reads a published ready Silver build and computes cases/facts/traces | Does not publish Gold and cannot consume an unpersisted Silver preview |
| Gold publication (`WRITE_TABLES=True`) | Writes and verifies owned `gold.*` snapshots with a readiness gate | Does not create report relationships or refresh/rebind FM |
| Semantic-model integration/refresh | A separate future step to expose the intended tables, relationships and measures | Does not itself collect missing execution evidence |

A workspace folder named **Silver** organizes a notebook. A Lakehouse schema
named **silver** organizes tables. Creating the folder does not create the schema,
and creating the schema does not create/populate the tables.

Publication replaces only the owned derived snapshots; it does not append an
independent investigation history on every run or overwrite Bronze history.

A **ready build means the published snapshot passed consistency checks**.
It does not mean collection coverage is complete. A ready build can correctly
contain zero execution observations and explicit evidence gaps.

If a previous Silver build exists, Gold reads the published build, not your
newer preview. Review build IDs and coverage to avoid mistaking an older
published snapshot for the preview you just ran.

## 6. What we can answer, and what remains unfinished

| Question | Current capability / limitation |
|---|---|
| What operations were reported, and when? | Normalized Silver audit evidence; Gold event cases when built from published Silver |
| What artifact did an event reference? | Explicit scoped references and historical label hints; unresolved references remain visible |
| What identity/IP was reported? | Keys are available. Actual values require Silver opt-in and access review; Gold does not copy those raw values. A reported IP may represent a proxy/service and is not proof of a person's device or location. |
| Which pipeline run matches this event? | Supported only with retained exact identifiers and compatible scope; your shared inputs currently contain no run observations |
| What activities/metrics were retained for that run? | Implemented when activity evidence exists; your shared activity-observation input is empty |
| Which physical data was read or written, and where? | Not established by the retained activity contract. Audit locations and artifact references are not physical runtime endpoints. |
| What would break if an artifact were deleted or changed? | Dependency-impact closure is still pending; it is not replaced by runtime correlation |
| Did this actor cause a particular downstream effect? | Not proven by an audit/run correlation |
| Can I already consume Gold through the FM semantic model? | No new Gold model binding, dimensions, measures or report integration has been implemented |

This is the **first event/artifact/execution slice**, not the entire original
investigation vision. Effective access analysis, comprehensive control-plane
classification, dependency-impact outputs and a new semantic-model experience
remain further work. Operations/workloads retained in Silver do not by
themselves constitute those higher-level classifications.

## 7. Safety and operating limits

Schemas are not security boundaries. Hashed keys can still be linkable; names,
identifiers, paths and detail previews can still be sensitive. No RLS, OLS,
permission grants or export restrictions have been introduced. Turning on
reported actor/IP values requires a separate access review.

Source versions and raw-file hashes are pinned/rechecked so a build cannot
silently combine changing inputs. Ownership/schema checks prevent an automatic
takeover of unrelated tables. A failed write leaves a non-ready gate; consumers
must respect readiness and matching build IDs.

There is no cross-table transaction or distributed writer lock. Run serially,
with upstream and layer writers idle, and retain Delta history.

This first implementation reads through Spark but processes bounded rows on the
Python driver. It is not yet a distributed, unrestricted-scale correlation
engine. Limits fail rather than publishing silently truncated results.

Local synthetic/mocked tests validate transformation and guard behavior.
Your shared Silver preview is live runtime evidence, but controlled Delta
publication, Gold execution, permissions and semantic-model acceptance are
separate checks.

## Where to go for the operational details

- [Gold query examples](GOLD_QUERIES.md): read-only notebook setup and queries
  for events, artifact labels, traces, activities and evidence gaps.
- [Medallion runbook](MEDALLION.md): configuration, upload/run order, publication,
  exact limits and validation commands.
- [Notebook reference](README.md): existing Bronze table contracts and producers.
- [Tracking checklist](../TODO.md): implemented first-slice work and pending
  collection, access, impact and model acceptance.

**Bottom line:** we have built a disciplined way to turn collected monitoring
records into an event investigation without filling missing evidence with
assumptions. Your preview shows usable audit/artifact inputs and an execution
coverage gap. Filling that Bronze gap is necessary before the implemented
Silver/Gold pipeline trace can demonstrate actual retained executions.
