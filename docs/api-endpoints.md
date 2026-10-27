# API endpoints used by Fabric Monitor

Source: `env/modules/*.py`. Base URLs and token scopes are defined per cloud in `env/cloud.py`; all calls go through `Context.invokeAPI` in `env/context.py` (some modules call `requests.get` directly).

Base URLs (Commercial):
- Power BI: `https://api.powerbi.com/v1.0/myorg/`
- Fabric: `https://api.fabric.microsoft.com/`
- Graph: `https://graph.microsoft.com/beta`

## Fabric REST API (admin)

| Module | Endpoint | File |
|---|---|---|
| Domains | `GET v1/admin/domains` | `modules/domains.py` |
| Domains | `GET v1/admin/domains/{domainId}/workspaces` | `modules/domains.py` |
| FabricItems | `GET v1/admin/items` | `modules/fabricitems.py` |
| Workspaces | `GET v1/admin/workspaces` | `modules/workspaces.py` |
| Roles | `GET v1/admin/workspaces` | `modules/roles.py` |
| Tenant | `GET v1/admin/tenantsettings` | `modules/tenant.py` |
| FabricItems (lineage, beta) | `GET v1/workspaces/{ws}/items/{id}/relations/upstream?beta=true` and `/relations/downstream?beta=true` | `modules/fabricitems.py` |

## Fabric REST API (workspace-level, needs workspace access)

| Module | Endpoint | File |
|---|---|---|
| ItemJobs | `GET v1/workspaces/{ws}/items/{id}/jobs/instances` | `modules/itemjobs.py` |
| ItemJobs | `POST v1/workspaces/{ws}/items/{id}/getDefinition` (long-running operation) for CopyJob and DataPipeline | `modules/itemjobs.py` |
| ItemJobs | `GET v1/workspaces/{ws}/datapipelines/pipelineruns/{runId}/queryactivityruns` (recurses into child pipelines) | `modules/itemjobs.py` |

## Power BI REST API

| Module | Endpoint | File |
|---|---|---|
| Activity | `GET admin/activityevents?startDateTime=...&endDateTime=...` (continuation URIs) | `modules/activity.py` |
| Apps | `GET admin/apps?$top=5000&$skip=0` | `modules/apps.py` |
| Capacity | `GET admin/capacities` | `modules/capacity.py` |
| CapacityMetrics | `GET admin/capacities/metrics`, `POST datasets/{datasetId}/executeQueries` | `modules/capacity_metrics.py` |
| Catalog | `GET admin/workspaces/modified?...` | `modules/catalog.py` |
| Catalog | `POST admin/workspaces/getInfo?lineage=True&datasourceDetails=True&datasetSchema=True&datasetExpressions=True` | `modules/catalog.py` |
| Catalog | `GET admin/workspaces/scanStatus/{scanId}` | `modules/catalog.py` |
| Catalog | `GET admin/workspaces/scanResult/{scanId}` | `modules/catalog.py` |
| Gateway | `GET gateways` | `modules/gateway.py` |
| Gateway | `GET gateways/{id}/datasources` | `modules/gateway.py` |
| Gateway | `GET gateways/{gatewayId}/datasources/{id}`, `/users`, `/status` | `modules/gateway.py` |
| Refreshables | `GET admin/capacities/refreshables?$expand=capacity,group` | `modules/refreshables.py` |
| RefreshHistory | `GET admin/groups?$expand=datasets&$top=5000` | `modules/refreshhistory.py` |
| RefreshHistory | `GET groups/{groupId}/datasets/{datasetId}/refreshes` | `modules/refreshhistory.py` |
| Roles | `GET admin/groups?$expand=users&$top=5000&$skip={n}` | `modules/roles.py` |

## Microsoft Graph

| Module | Endpoint | File |
|---|---|---|
| Graph | `GET /users` | `modules/graph.py` |
| Graph | `GET /subscribedSkus` | `modules/graph.py` |
| Graph | `GET /groups` | `modules/graph.py` |
| Graph | `GET /groups/{groupId}/transitiveMembers/microsoft.graph.user` | `modules/graph.py` |

## Derived output

| Output | Built from | File |
|---|---|---|
| `lineage_edges/` (flat upstream and downstream edges) | Scanner `getInfo` results (`relations`, report `datasetId`, `datasourceUsages`) | `utility/lineage_edges.py`, called from `modules/catalog.py` |

## Notes

- `modules/catalog_bkbk.py` is a backup copy of `catalog.py` and is not a separate set of endpoints.
- Admin endpoints require the service principal to be in a security group allowed under the Fabric tenant settings for admin APIs.
- Graph calls require Application permissions with admin consent.
- Query strings are abbreviated; see the module source for exact parameters.
