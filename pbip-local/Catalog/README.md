# Catalog report: Lineage

Open `Schema.pbip` in Power BI Desktop and refresh. The **Lineage** page reads the
JSON already collected by Catalog; no Functions restart, Azurite, or API call is
needed to view existing files.

In **Transform data > Manage Parameters**, set `CatalogOutputPath` to your monitor
output root. It defaults to `C:\Projects\Tests\monitor-poc-output` and is shared
by the existing Catalog scan queries and the new lineage queries. This replaces
the previous hardcoded `C:\Projects\Tests\monitor` root. The root must contain
`catalog\scans` for the existing Catalog pages and `lineage_edges` for lineage.
This project remains a local-folder report, not a Blob/OneLake connector.

## What the page shows

- Workspace and item selectors. Item labels include type and ID so a report and
  model with the same name are distinct.
- Upstream dependencies and downstream consumers, with source/target identities,
  relationship type, target workspace, resolution label and observation time.
  Wide tables can be scrolled horizontally to inspect identity fields.
- Cards for selected items, upstream/downstream directional rows, unresolved
  references, file-load errors and the newest selected UTC observation.
- Workspace coverage, including returned workspaces with no supported items.
  The workspace selector filters coverage, but the item selector does not.
- Disconnected file diagnostics and a global warning that remain visible when
  workspace/item filters produce no rows. Files with missing fields, unsupported
  schema versions, invalid JSON or unreadable contents are rejected, not treated
  as successful zero-dependency observations. Missing/unreadable lineage folders
  and empty folders have different status messages.

## Snapshot selection and limits

The loader supports version 1 `Scanner` envelopes with `complete: true`. It
selects the newest complete observation **per returned workspace**, ordered by
UTC observation time, then scan ID and path to break ties. It selects a snapshot
before expanding items or edges: a newer returned workspace with an empty
inventory replaces that workspace's older inventory and edges.

It does **not** combine every historical edge. A requested-but-not-returned
workspace does not erase its previous returned observation; the selected older
timestamp and per-file requested-not-returned count remain visible. Different
workspaces can therefore have observations from different times. Invalid newer
files can leave an older basis selected; any rejected file produces a global
warning that the selection may be stale. Historical rejected files remain in the
load-error count until they are repaired or deliberately removed from the input.
Do not delete collector state/checkpoints to refresh the report.

Workspace names come from Catalog's workspace inventory for display only; lineage
membership and selection use snapshot workspace IDs. Unresolved target IDs are
retained, not silently joined to an older item inventory. A datasource label such
as `Extension` is not proof that its underlying endpoint is identified.

These are direct scanner relationships, not recursive impact analysis, change
detection, or exhaustive Fabric portal lineage. Reverse relationships require
both supported items in the same scan batch; datasource endpoints are not item
inventory. Upstream and downstream row totals need not match. “No rows” means no
relationships **observed in that selected snapshot**, not proof of no dependency.

## Lineage Graphs: Sankey, Chord and ZoomCharts Network

The separate **Lineage Graphs** page uses the three gallery visuals already
registered in the report:

| Visual | Binding | Interpretation |
|---|---|---|
| Microsoft Sankey | Source = upstream node; Destination = consumer; Weight = Graph Link Weight | Dependency topology, including source/model/report chains |
| Microsoft Chord | From = upstream node; To = consumer; Values = Graph Link Weight | Connectivity; ribbons are not directional arrows |
| ZoomCharts Drill Down Network PRO | Nodes = Source, then Consumer; Measure = Graph Link Weight | Two category levels, not an arbitrary directed graph |

These are the **Network** visual's `Nodes`/`Size` roles, not the Source/Target
roles of ZoomCharts' separate **Graph** product. Roles were checked against
Microsoft's [Sankey capabilities](https://github.com/microsoft/powerbi-visuals-sankey/blob/master/capabilities.json),
[Chord capabilities](https://github.com/microsoft/powerbi-visuals-chord/blob/master/capabilities.json),
and the published Network package (1.12.74.0) plus its
[vendor field documentation](https://zoomcharts.com/en/microsoft-power-bi-custom-visuals/documentation/drill-down-network-visual/quickstart/).

Graph links derive from the same selected snapshots as the detail page. Only
`upstream` records are used, oriented **upstream endpoint -> dependent consumer**.
The reverse-copy `downstream` rows are excluded. Multiple relation types for the
same pair are one topology link, with their types retained on `Lineage Graph Links`.
Weights are dependency counts, not data volumes or conserved flow quantities.

Node identity uses item/datasource IDs in separate namespaces, never names alone.
Captions include item type; repeated name/type captions also include the full
identity. The same canonical caption is used at both ends of a chain. A known
consumer name is preferred over reference metadata for display only; this does
not add edges or prove that unresolved source details are now resolved.

**Consumer workspace** filters the workspace that observed the dependency; an
upstream endpoint may be external or in another workspace. **Focus node** is an
optional, disconnected selector across observed endpoints: it retains links
where either endpoint matches. It does not recursively find all descendants.
Clear a previous focus selection if a new workspace produces no matching links.
Items with no observed links remain on the detail page, not in this graph-node
selector. Coverage warnings/load errors remain independent of node focus.

Custom visuals can reduce or limit the rendered dataset. The diagrams are not
proof that all dependencies are displayed; use the detail tables and coverage
evidence. Network may show a model in different category-level contexts and is
not a substitute for an identity-preserving directed graph. Licensing/trial and
tenant custom-visual policies may affect ZoomCharts functionality; no license was
purchased or configured by this change.

Reopen the updated PBIP and refresh; do not save an older open Desktop instance
over these files. If using the WSL checkout, its Windows path is
`\\wsl.localhost\Ubuntu-24.04\home\brandon\projects\fabric\monitor\pbip-local\Catalog\Schema.pbip`.
The separate `C:\Projects\Fabric\monitor` checkout is not updated automatically.
No Functions restart, new collection or API call is required.

## Validation

Offline checks cover page/model field wiring, source/target identity retention,
direction filters, single-direction relationships, disconnected diagnostics and
snapshot-query structure. Microsoft Power Query syntax parsing and published
PBIR schema validation supplement these checks; neither executes M/DAX.

**Power BI Desktop acceptance is still required:** refresh the project, verify the
Lineage page opens, select a model with a known report, and check its upstream
source and downstream report. Select the corresponding report to see its model
upstream. Check returned-empty workspace coverage and zero/rejected-file
diagnostics. Validate replacement by a newer empty snapshot using an isolated
test copy of the output, not by modifying live collector evidence. No native
Desktop refresh/rendering validation is implied by offline checks.

For the graph page, first clear focus and confirm source -> model -> report
chains in Sankey, connectivity in Chord, and source/consumer categories in
Network. Selecting a model should keep both its direct upstream and downstream
links; selecting a shared datasource should retain its direct consumer links.
Check duplicate names, empty-workspace behavior and any ZoomCharts license
prompt. Microsoft schema/M parsing cannot execute the custom visual code or
verify rendering, interactions, data reduction or licensing.
