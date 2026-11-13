# Fabric Monitor medallion investigation TODO

Track the proposed event-led investigation layer in the existing `lh_monitor`
Lakehouse. The first event/artifact/execution slice is implemented in notebooks
24/25 and tested offline. Upload, controlled publication and live acceptance
remain pending. Checked implementation items mean code/tests are ready, not
that tables have been deployed to Fabric.

## Baseline and boundaries

- [x] Establish the existing raw files and `dbo.monitor_*` tables as Bronze inputs.
- [x] Build the local FM Observability investigation-model/report prototype.
- [x] Choose separate Silver and Gold schemas in the same schema-enabled Lakehouse.
- [x] Preserve existing Bronze tables, files, collectors and reports without moving or renaming them.
- [ ] Confirm publication, actor/IP access and sharing boundaries before cloud writes.
- [x] Document every non-Admin source: required permissions, caller-visible scope,
      collection boundaries and limitations. Transformations must not imply broader coverage.

## First deliverable

Deliver an evidence-backed trace:

```text
Audit event -> scoped artifact -> exact execution link -> retained activity
                                                        -> reported metrics
                                                        -> explicit evidence gaps
```

- [x] Produce one Gold event case with drillable evidence links.
- [x] Demonstrate the trace with synthetic fixtures before using tenant evidence.
- [x] Explain Bronze/Silver/Gold transformations, preview/publication distinctions
      and the reported execution-coverage gap in a plain-language walkthrough.
- [x] Retain events with missing references or execution evidence.
- [x] Keep historical dependency impact separate from observed runtime movement.

## Silver: normalize and link evidence

- [x] Define and version schemas, natural grains, keys and provenance fields.
- [x] Create `silver.audit_event`: one distinct provider event; normalize UTC
      timestamps, IDs, operations and nullable reported outcomes.
- [x] Deduplicate canonical event content independently of JSON property order.
      Quarantine conflicting content for the same provider event ID.
- [x] Preserve the provider ID or explicitly label a derived full-record hash.
- [ ] Create `silver.actor_identity`: scoped reported identities, preserving
      whether the source was `UserId` or `UserKey`; restrict sensitive identity access.
- [ ] Create `silver.client_ip`: provider-reported values and format validation;
      do not infer geolocation or human identity.
- [x] Create `silver.artifact_observation`: scoped IDs, historical names/types,
      observation timing and source provenance.
- [x] Use tenant/workspace/item identity, never name-only joins.
- [x] Label names observed after an event as later-observed hints, not verified
      event-time names. Do not infer deletion from absence in inventory.
- [x] Create `silver.event_artifact`: one event/reference role, preserving the
      source field and explicit resolution state.
- [ ] Retain `SCOPED_IDENTIFIER`, `IDENTIFIER_REPORTED_NOT_IN_INVENTORY`,
      `UNRESOLVED_SCOPE`, `REPORTED_REFERENCE_ONLY` and `CONFLICT` outcomes.
- [x] Create `silver.execution_observation`: immutable scoped run/poll history;
      distinguish execution IDs from collector run IDs.
- [x] Create `silver.execution_latest`: one latest usable retained execution;
      reject conflicting ties and expose failed/stale polling coverage.
- [x] Create `silver.pipeline_activity`: latest scoped activity observations,
      nullable movement metrics and explicit parent/child run references.
- [x] Create `silver.event_correlation_id`: canonical reported ActivityId/RequestId
      values, source-field identity and validation state.
- [x] Build scoped correlation candidates and flag ambiguous or contradictory matches.
- [x] Create `silver.event_execution_link`: one event/execution pair with exact
      identifier evidence, compatible artifact scope and matching fields.
- [x] Do not promote time/name proximity into exact links or claim the correlated
      event actor is proven to have initiated the run.
- [x] Resolve child-run references only when observed execution identity/scope
      supports them; do not invent child artifacts or workspaces.
- [x] Create `silver.reported_location`: retain reported object/source references;
      redact credentials, query strings and fragments.
- [ ] Keep configured endpoints, reported audit locations and observed runtime
      endpoints distinct. Current activity metrics do not reveal physical sources/sinks.
- [ ] Create `silver.dependency_observation`: direction, resolution, evidence type,
      collection scope and historical timing.
- [ ] Create `silver.evidence_coverage`: distinguish missing, empty, partial,
      failed, invalid and usable evidence.

## Gold: question-led outputs

- [x] Create `gold.event_case`: one event per published build, with reported actor/IP
      keys, outcome, reference/link counts, resolution states and evidence gaps.
- [x] Aggregate artifact references and execution links independently before
      joining them to events; avoid fan-out and preserve unmatched events.
- [x] Create `gold.event_trace_edge`: typed source/target evidence links with
      provenance, basis, resolution and timing. Represent gaps without fabricated links.
- [x] Create `gold.execution_fact`: one scoped execution with latest reported
      status/timing and coverage, not a claim of live status.
- [x] Create `gold.pipeline_activity_fact`: one scoped activity with latest metrics.
      Keep movement metrics at activity/run grain, not additive across correlated events.
- [ ] Create `gold.potential_impact`: cycle-safe shortest paths over eligible
      resolved scanner evidence; preserve historical timing and explicit depth caps.
- [x] Create `gold.evidence_coverage`: build/source/scope assessments and limitations.
- [ ] Provide artifact, actor, IP and date dimensions and explicit bridges for
      an FM-style semantic model; preserve distinct lookup roles.
- [x] Explain that zero supported execution links is not proof that no executions occurred.
- [x] Keep unknown destinations and missing metrics null, with explanatory states.
- [ ] Present potential downstream dependencies separately from actual movement.

## Persistence and integration

- [x] Default transformations to preview-only; require explicit publication.
- [x] Discover Silver's tenant namespace from Fabric execution identity by default;
      allow a manual UUID override and explicit discovery opt-out.
- [x] Carry source paths, content hashes, observation times, collection scope,
      transformation versions and source Delta versions.
- [x] Pin/recheck input versions and raw-file scope during a build.
- [x] Use a shared build ID and readiness gate; expose only a validated Gold build.
- [x] Enforce table ownership, schema compatibility and repeatable writes.
- [x] Document serial-writer expectations and the absence of cross-table transactions.
- [x] Implement Silver/Gold transformation notebook sources and generated upload artifacts.
- [x] Provide self-contained read-only notebook 26 for validated Gold queries and
      separate investigation results per selected event key.
- [x] Keep source-schema synchronization and model refresh separate from rebuilding derived data.
- [ ] Publish only after approval, then connect an investigation semantic model
      without silently replacing existing shared models.
- [ ] Review Lakehouse and semantic-model access/export permissions. Schema
      separation and hashed actor keys are not sufficient security boundaries.

## Acceptance checks

- [x] Duplicate events and repeated polls do not inflate event/run/activity counts.
- [ ] Same-name artifacts in different workspaces remain distinct.
- [x] Conflicting IDs/content and ambiguous correlations are not promoted.
- [x] Missing workspace/item scope remains unresolved.
- [ ] Event time, observation time and legacy folder dates remain distinguishable.
- [x] Historical labels are not presented as verified current or event-time state.
- [x] Events survive missing inventory, jobs, activities or relationship evidence.
- [x] Missing sources differ from present-but-empty sources.
- [ ] Null metrics remain unknown; zero reported metrics remain valid zeros.
- [x] Multiple artifact references or correlated events do not multiply movement metrics.
- [x] Child-run resolution does not assume the parent's artifact/workspace.
- [ ] Configured/static/unresolved dependencies do not become observed runtime I/O.
- [x] Cycles terminate; traversal limits are visible rather than silent.
- [ ] Partial/failed collection and stale observations remain visible in Gold.
- [x] Source changes or incomplete writes prevent a Gold build from becoming ready.
- [ ] No raw actor/IP values, credentials or sensitive source rows enter Git artifacts or logs.
- [ ] Validate persisted table grains, schema/ownership, relationships, live DAX,
      filters and trace explanations before sharing the model.
