# Consuming Monitor Delta tables: Eventhouse, Event Hubs and Splunk

This guide separates available Fabric platform options from integrations
implemented in this repository. Start with the
[notebook walkthrough](../notebooks/notebook-guide.md) to create the Delta tables.

## Current implementation boundary

The numbered suite ends at curated Delta tables, notebook visualizations and
validation. It does **not** contain an Event Hubs publisher, native Eventhouse
ingestion job or Splunk export. No destination resources, credentials, connectors,
cloud schedules or network permissions are created by the notebooks.

| Service | Role | Required for Splunk delivery? |
|---|---|---|
| Lakehouse / Delta tables | Persist curated Monitor observations | Source for the proposed direct route |
| Fabric Eventhouse / KQL database | Query and analyze data using KQL | No |
| Azure Event Hubs | Buffer/transport events for downstream consumers | Only if this delivery mechanism is selected |
| Splunk | Consume and index approved records | Destination in the proposed route |

**Eventhouse and Event Hubs are different services.** An Eventhouse endpoint is
not an Event Hub, and exposing a Delta table to KQL does not start a message stream.

## Option 1: query Delta data with KQL

For analysis without a separately maintained native KQL copy, Fabric supports:

- A Lakehouse **Analyze data with > Eventhouse endpoint**, which exposes tables
  through shortcuts in a linked read-only KQL database and synchronizes discovery.
- A **OneLake shortcut** created in an existing KQL database, targeting a
  Lakehouse table. Query acceleration can be configured where supported.

For a shortcut named `dbo_monitor_activity_events`, a query is:

```kql
external_table("dbo_monitor_activity_events")
| take 10
```

Use the exact shortcut name shown in the database Explorer; schema prefixes
depend on the source. These are external Delta references, not ordinary native
KQL ingestion. Preserve the source's historical grain and privacy restrictions.
Check both source and endpoint permissions and review acceleration/cache costs.
Availability, region/capacity support and actual private-network connectivity
must be verified in the target environment.

If native KQL tables are needed instead, that requires a separately designed
ingestion, schema, retention and duplicate-handling workflow.

References: [Eventhouse endpoint](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/eventhouse-as-endpoint),
[KQL database OneLake shortcuts](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/onelake-shortcuts).

## Option 2: proposed direct delivery to Splunk through Event Hubs

KQL is not necessary for this route:

```text
API collectors -> raw JSON -> transformation notebooks -> Delta tables
                                                        |
                                                        v
                                            Separate publisher notebook
                                                        |
                                                        v
                                                Azure Event Hub
                                                        |
                                                        v
                                                Splunk consumer
```

A separate publisher would keep delivery state and retries out of the 19
transformation notebooks. Its cadence would follow source collection and
transformation availability: sending events does not make periodic snapshots
instantaneous real-time API telemetry.

Before implementing or enabling publication, agree:

| Decision | Required behavior |
|---|---|
| Dataset/field scope | Explicit approved allowlist; do not automatically send all 48 datasets or sensitive identifiers |
| Execution | Scheduled incremental runs versus a long-running streaming session, including capacity/runtime budgets |
| Initial history | Backfill existing rows versus future changes only; define an explicit starting boundary |
| Producer identity | Authorized source reads and Event Hubs send access; store secrets in an approved store, never notebook source/output |
| Delivery state | Persistent checkpoints/export ledger separate from collector controls and validation baselines |
| Message contract | Versioned JSON carrying dataset identity and `observation_id`, with batching and message-size handling |
| Recovery | Advance delivery state after acknowledged sends, with bounded retries, replay and duplicate handling |
| Splunk input | Supported connector for the customer's deployment, a dedicated consumer group, authentication, checkpoints, index and sourcetype |
| Network and operations | Verified private/public access policy, DNS, retention, monitoring, outage recovery and costs |

Plan for **at-least-once delivery**. A successful send followed by a crash before
checkpoint persistence can be replayed. Keep `(dataset, observation_id)` available
for idempotent downstream handling; consumer checkpoints alone do not eliminate
producer duplicates.

Do not use `max(observed_at_utc)` as the sole export watermark. Legacy
observations can have null exact collection timestamps, and business event time
is not a reliable record-arrival boundary. An implementation needs a suitable
Delta commit/change-feed strategy or an observation-ID delivery ledger. Change
Data Feed is not enabled by these notebooks and must not be assumed available.
Notebook-06 baselines test rerun stability; they are not delivery checkpoints.

Typical least-privilege roles are **Azure Event Hubs Data Sender** for a publisher
and **Azure Event Hubs Data Receiver** for a consumer; source access and connector
setup permissions are separate. A workspace Member role alone does not grant
those Azure data-plane permissions. Splunk Cloud Data Manager supports Event Hubs
onboarding; other deployments need a supported input/add-on matched to their
version and operating model.

References: [Event Hubs Python producer SDK](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-python-get-started-send),
[Splunk Event Hubs onboarding](https://help.splunk.com/en/splunk-cloud-platform/ingest-data-from-cloud-services/data-inputs-user-manual/1.16/microsoft-azure-data/onboarding-for-azure-data-in-data-manager).

## If KQL must be the publisher's source

A separately authorized application could query KQL and publish results using
the Event Hubs SDK. This adds a query/export dependency rather than a native
KQL-to-Event-Hubs switch. Kusto continuous export targets external storage; it
does not directly publish to an Event Hub. Shortcuts should not be treated as
native ingested tables with an ingestion-time cursor.

See [Kusto continuous export](https://learn.microsoft.com/en-us/kusto/management/data-export/continuous-data-export?view=microsoft-fabric).

## Private networking is an independent acceptance gate

Verify publisher-to-source, publisher-to-Event-Hubs and Splunk-consumer-to-hub
connectivity separately, including DNS, identity and approved runtime networking.
Do not assume a managed Splunk Cloud connector can reach a private namespace,
that a shortcut bypasses policy, or that successful public OneLake access proves
a private-only deployment. Do not enable public access as a workaround for an
unvalidated private path.

Current work items and approval boundaries are tracked in the
[analytics roadmap](enhancement-plan.md#f-fabric-notebook-analytics-and-optional-customer-integration).
