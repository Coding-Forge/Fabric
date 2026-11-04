# Monitor vs FUAM: Side-by-Side

FUAM = `fabric-toolbox/monitoring/fabric-unified-admin-monitoring` (Fabric Unified Admin Monitoring).
Monitor = this repo. Based on a static read; nothing was executed.

## Architecture

| Aspect | Monitor | FUAM |
|---|---|---|
| Form | Azure Functions v2 (Python), timer trigger | Fabric items: 24 notebooks, 17 pipelines, 5 semantic models, 5 reports |
| Runs in Fabric? | No (Blob, Lakehouse via ADLS, or local) | Yes, required (Spark, `notebookutils`, `sempy`, lakehouse mounts, `TridentNotebook` pipelines) |
| Schedule | Daily 02:00 UTC, `run_on_startup=True`; optional per-module cron in `state.yaml` | Fabric pipeline schedules |
| Auth | One service principal, MSAL secret, token not cached, no Key Vault | Key Vault SP or notebook-owner identity (`getToken('pbi')`) |
| Storage | Raw JSON at `<module>/YYYY/MM/DD/<file>` | Bronze to silver to gold Delta tables in Lakehouse |
| State | `state.yaml` (`lastRun`) | Pipeline day arrays, Delta merge, status tables |
| Deployment | Bicep (`infra/`), azd, Docker, `.azdo` pipeline | `scripts/Deploy_FUAM.ipynb` (`fab` CLI), `config/deployment_*.yaml` |
| Reporting | `Fabric/*.pbit`, `FabricFlow.json` | Core, Item, Gateway, SQL-endpoint and SM-analyzer reports, Direct Lake models |

## Data coverage

| Domain | Monitor | FUAM |
|---|---|---|
| Capacities | Raw `admin/capacities` | `01_Transfer_Capacities_Unit`, history snapshots, regions |
| Workspaces / inventory | Scanner API, raw (`catalog.py`) | Incremental scanner inventory, gold tables |
| Activities | Raw per-day JSON | Day loop, silver/gold, aggregation, anonymisation |
| Tenant settings | Raw dump | Dump plus delegated overrides |
| Gateways | Yes (`gateway.py`) | File-based gateway report only |
| Refresh history | Yes (`refreshhistory.py`) | Capacity refreshables only |
| Apps | Yes | No |
| Graph / Entra (users, SKUs, groups) | Yes | No |
| Domains | Yes (buggy) | Yes (`01_Transfer_Domains_Unit`) |
| Capacity Metrics | One DAX query on `CUDetail` | Timepoints, item kind, item operation; version detection |
| Git connections | No | Yes |
| Tags | No | Yes |
| Items | Raw `admin/items` | Active items, item analyzer |
| Widely shared / published-to-web | No | Yes |
| Spark / Lakehouse tooling | No | SM optimisation (BPA, VertiPaq), lakehouse optimise and backup |
| Cost | No | Via capacity metrics only |

## Engineering practices

| Aspect | Monitor | FUAM |
|---|---|---|
| Retry / throttling | None in `Context.invokeAPI`; fixed sleeps in catalog | `RequestWithRetry` honours `Retry-After`; 16 parallel scans; 500 requests/hour limit |
| Incremental loads | `lastRun` per module; catalog full scan every run (bug) | Delta merge, `Snapshot_Date` delete-then-append |
| Schema / modelling | None (raw JSON) | Table definitions, semantic models, calendar table |
| Privacy | None | Anonymise user fields after N days |
| Observability | `print`, App Insights | Pipeline run history, version check, changelog |
| Update path | Manual | `Check_FUAM_Version`, update guide |
| Tests | None | None |
| Known weaknesses | Bugs listed in `enhancement-plan.md` section A | Hard-coded workspace names/GUIDs, private `sempy` API, duplicated auth code, interactive-user deployment |

## Where Monitor is ahead

- Runs anywhere (no Fabric capacity CU cost).
- Graph/Entra data, gateway details, refresh history, apps.
- Infrastructure as code (Bicep/azd/Docker) with managed identity for storage.

## Where FUAM is ahead

- Modelled data (silver/gold, snapshots) and ready-made reports.
- Throttle-aware, incremental extraction.
- Wider coverage of governance data (Git, tags, delegated settings, widely shared links).
- Capacity Metrics depth and a defined update process.

See `enhancement-plan.md` for the work items.
