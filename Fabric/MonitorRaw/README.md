# MonitorRaw (Power BI Project)

> **Validation status: this project has NOT been validated by a Power BI Desktop refresh.** It was written and reviewed as text. See [Validation status](#validation-status) before you rely on it.

## What it is

`MonitorRaw.pbip` is a Power BI Project (PBIP) that reports directly on the raw JSON files the monitor writes. It has no silver/gold layer (plan item E4 is not pursued); every table is built in Power Query from the dated module folders.

- Semantic model: `MonitorRaw.SemanticModel/` in TMDL format, **Import** mode.
- Report: `MonitorRaw.Report/` in PBIR format, 8 pages.
- Source: a local folder (the `LOCAL_OUTPUT_PATH` output) or Azure Blob Storage, chosen with the `SourceType` parameter.

## Prerequisites

- Power BI Desktop on Windows, a recent release. Older builds may not open PBIR/TMDL projects.
- In Desktop, under **File > Options and settings > Options > Preview features**, enable the **Power BI Project (.pbip) save option** and the **TMDL view** if your Desktop version still lists them as previews, then restart Desktop. Newer versions may have these on already.
- Monitor output to read: either a folder produced with `LOCAL_OUTPUT_PATH` (see [local-development.md](../../docs/local-development.md#local-folder-poc-mode)) or a Blob container written by the monitor.

## Open the project

Open `Fabric/MonitorRaw/MonitorRaw.pbip` in Power BI Desktop. Set the parameters (below), then refresh.

## Parameters

| Parameter | Used when | Meaning |
|-----------|-----------|---------|
| `SourceType` | always | `Local` or `Blob`. Default `Local`. |
| `LocalFolder` | `Local` | Absolute path of the folder that contains the module folders (`activity`, `capacity_metrics`, ...). This is the `LOCAL_OUTPUT_PATH` folder, or the container root. Default is a placeholder, `C:\path\to\monitor-output`. |
| `BlobAccountUrl` | `Blob` | Storage account URL, `https://<storage-account>.blob.core.windows.net/`. |
| `BlobContainer` | `Blob` | Container name (`STORAGE_ACCOUNT_CONTAINER_NAME`). |
| `BlobRootPath` | `Blob` | Root path inside the container (`STORAGE_ACCOUNT_CONTAINER_ROOT_PATH`). Leave empty when the module folders sit directly in the container. |

Replace the placeholders with your own values. Do not commit your values, SAS tokens or account keys.

## How dates are determined

Dates come from the `<module>/YYYY/MM/DD` folder layout (UTC), **not** from file modified time. Copying or syncing files does not change the dates. For `delegatedsettings` the scope folder sits before the date (`delegatedsettings/<scope>/YYYY/MM/DD/`).

## Tables

| Table | Module folder | Notes |
|-------|---------------|-------|
| Capacity Metrics | `capacity_metrics` | One row per capacity and timepoint. Utilization and carry-over groups are merged. |
| Capacities | `capacity_metrics` | Capacity dimension (id, name, SKU), latest run wins. |
| Activity | `activity` | Lean activity event table. |
| Git Connections | `gitconnections` | Latest snapshot. |
| Tags | `tags` | Latest snapshot. |
| Delegated Settings | `delegatedsettings` | Latest snapshot per scope; one row per override. |
| Widely Shared Links | `widelysharedlinks` | Latest snapshot per endpoint (organization, published to web). |
| Calendar | derived | Dates found in Capacity Metrics and Activity, plus today. |

## Report pages

1. Capacity utilization
2. Carry-over
3. Activity overview
4. Git connections
5. Tags
6. Delegated settings
7. Widely shared links
8. About and setup

## Data semantics

- **Latest snapshot (E5 modules).** Git connections, tags, delegated settings and widely shared links write a full copy each day. The model keeps only the files of the most recent date (per scope or endpoint where there is one). Days are **not summed**.
- **Capacity metrics reruns.** The latest run wins per (capacity, group, timepoint), so a rerun for the same day is not double counted. The run is taken from the file name prefix.
- **Carry-over.** Carry-over columns are empty when the Capacity Metrics app version does not expose them; the report shows a status message.
- **Malformed JSON.** A file that cannot be parsed stays as a row with the `Load Error` column filled in. The `Load Errors` measure counts them across tables. Empty files give no rows and no error.

## Things that can surprise you

- **Wrong `LocalFolder` gives empty tables, not an error.** If `LocalFolder` points to an existing folder that has no module subfolders, every table loads empty without an error. A module folder that does not exist is treated as empty. Check row counts after the first refresh.
- **Privacy.** The Activity table contains `UserId` (a UPN or email address), which is personal data. Restrict who can open the report and the file, and treat published copies accordingly. Blob retention is optional and off by default; see [deployment.md](../../docs/deployment.md#key-vault-reference-and-blob-retention-e09-and-e08) and the [E8 outcome](../../docs/enhancement-plan.md#e8-and-e9-outcome). Retention deletes whole blobs by age. It is not anonymisation.
- **Service refresh.** A local folder source needs an on-premises data gateway to refresh in the Power BI service. Blob mode does not.
- **Blob credentials.** In Blob mode, Desktop asks for credentials (for example an account key or organizational account) the first time. Enter them in Desktop; they are not stored in the project.
- **`.gitignore`.** The repository root `.gitignore` ignores `*.json`. PBIP and PBIR definitions are JSON, so `Fabric/MonitorRaw/.gitignore` re-includes them and ignores Desktop's local `.pbi/` state and cache.

## Validation status

**This project was NOT validated by a Power BI Desktop refresh.** It was never opened or refreshed in Desktop. Code Reviewer approved it as a static review. Treat it as a starting point that still needs a Desktop check.

Desktop-only risks listed by the reviewer:

- **Blob `Name` column.** The Blob source assumes `Name` is the full virtual path of the blob. If it is not, the Blob tables load empty.
- **Credential or privacy-level prompt in Local mode.** The unused Blob placeholder may still trigger a credential or privacy-level prompt in Local mode.
- **Missing-folder detection.** It relies on the `DataSource.NotFound` error reason. A different reason would raise an error instead of giving an empty table.
- **Percent columns.** They assume fractions (for example `0.85`), formatted as `0.0%`. Values on a 0-100 scale would display 100 times too large.
- **Time zones.** `ToUtcDateTime` handles only `Z` and `+` offsets. Negative offsets are not converted.
- **Activity duplicates.** There is no Event Id dedupe for Activity. A re-fetch of a day with fewer pages could double count events.
- **Theme.** The theme reference is `CY24SU10` without a static resource. Desktop may prompt or warn.
- **Visual schema versions.** The visual schema versions are unconfirmed.

**Field names not verified.** The field names for **Git connections, Tags, Delegated settings and Widely shared links** were **not** verified against real payloads. These tables read fields through a null-tolerant accessor, so a wrong name produces a null column, not an error. A table can look healthy and still have empty columns. Check one real file per module and compare it with the table columns.

## Acceptance checklist

Run this in Desktop and record the results.

- [ ] Open `MonitorRaw.pbip`. The project loads without errors.
- [ ] **Local mode.** Set `SourceType = Local` and `LocalFolder` to a `LOCAL_OUTPUT_PATH` sample. Refresh. No credential or privacy prompt, or you can resolve it.
- [ ] Row counts are plausible for each table (Capacity Metrics, Capacities, Activity, Git Connections, Tags, Delegated Settings, Widely Shared Links, Calendar). Compare them with the files on disk.
- [ ] `Load Errors` is 0 for good data. Put in one malformed file and confirm it shows as a Load Error row.
- [ ] For each of the four E5 tables, open one real JSON file and confirm the columns are filled, not null.
- [ ] Point `LocalFolder` to a folder with no module subfolders and confirm tables are empty (expected), then restore it.
- [ ] **Blob mode.** Set `SourceType = Blob` with `BlobAccountUrl`, `BlobContainer` and `BlobRootPath`. Enter credentials. Refresh. Row counts match Local mode for the same data.
- [ ] All 8 pages render with no visual errors.
- [ ] Reconcile one capacity's utilization for one day against the Capacity Metrics app (percent values are fractions, not x100).
- [ ] Confirm the Activity row count for one day against the source files (no duplicates).
