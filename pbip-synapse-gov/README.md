# Azure Government PBIP Copies

These PBIP projects are copies of the local reports configured to read Fabric Monitor output from Azure Government ADLS Gen2 / Blob-backed storage.

## Projects

| Project | PBIP file | Purpose |
|---|---|---|
| Audits | `Audits\Activities.pbip` | Activity, audit, Graph, and catalog governance reporting |
| Catalog | `Catalog\Schema.pbip` | Power BI / Fabric schema and catalog inventory |
| Capacity_Gateways | `Capacity_Gateways\CapacityGateways.pbip` | Capacity, gateway, datasource, and impact mapping |

## Required Power Query parameters

Update these parameters in Power BI Desktop before refresh:

| Parameter | Example |
|---|---|
| `MonitorStorageAccountName` | `mystorageacct` |
| `MonitorStorageContainerName` | `monitor` |
| `MonitorStorageRootPath` | `fabric-monitor` |
| `MonitorDfsEndpointSuffix` | `core.usgovcloudapi.net` |

The reports use:

```powerquery
AzureStorage.DataLake("https://" & MonitorStorageAccountName & ".dfs." & MonitorDfsEndpointSuffix)
```

and filter files under:

```text
/<container>/<root>/<module>/
```

For Commercial Azure, change `MonitorDfsEndpointSuffix` to `core.windows.net`.

## Expected storage root

```text
fabric-monitor/
  activity/
  apps/
  capacity/
  catalog/scans/
  catalog/snapshots/
  gateways/
  graph/
  refreshables/
  refresh_history/
```

