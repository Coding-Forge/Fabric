# Audit Dashboard Build Guide

This PBIP is intentionally structured as a stable Power BI Desktop starting point:

- The semantic model includes an `activity` table sourced from monitor activity JSON files.
- A visible `_Measures` table contains reusable DAX measures.
- The report includes named pages with starter visuals for the audit dashboard sections.

The generated starter visuals use conservative Power BI Desktop visual patterns only: cards, slicers, text boxes, shapes, bar charts, column charts, and a line chart. Add richer visuals, drillthrough fields, and navigation inside Power BI Desktop rather than hand-editing enhanced PBIR bookmark or table visual JSON.

## Dashboard Pages

| Page | Purpose |
|---|---|
| Audit Overview | Executive audit posture, activity volume, success/failure, trend, top workloads |
| Activity & Operations | Operation and activity analysis, refresh activity, failure hotspots |
| Users & Access | User behavior, top users, client IPs, user types, access investigation |
| Workspaces & Artifacts | Workspace, dataset, capacity, artifact activity and ownership-style views |
| Risk & Anomalies | Failed activity, unusual client IPs, high-volume users, suspicious operations |
| Drillthrough Detail | Row-level investigation target for user/workspace/activity/artifact context |
| Refresh Health (`refresh_health`) | Dataset refresh volume, failures, staleness and credential/parameter changes. See [Refresh Health Page](#refresh-health-page) |
| Activity vs Capacity (`activity_vs_capacity`) | Audit activity set against Capacity Metrics utilization by UTC day and hour. See [Activity vs Capacity Page](#activity-vs-capacity-page) |

## Recommended Global Slicers

Add these slicers to the top or left side of the main pages:

| Field | Slicer Type |
|---|---|
| `activity[CreationTime]` | Between / relative date |
| `activity[Workload]` | Dropdown |
| `activity[WorkSpaceName]` | Dropdown with search |
| `activity[Activity]` | Dropdown with search |
| `activity[UserId]` | Dropdown with search |
| `activity[IsSuccess]` | Tile or dropdown |
| `activity[ArtifactKind]` | Dropdown |
| `activity[CapacityName]` | Dropdown |

## Measures in `_Measures`

Use these measures for cards, KPIs, and charts:

| Measure | Suggested Use |
|---|---|
| `Total Activities` | Main activity volume KPI |
| `Unique Users` | User population KPI |
| `Distinct Workspaces` | Workspace footprint KPI |
| `Distinct Artifacts` | Artifact footprint KPI |
| `Successful Activities` | Success count |
| `Failed Activities` | Failure count and risk page |
| `Success Rate` | Quality / health KPI |
| `Refresh Activities` | Refresh monitoring |
| `Activities Last 24 Hours` | Recent activity KPI |
| `Activities Last 7 Days` | Weekly trend KPI |
| `Activities Last 30 Days` | Monthly trend KPI |
| `Avg Activities per User` | Usage density |
| `Last Activity Time` | Freshness KPI |
| `Unique Client IPs` | Access/risk analysis |
| `Dataset Activities` | Dataset activity scope |
| `Capacity Activities` | Capacity activity scope |

## Derived Activity Columns

The `activity` table query adds the columns below after the file load. They are computed in Power Query (M), not DAX.

| Column | Definition |
|---|---|
| `Event Time Local` | `CreationTime` (UTC) plus the `Local UTC Offset Hours` parameter. |
| `Event Date` | Date part of `Event Time Local`. Daily trend axis for the risk measures. |
| `Hour of Day` | Hour (0-23) of `Event Time Local`. |
| `Day of Week` | `Mon` to `Sun`, taken from `Event Date`. Sorted by `Day of Week Sort`. |
| `Day of Week Sort` | 1 = Monday ... 7 = Sunday. |
| `Actor Type` | `Human`, `Service principal` or `External app`. Sorted by `Actor Type Sort`. |
| `Actor Type Sort` | 1 = Human, 2 = Service principal, 3 = External app. |
| `Operation Category` | `View`, `Refresh`, `Edit`, `Admin API`, `Sharing`, `Export`, `Security`, `External app` or `Other`. |
| `Is System Activity` | True when `Actor Type` is `Service principal` or `Operation Category` is `Admin API`. Displays as "System activity" / "User activity". |

Classification uses the `Activity` value, falling back to `Operation` when `Activity` is empty.

### Id Dedupe

After the type change, the query keeps one row per `Id` (`Table.Distinct` on `Id`), so overlapping reruns of the monitor are not double counted. Rows with a null or empty `Id` are all kept.

### Local UTC Offset Hours Parameter

- Power Query parameter `Local UTC Offset Hours` (number, required), default `-4`.
- It is a fixed offset with no daylight saving handling. Use `-4` for US Eastern daylight time and `-5` for standard time. Change it in Transform data > Manage Parameters, then refresh.
- It shifts `Event Time Local`, so `Event Date`, `Hour of Day`, `Day of Week` and all off-hours and daily measures follow it.

### Actor Type Rules

First match wins:

1. `Service principal` when `UserType` is in {3, 4, 5, 6}, or the activity is an Admin API call. The sample refresh events carry `UserType` 6.
2. `External app` when the activity is `AnalyzedByExternalApplication` or `ConnectFromExternalApplication`.
3. Otherwise `Human`.

Admin API activities are the names `ExportActivityEvents`, `GetCapacitiesAsAdmin`, `GetModifiedWorkspacesAPI`, `GetWorkspacesInfoAPI`, `GetWorkspacesInfoResult`, `GetWorkspacesViaAdminApi`, `GetTenantSettingsViaAdminApi`, and any `Get...` name ending in `ViaAdminApi` or `AsAdmin`.

### Operation Category Precedence

Rules are evaluated in this order and the first match wins:

| Order | Category | Matches |
|---|---|---|
| 1 | External app | `AnalyzedByExternalApplication`, `ConnectFromExternalApplication` |
| 2 | Admin API | Admin API names above, or starts with `GetWorkspacesInfo` |
| 3 | Refresh | Contains `Refresh` |
| 4 | View | Starts with `View` or `Read` |
| 5 | Sharing | Starts with `Share`, or contains `Permission`, `Link` or `Access` |
| 6 | Export | Starts with `Export`, `Print` or `Download` |
| 7 | Security | Contains `Role`, `Credentials` or `Label`, or contains both `Tenant` and `Settings` |
| 8 | Edit | Starts with `Update`, `Create`, `Edit`, `Delete`, `Import` or `Install` |
| 9 | Other | Everything else, including a null activity |

## Risk & Anomalies Measures

All 19 measures live in `_Measures` under the display folder `Risk & Anomalies`.

| Measure | Definition |
|---|---|
| `Failure Rate` | `Failed Activities` / (`Successful Activities` + `Failed Activities`). Rows with a null `IsSuccess` are excluded from both sides. |
| `Failures Last 7 Days` | `Failed Activities` with `CreationTime` within `NOW() - 7`. |
| `Human Activities` | `Total Activities` where `Is System Activity` is false. |
| `Off-hours Activities` | Activities with local `Hour of Day` < 7 or >= 19, or on Saturday or Sunday. |
| `Off-hours %` | `Off-hours Activities` / `Total Activities`. |
| `Daily Activities` | `Total Activities`; use with `Event Date` on the axis. |
| `Daily Activities 7D Avg` | Average of the daily totals over the prior 7 days (day-7 to day-1). The tested day is excluded. Days with no activity are not counted. Blank when there is no prior day. |
| `Daily Std Dev 7D` | Population standard deviation of the daily totals over the same prior 7-day window. |
| `Spike Flag` | 1 on a single day when `Daily Activities` is at least 10 and above the prior-7-day average + 2 x standard deviation. When the standard deviation is 0, the threshold is 1.5 x the average. A blank baseline or an average of 0 never flags. |
| `Spike Days` | Sum of `Spike Flag` over the `Event Date` values in context. |
| `Spike Day Activities` | `Daily Activities` on spike days, blank otherwise. Plotted as the red marker series. |
| `Sharing Operations` | `Total Activities` with `Operation Category` = Sharing. |
| `Export Operations` | Same, for Export. |
| `Security Operations` | Same, for Security. |
| `Sharing Export Security Operations` | Same, for Sharing, Export and Security together. |
| `First Seen Time` | Earliest `CreationTime` ever recorded for the current (`UserId`, `ClientIP`) pair, ignoring all other filters. |
| `Period Start` | Earliest `CreationTime` inside the selected `Event Date` range. |
| `Is New Client IP` | 1 when the (`UserId`, `ClientIP`) pair has both values and `First Seen Time` is on or after `Period Start`. Always 0 when `Period Start` is the very first recorded event. |
| `First-Seen IPs` | Count of (`UserId`, `ClientIP`) pairs where `Is New Client IP` = 1. |

The 7-day measures (`Daily Activities 7D Avg`, `Daily Std Dev 7D`, `Spike Flag`, `Spike Days`, `Spike Day Activities`) are only meaningful with `activity[Event Date]` on the axis.

## Audit Overview Layout

Recommended visuals:

1. Cards:
   - `Total Activities`
   - `Unique Users`
   - `Distinct Workspaces`
   - `Distinct Artifacts`
   - `Success Rate`
   - `Activities Last 24 Hours`
2. Line chart:
   - Axis: `activity[CreationTime]`
   - Values: `Total Activities`
3. Bar chart:
   - Axis: `activity[Activity]`
   - Values: `Total Activities`
4. Column chart:
   - Axis: `activity[Workload]`
   - Legend: `activity[IsSuccess]`
   - Values: `Total Activities`
5. Bar chart:
   - Axis: `activity[WorkSpaceName]`
   - Values: `Total Activities`

## Activity & Operations Layout

Recommended visuals:

1. Cards:
   - `Total Activities`
   - `Failed Activities`
   - `Refresh Activities`
   - `Success Rate`
2. Bar chart:
   - Axis: `activity[Operation]`
   - Values: `Total Activities`
3. Column chart:
   - Axis: `activity[ArtifactKind]`
   - Values: `Total Activities`
4. Stacked column chart:
   - Axis: `activity[Operation]`
   - Legend: `activity[IsSuccess]`
   - Values: `Total Activities`
5. Matrix:
   - Rows: `activity[Activity]`, `activity[Operation]`
   - Columns: `activity[IsSuccess]`
   - Values: `Total Activities`

## Users & Access Layout

Recommended visuals:

1. Cards:
   - `Unique Users`
   - `Unique Client IPs`
   - `Avg Activities per User`
2. Bar chart:
   - Axis: `activity[UserId]`
   - Values: `Total Activities`
3. Bar chart:
   - Axis: `activity[ClientIP]`
   - Values: `Total Activities`
4. Column chart:
   - Axis: `activity[UserType]`
   - Values: `Total Activities`
5. Table:
   - `CreationTime`
   - `UserId`
   - `ClientIP`
   - `Activity`
   - `WorkSpaceName`
   - `ArtifactName`
   - `IsSuccess`

## Workspaces & Artifacts Layout

Recommended visuals:

1. Cards:
   - `Distinct Workspaces`
   - `Distinct Artifacts`
   - `Dataset Activities`
   - `Capacity Activities`
2. Bar chart:
   - Axis: `activity[WorkSpaceName]`
   - Values: `Total Activities`
3. Bar chart:
   - Axis: `activity[ArtifactName]`
   - Values: `Total Activities`
4. Column chart:
   - Axis: `activity[CapacityName]`
   - Values: `Total Activities`
5. Matrix:
   - Rows: `WorkSpaceName`, `ArtifactKind`, `ArtifactName`
   - Values: `Total Activities`, `Failed Activities`

## Risk & Anomalies Layout

This page (internal name `f1000000000000000005`, 1920 x 1080) was rebuilt around the 19 measures in the `Risk & Anomalies` display folder of `_Measures` (see [Risk & Anomalies Measures](#risk--anomalies-measures)). It reflects ideas from Power BI monitoring, FUAM-style estate monitoring, and Purview audit investigation reports.

Layout, top to bottom:

1. Slicers (row at y=90):
   - `activity[Event Date]` (Between)
   - `activity[Workload]`
   - `activity[WorkSpaceName]`
   - `activity[IsSuccess]`
   - `activity[Actor Type]`
   - `activity[Is System Activity]`, titled "Hide system activity", saved with `false` selected (see [Hide System Activity Default](#hide-system-activity-default))
2. KPI cards (row at y=180):
   - `Failure Rate`
   - `Off-hours %` (before 07:00, after 19:00, weekends)
   - `Spike Days`
   - `First-Seen IPs`
   - `Sharing Export Security Operations`
3. Trend row (y=295):
   - Line chart: axis `activity[Event Date]`; values `Daily Activities`, `Daily Activities 7D Avg`, `Spike Day Activities` (the last is drawn as red markers only, no line).
   - Column chart "Failures by day": axis `activity[Event Date]`; values `Failed Activities`.
   - Bar chart "Failures by activity": axis `activity[Activity]`; values `Failed Activities`.
4. Middle row (y=555):
   - Matrix "Activity by local hour and weekday": rows `activity[Day of Week]`, columns `activity[Hour of Day]`, values `Total Activities`.
   - Bar chart "High-volume users": axis `activity[UserId]`; values count of `activity[Id]`.
   - Bar chart of `activity[ClientIP]` by count of `activity[Id]`.
5. Tables (y=820):
   - "Sharing, export and security operations (local time, newest first)": `Event Time Local`, `UserId`, `Operation Category`, `Activity`, `ItemName`, `WorkSpaceName`, `ClientIP`. Filtered to `Operation Category` in Sharing, Export, Security; sorted by `Event Time Local` descending.
   - "New client IPs per user (first seen in selected period)": `UserId`, `ClientIP`, `First Seen Time`, `Total Activities`. Filtered to the measure `Is New Client IP` = 1; sorted by `First Seen Time` descending.

The page also has the title text box and the page navigator.

## Drillthrough Detail

Configure this page as a drillthrough target.

Recommended drillthrough fields:

- `activity[UserId]`
- `activity[WorkSpaceName]`
- `activity[Activity]`
- `activity[Operation]`
- `activity[ArtifactName]`
- `activity[ArtifactKind]`
- `activity[RequestId]`

Recommended detail table fields:

- `CreationTime`
- `UserId`
- `ClientIP`
- `Workload`
- `Activity`
- `Operation`
- `WorkSpaceName`
- `ArtifactKind`
- `ArtifactName`
- `DatasetName`
- `CapacityName`
- `IsSuccess`
- `RequestId`
- `ActivityId`

## Capacity Metrics

Three pages show Fabric/Power BI capacity utilization, throttling, and carry-over from the monitor `CapacityMetrics` module output. All three pages have a `Capacities[Capacity Name]` dropdown slicer and a `CapacityMetrics[Metric Date]` between slicer, plus a page navigator and title.

### Pages and Visuals

| Page | Visuals |
|---|---|
| Capacity Overview | Cards: `Capacity Count`, `Peak Utilization %`, `Avg Utilization %`, `Max Carry Over %`. Line chart: `Timepoint` with `Peak Utilization %` and `Avg Utilization %` (100% = SKU limit). Table "Capacity summary": `Capacity Name`, `SKU`, `Peak Utilization %`, `Avg Utilization %`, `Max Carry Over %`, `Overload Timepoints`, `Throttling Status`. |
| Capacity Utilization | Column chart by `Metric Date`: `Avg Background Billable %`, `Avg Interactive Billable %`. Line chart by `Timepoint`: `Max Background Billable %`, `Max Interactive Billable %`. Bar chart by `Capacity Name`: average background vs interactive billable. Table "Top timepoints" (sorted by `Peak Utilization %` descending): `Capacity Name`, `Timepoint`, `Peak Utilization %`, `Max Background Billable %`, `Max Interactive Billable %`, `CU Usage (CU-s)`. |
| Capacity Carry-over | Cards: `Max Carry Over %`, `Max Expected Burndown (min)`, `Carry Over Timepoints`, `Overload Timepoints`. Line charts by `Timepoint`: cumulative carry-over (`Max Carry Over %`) and `Avg Carry Over Add %` vs `Avg Carry Over Burndown %`. Table (sorted by `Max Carry Over %` descending): `Capacity Name`, `Timepoint`, `Peak Utilization %`, `Max Carry Over %`, `Max Carry Over Add %`, `Avg Carry Over Burndown %`, `Max Expected Burndown (min)`, `Overload Timepoints`. |

### Tables and Relationships

| Table | Type | Grain |
|---|---|---|
| `CapacityMetrics` | Fact | One row per capacity and timepoint (about 30 seconds). The utilization and carry-over groups are joined on `Capacity Id` + `Timepoint`. |
| `Capacities` | Dimension | One row per capacity: `Capacity Id` (hidden), `Capacity Name`, `SKU`. |

Relationships:

- `CapacityMetrics[Capacity Id]` -> `Capacities[Capacity Id]`
- `CapacityMetrics[Metric Date]` -> `dimDate[Date]`

### Data Source

- Source: files written by the monitor `CapacityMetrics` module under `<output>/capacity_metrics/YYYY/MM/DD`, named `{runYYYYMMDD}_{capacityId}_{group}_{metricDayYYYYMMDD}.capacity_metrics.json`.
- Both M queries (`CapacityMetrics` and `Capacities`) hardcode the root `C:\Projects\Tests\monitor-poc-output\capacity_metrics`. Edit `Root` in both queries to your own `capacity_metrics` folder.
- The latest run wins per capacity, group, and timepoint (and per capacity for `Capacities`), so reruns are not double counted.
- `Capacity Id` is upper-cased in both tables so the relationship matches.
- If no files match, both tables load empty.

### Measures

All measures live in `CapacityMetrics` under the display folder `Capacity Metrics\<folder>`. Percentages are fractions: 1.0 = 100%.

| Folder | Measures | Definition |
|---|---|---|
| Utilization | `Peak Utilization %`, `Avg Utilization %` | Utilization = background billable + interactive billable, as a fraction per timepoint; peak is the max and average is the mean across timepoints. |
| Utilization | `Avg/Max Background Billable %`, `Avg/Max Interactive Billable %`, `Avg Background Non-billable %`, `Avg Interactive Non-billable %` | Average or max of the matching column. |
| Utilization | `CU Usage (CU-s)` | Sum over timepoints of (background + interactive billable fraction) x `SKU CU by timepoint`. |
| Utilization | `CU Capacity (CU-s)`, `CU Limit (max)` | Sum of `SKU CU by timepoint`; max of `CU limit`. |
| Throttling | `Overload Timepoints` | Timepoints where billable utilization is greater than `SKU CU by timepoint %`. |
| Throttling | `Overload % of Timepoints` | `Overload Timepoints` / `Timepoint Count`. |
| Throttling | `Throttling Status` | "No data", "Overload or carry-over detected", or "No overload detected". |
| Carry-over | `Max Carry Over %`, `Max Carry Over Add %`, `Avg Carry Over Add %`, `Avg Carry Over Burndown %`, `Max Expected Burndown (min)` | Max or average of the matching column. |
| Carry-over | `Carry Over Timepoints` | Timepoints where cumulative carry-over is above zero. |
| Carry-over | `Carry Over Status` | "No carry-over data loaded", "Carry-over present", or "No carry-over in the selected period". |
| Counts | `Capacity Count`, `Timepoint Count` | Distinct `Capacity Id`; count of `Timepoint`. |

### Producing the Data

1. Set `CAPACITY_METRICS_DATASET_ID` to the dataset ID of the Microsoft Fabric Capacity Metrics semantic model.
2. Run the monitor module `CapacityMetrics`.
3. Make sure the service principal used by the monitor is a member of the workspace that hosts the Metrics app/model.
4. Suspended capacities are skipped unless `CAPACITY_METRICS_INCLUDE_SUSPENDED` is set.

### Validation Status

This addition has **NOT** been opened or refreshed in Power BI Desktop. It was reviewed and approved by reading the PBIP files only. Open it in Desktop, edit `Root` in both M queries, refresh, and check each page before relying on it.

### Known Limits

- The sample data was a single F64 capacity with near-zero utilization and all-zero carry-over. The carry-over visuals and the overload/throttling measures are unverified with real non-zero values.
- Microsoft does not support consuming the Capacity Metrics model. Its schema may change and break the module output or these measures.
- `.pbi/cache.abf` contains tenant data. Do not commit `pbip-local`.

## Customer Audit Overview Additions

The `Customer Audit Overview` page (internal name `customer_audit_overview`) gained these visuals:

| Visual | Fields |
|---|---|
| Slicer "Actor Type" | `activity[Actor Type]` |
| Slicer "Hide system activity" | `activity[Is System Activity]`, saved with `false` selected |
| Matrix "Activity by local hour and weekday" | Rows `Day of Week`, columns `Hour of Day`, values `Total Activities` |

The existing slicers on this page (date/time on `CreationTime`, operation, user, workload, workspace) are unchanged.

## Hide System Activity Default

Both the `Risk & Anomalies` page and the `Customer Audit Overview` page ship with a "Hide system activity" slicer on `activity[Is System Activity]`. The saved slicer state selects `false`, so service principal and Admin API activity (the monitor's own noise) is hidden when the report opens. Slicers do not sync between pages, so set each page separately.

To change it:

- In Power BI Desktop, clear the slicer selection, or select `System activity`, to include system activity. Save the report to keep the choice.
- To change the shipped default, edit the slicer in Desktop and save, rather than editing the saved filter in the visual JSON by hand.
- To restrict by actor instead, use the `Actor Type` slicer on the same page.

## Refresh Health Page

Page `refresh_health`, display name "Refresh Health", 1920 x 1080. It sits after `Risk & Anomalies` in the page order. All visuals read the `activity` table and the `Refresh Health` measures. Dates and hours on this page are **local time** (`Event Date`, `Hour of Day`, driven by `Local UTC Offset Hours`).

Slicers (row at y=90):

- `activity[Event Date]` (Between)
- `activity[WorkSpaceName]`
- `activity[DatasetName]`
- `activity[Actor Type]`

KPI cards (row at y=180): `Refresh Events` ("Refreshes"), `Failed Refreshes`, `Refresh Failure Rate`, `Datasets Refreshed`, `Credential and Parameter Changes`.

Visuals:

| Row | Visual | Fields |
|---|---|---|
| Trend (y=295) | Column chart "Refreshes by day (succeeded / failed)" | Axis `Event Date`; values `Succeeded Refreshes`, `Failed Refreshes` (failed in red). |
| Trend | Donut "Refreshes by refresh type" | Legend `activity[RefreshType]`; values `Refresh Events`. |
| Trend | Column chart "Refreshes by hour of day (local time)" | Axis `Hour of Day`; values `Refresh Events`. |
| Middle (y=555) | Bar chart "Refreshes by dataset" | Axis `DatasetName`; values `Refresh Events`, highest first. |
| Middle | Bar chart "Failed refreshes by dataset" | Axis `DatasetName`; values `Failed Refreshes`, highest first. |
| Middle | Table "Last refresh per dataset (local time, stalest first)" | `DatasetName`, `Last Refresh Event Time`, `Last Refresh Status`, `Hours Since Last Refresh`; sorted by `Hours Since Last Refresh` descending. |
| Bottom (y=820) | Table "Credential and parameter changes (local time, newest first)" | `Event Time Local`, `UserId`, `DatasetName`, `Effective Activity`, `WorkSpaceName`, `IsSuccess`. Filtered to `Effective Activity` in `UpdateDatasourceCredentials`, `UpdateDatasetParameters`; sorted by `Event Time Local` descending. |

The page also has the title text box and the page navigator. It has no "Hide system activity" slicer: scheduled refreshes by service principals are counted on purpose.

### Refresh Health Measures

All 11 measures live in `_Measures` under the display folder `Refresh Health`.

| Measure | Definition |
|---|---|
| `Refresh Events` | Rows where `Operation Category` = Refresh. Not filtered by actor. |
| `Failed Refreshes` | `Refresh Events` where `IsSuccess` = FALSE. |
| `Succeeded Refreshes` | `Refresh Events` minus `Failed Refreshes` (so a null `IsSuccess` counts as succeeded). |
| `Refresh Failure Rate` | `Failed Refreshes` / `Refresh Events`. |
| `Datasets Refreshed` | Distinct `DatasetName` among refresh events. |
| `Credential Changes` | Rows where `Effective Activity` = `UpdateDatasourceCredentials`. |
| `Parameter Changes` | Rows where `Effective Activity` = `UpdateDatasetParameters`. |
| `Credential and Parameter Changes` | `Credential Changes` + `Parameter Changes`. |
| `Last Refresh Event Time` | Latest `Event Time Local` among refresh events in context. |
| `Last Refresh Status` | "Failed" if any refresh at the latest refresh `CreationTime` failed, otherwise "Succeeded"; blank with no refresh event. |
| `Hours Since Last Refresh` | Hours between the latest refresh `CreationTime` (UTC) and `UTCNOW()`, rounded to 0.1. Blank with no refresh event. |

## Activity vs Capacity Page

Page `activity_vs_capacity`, display name "Activity vs Capacity", 1920 x 1080. It compares audit activity with Capacity Metrics utilization. Dates and hours on this page are **UTC**, to match `CapacityMetrics[Metric Date]` and `Timepoint`.

Slicers (row at y=90):

- `Capacities[Capacity Name]`
- `dimDate[Date]` (Between, titled "Date (UTC)")

KPI cards (row at y=180): `CapacityMetrics[Peak Utilization %]` (100% = SKU limit), `Activities on Capacity`, `Refreshes on Capacity`, `Throttled Days`.

Visuals:

| Visual | Fields |
|---|---|
| Combo chart "Activities per day vs peak utilization (UTC days)" | Axis `dimDate[Date]`; Y `Activities on Capacity`; Y2 `Peak Utilization %`. |
| Combo chart "Activities and refreshes vs peak utilization by hour (UTC)" | Axis `'UTC Hours'[Hour (UTC)]`; Y `Activities by Hour (UTC)`, `Refreshes by Hour (UTC)`; Y2 `Peak Utilization by Hour (UTC)`. |
| Table "Capacities: utilization and activity" | `Capacities[Capacity Name]`, `SKU`, `Peak Utilization %`, `Activities on Capacity`, `Refreshes on Capacity`, `Users on Capacity`; sorted by `Peak Utilization %` descending. |
| Bar chart "Workspaces by activity on selected capacity (highest first)" | Axis `activity[WorkSpaceName]`; values `Activities on Capacity`. |

The page also has the title text box and the page navigator.

### Activity vs Capacity Measures

All 7 measures live in `_Measures` under the display folder `Activity vs Capacity`.

| Measure | Definition |
|---|---|
| `Activities on Capacity` | `Total Activities` limited to rows whose `Capacity Key` matches a row in `Capacities`. Activities with no known capacity are excluded. |
| `Refreshes on Capacity` | `Refresh Events` limited to the same rows. |
| `Users on Capacity` | Distinct `UserId` over the same rows. |
| `Throttled Days` | Count of UTC `Metric Date` values with at least one overloaded timepoint or `Max Carry Over %` above 0. |
| `Activities by Hour (UTC)` | `Activities on Capacity` for the `'UTC Hours'` hour on the axis, matched on `Event Hour UTC`. Total when no single hour is in context. |
| `Refreshes by Hour (UTC)` | Same, for `Refreshes on Capacity`. |
| `Peak Utilization by Hour (UTC)` | Highest billable utilization (background + interactive) among `CapacityMetrics` timepoints whose UTC hour equals the axis hour. Falls back to `Peak Utilization %` when no single hour is in context. |

Use the three `... by Hour (UTC)` measures only with `'UTC Hours'[Hour (UTC)]` on the axis.

## New Activity Columns and `UTC Hours`

Four calculated (DAX) columns were added to `activity`. Unlike the Power Query columns above, these are computed in the model.

| Column | Definition |
|---|---|
| `Effective Activity` | `Activity` when filled, otherwise `Operation`. Same rule the `Operation Category` classification uses. |
| `Capacity Key` | `UPPER(CapacityId)`. Matches the upper-cased `Capacity Id` in `Capacities` and `CapacityMetrics`. |
| `Event Date UTC` | UTC calendar date of `CreationTime` (date only, no time part). This is not the local `Event Date`. |
| `Event Hour UTC` | `HOUR(CreationTime)`, 0-23. |

`UTC Hours` is a calculated, disconnected table with one column, `Hour (UTC)`, holding 0 to 23 (`GENERATESERIES(0, 23, 1)`). It has no relationships and exists only as the axis for the hour-of-day combo chart.

## New Relationships

| From | To | Cardinality and direction |
|---|---|---|
| `activity[Capacity Key]` | `Capacities[Capacity Id]` | Many to one, single direction (`Capacities` filters `activity`). |
| `activity[Event Date UTC]` | `dimDate[Date]` | Many to one, single direction (`dimDate` filters `activity`). |

Why they are safe:

- `Capacities[Capacity Id]` is unique: the query keeps one row per upper-cased `Capacity Id` (latest run wins). `dimDate[Date]` is unique, one row per day for 2020-01-01 to 2030-12-31.
- Both keys are normalised to match: `Capacity Key` is upper-cased like `Capacities[Capacity Id]`, and `Event Date UTC` is a date with no time part like `dimDate[Date]`. `CapacityMetrics` already uses the same two dimensions.
- Both are single direction, and `activity` and `CapacityMetrics` have no direct relationship. They share only the `Capacities` and `dimDate` dimensions, so there is no ambiguous path or cycle.
- Activity rows with a blank or unknown capacity, or a date outside `dimDate`, simply do not match. They are not errors, and the `... on Capacity` measures exclude them.
- Consequence: a `Capacities[Capacity Name]` slicer now filters `activity` as well as `CapacityMetrics`. On the Capacity Metrics pages this does not change the existing visuals, which do not use `activity`.

## Fixes in This Change

- **`risk_kpi_spikes` (Risk & Anomalies, "Spike days" card) had no query.** It now has a query bound to `Spike Days`, so the card shows a value.
- **`audit_top_reports` (Customer Audit Overview, "Top 10 reports by views") TopN is restricted to `ViewReport` and `ReadArtifact`.** The visual has a categorical filter on `activity[Activity]` for those two values, and the TopN subquery on `ItemName` applies the same restriction. Before, the top 10 could be picked from all activity types.

## Known Caveats

- **Not opened in Power BI Desktop.** The changes were reviewed and approved by reading the PBIP files only. Open the project, refresh, and check each page before relying on it.
- **Hand-written PBIR pieces may need a check.** These were authored by hand and could be adjusted or dropped by Desktop on open: the saved slicer state ("Hide system activity"), the TopN filter, and the measure filter on the "New client IPs per user" table (`Is New Client IP` = 1).
- **`Period Start` respects only `Event Date`.** It clears every other filter on `activity`, including slicers on `CreationTime` or its date hierarchy. Use an `Event Date` slicer to set the period for `First-Seen IPs`.
- **7-day measures need a daily axis.** See [Risk & Anomalies Measures](#risk--anomalies-measures).
- **`First-Seen IPs` is 0 when the selected range starts at the first recorded event**, because there is no earlier baseline.
- **Saved date range on `audit_date_slicer`.** This pre-existing slicer on `Customer Audit Overview` has a hard-coded saved range of 2026-06-16 to 2026-10-16. Widen or reset it in Desktop when newer data is loaded.
- **Fixed UTC offset.** `Local UTC Offset Hours` has no daylight saving handling.
- **Refresh Health and Activity vs Capacity are unverified in Power BI Desktop.** They were reviewed and approved by reading the PBIP files only. Open, refresh and check both pages and the two new relationships.
- **Combo chart roles.** Both combo charts use role `Y` (columns) for activity and refresh counts and role `Y2` (line, secondary axis) for utilization. These roles were hand-written, so confirm in Desktop that columns and line render as intended.
- **CapacityMetrics `Timepoint` is assumed to be UTC.** A sample value is `2026-10-14T21:23:00`. If the Capacity Metrics app returns local time, the hour and day comparison is offset by that amount and needs adjusting.
- **`Hours Since Last Refresh` is based on UTC now.** It uses `UTCNOW()`, so it grows as the extract ages and is only meaningful when the audit data is current.
- **`Activities on Capacity` scans the table.** It filters `activity` row by row with `RELATED`. The `Refreshes on Capacity`, `Users on Capacity` and `... by Hour (UTC)` measures build on it. If the page is slow on a large `activity` table, optimise the measures.
- **Mixed time bases between pages.** The `Activity vs Capacity` date slicer is UTC (`dimDate[Date]` via `Event Date UTC`). `Refresh Health` and the other audit pages use local time (`Event Date`). The same day can hold different counts on each page.
- **Graph tables fill only when the Graph module has produced the data.** `GraphUserLicenses` is fed by `userlicenses.json`, which the `Graph` module always writes (when the users call succeeds). `GraphGroups` and `GraphGroupMembers` are fed by `groups.json` and `groupmembers.json`, which are written only when `GRAPH_EXTRACT_GROUPS` is on (`1`, `true`, `yes` or `on`; default off) and the app registration has the Graph permissions `User.Read.All`, `Group.Read.All` and `GroupMember.Read.All`. Without those, the group tables load no rows. Member lookups are capped by `GRAPH_MAX_GROUPS_FOR_MEMBERS` (default 200, audience groups first), so on large tenants the member table can be partial. See [configuration-reference.md](../../docs/configuration-reference.md#microsoft-graph-graph).

## Navigation

Use native Power BI Desktop navigation:

1. Insert > Buttons > Navigator > Page navigator.
2. Put the page navigator at the top of each page.
3. Format it as horizontal navigation.
4. Optionally create bookmarks for common states:
   - Executive overview
   - Failed activity investigation
   - User investigation
   - Workspace investigation
   - Refresh monitoring

## Design Notes

- Use a light background with high-contrast KPI cards.
- Keep slicers consistent across pages.
- Use drillthrough rather than overcrowding overview pages.
- Use native Desktop visuals and navigators to avoid enhanced PBIR hand-authoring issues.
