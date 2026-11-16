"""Remaining collector modules: allowlisted scalar facts, no collection or mutation."""

import math
import re
from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID

from notebooks.monitor_analytics import canonical, records, row, sha256, text, utc
from notebooks.monitor_estate_analytics import (
    estate_count,
    estate_optional,
    estate_optional_records,
    estate_records,
    estate_row,
)
from notebooks.monitor_fabric_runtime import latest_frame, plot_counts, to_frame

MODULE_DOMAINS = {
    "apps": ("apps",),
    "capacity": ("capacities", "capacity_metric_observations"),
    "directory": (
        "directory_users",
        "directory_groups",
        "group_memberships",
        "user_licenses",
        "subscribed_skus",
    ),
    "roles": ("workspace_role_scopes", "workspace_role_assignments"),
    "settings": (
        "tenant_settings",
        "delegated_setting_scopes",
        "delegated_setting_overrides",
        "tenant_setting_groups",
    ),
    "domains": ("domains", "domain_workspaces"),
    "git": ("workspace_git_connections",),
    "tags": ("tags",),
    "sharing": ("organization_shares", "publish_to_web_shares"),
    "deployments": (
        "deployment_pipelines",
        "deployment_operation_resources",
        "deployment_operations",
    ),
}
MODULE_SOURCES = {
    "apps": ("catalog",),
    "capacity": ("capacity", "capacity_metrics"),
    "directory": ("graph",),
    "roles": ("roles",),
    "settings": ("tenant", "delegatedsettings"),
    "domains": ("domains",),
    "git": ("gitconnections",),
    "tags": ("tags",),
    "sharing": ("widelysharedlinks",),
    "deployments": ("fabricdeploymentpipelineoperations",),
}
MODULE_LIMITS = {
    "apps": "App inventory only; app audiences/access and complete paging are not established.",
    "capacity": "Metrics app extraction is opt-in. Values/units are unchanged; naive timepoints have unknown UTC. Snapshots are not additive KPIs.",
    "directory": "Groups/members are optional and capped; membership is transitive USERS only. IDs are not anonymous; names, UPNs and mail are excluded.",
    "roles": "Observed workspace roles, not item grants or effective access. Omitted users are unknown, not zero assignments.",
    "settings": "Observed settings/group rules, not computed effective policy or precedence. Missing override collections stay unknown.",
    "domains": "The collector omits domains with no workspaces. Derived domain inventory is therefore incomplete.",
    "git": "Observed repository/branch metadata, not source code or sync health proof. Owners/directories are pseudonyms; URLs/credentials are excluded.",
    "tags": "Tag definitions only; item/tag assignments are not collected.",
    "sharing": "Observed organization/public exposures, not complete access or verified live links. Sharer identities and link URLs are excluded.",
    "deployments": "Caller-visible pipelines; operation history needs pipeline Admin and exposes up to 20 recent deployments. Polling gaps cannot be recovered.",
}
MODULE_ARTIFACTS = {
    "apps": ("apps.json",),
    "directory": (
        "users.json",
        "groups.json",
        "groupmembers.json",
        "userlicenses.json",
        "subscribedskus.json",
    ),
    "roles": (),
    "capacity": (),
    "deployments": (),
    "settings": (
        "tenant-settings.json",
        "capacities.json",
        "domains.json",
        "workspaces.json",
    ),
    "domains": ("domains.json",),
    "git": ("gitconnections.json",),
    "tags": ("tags.json",),
    "sharing": (
        "widelysharedlinks_organization.json",
        "widelysharedlinks_publishedtoweb.json",
    ),
}
METRIC_NAMES = {
    "CU limit",
    "SKU CU by timepoint %",
    "Background billable CU %",
    "Interactive billable CU %",
    "SKU CU by timepoint",
    "Background non billable CU %",
    "Interactive non billable CU %",
    "Carry over add %",
    "Carry over burndown %",
    "Cumulative carry over %",
    "Expected burndown in minutes",
}


def module_source_date(doc):
    parts = PurePosixPath(doc["path"]).parts
    offset = 2 if parts[0] in {"catalog", "delegatedsettings"} else 1
    if parts[0] == "catalog" and parts[1] != "snapshots":
        raise ValueError("Not an app snapshot")
    if parts[0] == "delegatedsettings" and parts[1] not in {
        "capacities",
        "domains",
        "workspaces",
    }:
        raise ValueError("Unknown delegated scope")
    expected = 6 if parts[0] == "fabricdeploymentpipelineoperations" else offset + 4
    if len(parts) != expected:
        raise ValueError("Unexpected module artifact path")
    date = "/".join(parts[offset : offset + 3])
    if not re.fullmatch(r"\d{4}/\d{2}/\d{2}", date):
        raise ValueError("Unexpected module date partition")
    return datetime.strptime(date, "%Y/%m/%d").strftime("%Y-%m-%d")


def module_row(dataset, doc, key, **values):
    return estate_row(dataset, doc, key, source_date=module_source_date(doc), **values)


def module_object(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("Invalid metadata object")
    return value


def module_strings(value):
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError("Invalid string collection")
    return canonical(value)


def module_key(value):
    if value is None:
        return None
    value = text(value)
    try:
        return str(UUID(value))
    except ValueError:
        return "sha256:" + sha256(value.casefold().encode())


def module_time(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(text(value).replace("Z", "+00:00"))
    return utc(value) if parsed.tzinfo is not None else None


def module_duration(start, end):
    if start is None or end is None:
        return None
    delta = (
        datetime.fromisoformat(end.replace("Z", "+00:00"))
        - datetime.fromisoformat(start.replace("Z", "+00:00"))
    ).total_seconds()
    return delta if delta >= 0 else None


def module_apps(doc, pending):
    if PurePosixPath(doc["path"]).name != "apps.json":
        raise ValueError("Unexpected app file")
    for item in estate_records(doc):
        identity = text(item["id"])
        pending["apps"].append(
            module_row(
                "apps",
                doc,
                identity,
                app_id=identity,
                app_name=estate_optional(item.get("name")),
                workspace_id=estate_optional(item.get("workspaceId")),
                last_update_utc=module_time(item.get("lastUpdate")),
            )
        )


def module_capacity(doc, pending):
    if doc["path"].split("/")[0] == "capacity":
        if not re.fullmatch(
            r"\d{8}_\d+\.capacity\.json", PurePosixPath(doc["path"]).name
        ):
            raise ValueError("Unexpected capacity file")
        for item in estate_records(doc):
            identity = text(item["id"])
            pending["capacities"].append(
                module_row(
                    "capacities",
                    doc,
                    identity,
                    capacity_id=identity,
                    capacity_name=estate_optional(item.get("displayName")),
                    sku=estate_optional(item.get("sku")),
                    state=estate_optional(item.get("state")),
                    region=estate_optional(item.get("region")),
                )
            )
        return
    value = doc["value"]
    if not isinstance(value, dict) or doc["issue"]:
        raise TypeError("Invalid metrics envelope")
    capacity = text(value["capacityId"])
    UUID(capacity)
    group = text(value["group"])
    date = datetime.strptime(text(value["date"]), "%Y-%m-%d").strftime("%Y-%m-%d")
    filename = f"{module_source_date(doc).replace('-', '')}_{capacity}_{group}_{date.replace('-', '')}.capacity_metrics.json"
    if (
        group not in {"utilization", "carryover"}
        or PurePosixPath(doc["path"]).name != filename
    ):
        raise ValueError("Metrics identity does not match artifact")
    for item in records(value["rows"]):
        timepoint = item.get("Timepoints[Timepoint]", item.get("[Timepoint]"))
        raw_time = text(timepoint)
        time_utc = module_time(raw_time)
        metrics = [name for name in sorted(METRIC_NAMES) if "[" + name + "]" in item]
        if not metrics:
            raise ValueError("No supported returned metrics")
        for name in metrics:
            number = item["[" + name + "]"]
            if number is not None and (
                type(number) not in (int, float) or not math.isfinite(number)
            ):
                raise ValueError("Invalid metric value")
            pending["capacity_metric_observations"].append(
                module_row(
                    "capacity_metric_observations",
                    doc,
                    [raw_time, name],
                    capacity_id=capacity,
                    sku=estate_optional(value.get("sku")),
                    metric_group=group,
                    metric_date=date,
                    timepoint_raw=raw_time,
                    timepoint_utc=time_utc,
                    metric_name=name,
                    metric_value=float(number) if number is not None else None,
                )
            )


def module_directory(doc, pending):
    name = PurePosixPath(doc["path"]).name
    if name not in MODULE_ARTIFACTS["directory"]:
        raise ValueError("Unexpected directory file")
    for item in estate_records(doc):
        if name == "users.json":
            identity = module_key(text(item["id"]))
            licenses = estate_optional_records(item.get("assignedLicenses"))
            pending["directory_users"].append(
                module_row(
                    "directory_users",
                    doc,
                    identity,
                    principal_id=identity,
                    account_enabled=estate_optional(item.get("accountEnabled"), bool),
                    user_type=estate_optional(item.get("userType")),
                    assigned_license_count=len(licenses)
                    if licenses is not None
                    else None,
                )
            )
        elif name == "groups.json":
            identity = module_key(text(item["id"]))
            pending["directory_groups"].append(
                module_row(
                    "directory_groups",
                    doc,
                    identity,
                    group_id=identity,
                    security_enabled=estate_optional(item.get("securityEnabled"), bool),
                    mail_enabled=estate_optional(item.get("mailEnabled"), bool),
                    group_types_json=module_strings(item.get("groupTypes")),
                    is_audience_group=estate_optional(
                        item.get("isPowerBIAudienceGroup"), bool
                    ),
                )
            )
        elif name == "groupmembers.json":
            group, principal = (
                module_key(text(item["groupId"])),
                module_key(text(item["memberId"])),
            )
            pending["group_memberships"].append(
                module_row(
                    "group_memberships",
                    doc,
                    [group, principal],
                    group_id=group,
                    principal_id=principal,
                    membership_kind="transitive_user",
                    is_audience_group=estate_optional(
                        item.get("isPowerBIAudienceGroup"), bool
                    ),
                )
            )
        elif name == "userlicenses.json":
            principal, sku = module_key(text(item["userId"])), text(item["skuId"])
            pending["user_licenses"].append(
                module_row(
                    "user_licenses",
                    doc,
                    [principal, sku],
                    principal_id=principal,
                    sku_id=sku,
                    disabled_plans_json=module_strings(item.get("disabledPlans")),
                )
            )
        else:
            sku = text(item["skuId"])
            units = module_object(item.get("prepaidUnits"))
            pending["subscribed_skus"].append(
                module_row(
                    "subscribed_skus",
                    doc,
                    sku,
                    sku_id=sku,
                    sku_part_number=estate_optional(item.get("skuPartNumber")),
                    capability_status=estate_optional(item.get("capabilityStatus")),
                    consumed_units=estate_count(item.get("consumedUnits")),
                    enabled_units=estate_count(units.get("enabled")),
                    suspended_units=estate_count(units.get("suspended")),
                    warning_units=estate_count(units.get("warning")),
                )
            )


def module_roles(doc, pending):
    if not re.fullmatch(r"\d{8}_\d+\.roles\.json", PurePosixPath(doc["path"]).name):
        raise ValueError("Unexpected roles file")
    for workspace in estate_records(doc):
        identity = text(workspace["id"])
        users = estate_optional_records(workspace.get("users"))
        pending["workspace_role_scopes"].append(
            module_row(
                "workspace_role_scopes",
                doc,
                identity,
                workspace_id=identity,
                roles_returned=users is not None,
                assignment_count=len(users) if users is not None else None,
            )
        )
        for index, user in enumerate(users or []):
            principal = module_key(user.get("graphId") or user.get("identifier"))
            role = estate_optional(user.get("groupUserAccessRight"))
            pending["workspace_role_assignments"].append(
                module_row(
                    "workspace_role_assignments",
                    doc,
                    [identity, principal, role, index],
                    workspace_id=identity,
                    principal_id=principal,
                    principal_type=estate_optional(user.get("principalType")),
                    workspace_role=role,
                )
            )


def module_settings(doc, pending):
    tenant = doc["path"].split("/")[0] == "tenant"
    scope = "tenant" if tenant else doc["path"].split("/")[1]
    if tenant:
        if PurePosixPath(doc["path"]).name != "tenant-settings.json" or doc["issue"]:
            raise ValueError("Unexpected tenant settings file")
        root = module_object(doc["value"])
        settings = records(root["tenantSettings"])
        parents = [(None, settings)]
    else:
        if PurePosixPath(doc["path"]).name != scope + ".json":
            raise ValueError("Unexpected delegated settings file")
        parents = []
        for entity in estate_records(doc):
            identity = text(entity["id"])
            if (
                "tenantSettings" in entity
                and "overrides" in entity
                and entity["tenantSettings"] != entity["overrides"]
            ):
                raise ValueError("Conflicting override collections")
            settings = estate_optional_records(
                entity.get("tenantSettings", entity.get("overrides"))
            )
            parents.append((identity, settings))
            pending["delegated_setting_scopes"].append(
                module_row(
                    "delegated_setting_scopes",
                    doc,
                    identity,
                    scope_type=scope,
                    entity_id=identity,
                    settings_returned=settings is not None,
                    setting_count=len(settings) if settings is not None else None,
                )
            )
    for identity, settings in parents:
        for setting in settings or []:
            name = text(setting["settingName"])
            counts = {}
            for field, rule in (
                ("enabledSecurityGroups", "enabled"),
                ("excludedSecurityGroups", "excluded"),
            ):
                groups = setting.get(field)
                if groups is not None and not isinstance(groups, list):
                    raise TypeError("Invalid setting group collection")
                counts[rule] = len(groups) if groups is not None else None
                for group in groups or []:
                    group_id = (
                        group
                        if isinstance(group, str)
                        else module_object(group).get("graphId")
                        or module_object(group).get("id")
                    )
                    group_key = module_key(text(group_id))
                    pending["tenant_setting_groups"].append(
                        module_row(
                            "tenant_setting_groups",
                            doc,
                            [scope, identity, name, rule, group_key],
                            scope_type=scope,
                            entity_id=identity,
                            setting_name=name,
                            group_id=group_key,
                            group_rule=rule,
                        )
                    )
            values = {
                "setting_name": name,
                "title": estate_optional(setting.get("title")),
                "setting_group": estate_optional(setting.get("tenantSettingGroup")),
                "enabled": estate_optional(setting.get("enabled"), bool),
                "enabled_group_count": counts["enabled"],
                "excluded_group_count": counts["excluded"],
            }
            if tenant:
                pending["tenant_settings"].append(
                    module_row(
                        "tenant_settings",
                        doc,
                        name,
                        **values,
                        can_specify_groups=estate_optional(
                            setting.get("canSpecifySecurityGroups"), bool
                        ),
                    )
                )
            else:
                pending["delegated_setting_overrides"].append(
                    module_row(
                        "delegated_setting_overrides",
                        doc,
                        [identity, name],
                        **values,
                        scope_type=scope,
                        entity_id=identity,
                        delegated_from=estate_optional(setting.get("delegatedFrom")),
                    )
                )


def module_domains(doc, pending):
    if PurePosixPath(doc["path"]).name != "domains.json":
        raise ValueError("Unexpected domains file")
    for item in estate_records(doc):
        domain, workspace = text(item["id"]), text(item["workspaceId"])
        pending["domains"].append(
            module_row(
                "domains",
                doc,
                domain,
                domain_id=domain,
                domain_name=estate_optional(item.get("displayName")),
                parent_domain_id=estate_optional(item.get("parentDomainId")),
            )
        )
        pending["domain_workspaces"].append(
            module_row(
                "domain_workspaces",
                doc,
                [domain, workspace],
                domain_id=domain,
                workspace_id=workspace,
                workspace_name=estate_optional(item.get("workspace")),
            )
        )


def module_git(doc, pending):
    if PurePosixPath(doc["path"]).name != "gitconnections.json":
        raise ValueError("Unexpected Git file")
    for item in estate_records(doc):
        identity = text(item["workspaceId"])
        provider, sync = (
            module_object(item.get("gitProviderDetails")),
            module_object(item.get("gitSyncDetails")),
        )
        owner, directory = (
            estate_optional(provider.get("ownerName")),
            estate_optional(provider.get("directoryName")),
        )
        pending["workspace_git_connections"].append(
            module_row(
                "workspace_git_connections",
                doc,
                identity,
                workspace_id=identity,
                provider_type=estate_optional(provider.get("gitProviderType")),
                owner_key=sha256(owner.encode()) if owner is not None else None,
                organization_name=estate_optional(provider.get("organizationName")),
                project_name=estate_optional(provider.get("projectName")),
                repository_name=estate_optional(provider.get("repositoryName")),
                branch_name=estate_optional(provider.get("branchName")),
                directory_key=sha256(directory.encode())
                if directory is not None
                else None,
                connection_state=estate_optional(item.get("gitConnectionState")),
                last_sync_utc=module_time(sync.get("lastSyncTime")),
            )
        )


def module_tags(doc, pending):
    if PurePosixPath(doc["path"]).name != "tags.json":
        raise ValueError("Unexpected tags file")
    for item in estate_records(doc):
        identity, scope = text(item["id"]), module_object(item.get("scope"))
        pending["tags"].append(
            module_row(
                "tags",
                doc,
                identity,
                tag_id=identity,
                tag_name=estate_optional(item.get("displayName")),
                scope_type=estate_optional(scope.get("type")),
                domain_id=estate_optional(scope.get("domainId")),
            )
        )


def module_sharing(doc, pending):
    name = PurePosixPath(doc["path"]).name
    if name not in MODULE_ARTIFACTS["sharing"]:
        raise ValueError("Unexpected sharing file")
    dataset = (
        "publish_to_web_shares" if "publishedtoweb" in name else "organization_shares"
    )
    for item in estate_records(doc):
        identity = text(item["artifactId"])
        access, share = (
            estate_optional(item.get("accessRight")),
            estate_optional(item.get("shareType")),
        )
        pending[dataset].append(
            module_row(
                dataset,
                doc,
                [identity, access, share],
                artifact_id=identity,
                artifact_type=estate_optional(item.get("artifactType")),
                access_right=access,
                share_type=share,
            )
        )


def module_append(output, pending):
    prepared = {}
    for dataset, entries in pending.items():
        unique = {}
        for entry in entries:
            identity = entry["observation_id"]
            if identity in unique and unique[identity] != entry:
                raise ValueError("Conflicting normalized identity")
            unique[identity] = entry
        prepared[dataset] = list(unique.values())
    for dataset, entries in prepared.items():
        output[dataset].extend(entries)
    return sum(len(entries) for entries in prepared.values())


def module_deployments(runs, output):
    for run in runs.values():
        if run["module"] != "fabricdeploymentpipelineoperations":
            continue
        status, issue, count = "invalid", "invalid_deployment_run", None
        manifest = run["manifest"]
        pending = {name: [] for name in MODULE_DOMAINS["deployments"]}
        if run["valid"] and not manifest["finished"]:
            status, issue = "unfinished", "unfinished_deployment_run"
        elif run["valid"]:
            try:
                inventory = [
                    doc
                    for doc in run["resources"]
                    if PurePosixPath(doc["path"]).name == "pipelines.json"
                ]
                if len(inventory) != 1:
                    raise ValueError("Missing pipeline inventory")
                inventory = inventory[0]
                resource = inventory["value"]
                if (
                    resource["requestPath"] != "deploymentPipelines"
                    or resource["parent"]
                ):
                    raise ValueError("Wrong pipeline inventory endpoint")
                pipelines = {}
                if resource["complete"]:
                    for item in records(resource["records"]):
                        identity = str(UUID(text(item["id"])))
                        if identity in pipelines:
                            raise ValueError("Duplicate pipeline")
                        pipelines[identity] = item
                        pending["deployment_pipelines"].append(
                            row(
                                "deployment_pipelines",
                                inventory,
                                identity,
                                pipeline_id=identity,
                                pipeline_name=text(item["displayName"]),
                                source_date=module_source_date(inventory),
                            )
                        )
                expected = {
                    "pipelines.json",
                    *(identity + ".json" for identity in pipelines),
                }
                if {
                    PurePosixPath(doc["path"]).name for doc in run["resources"]
                } != expected:
                    raise ValueError("Missing or unexpected pipeline resource")
                for doc in run["resources"]:
                    if doc is inventory:
                        continue
                    value = doc["value"]
                    identity = PurePosixPath(doc["path"]).stem
                    if (
                        value["parent"] != {"deploymentPipeline": pipelines[identity]}
                        or value["requestPath"]
                        != f"deploymentPipelines/{identity}/operations"
                    ):
                        raise ValueError("Operation parent or endpoint mismatch")
                    values = records(value["records"]) if value["complete"] else []
                    pending["deployment_operation_resources"].append(
                        row(
                            "deployment_operation_resources",
                            doc,
                            identity,
                            pipeline_id=identity,
                            source_date=module_source_date(doc),
                            coverage_status="success"
                            if value["complete"]
                            else "failed",
                            resource_outcome="success"
                            if value["complete"]
                            else "failed",
                            record_count=len(values) if value["complete"] else None,
                        )
                    )
                    for item in values:
                        operation = text(item["id"])
                        start, end = (
                            module_time(item.get("executionStartTime")),
                            module_time(item.get("executionEndTime")),
                        )
                        pending["deployment_operations"].append(
                            row(
                                "deployment_operations",
                                doc,
                                operation,
                                pipeline_id=identity,
                                operation_id=operation,
                                operation_type=text(item["type"]),
                                status=text(item["status"]),
                                last_updated_utc=module_time(
                                    item.get("lastUpdatedTime")
                                ),
                                execution_start_utc=start,
                                execution_end_utc=end,
                                duration_seconds=module_duration(start, end),
                                source_stage_id=estate_optional(
                                    item.get("sourceStageId")
                                ),
                                target_stage_id=estate_optional(
                                    item.get("targetStageId")
                                ),
                                source_date=module_source_date(doc),
                            )
                        )
                count = module_append(output, pending)
                status = "success" if manifest["complete"] else "partial"
                issue = MODULE_LIMITS["deployments"]
                if not resource["complete"]:
                    count, status = None, "failed"
            except (ValueError, KeyError, TypeError, AttributeError, IndexError):
                status, issue, count = (
                    "invalid",
                    "invalid_deployment_metadata_or_scope",
                    None,
                )
        output["estate_coverage"].append(
            row(
                "estate_coverage",
                run["doc"],
                "deployments",
                analysis="deployments",
                coverage_status=status,
                record_count=count,
                issue=issue,
            )
        )


def transform_modules(documents, runs, output):
    module_deployments(runs, output)
    parsers = {
        "apps": module_apps,
        "capacity": module_capacity,
        "directory": module_directory,
        "roles": module_roles,
        "settings": module_settings,
        "domains": module_domains,
        "git": module_git,
        "tags": module_tags,
        "sharing": module_sharing,
    }
    for doc in documents:
        prefix = doc["path"].split("/")[0]
        domain = next(
            (
                name
                for name, sources in MODULE_SOURCES.items()
                if prefix in sources and name != "deployments"
            ),
            None,
        )
        if domain is None or (
            domain == "apps" and not doc["path"].startswith("catalog/snapshots/")
        ):
            continue
        status, count, date, issue = (
            "legacy_unverified",
            None,
            None,
            MODULE_LIMITS[domain],
        )
        pending = {name: [] for name in MODULE_DOMAINS[domain]}
        try:
            date = module_source_date(doc)
            parsers[domain](doc, pending)
            count = module_append(output, pending)
            if isinstance(doc["value"], dict) and doc["value"].get("continuationToken"):
                issue = "source_continuation_present_completeness_unverified"
        except (
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            IndexError,
            OverflowError,
        ):
            status, issue = "invalid", "invalid_or_unavailable_module_metadata"
        output["estate_coverage"].append(
            estate_row(
                "estate_coverage",
                doc,
                domain,
                analysis=domain,
                source_date=date,
                coverage_status=status,
                record_count=count,
                issue=issue,
            )
        )


def module_capacity_chart(frame):
    import matplotlib.pyplot as plt
    from pyspark.sql import functions as F

    chosen = (
        frame.filter(F.col("metric_value").isNotNull())
        .orderBy(
            F.col("source_date").desc(),
            F.col("metric_date").desc(),
            "capacity_id",
            "metric_group",
            "metric_name",
        )
        .limit(1)
        .collect()
    )
    if not chosen:
        print("No numeric capacity metrics collected; extraction is opt-in.")
        return
    selected = chosen[0]
    fields = (
        "source_date",
        "metric_date",
        "capacity_id",
        "metric_group",
        "metric_name",
    )
    for key in fields:
        frame = frame.filter(F.col(key) == selected[key])
    total = frame.count()
    points = (
        frame.select("timepoint_raw", "metric_value")
        .orderBy("timepoint_raw")
        .limit(200)
        .toPandas()
    )
    axis = points.plot(
        x="timepoint_raw", y="metric_value", legend=False, title=selected["metric_name"]
    )
    axis.set_xlabel("Provider timepoint (timezone may be unknown)")
    axis.set_ylabel("Unscaled provider value")
    print(
        {key: selected[key] for key in fields},
        f"showing {len(points)}/{total} observations",
    )
    plt.tight_layout()
    plt.show()


def preview_modules(spark_session, display_frame, tables, domain):
    from pyspark.sql import functions as F

    coverage = [
        entry for entry in tables["estate_coverage"] if entry["analysis"] == domain
    ]
    print(MODULE_LIMITS[domain])
    print(
        "Retained raw-file observations, not current tenant-wide or effective-state claims."
    )
    if not coverage:
        print("NOT COLLECTED: no supported source files, not successful zero.")
    else:
        display_frame(
            to_frame(spark_session, "estate_coverage", coverage)
            .groupBy("coverage_status", "issue")
            .count()
        )
    for name in MODULE_ARTIFACTS[domain]:
        if not any(entry["source_path"].endswith("/" + name) for entry in coverage):
            print(
                f"{name}: NOT COLLECTED; optional, failed or unavailable is not empty success."
            )
    frames = {
        name: to_frame(spark_session, name, tables[name])
        for name in MODULE_DOMAINS[domain]
    }
    categories = {
        "apps": ("apps", "workspace_id"),
        "capacity": ("capacities", "sku"),
        "directory": ("directory_users", "user_type"),
        "roles": ("workspace_role_assignments", "workspace_role"),
        "settings": ("tenant_settings", "enabled"),
        "domains": ("domain_workspaces", "domain_id"),
        "git": ("workspace_git_connections", "connection_state"),
        "tags": ("tags", "scope_type"),
        "sharing": ("organization_shares", "artifact_type"),
        "deployments": ("deployment_operations", "status"),
    }
    dataset, category = categories[domain]
    plotted = frames[dataset]
    if domain == "deployments":
        plotted = latest_frame(plotted, ["pipeline_id", "operation_id"])
    plot_counts(plotted, category, domain + ": retained observations")
    for name, frame in frames.items():
        print(
            name + ": at most 100 metadata rows; history is not a current-state union"
        )
        display_frame(
            frame.orderBy(
                F.col("observed_at_utc").desc_nulls_last(), F.col("source_path").desc()
            ).limit(100)
        )
    if domain == "capacity":
        metrics = frames["capacity_metric_observations"]
        display_frame(
            metrics.groupBy("capacity_id", "metric_group", "metric_name").agg(
                F.count("*").alias("observations"),
                F.count("metric_value").alias("known_values"),
                F.avg("metric_value").alias("mean_provider_value"),
            )
        )
        module_capacity_chart(metrics)
    if domain == "sharing":
        plot_counts(
            frames["publish_to_web_shares"],
            "artifact_type",
            "Retained publish-to-web observations",
        )
