# Updating the Fabric Monitor

This guide explains how to find the version you run, how to upgrade, how to bump the version, and how to roll back.

There is **no automatic remote update check**, by design. The monitor never makes a network call to look for new versions. You decide when to upgrade.

## Find the current version

The top-level `VERSION` file is the single source of truth. The baseline version is `0.2.0`.

- Read the file: `cat VERSION`.
- Check the startup log. `app/monitor.py` logs this line at the start of each run:

  ```
  Starting Fabric Monitor run (version 0.2.0)
  ```

`env/version.py` `get_version()` reads the file and strips whitespace. It returns `"unknown"` if the file is missing, unreadable or empty.

> INFO logs may not appear unless logging is configured for your host. If you do not see the line, check your logging level before concluding the version is missing.

## Read the changelog first

Read [changelog.md](changelog.md) for every entry newer than your version. Look for breaking changes and behaviour changes. For example, E7 rewrote the `CapacityMetrics` module and changed its output format. Consumers of the old files must be updated.

## Upgrade steps

1. Pull the new code.
2. Review [changelog.md](changelog.md) and [configuration-reference.md](configuration-reference.md). Add any new environment keys to your `.env` or Function App settings.
3. Install the pinned dependencies:

   ```
   pip install -r requirements.txt
   ```

4. Run the tests from the repository root:

   ```
   .venv/bin/python -m unittest discover -s tests -t .
   ```

5. Deploy (see [deployment.md](deployment.md)).
6. Verify: the startup log shows the new version, and the run completes cleanly with no module failures.

### Function App deploys

The `VERSION` file ships with Function App deploys. Neither `azure.yaml` nor `.funcignore` excludes it.

### Legacy retry and token-renewal changes

When deploying the legacy backoff/authentication changes, let the active run end
and restart/redeploy the collector runtime to load the new code. Do not clear
collector state or request-gate ledgers to force an early retry.
`API_MAX_RETRY_DELAY` caps fallback backoff only: a valid longer `Retry-After`
is honored in full, so review hosting timeouts and schedules. Legacy cooldowns
are per-Context/in-memory and do not survive restart or coordinate other workers;
newer Fabric durable gates retain their own controls. See
[retry/authentication behavior](configuration-reference.md#throttling-and-retries).

### Numbered Fabric analytics notebooks

Import updated generated `.ipynb` artifacts from `notebooks/` and review their
parameter cells; a local Python upgrade does not update already imported Fabric
notebooks. Keep executed outputs and secrets out of source control. Follow the
[notebook walkthrough](../notebooks/notebook-guide.md) and
[shared table contract](../notebooks/README.md#shared-contract-and-reruns).

Existing managed tables must pass ownership/schema/content checks. Do not
overwrite them or weaken those checks during an upgrade; choose a separate
supported prefix for an intentional incompatible contract. Notebook 06 preserves
the original 10-table and opt-in 25-table scopes and can opt into all 48. A new
scope requires a new baseline name after its writers have published; do not
overwrite a prior baseline or vacuum its retained Delta versions during comparison.

### Container caveat

The container images (`containers/Dockerfile` and `containers/Dockerfile2`) copy only `app/`. They do not copy `VERSION` or `env/`. The missing `env/` is a pre-existing gap. Until it is fixed, a container reports the version as `unknown`.

When the images are fixed, add these lines:

```
COPY VERSION .
COPY env ./env
```

## Bump the version

When you cut a release:

1. Edit `VERSION` to the new `X.Y.Z` value. The version check test requires strict `X.Y.Z`.
2. Add an entry at the top of [changelog.md](changelog.md) that names the new version and any breaking changes.
3. Run the tests.

## Roll back

Redeploy the previous code (and previous `VERSION`). State files record a `lastRun` per module, and a module that fails does not advance its `lastRun`, so the next run retries the same window. Check the changelog for output-format changes (such as E7) before you roll back, because files written by the newer version stay in storage.
