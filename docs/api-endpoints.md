# API endpoints used by Fabric Monitor

Source: `env/modules/*.py`. Base URLs and token scopes are defined per cloud in `env/cloud.py`; all calls go through `Context.invokeAPI` in `env/context.py` (some modules call `requests.get` directly). Links below point to the official Microsoft Learn REST references; where an exact operation reference is unavailable, the API-family reference is linked.

Base URLs (Commercial):
- Power BI: `https://api.powerbi.com/v1.0/myorg/`
- Fabric: `https://api.fabric.microsoft.com/`
- Graph: `https://graph.microsoft.com/beta`

## Fabric REST API (admin)

| Module | Endpoint | Microsoft Learn reference | File |
|---|---|---|---|
| Domains | `GET v1/admin/domains` | [List domains](https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/list-domains) | `modules/domains.py` |
| Domains | `GET v1/admin/domains/{domainId}/workspaces` | [Fabric Admin REST API](https://learn.microsoft.com/en-us/rest/api/fabric/admin/) | `modules/domains.py` |
| FabricItems | `GET v1/admin/items` | [List items (Admin)](https://learn.microsoft.com/en-us/rest/api/fabric/admin/items/list-items) | `modules/fabricitems.py` |
| Workspaces | `GET v1/admin/workspaces` | [List workspaces (Admin)](https://learn.microsoft.com/en-us/rest/api/fabric/admin/workspaces/list-workspaces) | `modules/workspaces.py` |
| Roles | `GET v1/admin/workspaces` | [Fabric Admin REST API](https://learn.microsoft.com/en-us/rest/api/fabric/admin/) | `modules/roles.py` |
| Tenant | `GET v1/admin/tenantsettings` | [Fabric Admin REST API](https://learn.microsoft.com/en-us/rest/api/fabric/admin/) | `modules/tenant.py` |
| FabricItems (lineage, beta) | `GET v1/workspaces/{ws}/items/{id}/relations/upstream?beta=true` and `/relations/downstream?beta=true` | [Fabric REST API reference](https://learn.microsoft.com/en-us/rest/api/fabric/) | `modules/fabricitems.py` |

## Fabric REST API (workspace-level, needs workspace access)

| Module | Endpoint | Microsoft Learn reference | File |
|---|---|---|---|
| ItemJobs | `GET v1/workspaces/{ws}/items/{id}/jobs/instances` | [Fabric REST API reference](https://learn.microsoft.com/en-us/rest/api/fabric/) | `modules/itemjobs.py` |
| ItemJobs | `POST v1/workspaces/{ws}/items/{id}/getDefinition` (long-running operation) for CopyJob and DataPipeline | [Get item definition](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/get-item-definition) | `modules/itemjobs.py` |
| ItemJobs | `GET v1/workspaces/{ws}/datapipelines/pipelineruns/{runId}/queryactivityruns` (recurses into child pipelines) | [Fabric REST API reference](https://learn.microsoft.com/en-us/rest/api/fabric/) | `modules/itemjobs.py` |

## Power BI REST API

| Module | Endpoint | Microsoft Learn reference | File |
|---|---|---|---|
| Activity | `GET admin/activityevents?startDateTime=...&endDateTime=...` (continuation URIs) | [Get Activity Events](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/get-activity-events) | `modules/activity.py` |
| Apps | `GET admin/apps?$top=5000&$skip=0` | [Power BI Admin REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/admin) | `modules/apps.py` |
| Capacity | `GET admin/capacities` | [Power BI Admin REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/admin) | `modules/capacity.py` |
| CapacityMetrics | `GET admin/capacities/metrics`, `POST datasets/{datasetId}/executeQueries` | [Power BI Admin REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/admin) and [Execute Queries](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries) | `modules/capacity_metrics.py` |
| Catalog | `GET admin/workspaces/modified?...` | [Power BI Admin REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/admin) | `modules/catalog.py` |
| Catalog | `POST admin/workspaces/getInfo?lineage=True&datasourceDetails=True&datasetSchema=True&datasetExpressions=True` | [Post Workspace Info](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-post-workspace-info) | `modules/catalog.py` |
| Catalog | `GET admin/workspaces/scanStatus/{scanId}` | [Get Scan Status](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-scan-status) | `modules/catalog.py` |
| Catalog | `GET admin/workspaces/scanResult/{scanId}` | [Get Scan Result](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-scan-result) | `modules/catalog.py` |
| Gateway | `GET gateways`, `GET gateways/{id}/datasources`, datasource users and status | [Power BI Gateway REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/gateways) | `modules/gateway.py` |
| Refreshables | `GET admin/capacities/refreshables?$expand=capacity,group` | [Get Refreshables](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/get-refreshables) | `modules/refreshables.py` |
| RefreshHistory | `GET admin/groups?$expand=datasets&$top=5000` | [Get Groups as Admin](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/groups-get-groups-as-admin) | `modules/refreshhistory.py` |
| RefreshHistory | `GET groups/{groupId}/datasets/{datasetId}/refreshes` | [Get Refresh History in Group](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-refresh-history-in-group) | `modules/refreshhistory.py` |
| Roles | `GET admin/groups?$expand=users&$top=5000&$skip={n}` | [Get Groups as Admin](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/groups-get-groups-as-admin) | `modules/roles.py` |

## Microsoft Graph

| Module | Endpoint | Microsoft Learn reference | File |
|---|---|---|---|
| Graph | `GET /users` | [List users](https://learn.microsoft.com/en-us/graph/api/user-list?view=graph-rest-1.0) | `modules/graph.py` |
| Graph | `GET /subscribedSkus` | [List subscribed SKUs](https://learn.microsoft.com/en-us/graph/api/subscribedsku-list?view=graph-rest-1.0) | `modules/graph.py` |
| Graph | `GET /groups` | [List groups](https://learn.microsoft.com/en-us/graph/api/group-list?view=graph-rest-1.0) | `modules/graph.py` |
| Graph | `GET /groups/{groupId}/transitiveMembers/microsoft.graph.user` | [List transitive members](https://learn.microsoft.com/en-us/graph/api/group-list-transitivemembers?view=graph-rest-1.0) | `modules/graph.py` |

## Derived output

| Output | Built from | File |
|---|---|---|
| `lineage_edges/` (flat upstream and downstream edges) | Scanner `getInfo` results (`relations`, report `datasetId`, `datasourceUsages`) | `utility/lineage_edges.py`, called from `modules/catalog.py` |

## Notes

- `modules/catalog_bkbk.py` is a backup copy of `catalog.py` and is not a separate set of endpoints.
- Admin endpoints require the service principal to be in a security group allowed under the Fabric tenant settings for admin APIs.
- Graph calls require Application permissions with admin consent.
- Query strings are abbreviated; see the module source for exact parameters.
