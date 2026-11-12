# Notebook walkthrough and operator runbook

Use this guide to understand and run the **22 numbered Fabric analytics
notebooks**. Use the [technical reference](README.md) for the full list of
**50 managed datasets** (including optional notebook 22), field/provenance
contracts and the [collector coverage matrix](README.md#registered-collector-coverage).

These are analytics notebooks, not collectors. They read files that Monitor
already collected. Running a notebook does not request new API data, enable a
module, grant permissions or discover fields that the source never returned.

## How the pieces fit together

```text
Authorized API collectors
    |
    v
Lakehouse Files/monitor: retained raw JSON and collector controls
    |
    v
01-04 and 07-21: preview, then optional insert-only Delta publication
    |
    v
Lakehouse Tables/monitor_*: curated historical observations
    |
    +-- 05: read-only core visualizations
    +-- 06: rerun validation and optional saved metadata baseline
    +-- 07-21: domain charts alongside their transformations
    +-- Optional 22: Data Factory pipeline activity facts and query coverage
    +-- Optional/future consumption: KQL access or external delivery
```

The example deployment uses workspace **FabricMonitor**, default Lakehouse
**lh_monitor**, raw root `/lakehouse/default/Files/monitor` and table prefix
`monitor_`. Names are examples; match the raw root and prefix consistently if
you use a different Lakehouse.

The notebooks preserve evidence and its uncertainty. A retained successful
observation is not proof of current state after a later failed poll. Missing
data is not zero, and missing items are not automatically deleted.

## Import, preview and publish

1. Import the numbered `.ipynb` files into Fabric. They embed their tested
   helpers; do not upload the `.py` files, install repository dependencies or
   use `%run` to connect them.
2. Attach the intended Lakehouse as **default** to each notebook. Use a
   supported Fabric PySpark runtime with Spark, Delta, pandas and matplotlib.
3. Check `RAW_ROOT` and `TABLE_PREFIX` in the parameter cell. Confirm the
   executing identity can read raw files and write the intended curated tables.
   The collector's shell credentials do not configure notebook authentication.
4. Run 01-04 with `WRITE_TABLES = False`. Inspect coverage and preview counts,
   then rerun each with `WRITE_TABLES = True` when the destination is correct.
5. Run the required domain notebooks, 07-21, with the same preview/write
   workflow. They read their raw sources rather than consuming another domain
   notebook's output. They can be adopted individually.
6. Run 05 after 01-04 have published. It reads the original core tables, not
   all domain tables. Use each domain notebook's own charts for the other topics.
7. Run 06's capture/rerun/compare experiment after all writers in your chosen
   validation scope have published.

The numbering organizes the suite; it is not a requirement to execute 06 before
07. For a full 48-table acceptance test, publish 01-04 and 07-21 first, then
validate with 06. Do not run writers concurrently: multiple domain notebooks
share `estate_coverage`, and same-prefix concurrent writing is unsupported.
Notebook 22 can be added independently. Its publication, validation scope and
serial-orchestrator inclusion are explicit opt-ins; the previous defaults remain.

Preview still validates existing table ownership/schema/content when present.
It does not bypass safeguards. The publication counts describe transformed
observations, not necessarily newly inserted rows or current unique resources.

## Notebook-by-notebook walkthrough

### 01 - Inventory and collection health

[Open notebook](01_monitor_inventory_health.ipynb).
Use it to establish the core inventory and retained collection outcomes before
interpreting permissions, jobs or lineage. It writes `inventory` and
`collection_health`. Daily workspace/item files remain legacy-unverified;
their presence does not establish a complete current tenant inventory.
Domain-specific coverage is also recorded by 07-21 in `estate_coverage`.

### 02 - Scoped and Tenant permissions

[Open notebook](02_monitor_permissions.ipynb).
Use it to examine observed item grants, resource outcomes and linked collection
cycles. It writes `permission_cycles`, `permission_resources` and
`permission_grants`. Set `PERMISSION_MODE` explicitly for the preview; retained
Scoped and Tenant evidence stays separate. This does not expand groups or
calculate effective access, and failed resources are unknown rather than
zero-access items.

### 03 - Fabric item job history

[Open notebook](03_monitor_job_history.ipynb).
Use it to investigate collected job statuses, timing and failed/empty item
polls. It writes `job_resources` and `job_observations`. A retained ongoing job
may be old; use its collection coverage and observation time alongside status.
This is separate from semantic-model refresh history in 11.

### 04 - Scanner, static lineage and configured associations

[Open notebook](04_monitor_lineage.ipynb).
Use it to inspect upstream/downstream relationship observations, successful
zero-edge evidence and unsupported-definition diagnostics. It writes
`lineage_resources`, `lineage_edges` and `lineage_diagnostics`. Scanner evidence
and static definition inference are separate; neither proves runtime I/O or
exhaustive column-level lineage.

For collected Lakehouse shortcuts, set `INCLUDE_SHORTCUTS=True` in 01-04 and 06,
or in the serial orchestrator and 06. This adds `shortcut_configuration` evidence
to the existing lineage tables, not new datasets. Known OneLake IDs remain
unverified configuration; external fingerprints and unavailable target details
are not resolved storage or access proof. Notebook 05 draws non-directional
dashed associations. Inspect collection health before selecting the graph.

For Eventstream configuration, set `INCLUDE_EVENTSTREAM_TOPOLOGY=True` in 01-04
or the orchestrator and match it in 06. It adds sources, streams, operators,
destinations and declared input links to the existing lineage tables. Purple
dashed arrows mean declared inputs, gray dashed lines mean node membership and
green dashed associations mean configured targets, never verified runtime I/O.
Names/payloads are omitted or fingerprinted; unresolved targets and inputs stay
diagnostic. No new tables or notebooks are required.

### 05 - Core visualizations

[Open notebook](05_monitor_visualizations.ipynb).
Use it after publishing 01-04 to view collection coverage, permissions, retained
job status/durations and a bounded directed lineage graph. It does not write
tables or collect data. Choose a permission mode/cycle and, when needed, an
explicit historical lineage source; do not union past relationships as current.

### 06 - Persistent rerun validation

[Open notebook](06_monitor_validation.ipynb).
Use it to test whether unchanged-input reruns preserve exact curated contents,
not just row counts. Capture saves a new metadata-only file outside raw evidence;
compare reads that file and retained Delta versions. Existing baselines are never
overwritten. A PASS proves rerun stability, not data freshness, completeness or
full workspace acceptance. See the validation workflow below.

### 07 - Activity and audit events

[Open notebook](07_monitor_activity_events.ipynb).
Use it to explore recorded operations, workload/workspace/item context and
provider event times. It writes `activity_events` and shared coverage. It covers
collected Power BI activity evidence, not every Fabric/Azure audit service.
Actor keys are pseudonyms, not anonymous identities; UPNs, IPs and raw payloads
are excluded.

### 08 - Estate catalog and semantic-model schema

[Open notebook](08_monitor_estate_catalog_schema.ipynb).
Use it to explore collected workspaces/items and returned semantic-model tables,
columns, measures and relationships. It writes `catalog_*` and `model_*` tables
plus shared coverage. An absent schema differs from an explicitly empty one.
Lakehouse/Warehouse inventory is not physical schema discovery, and expression
text is not exported.

### 09 - Fabric connections

[Open notebook](09_monitor_connections.ipynb).
Use it to inspect connection types, connectivity/privacy metadata and associated
gateway IDs. It writes `connection_observations` and shared coverage. Results are
caller-visible, not tenant-complete; paths, credentials and raw connection
payloads are excluded. Invalid or unfinished immutable runs produce no facts.

### 10 - Gateways and datasources

[Open notebook](10_monitor_gateways.ipynb).
Use it to inspect gateway/datasource inventory and recorded connectivity
responses. It writes `gateway_observations`, `gateway_datasources`,
`gateway_status` and shared coverage. Missing detail/status files are flagged.
Recorded status is not a live connectivity test; gateway user/access lists and
connection details are deliberately excluded.

### 11 - Dataset refresh history

[Open notebook](11_monitor_refresh_history.ipynb).
Use it to inspect semantic-model refresh outcomes, durations, failure codes and
refreshable inventory/statistics. It writes `refresh_observations`,
`refreshable_observations` and shared coverage. API history windows cannot
recover missed refreshes; ongoing/unknown/inverted durations stay null. Raw
error messages and configured-by identities are excluded.

### 12 - Published apps

[Open notebook](12_monitor_apps.ipynb).
Use it to inspect collected application names, workspace references and update
times. It writes `apps` and shared coverage. This is app inventory, not audience
membership or app permissions; complete pagination is not established by the
legacy source.

### 13 - Capacity inventory and performance

[Open notebook](13_monitor_capacity_performance.ipynb).
Use it to inspect capacity SKU/state/region and returned utilization/carryover
measure timepoints. It writes `capacities`, `capacity_metric_observations` and
shared coverage. CapacityMetrics collection is opt-in. Provider values/units and
query dates are preserved; a naive timepoint has unknown UTC. Overlapping
snapshots must not be added together as capacity KPIs.

### 14 - Directory and licensing

[Open notebook](14_monitor_directory_licensing.ipynb).
Use it to inspect selected user/group attributes, transitive user memberships,
user/SKU assignments and subscribed SKU quantities. It writes directory,
membership, license and SKU tables plus shared coverage. Groups are optional and
membership collection can be capped; it is not direct group nesting or effective
authorization. Names, UPNs and mail are excluded, but joinable IDs remain sensitive.

### 15 - Workspace roles

[Open notebook](15_monitor_workspace_roles.ipynb).
Use it to distinguish returned workspace assignments from workspaces whose user
lists were not returned. It writes `workspace_role_scopes`,
`workspace_role_assignments` and shared coverage. Missing/null users is unknown,
not an empty assignment list. Workspace roles are distinct from the item grants
in 02; neither notebook computes effective access.

### 16 - Tenant and delegated settings

[Open notebook](16_monitor_tenant_settings.ipynb).
Use it to examine tenant settings, capacity/domain/workspace override scopes,
delegation origin and enabled/excluded security-group rules. It writes tenant
settings, delegated scopes/overrides and group-rule tables plus shared coverage.
These are observed settings, not computed precedence or effective policy.

### 17 - Domains and workspace associations

[Open notebook](17_monitor_domains.ipynb).
Use it to explore collected domain metadata and workspace associations. It
writes `domains`, `domain_workspaces` and shared coverage. The collector omits
domains without workspaces, so this cannot establish complete domain inventory.
Conflicting normalized domain metadata quarantines that source file.

### 18 - Workspace Git connections

[Open notebook](18_monitor_git_connections.ipynb).
Use it to inspect providers, repository/branch metadata, connection states and
returned sync times. It writes `workspace_git_connections` and shared coverage.
It does not read code or verify current sync health. Owners/directories are
hashed; URLs and credentials are excluded. Remaining repository metadata can
still be sensitive.

### 19 - Tag definitions

[Open notebook](19_monitor_tags.ipynb).
Use it to inspect tag names and tenant/domain scope. It writes `tags` and shared
coverage. It does not answer which items have which tags because item/tag
assignments are not collected.

### 20 - Organization-wide and public sharing

[Open notebook](20_monitor_broad_sharing.ipynb).
Use it to inspect artifact exposure observations for organization-wide and
publish-to-web sharing. It writes `organization_shares`,
`publish_to_web_shares` and shared coverage. Links are not verified live, access
is not exhaustive, and link URLs and sharer names/emails are excluded.

### 21 - Deployment pipelines and operations

[Open notebook](21_monitor_deployment_pipelines.ipynb).
Use it to inspect discovered pipelines, history-poll outcomes, operation status
and execution timing. It writes `deployment_pipelines`,
`deployment_operation_resources`, `deployment_operations` and shared coverage.
Discovery is caller-visible; history requires pipeline Admin and exposes up to
20 recent deployments. Failed counts are null, healthy empty counts zero.
This notebook never triggers a deployment.

### 22 - Data Factory pipeline activity (optional)

[Open notebook](22_monitor_pipeline_activity.ipynb).
Use it to inspect reported activity status, timing, row/byte metrics and native
throughput in retained `fabricpipelineactivityruns` captures. It publishes
`pipeline_activity_resources` and `pipeline_activity_observations`, with query
windows, mode, configured scope and source provenance.

The coverage preview distinguishes inventory, job history and activity queries.
An empty job list means no run IDs were returned; it is **not** a successful
zero-activity query. Failed/missing/unfinished evidence has unknown counts.
The activity preview selects the latest configured scope in each mode and the
latest query attempt before admitting metrics, without fallback after a failed
or empty query. `ACTIVITY_SOURCE_PATH` selects an explicit historical query.
Do not add repeated polls, throughput rates or chained activity counts together
as distinct end-to-end movement. Missing values stay null.

No collection API calls, workload execution or permissions are added. Notebook
03 still handles item jobs; 04 handles references; 21 handles deployments.
To include 22 in `nb_orchestrator`, import it and set
`INCLUDE_PIPELINE_ACTIVITY = True`; its default remains False.

## Validate the scope you actually published

| Scope in 06 | Required published writers | Table count |
|---|---|---|
| All inclusion flags false | 01-04 | 10 |
| `INCLUDE_ESTATE_TABLES = True`, module flag false | 01-04 and 07-11 | 25 |
| `INCLUDE_MODULE_TABLES = True` | 01-04 and 07-21 | 48 |
| Add `INCLUDE_PIPELINE_ACTIVITY_TABLES = True` to any scope above | Also publish 22 | Adds 2 (12, 27 or 50 total) |

For the previous full suite, `INCLUDE_MODULE_TABLES = True` implies estate tables.
For all 50 datasets, also enable `INCLUDE_PIPELINE_ACTIVITY_TABLES`.
`INCLUDE_SHORTCUTS` adds raw shortcut evidence to any selected scope without
changing table counts. Match the writers' value and use a new baseline when it
changes; older baselines remain valid for shortcut-disabled comparisons.
The same applies independently to `INCLUDE_EVENTSTREAM_TOPOLOGY`: match writer
and validator values, use a new baseline after a change, and do not add datasets.
Then perform this experiment:

1. Keep collectors and other writers idle. Set `VALIDATION_ACTION = "capture"`
   and a new `BASELINE_NAME`, with the same raw root, prefix and permission mode.
2. Run 06 to create `Files/monitor_validation/<BASELINE_NAME>`.
3. Rerun the transformation notebooks in the selected scope with unchanged
   inputs/settings and writes enabled, one at a time.
4. Set `VALIDATION_ACTION = "compare"` and rerun 06 with the same baseline.

A different source/table selection is `NOT_COMPARABLE`, not PASS. Unavailable
historic Delta data is `UNVERIFIED`; do not vacuum or change retention during the
experiment. Capture a new name for a new scope rather than overwriting a baseline.

## Common questions and troubleshooting

| Symptom or question | Meaning and action |
|---|---|
| A domain shows NOT COLLECTED or an empty table | Verify the module was enabled, authorized and produced the expected raw files. Notebook success is not collection success. |
| 05 reports a missing table | Publish 01-04 with the same default Lakehouse/prefix. Preview mode does not create their tables. |
| Existing table ownership/schema/content is rejected | Confirm the destination and provenance. Do not drop tables, edit hashes or weaken checks; isolate an intentional new contract with a new supported prefix. |
| Historical manifests are invalid or timestamp-inverted | Preserve the warning and raw evidence. Validate future collector clock/persistence behavior; do not rewrite history to force a successful load. |
| Counts increase between daily snapshots | These are retained observations. Select the intended scope/source/date and business grain before comparing current inventory or KPIs. |
| Schema or membership is missing | Review the domain's collection limits and permissions. Missing is not an empty model, empty group or effective denial. |
| API 429s or token expiry appear in collector logs | The analytics notebooks do not make those API calls. See [retry/authentication behavior](../docs/configuration-reference.md#throttling-and-retries). |
| Can these notebooks stream to Splunk? | Not currently. A separate publisher is proposed; see [integration options](../docs/analytics-integration.md). |

## Acceptance and maintenance

Local tests validate pure transformations, offline collector compatibility,
standalone generated code, write guards and notebook format. They do not execute
Fabric Spark/Delta/charts or establish private-only connectivity. Initial 01-05
execution was operator-reported successful; expanded runtime, parity, rerun and
network acceptance remain separate checks.

Review representative raw-to-curated results, missing/empty/failed coverage,
privacy/access controls, execution identity, retention and capacity costs before
scheduling. There is no automatic collector/notebook scheduling setup here.

The `.py` sources are maintained implementations; `.ipynb` files are generated
upload artifacts with cleared outputs. Follow the
[development instructions](README.md#development) to regenerate them. Do not
edit embedded generated code, commit executed outputs or publish raw/curated
metadata outside its approved customer scope.
