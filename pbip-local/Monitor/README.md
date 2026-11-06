# Fabric Estate Atlas

A new, data-led report over `FabricMonitor / lh_monitor`, built independently of
the other PBIP projects. It uses all 48 curated Monitor datasets and 20 separate
report lookup/context Delta tables. It does not collect API data or change the
48 curated source tables.

## Open the report

1. Close the previous Desktop session and open **Monitor.pbip** in a current
   Power BI Desktop version with PBIP/Direct Lake support.
2. Direct Lake cannot run in Desktop's local Analysis Services engine.
   When prompted for remote modeling, **create a new private semantic model**
   in the intended Fabric workspace, for example `Fabric Estate Atlas - Explore`.
   Do not select an existing shared model: Desktop can overwrite its definition.
3. Use your approved Fabric identity with source Lakehouse access, permission to
   create/write the remote model, an appropriate license, and required capacity
   XMLA read/write settings. The Python profiling credentials are not embedded
   in the PBIP or used automatically by Desktop.
4. Configure the OneLake connection/credentials if prompted, refresh/reframe the
   model, and start with **01 Estate** and **02 Confidence**.
5. On Access, choose exactly one permission mode. On Capacity, choose one metric
   and one source-folder date. On Licensing, select one source-folder date for
   unit totals.

No existing remote model was paired automatically, no semantic model/report was
deployed to Fabric by these tools, and no existing remote model was overwritten.
The approved 20 `monitor_report_*` tables have been materialized in `lh_monitor`.
No Git commit, new grant or schedule was created.

Microsoft references:
[Direct Lake with PBIP](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-power-bi-project),
[Desktop live editing and requirements](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-power-bi-desktop).

### Desktop source-evaluation troubleshooting

Desktop reported `Query Evaluation failed for query: DirectLake - Fabric Estate`
with the parameter-composed source URL. The existing exploration model contained
all 73 tables and successfully completed a Fabric-side Direct Lake framing refresh.
The source now uses the identical literal OneLake URL as a Desktop compatibility
workaround; whether this resolves Desktop evaluation still requires verification.
The generator uses the same literal form. No tables, relationships or measures
were changed by this workaround.

Close Desktop without saving before applying external file changes, then reopen
the PBIP. For the existing exploration model, confirm **Fabric Estate Atlas -
Explore** in **FabricMonitor** before choosing to overwrite its definition.
Cancel if a different/shared model is selected. Closing without saving does not
roll back remote-model edits, and Desktop may already have updated local metadata.

## Pages

| Page | Questions |
|---|---|
| 01 Estate | What evidence exists, what assets were observed, and which datasets have no rows? |
| 02 Confidence | How old is the evidence? Which outcomes are failed, partial, invalid or legacy-unverified? |
| 03 Workspaces | What workspace/item metadata is retained, and where does it come from? |
| 04 Access | What grants were observed, and which permission polls failed or deferred? |
| 05 Activity | Which operations/workloads appear in the collected event history? |
| 06 Reliability | Did polling return jobs, or are successful-empty polls distinct from missing refresh collection? |
| 07 Capacity | What historic provider metrics exist, over which query days and units? |
| 08 Connectivity | What connections are caller-visible, and what gateway evidence is actually available? |
| 09 Schema | What semantic-model tables, columns and measures did the scanner return? |
| 10 Lineage | What upstream/downstream links are observed, inferred or unresolved? |
| 11 Governance | What tenant settings and group rules were retained? |
| 12 Licensing | What directory and license evidence was collected? |
| 13 Change | What Git and deployment evidence exists? |
| 14 Organization | What app/domain/tag/sharing questions remain unanswered by missing collection? |
| Workspace detail | Hidden drillthrough target: right-click a Workspace Entity ID in page 03's evidence table |

There are 14 visible pages plus the workspace drillthrough page. Source data
and report metadata, rather than other reports, determine this layout.

## What the actual data showed

The initial read-only profile is recorded in `analysis/data-profile.json`,
including individual source Delta versions:

- 55,683 retained observations, 27 nonempty datasets and 21 datasets with no rows.
- Repeated historical entity IDs, but globally unique observation IDs.
- Failed/deferred permission polling; successful polls do not establish complete
  tenant-wide or effective access.
- 267 successful scoped job polls returning no job records.
- Capacity query dates only October 14-15, 2026 in that profile.
- Many legacy observations have no exact collection timestamp, even where an
  event/provider date or source-folder day exists.

These are dated profiling results, not promises about later Lakehouse contents.
The report exposes dates/coverage instead of treating absent observations as a
healthy or empty estate.

## Model and interpretation

The model has 73 Direct Lake tables, 73 single-direction relationships and 91
explicit measures. Raw numeric columns do not implicitly sum.

The unique Observation Context table connects each source row by observation ID
to contextual workspace/item/capacity/gateway/principal and other lookup keys.
This avoids many-to-many joins between repeated snapshots. Item identities
include their workspace; unresolved related workspaces are not guessed.
Source and related-item/workspace roles use separate model tables.

Collection Date, Source Folder Date, Event Date and Metric Query Date are
separate date roles. A legacy partition day never becomes an exact collection
time. Permission Mode directly filters only the three permission tables, not
unrelated workspace-role facts.

Names are retained descriptive labels, not authoritative current or historical
renaming/membership facts. Counts are observed resources or retained
observations, not certified current inventory. There is no implicit deletion
inference, effective-access engine, all-service audit completeness, physical
Lakehouse/Warehouse schema discovery, runtime-lineage proof or policy-precedence
calculation.

Principal IDs, actor pseudonyms, repository metadata and source paths can still
be sensitive. No credentials, actor names/UPNs/IPs, raw connection details or
expression text are introduced. Validate audiences, OneLake permissions,
RLS/OLS requirements and export policy before sharing.

## Refresh the reporting layer

The 20 lookup tables are derived reporting data, not replacements for the
immutable source datasets or notebook-06 baselines. Refresh them after the
curation notebooks finish, with collectors/curated writers idle:

```bash
# Run from the repository root; keep the row cache in private local storage.
.venv/bin/python pbip-local/Monitor/tools/profile_lakehouse.py \
  --cache-dir /private/path/fabric-estate-cache \
  --output pbip-local/Monitor/analysis/data-profile.json
.venv/bin/python pbip-local/Monitor/tools/refresh_report_lookups.py \
  --cache-dir /private/path/fabric-estate-cache
# After reviewing the preview:
.venv/bin/python pbip-local/Monitor/tools/refresh_report_lookups.py \
  --cache-dir /private/path/fabric-estate-cache --publish
```

The tools use the already configured `COMMERCIAL_*` environment credentials or
an authorized Azure CLI login. No secrets belong in these files. The profiling
reader uses Delta-native query execution so deletion vectors are respected;
plain Parquet scans are not an equivalent substitute.

Cache hashes and all 48 source versions are checked before publication. Only
owned `monitor_report_*` tables are replaceable; ownership is stored in each
table's description. A readiness gate is set to `building` first and `ready`
only after the lookup writes and source-version recheck succeed. No cross-table
transaction is claimed.

Refresh/reframe the semantic model afterwards. The **Unmapped Observations**
measure checks source/context identities in both directions. Business measures
are blanked if new/missing source observations require a lookup rebuild, or a
lookup build is incomplete. Do not ignore that readiness message.

Local profiling tools need Azure Identity, Delta Lake 1.6.6 or newer, PyArrow,
Requests and jsonschema. These are local development tools, not new collector
application dependencies.

## Maintenance and acceptance

`tools/estate_model.py` holds the new model registry and pure lookup logic.
`tools/build_estate_report.py` generates the TMDL and native PBIR visuals.
Back up Desktop edits before regenerating: generation replaces generated files.

```bash
.venv/bin/python -m unittest discover -s pbip-local/Monitor/tools \
  -p test_estate_model.py -v
.venv/bin/python pbip-local/Monitor/tools/build_estate_report.py
.venv/bin/python pbip-local/Monitor/tools/validate_report.py
ruff check --target-version py310 pbip-local/Monitor/tools
ruff format --check pbip-local/Monitor/tools
```

Validation includes actual-source key joins, local Delta ownership roundtrips,
Microsoft TOM TMDL deserialization, Microsoft's published PBIR JSON schemas,
field/measure bindings, one-direction acyclic relationships and canvas bounds.
The starter's unpublished report-3.4 schema URI was replaced with the compatible,
published 3.3 schema.

**Desktop rendering and DAX engine queries are not verified from this Linux
environment.** Open the PBIP using a new private remote model and run
`queries/acceptance.dax`; review visuals, drillthrough, empty states, filters,
permissions, query performance and metric/date selections before sharing.
