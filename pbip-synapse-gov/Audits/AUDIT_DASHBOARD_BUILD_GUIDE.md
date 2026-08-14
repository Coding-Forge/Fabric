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

This page should reflect ideas from Power BI monitoring, FUAM-style estate monitoring, and Purview audit investigation reports.

Recommended visuals:

1. Cards:
   - `Failed Activities`
   - `Success Rate`
   - `Unique Client IPs`
   - `Activities Last 24 Hours`
2. Bar chart:
   - Axis: `activity[Activity]`
   - Values: `Failed Activities`
3. Bar chart:
   - Axis: `activity[UserId]`
   - Values: `Failed Activities`
4. Bar chart:
   - Axis: `activity[ClientIP]`
   - Values: `Total Activities`
5. Table:
   - `CreationTime`
   - `UserId`
   - `ClientIP`
   - `Operation`
   - `Activity`
   - `RequestId`
   - `ActivityId`
   - `IsSuccess`

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
