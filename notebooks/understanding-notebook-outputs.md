# Understanding the Monitor notebook outputs

This guide explains the **21 numbered Monitor notebooks**: what their outputs
mean, what you should learn from them, and how they relate to each other.
It describes the implemented outputs, not a review of your latest live results.
The older `activity.ipynb`, `catalog.ipynb`, `Deconstruct.ipynb` and `nbk.ipynb`
are preserved in [archive/](archive/). They are experiments, not additional steps
in this suite.

## 1. The main idea: different views of the same estate

Think of the notebooks as different pages in an estate investigation:

| Question | Notebooks |
|---|---|
| What did we collect, and can we trust the coverage? | 01, each domain's coverage output, 06 |
| What workspaces, items and model structures did we observe? | 01, 08 |
| Who has observed access, and what governance rules surround it? | 02, 14, 15, 16, 20 |
| What activity, jobs and refreshes did we observe? | 03, 07, 11 |
| What depends on what, and how does it connect? | 04, 09, 10 |
| How is the estate organized, published and managed? | 12, 17, 18, 19, 21 |
| What capacity and performance evidence is available? | 13 |
| How can I see the core results together? | 05 |
| Does rerunning the transformations leave unchanged data unchanged? | 06 |

These are **analytics notebooks, not collectors**. They read previously saved
Monitor files. Running one does not contact the collection APIs, turn on a
collector, grant access or make old evidence fresh.

```text
Monitor collectors
       |
       v
Raw JSON files in Lakehouse Files
       |
       +--> 01-04: core inventory, health, permissions, jobs and lineage
       |
       +--> 07-21: additional domain tables and their own previews/charts
                      |
                      v
              Curated Delta tables
                      |
                      +--> 05: reads the core tables from 01-04
                      |
                      +--> 06: validates the selected table scope
```

**07-21 do not depend on running each preceding notebook.** Each transforms its
own raw sources. Notebook 05 is not an all-21-notebook dashboard; the additional
domains have their own displays.

## 2. How to read any notebook result

### There are three different kinds of output

| Output | Meaning |
|---|---|
| Printed counts, grouped tables and charts | A summary of the evidence being analyzed. They are not automatically counts of today's unique resources. |
| Published Delta tables | Reusable historical observations in Lakehouse Tables. Most notebooks write these only when `WRITE_TABLES = True`. |
| Coverage messages and diagnostics | Evidence about what was available, missing, failed, incomplete or rejected. Read these before drawing conclusions from the business rows. |

The default table prefix is `monitor_`. For example, `inventory` below means
`monitor_inventory` with the default configuration.

With `WRITE_TABLES = False`, the transformation notebooks show previews but do
not persist their tables. They can still show useful results even when notebook
05 has nothing to read yet.

A printed result such as:

```text
{'job_resources': 20, 'job_observations': 80}
```

means the transformation produced those numbers of observations from its input.
It does **not** mean 80 jobs were newly inserted on that execution. On an
unchanged-input rerun, those observations may all already exist.

### A row usually means an observation, not a unique object

Suppose the same pipeline appears in Monday's and Tuesday's catalog files.
The curated history can contain two observations of that pipeline.

Suppose a job is seen as `Running`, then later as `Completed`.
Those are two observations of one job, not two jobs.

Reprocessing the **same saved evidence** does not insert it again: the writers
use an insert-only Delta merge on `observation_id`. Collecting another snapshot
can legitimately create another observation of an unchanged object. Existing
observations are not updated into a single current-state row.

**For a current-style report, select the appropriate snapshot/cycle and business
identity first. Do not count all historical rows as today's estate.**

### Coverage tells you how strong the answer is

| Result or label | How to interpret it |
|---|---|
| `success` | The relevant resource/evidence passed its checks. Still inspect its scope and age. |
| Successful resource with zero records | The collection succeeded and returned nothing for that resource. This is a known empty result. |
| `NOT COLLECTED` or missing evidence | We do not have the evidence needed to answer. It is not a successful zero. |
| Failed resource or null record count | Its contents are unknown. Do not interpret it as no grants, no jobs or no operations. |
| `unfinished` | The saved run did not establish completed evidence. |
| `invalid` | Evidence failed structural/integrity checks; it is not admitted as usable business facts. |
| `legacy_unverified` | Older snapshot files lack immutable completion evidence and an exact collection time. Useful history, but not proof of a complete current snapshot. |
| Stale or unknown freshness | The retained facts may be old, or their exact observation time is unavailable. |

For legacy files, `source_date` is the folder date, **not an exact collection
timestamp**. An event's time, a job's start time and a file's collection time
are different concepts.

Before collecting or assessing new capacity results, ensure all monitored
tenant capacities are turned on.

## 3. Notebook-by-notebook interpretation

### 01 - Inventory and collection health

**Question:** What resources did we observe, and what happened during collection?

**Tables:** `inventory`, `collection_health`.

The preview groups collection observations by module and coverage status, then
inventory observations by source, item type and coverage status.

Read this as two separate answers:

- Inventory tells you what appeared in the saved workspace/item evidence.
- Health tells you where collection was successful, missing, unfinished or invalid.

**What to understand:** A notebook can run successfully while reporting failed
collection. That is a useful diagnostic result, not a contradiction. Daily
workspace/item inventory remains legacy-unverified; its presence alone does not
prove tenant completeness.

**Connection:** Use this as the opening coverage check for 02-05. Notebook 08
provides a richer catalog and semantic-model structure; do not add its inventory
counts to 01 as though they describe different resources.

### 02 - Scoped and Tenant permissions

**Question:** What item-access assignments were observed, and which targets
could we actually inspect?

| Table | What a row represents |
|---|---|
| `permission_cycles` | A linked collection-cycle tip, with chain validity and completion/health information. |
| `permission_resources` | A discovery/access resource outcome within a collection slice. |
| `permission_grants` | An observed principal/access-detail assignment, including permission lists. |

The preview prints the selected mode/cycle and groups its resource outcomes.
`cycle_finished = true` means the cycle finished processing its scope;
it does not imply `cycle_healthy = true`.

**What to understand:** Evaluate grants together with successful and failed
targets. For example, 95 successful targets out of 101 means the other six have
unknown access, not no access. A grant row can contain multiple permissions;
permission-assignment counts are not necessarily unique people or grant rows.

Scoped and Tenant evidence are separate. Selecting one does not fill its gaps
from the other, and old cycles must not be unioned into a current access list.
The preview mode selects a view; it is not a switch that enables collection.

**Connection:** 15 adds workspace roles; 14 provides directory/group context;
20 adds broad-sharing evidence. None alone, or automatically combined, computes
a person's effective access.

### 03 - Fabric item job history

**Question:** What jobs did we observe running against collected Fabric items?

**Tables:** `job_resources` records item-poll outcomes;
`job_observations` records the jobs returned.

The preview groups resource coverage and shows the latest retained status for
each workspace/item/job identity, grouped by item type and status.

**What to understand:** A retained `Running` status means that was the last
observed state, not necessarily that the job is running now. Check the latest
poll outcome and observation time. No returned jobs from a successful poll is
different from a failed poll. Missing or inverted timing leaves duration unknown.

**Connection:** Join to item context in 08. Compare with 04 when investigating
what a pipeline may depend on, but a successful job does not verify each lineage
edge. Notebook 11 covers semantic-model refreshes separately.

### 04 - Scanner and static lineage

**Question:** What upstream/downstream relationships were reported or inferred?

| Table | Meaning |
|---|---|
| `lineage_resources` | Which items/evidence were inspected, including successful zero-edge observations. |
| `lineage_edges` | Directional relationships and their evidence/resolution details. |
| `lineage_diagnostics` | Reasons some static references could not be resolved or supported. |

The preview groups resources by evidence/coverage, edges by evidence/direction/
related type, and diagnostics by reason.

**What to understand:** Scanner relationships and `static_inference` are
different evidence types. A pipeline definition referencing a notebook is
configuration evidence, not proof it executed that notebook. Dynamic expressions
can remain unresolved rather than becoming guessed edges. No edges without
successful coverage is not proof of no dependencies.

The curated output contains normalized references and diagnostics, **not copies
of notebook code or pipeline JSON**. Exported definitions remain raw evidence.

**Connection:** 08 supplies item/model context; 03 supplies separate execution
observations; 05 draws a bounded graph from selected lineage evidence.

### 05 - Core visualizations

**Question:** What do the published core results look like together?

**Tables written:** None. This notebook reads the outputs of 01-04.

| Display | What it tells you |
|---|---|
| Latest module health/freshness | How recent the latest selected collection observation is and its coverage status. |
| Retained coverage and inventory charts | Distribution of historical observations, not current unique inventory. |
| Selected permission-cycle coverage and assignments | Which item targets were inspected and which permission values were observed in the selected mode/cycle. |
| Latest retained job statuses/durations and poll coverage | What was last seen for each job, alongside whether item polling succeeded. |
| Lineage coverage, evidence, diagnostics and directed graph | Selected relationships and uncertainty, not runtime data flow. |

**What to understand:** Start with health, then interpret the charts. The
default permission selection is the latest attempt, not a silent fallback to
the last healthy cycle. Unknown-time cycle evidence can prevent automatic
selection.

The graph defaults to at most 40 edges and labels truncation. Blue edges are
scanner relationships; orange edges are potential static references.
Successful newer zero-edge evidence removes older edges from the selected view.
Failed latest evidence does not silently fall back to older edges. Invalid or
unfinished lineage evidence can block automatic selection; an explicitly chosen
historical source is a historical view, not a current graph.

**Connection:** This is the core presentation layer, not a dashboard for all
48 datasets. Use 07-21 for their additional domain displays.

### 06 - Persistent rerun validation

**Question:** If I transform exactly the same evidence again, do the curated
contents remain exactly the same?

**Outputs:** Per-table metrics, coverage/freshness summaries, a saved
metadata-only baseline in capture mode, and comparison checks in compare mode.
It writes no curated business table.

Read the metrics as follows: `rows` should equal `unique_ids`, and
`invalid_metadata_rows` should be zero. Table IDs and Delta versions identify
what was inspected; row counts alone are not the complete rerun test.

| Comparison status | Meaning |
|---|---|
| `PASS` | The relevant unchanged-input comparison passed. |
| `FAIL` | A comparable check found a change that should not have occurred. |
| `NOT_COMPARABLE` | Evidence or selected scope/settings changed, so this is not the same experiment. |
| `UNVERIFIED` | Required historical Delta evidence was unavailable, so equality could not be proved. |

**What to understand:** PASS means rerun stability. It does not mean collection
is complete, fresh, accurate against the source system or accepted in a private
network. Empty tables can pass stability checks.

Capture a new baseline, rerun the selected writers with unchanged input, then
compare against that baseline. Baselines are never overwritten; retain the
Delta history needed for comparison.

**Connection:** Default scope is the 10 core tables. Enabling
`INCLUDE_ESTATE_TABLES` covers 25 tables after 07-11 are published.
`INCLUDE_MODULE_TABLES` covers all 48 after 07-21 are published.

### 07 - Activity and audit events

**Question:** What operations were recorded, in which workloads and on which days?

**Tables:** `activity_events`, shared `estate_coverage`.

The outputs include operation counts, workload/operation summaries with distinct
known event IDs and pseudonymous actors, and counts by event date.

**What to understand:** This is recorded Power BI activity evidence, not every
Fabric/Azure audit log. Observation counts can include the same event in multiple
retained files. Distinct known event IDs help distinguish events from observations.
Actor keys are pseudonyms, not anonymous people.

**Connection:** Workspace/item IDs can add activity context to 08 and guide an
investigation into 03 or 11. An activity event is not automatically a matching
job run; identity and timing need explicit reconciliation.

### 08 - Estate catalog and semantic-model schema

**Question:** What was observed in the estate, and what structure was returned
inside semantic models?

**Tables:** `catalog_workspaces`, `catalog_items`, `catalog_models`,
`model_tables`, `model_columns`, `model_measures`, `model_relationships`,
plus `estate_coverage`.

Displays show item types, model-schema availability, column types and bounded
samples of models, columns, measures and relationships.

**What to understand:** This is the main descriptive context for the other
notebooks. A model's `schema_coverage` distinguishes unavailable schema from
returned schema; missing tables are not proof of an empty model.
`expression_returned` records whether a measure expression was present, not the
expression itself. Lakehouse/Warehouse items do not imply their physical schemas
were discovered.

**Connection:** Workspace/item IDs link inventory context to permissions, jobs,
refreshes and lineage. `capacity_id` in workspace observations relates to 13.
Model relationships here are relationships **inside a semantic model**; lineage
in 04 concerns dependencies between items/references.

### 09 - Fabric connections

**Question:** What caller-visible connections and connectivity/privacy metadata
were collected?

**Tables:** `connection_observations`, `estate_coverage`.

Displays show connection types, connectivity/privacy combinations, distinct
connection IDs associated with each gateway, and a metadata sample.

**What to understand:** A connection is configuration evidence, not proof that
it currently works. Visibility is limited to the collection identity, not
guaranteed tenant completeness. Credentials and connection paths are excluded.
Failed or unfinished evidence does not produce usable connection facts.

**Connection:** `gateway_id` can connect this output to 10. Do not assume every
connection maps to a collected datasource or that this output identifies every
item using that connection; those relationships must be evidenced separately.

### 10 - Gateways and datasources

**Question:** What gateways/datasources were observed, and what connectivity
responses were saved?

**Tables:** `gateway_observations`, `gateway_datasources`, `gateway_status`,
`estate_coverage`.

Displays summarize datasource types, connectivity observations and status codes,
then show gateway/datasource samples. Missing expected files are called out.

**What to understand:** Inventory, returned datasource detail and saved status
are separate pieces of evidence. A saved successful status is not a live
connectivity test. Missing status is unknown, not healthy.

**Connection:** Use gateway IDs with 09 and gateway/datasource IDs within 10.
Compare timing with refresh problems in 11, but a coincident gateway warning
does not establish the cause of a refresh failure.

### 11 - Dataset refresh history

**Question:** What semantic-model refresh outcomes, timings and failures were
observed?

**Tables:** `refresh_observations`, `refreshable_observations`,
`estate_coverage`.

Displays summarize refresh status/type, distinct known refresh identities,
mean known durations, schedule-enabled inventory and reported failures.
Failure-code summaries help locate affected workspace/model identities.

**What to understand:** Repeated API history windows can repeat the same
refresh across observations. The displayed average is observation-based, not
automatically a deduplicated per-run KPI. Reported refreshable failure totals
must not be added across snapshots as new incidents.

Ongoing or invalid timing produces unknown durations. History windows and
polling gaps prevent claims of exhaustive refresh history.

**Connection:** Use workspace/item IDs with semantic models in 08 and capacity
context in 13. This is not the same dataset as Fabric item jobs in 03.

### 12 - Published apps

**Question:** Which published apps and owning workspace IDs were observed?

**Tables:** `apps`, `estate_coverage`.

The chart counts retained app observations by workspace; the metadata sample
includes app IDs, names, workspace references and update times.

**What to understand:** An app is a distribution artifact, not proof of an
audience, user entitlement or complete pagination.

**Connection:** Workspace IDs supply context from 08 and roles from 15.
App inventory does not supply audience memberships for an access calculation.

### 13 - Capacity inventory and performance

**Question:** What capacity configuration and utilization/carryover evidence
were collected?

**Tables:** `capacities`, `capacity_metric_observations`, `estate_coverage`.

Outputs include capacity observations by SKU, capacity/metric samples, grouped
metric counts/known values/means, and a bounded timepoint chart.
The timepoint chart selects one capacity, metric group, metric, query day and
source date; it is not an automatically combined estate-wide view.

**What to understand:** Capacity inventory can exist without metrics because
metrics extraction is opt-in. Provider values are unscaled; interpret their
units before treating a fraction as a displayed percentage. A timezone-free
timepoint has unknown UTC. Snapshot means and overlapping metric observations
are not ready-made capacity KPIs.

**Connection:** Capacity IDs relate to workspaces in 08 and refreshable context
in 11. Use timing to investigate activity or job/refresh slowdowns, but correlation
does not prove a capacity issue caused a particular failure.

### 14 - Directory and licensing

**Question:** What user/group, membership and licensing evidence is available?

**Tables:** `directory_users`, `directory_groups`, `group_memberships`,
`user_licenses`, `subscribed_skus`, `estate_coverage`.

The chart groups user observations by user type. Metadata samples expose account
state, group attributes, user-to-group membership, user-to-SKU assignments and
subscribed SKU quantities.

**What to understand:** These are different views: an account, its observed
memberships, its assigned licenses and the tenant's SKU quantities. Missing
quantities are not zero. Groups are optional and membership extraction can be
capped. Membership represents transitive users, not direct group nesting.

**Connection:** Principal/group IDs provide context for 02, 15 and 16;
SKU IDs relate user licenses to subscribed SKUs. Matching IDs alone does not
compute effective authorization or establish complete membership. Joinable
identifiers remain sensitive even though names, UPNs and mail are excluded.

### 15 - Workspace roles

**Question:** What workspace-level assignments were returned?

**Tables:** `workspace_role_scopes`, `workspace_role_assignments`,
`estate_coverage`.

The chart groups role observations. Scope rows show whether a workspace's role
list was returned and its known assignment count; assignment rows identify
observed principals and workspace roles.

**What to understand:** A returned empty list is different from missing/null
users. Read scope rows before concluding that a workspace has no assignments.
These are workspace roles, not item-specific grants.

**Connection:** 02 adds item permissions; 14 adds identity context; 08 supplies
workspace metadata. Do not add all three row counts to get a number of people
with access.

### 16 - Tenant and delegated settings

**Question:** What policy settings and scoped overrides were observed?

**Tables:** `tenant_settings`, `delegated_setting_scopes`,
`delegated_setting_overrides`, `tenant_setting_groups`, `estate_coverage`.

The chart groups tenant setting observations by enabled state. Metadata samples
show individual settings, whether delegated settings were returned, override
values/origins, and enabled/excluded security-group rules.

**What to understand:** A tenant setting and a capacity/domain/workspace
override are different scopes, not conflicting duplicate rows. A missing override
collection is unknown. The notebook does not calculate precedence or effective
policy for a user.

**Connection:** Group IDs relate to 14; scope entity IDs can relate to capacity,
domain and workspace context in 13, 17 and 08. Use `scope_type` as well as the
entity ID when interpreting an override.

### 17 - Domains and workspace associations

**Question:** How were observed workspaces organized into domains?

**Tables:** `domains`, `domain_workspaces`, `estate_coverage`.

The chart groups workspace-association observations by domain; metadata samples
show domains, parent references and workspace associations.

**What to understand:** An association describes organization, not a permission
grant. The collector omits domains without workspaces, so this is not a complete
domain inventory. Counts across historical snapshots are not today's workspace
counts.

**Connection:** Workspace IDs relate to 08; domain IDs contextualize settings in
16 and domain-scoped tag definitions in 19.

### 18 - Workspace Git connections

**Question:** What Git integration metadata was returned for workspaces?

**Tables:** `workspace_git_connections`, `estate_coverage`.

The chart groups connection states. Metadata samples include provider,
repository/branch details and returned sync times.

**What to understand:** A saved connection state or sync time is not proof
that a workspace is currently synchronized. This output does not read code,
compare commits or detect source changes. Owner/directory values are hashed;
remaining repository metadata can still be sensitive.

**Connection:** Workspace IDs connect to 08 and 15. Git integration and
deployment pipeline operations in 21 are separate lifecycle evidence, not an
automatically reconstructed end-to-end release history.

### 19 - Tag definitions

**Question:** What tags were defined, and were they tenant- or domain-scoped?

**Tables:** `tags`, `estate_coverage`.

The chart groups tag observations by scope; metadata samples show tag IDs,
names and domain references where applicable.

**What to understand:** This is a tag dictionary, **not item tagging**.
It cannot tell you which notebooks, models or reports have a tag because those
assignments are not collected.

**Connection:** Domain scope relates to 17. There is no collected item/tag bridge
that lets you assign these tags to the items in 08.

### 20 - Organization-wide and public sharing

**Question:** What broad-exposure observations were collected for artifacts?

**Tables:** `organization_shares`, `publish_to_web_shares`, `estate_coverage`.

Separate charts group organization-wide and publish-to-web observations by
artifact type. Metadata samples show artifact identity, access right and share
type.

**What to understand:** Organization-wide sharing and public publication are
different exposures. Treat these as review candidates, not a complete effective
access list or confirmation that a link works now. Link URLs and sharer names/
emails are excluded.

**Connection:** Where artifact identity/type can be reconciled to catalog items,
08 adds context. Keep sharing separate from the item grants in 02 and workspace
roles in 15; do not expect those outputs to be interchangeable.

### 21 - Deployment pipelines and operations

**Question:** What deployment pipelines and deployment-operation outcomes were
observed?

**Tables:** `deployment_pipelines`, `deployment_operation_resources`,
`deployment_operations`, `estate_coverage`.

The chart uses the latest retained status per pipeline/operation identity.
Metadata samples distinguish discovered pipelines, history-poll outcomes and
operation status/timing/source-stage/target-stage details.

**What to understand:** A visible pipeline with failed history collection is
different from a successful empty history. Discovery is caller-visible; history
requires pipeline Admin and exposes up to 20 recent deployments. Retained polls
cannot recover operations missed outside that window.

**Connection:** This concerns **deployment between stages**, not Data Factory
data-processing pipelines. Data Factory pipeline jobs belong with 03; static
Data Factory definition references belong with 04. This notebook does not trigger
deployments or provide a complete deployed-item/stage-to-workspace mapping.

## 4. How to relate the outputs without creating misleading totals

### Shared identifiers are the connecting tissue

These are possible analytical relationships, not automatically created foreign
keys or a prebuilt semantic model.

| Identifier/context | Useful connections | Caution |
|---|---|---|
| `workspace_id` | 08 catalog to item context in 02/03/04/07/11, apps in 12, roles in 15, domains in 17 and Git in 18 | Align snapshots and scope; an old workspace row is not proof of its current state. |
| `workspace_id` + `item_id` | Catalog item to grants, jobs, refreshes and queried lineage item | Item type and source visibility still matter; not every item exists in every collection. |
| Related workspace/item IDs | Lineage edge in 04 to referenced item context in 08 | Some edges have only unresolved/external references, not joinable item IDs. |
| `principal_id` / `group_id` | Grants/roles/settings to directory and membership context in 14 | Preserve principal type, membership limits and observation scope; not an effective-access calculation. |
| `capacity_id` | Workspace catalog/refreshable inventory to capacities and metrics | Align the observed assignment and metric time window. |
| `gateway_id` / `datasource_id` | 09 connections to 10 gateways; datasource detail to status within 10 | Does not establish every consuming item or live connectivity. |
| `domain_id` | Domains, workspace associations, domain settings and tag scope | Tag scope does not mean an item has that tag. |
| `pipeline_id` + `operation_id` | Deployment history outcomes and operation observations in 21 | Not a Data Factory pipeline/job identity. |
| `source_path`, run/cycle IDs and observation time | Trace a curated fact back to its evidence and collection context | An observation ID identifies a particular observation, not the business object across time. |

**Select the relevant history before joining.** Joining all catalog snapshots to
all permission snapshots by workspace/item alone can multiply rows. Joining one
grant to several group-membership observations can multiply them again. A larger
join result does not mean more items, grants or people.

Permission evidence should preserve its selected mode/cycle/resource provenance.
Other datasets need their appropriate source/date/time selection. Do not invent
an exact common timestamp when a source has only a legacy folder date.

### Example: investigating a failed Data Factory pipeline

This is an illustrative investigation, not a statement about your latest data.

1. **01 and the relevant coverage outputs:** establish which evidence is usable
   and how old it is.
2. **08:** identify the workspace and pipeline item.
3. **03:** inspect the latest retained job status, timing and item-poll outcome.
4. **04:** inspect saved definition references, such as a notebook the pipeline
   is configured to invoke. Keep unresolved expressions visible.
5. **13:** inspect capacity evidence for an applicable time window, if collected.
6. **09/10:** review connection/gateway evidence where an actual relationship is
   available; do not assume one from a similar name.
7. **02/15/14:** review observed access and identity context if authorization is
   a plausible investigation path.

These outputs build context. They do not automatically prove the root cause.
Notebook 21 is not the pipeline's run history, and notebook 11 is relevant only
to semantic-model refresh evidence, not a replacement for its jobs.

### Example: reviewing access to a semantic model

Start with the model identity in **08**, item grants and failed-target coverage
in **02**, workspace roles and returned-list coverage in **15**, directory/group
context in **14**, broad sharing in **20**, and applicable settings in **16**.

The combined conclusion is: "Here are the access-related observations and gaps."
It is not automatically: "Here is every person who can access the model."

## 5. Collection scope and non-Admin API boundaries

The notebooks add **no new API calls or permissions**. Their limits come from
the original collectors. Tenant Admin discovery does not confer every other
resource permission.

| Evidence | Scope/authorization boundary to keep visible |
|---|---|
| Item definition references used by 04 | Definitions come from non-Admin export APIs requiring item read/write access, commonly workspace Contributor or higher. Discovery visibility alone is insufficient. Supported static parsing is not exhaustive runtime lineage. |
| Fabric item job history in 03 | Non-Admin resource history requires resource access and configured collection targets. It is bounded recent history, not every historical tenant job. |
| Connections in 09 | Non-Admin caller-visible connection inventory, not tenant-wide Admin inventory. |
| Gateway evidence in 10 | Resource/caller visibility does not establish tenant completeness or guaranteed VNet gateway coverage. |
| Directory/licensing in 14 | Microsoft Graph evidence has its own consent, visibility and optional/capped membership collection; it is not Power BI/Fabric Admin inventory. |
| Capacity metric evidence in 13 | Optional Metrics-app extraction has separate availability/access requirements; capacity inventory alone does not supply metrics. |
| Deployment evidence in 21 | Non-Admin caller-visible discovery; operation history requires pipeline Admin and is limited to the recent window. |

This is an interpretation summary, not an exhaustive permissions matrix.
Use the [collector configuration reference](../docs/configuration-reference.md)
for collector-specific permissions, collection boundaries and opt-in settings.
No notebook widens the scope of the evidence already collected.

## 6. A practical reading and run order

1. Preview **01** and the domain notebooks you need. Read coverage before counts.
2. For core investigation, preview **02-04**; for richer context use **08** and
   the applicable domain notebooks.
3. Publish the chosen transformations with `WRITE_TABLES = True` after checking
   the Lakehouse, prefix and evidence. Run writers sequentially; multiple
   notebooks share `estate_coverage`.
4. Run **05** after publishing 01-04. Read the other domains' own charts rather
   than expecting them in 05.
5. Run **06** after publishing every writer in the selected validation scope:
   capture, unchanged-input rerun, compare.

The most useful summary of any result is:

> We observed **what**, for **which resources and scope**, at **what trustworthy
> time**, with **which collection gaps**?

If you cannot answer those four parts, the chart is a starting point for
investigation, not a reliable current-state total.

## References

- [Notebook walkthrough and operator runbook](notebook-guide.md)
- [Table contracts, coverage and validation reference](README.md)
- [Analytics integration options and implementation status](../docs/analytics-integration.md)

Implementation sources for these descriptions: `build_monitor_notebooks.py`,
`monitor_fabric_runtime.py`, `monitor_visualizations.py`,
`monitor_estate_analytics.py`, `monitor_module_analytics.py`,
`monitor_analytics.py` and `monitor_validation.py`.
