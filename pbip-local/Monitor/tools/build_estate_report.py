"""Generate a fresh Direct Lake estate model and native Power BI report."""

import json
from uuid import NAMESPACE_URL, uuid5

from estate_model import (
    COMMON,
    DATE_ROLES,
    DERIVED_SCHEMAS,
    ENTITIES,
    FACTS,
    LAKEHOUSE,
    PREFIX,
    PROJECT,
    SCHEMAS,
    SPECIAL_MODELS,
    WORKSPACE,
    title,
)

MODEL = PROJECT / "Monitor.SemanticModel" / "definition"
REPORT = PROJECT / "Monitor.Report" / "definition"
MEASURES = {}
TABLES = {}
RELATIONSHIPS = []
PAGES = []
MEASURE_TABLE = "Estate Measures"
BASE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def column(table, name):
    return f"{quote(table)}[{name}]"


def fact(dataset, name):
    return column(FACTS[dataset][0], title(name))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def measure(name, expression, folder, fmt="#,0", *, guarded=True, description=None):
    if guarded:
        expression = f"IF ( [Unmapped Observations] = 0 && SELECTEDVALUE ( 'Estate Measures'[State] ) = \"ready\", {expression} )"
    MEASURES[name] = {
        "expression": expression,
        "folder": folder,
        "format": fmt,
        "description": description
        or "Retained evidence in the selected context; not an exhaustive current-state claim.",
    }


def rows(dataset):
    return f"COALESCE ( COUNTROWS ( {quote(FACTS[dataset][0])} ), 0 )"


def distinct(dataset, fields, condition=None):
    table = quote(FACTS[dataset][0])
    if condition:
        table = f"FILTER ( {table}, {condition} )"
    return f"COALESCE ( COUNTROWS ( SUMMARIZE ( {table}, {', '.join(fact(dataset, name) for name in fields)} ) ), 0 )"


def create_measures():
    missing = [
        f"COUNTROWS ( EXCEPT ( VALUES ( {fact(name, 'observation_id')} ), VALUES ( 'Observation Context'[Observation ID] ) ) )"
        f" + COUNTROWS ( EXCEPT ( CALCULATETABLE ( VALUES ( 'Observation Context'[Observation ID] ), 'Observation Context'[Dataset] = \"{name}\" ), VALUES ( {fact(name, 'observation_id')} ) ) )"
        for name in FACTS
    ]
    measure(
        "Unmapped Observations",
        "CALCULATE ( " + " + ".join(missing) + ", REMOVEFILTERS () )",
        "00 Readiness",
        guarded=False,
        description="Source/context identity mismatch in either direction. Nonzero blocks business measures until lookups are rebuilt.",
    )
    measure(
        "Model Status",
        'IF ( SELECTEDVALUE ( \'Estate Measures\'[State] ) <> "ready", "Lookup build is incomplete - do not interpret this report", '
        'IF ( [Unmapped Observations] > 0, "REFRESH REQUIRED: source observations and report lookups no longer match", '
        '"Historical evidence - check coverage and date precision before interpreting results" ) )',
        "00 Readiness",
        "",
        guarded=False,
    )
    measure(
        "Lookup Built At",
        'FORMAT ( MAX ( \'Estate Measures\'[Built At] ), "yyyy-MM-dd HH:mm" ) & " UTC"',
        "00 Readiness",
        "",
        guarded=False,
    )
    measure("Dataset Count", "COUNTROWS ( 'Dataset' )", "00 Readiness")
    measure(
        "Datasets With Rows",
        "CALCULATE ( COUNTROWS ( 'Dataset' ), 'Dataset'[Profiled Rows] > 0 )",
        "00 Readiness",
    )
    measure(
        "Datasets Without Rows",
        "CALCULATE ( COUNTROWS ( 'Dataset' ), 'Dataset'[Profiled Rows] = 0 )",
        "00 Readiness",
    )
    measure(
        "Retained Observations",
        "COALESCE ( COUNTROWS ( 'Observation Context' ), 0 )",
        "00 Readiness",
    )
    measure(
        "Legacy Observations",
        "CALCULATE ( [Retained Observations], 'Observation Context'[Coverage Status] = \"legacy_unverified\" )",
        "00 Readiness",
    )
    measure(
        "Exact Collection Times",
        "COUNT ( 'Observation Context'[Observed At] )",
        "00 Readiness",
    )
    measure(
        "Latest Exact Collection",
        'FORMAT ( MAX ( \'Observation Context\'[Observed At] ), "yyyy-MM-dd HH:mm" ) & " UTC"',
        "00 Readiness",
        "",
    )
    measure(
        "Hours Since Exact Collection",
        "IF ( NOT ISBLANK ( MAX ( 'Observation Context'[Observed At] ) ), DATEDIFF ( MAX ( 'Observation Context'[Observed At] ), UTCNOW (), HOUR ) )",
        "00 Readiness",
    )
    for dataset, (name, domain) in FACTS.items():
        expression = rows(dataset)
        if dataset in (
            "permission_cycles",
            "permission_resources",
            "permission_grants",
        ):
            expression = (
                "IF ( HASONEVALUE ( 'Permission Mode'[Mode] ), " + expression + " )"
            )
        measure(name + " Rows", expression, domain + " | Observation counts")
    definitions = [
        (
            "Workspaces Observed",
            "catalog_workspaces",
            ("workspace_id",),
            None,
            "Inventory",
        ),
        (
            "Items Observed",
            "inventory",
            ("workspace_id", "item_id"),
            fact("inventory", "item_type") + ' <> "Workspace"',
            "Inventory",
        ),
        (
            "Models Observed",
            "catalog_models",
            ("workspace_id", "item_id"),
            None,
            "Schema",
        ),
        (
            "Tables Observed",
            "model_tables",
            ("workspace_id", "item_id", "table_name"),
            None,
            "Schema",
        ),
        (
            "Columns Observed",
            "model_columns",
            ("workspace_id", "item_id", "table_name", "column_name"),
            None,
            "Schema",
        ),
        (
            "Measures Observed",
            "model_measures",
            ("workspace_id", "item_id", "table_name", "measure_name"),
            None,
            "Schema",
        ),
        (
            "Connections Observed",
            "connection_observations",
            ("connection_id",),
            None,
            "Connectivity",
        ),
        ("Capacities Observed", "capacities", ("capacity_id",), None, "Capacity"),
        (
            "Actor Keys Observed",
            "activity_events",
            ("actor_key",),
            fact("activity_events", "actor_key") + " <> BLANK ()",
            "Activity",
        ),
        (
            "Directory Users Observed",
            "directory_users",
            ("principal_id",),
            None,
            "Directory",
        ),
        (
            "Directory Groups Observed",
            "directory_groups",
            ("group_id",),
            None,
            "Directory",
        ),
        (
            "Licensed Users Observed",
            "user_licenses",
            ("principal_id",),
            None,
            "Directory",
        ),
        (
            "Git Workspaces Observed",
            "workspace_git_connections",
            ("workspace_id",),
            None,
            "Change",
        ),
        (
            "Upstream Pairs Observed",
            "lineage_edges",
            (
                "workspace_id",
                "item_id",
                "related_workspace_id",
                "related_item_id",
                "related_type",
                "relation_type",
                "evidence_type",
            ),
            fact("lineage_edges", "direction") + ' = "upstream"',
            "Lineage",
        ),
    ]
    for name, dataset, fields, condition, folder in definitions:
        measure(name, distinct(dataset, fields, condition), folder)
    for status in ("success", "failed", "deferred"):
        measure(
            "Permission Polls - " + status.title(),
            f'CALCULATE ( [Permission Polls Rows], {fact("permission_resources", "coverage_status")} = "{status}" )',
            "Access",
        )
    measure(
        "Permission Poll Success %",
        "DIVIDE ( [Permission Polls - Success], [Permission Polls Rows] )",
        "Access",
        "0.0%",
    )
    measure(
        "Mode Selection",
        "IF ( HASONEVALUE ( 'Permission Mode'[Mode] ), \"Permission scope: \" & SELECTEDVALUE ( 'Permission Mode'[Mode] ), \"Select exactly one permission mode - Scoped and Tenant are not interchangeable\" )",
        "Access",
        "",
        guarded=False,
    )
    measure(
        "Scoped Grant Observations",
        "IF ( HASONEVALUE ( 'Permission Mode'[Mode] ), [Permission Grants Rows] )",
        "Access",
    )
    measure(
        "Completed Healthy Cycles",
        f"CALCULATE ( [Permission Cycles Rows], {fact('permission_cycles', 'chain_valid')} = TRUE (), {fact('permission_cycles', 'cycle_finished')} = TRUE (), {fact('permission_cycles', 'cycle_healthy')} = TRUE () )",
        "Access",
    )
    measure(
        "Successful Empty Job Polls",
        f'CALCULATE ( [Job Polls Rows], {fact("job_resources", "coverage_status")} = "success", {fact("job_resources", "record_count")} = 0 )',
        "Reliability",
    )
    measure(
        "Mean Job Seconds",
        f"AVERAGE ( {fact('job_observations', 'duration_seconds')} )",
        "Reliability",
        "#,0.0",
    )
    measure(
        "Mean Refresh Seconds",
        f"AVERAGE ( {fact('refresh_observations', 'duration_seconds')} )",
        "Reliability",
        "#,0.0",
    )
    measure(
        "Unresolved Lineage Rows",
        f'CALCULATE ( [Lineage Edges Rows], {fact("lineage_edges", "resolution")} <> "in_batch" )',
        "Lineage",
    )
    measure(
        "Runtime Verified Lineage Rows",
        f"CALCULATE ( [Lineage Edges Rows], {fact('lineage_edges', 'runtime_verified')} = TRUE () )",
        "Lineage",
    )
    measure(
        "Metric Selection",
        "IF ( HASONEVALUE ( 'Capacity Metrics'[Metric Name] ) && HASONEVALUE ( 'Source Folder Date'[Date] ), \"Provider values are unscaled; naive timepoints have unknown UTC\", \"Select one metric and one source-folder date before reading values\" )",
        "Capacity",
        "",
        guarded=False,
    )
    metric_scope = "HASONEVALUE ( 'Capacity Metrics'[Metric Name] ) && HASONEVALUE ( 'Source Folder Date'[Date] )"
    measure(
        "Provider Metric Average",
        f"IF ( {metric_scope}, AVERAGE ( {fact('capacity_metric_observations', 'metric_value')} ) )",
        "Capacity",
        "#,0.000",
    )
    measure(
        "Provider Metric Peak",
        f"IF ( {metric_scope}, MAX ( {fact('capacity_metric_observations', 'metric_value')} ) )",
        "Capacity",
        "#,0.000",
    )
    measure(
        "Metric Query Window",
        f'MIN ( {fact("capacity_metric_observations", "metric_date")} ) & " to " & MAX ( {fact("capacity_metric_observations", "metric_date")} )',
        "Capacity",
        "",
    )
    measure(
        "License Units - Single Date",
        f"IF ( HASONEVALUE ( 'Source Folder Date'[Date] ), SUM ( {fact('subscribed_skus', 'enabled_units')} ) )",
        "Directory",
    )
    measure(
        "Consumed Units - Single Date",
        f"IF ( HASONEVALUE ( 'Source Folder Date'[Date] ), SUM ( {fact('subscribed_skus', 'consumed_units')} ) )",
        "Directory",
    )


def add_table(name, source, types, *, dataset=None, hidden=False):
    TABLES[name] = {
        "source": source,
        "types": types,
        "dataset": dataset,
        "hidden": hidden,
    }


def relate(source, from_column, target, to_column):
    RELATIONSHIPS.append((source, title(from_column), target, title(to_column)))


def emit_model():
    create_measures()
    for dataset, (name, _) in FACTS.items():
        add_table(
            name, "monitor_" + dataset, COMMON | SCHEMAS[dataset], dataset=dataset
        )
        relate(name, "observation_id", "Observation Context", "observation_id")
    for kind, (name, _, _) in ENTITIES.items():
        add_table(name, PREFIX + kind, DERIVED_SCHEMAS[kind])
        relate("Observation Context", kind + "_key", name, "entity_key")
    for kind in ("workspace", "item"):
        name = "Related " + ENTITIES[kind][0]
        add_table(name, PREFIX + kind, DERIVED_SCHEMAS[kind])
        relate("Observation Context", "related_" + kind + "_key", name, "entity_key")
    for kind, name in SPECIAL_MODELS.items():
        add_table(name, PREFIX + kind, DERIVED_SCHEMAS[kind], hidden=kind == "context")
    relate("Observation Context", "source_key", "Evidence Source", "source_key")
    relate("Observation Context", "dataset", "Dataset", "dataset")
    for name, source_column in DATE_ROLES.items():
        add_table(name, PREFIX + "date", DERIVED_SCHEMAS["date"])
        relate("Observation Context", source_column, name, "date_key")
    for dataset in ("permission_cycles", "permission_resources", "permission_grants"):
        relate(FACTS[dataset][0], "mode", "Permission Mode", "mode")
    types = {
        "string": "string",
        "long": "int64",
        "int": "int64",
        "double": "double",
        "boolean": "boolean",
        "timestamp": "dateTime",
        "date": "dateTime",
    }
    technical = {
        "schema_version",
        "observation_id",
        "source_path",
        "source_sha256",
        "record_sha256",
        "run_id",
        "cycle_id",
    }
    table_dir = MODEL / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    for name, spec in TABLES.items():
        content = [
            f"table {quote(name)}",
            f"\tlineageTag: {uuid5(NAMESPACE_URL, 'fabric-estate/table/' + name)}",
        ]
        if spec["hidden"]:
            content.append("\tisHidden")
        if spec["dataset"]:
            content.insert(
                0,
                "/// Historical source observations. Counts are not automatically current inventory or effective policy.",
            )
        for source_column, data_type in spec["types"].items():
            content.extend(
                [
                    "",
                    f"\tcolumn {quote(title(source_column))}",
                    f"\t\tdataType: {types[data_type]}",
                    "\t\tsummarizeBy: none",
                    f"\t\tsourceColumn: {source_column}",
                ]
            )
            if (
                source_column in technical
                or source_column.endswith("_key")
                or (name == MEASURE_TABLE)
            ):
                content.append("\t\tisHidden")
            if data_type == "date":
                content.append("\t\tformatString: yyyy-MM-dd")
            if data_type == "timestamp":
                content.append("\t\tformatString: yyyy-MM-dd HH:mm:ss")
        if name == MEASURE_TABLE:
            for measure_name, spec_measure in MEASURES.items():
                content.extend(
                    [
                        "",
                        "\t/// " + spec_measure["description"],
                        f"\tmeasure {quote(measure_name)} =",
                        "\t\t\t" + spec_measure["expression"],
                        f"\t\tdisplayFolder: {spec_measure['folder']}",
                    ]
                )
                if spec_measure["format"]:
                    content.append("\t\tformatString: " + spec_measure["format"])
        content.extend(
            [
                "",
                f"\tpartition {quote(name)} = entity",
                "\t\tmode: directLake",
                "\t\tsource",
                "\t\t\tentityName: " + spec["source"],
                "\t\t\tschemaName: dbo",
                "\t\t\texpressionSource: 'DirectLake - Fabric Estate'",
                "",
            ]
        )
        (table_dir / (name + ".tmdl")).write_text("\n".join(content))
    expressions = (
        "expression 'DirectLake - Fabric Estate' =\n"
        "\t\tlet\n"
        f'\t\t    Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/{WORKSPACE}/{LAKEHOUSE}", [HierarchicalNavigation = true])\n'
        "\t\tin\n\t\t    Source\n"
    )
    (MODEL / "expressions.tmdl").write_text(expressions)
    model = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "\tdirectLakeBehavior: directLakeOnly",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        "ref expression 'DirectLake - Fabric Estate'",
        "",
        "ref cultureInfo en-US",
        "",
        *[f"ref table {quote(name)}" for name in TABLES],
        "",
    ]
    (MODEL / "model.tmdl").write_text("\n".join(model))
    (MODEL / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1604\n")
    relations = []
    for source, field, target, target_field in RELATIONSHIPS:
        identifier = uuid5(
            NAMESPACE_URL, f"fabric-estate/{source}/{field}/{target}/{target_field}"
        )
        relations.extend(
            [
                f"relationship {identifier}",
                "\tfromCardinality: many",
                "\ttoCardinality: one",
                "\tcrossFilteringBehavior: oneDirection",
                f"\tfromColumn: {quote(source)}.{quote(field)}",
                f"\ttoColumn: {quote(target)}.{quote(target_field)}",
                "",
            ]
        )
    (MODEL / "relationships.tmdl").write_text("\n".join(relations))


def literal(value):
    if isinstance(value, bool):
        value = "true" if value else "false"
    elif isinstance(value, str):
        value = quote(value)
    else:
        value = str(value) + "D"
    return {"expr": {"Literal": {"Value": value}}}


def field(entity, property_name, *, is_measure=False):
    return {
        ("Measure" if is_measure else "Column"): {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": property_name,
        }
    }


def projection(entity, property_name, *, is_measure=False):
    return {
        "field": field(entity, property_name, is_measure=is_measure),
        "queryRef": entity + "." + property_name,
        "nativeQueryRef": property_name,
    }


def navigation_objects():
    return {
        "layout": [
            {
                "properties": {
                    "orientation": literal(0),
                    "rowCount": literal(2),
                    "columnCount": literal(7),
                    "cellPadding": literal(6),
                }
            }
        ],
        "text": [
            {
                "selector": {"id": state},
                "properties": {
                    "fontFamily": literal("Segoe UI"),
                    "fontSize": literal(10),
                    "topMargin": literal(2),
                    "bottomMargin": literal(2),
                },
            }
            for state in ("default", "hover", "selected", "disabled")
        ],
        "pages": [
            {
                "properties": {
                    "showHiddenPages": literal(False),
                    "showTooltipPages": literal(False),
                }
            }
        ],
    }


def visual(page_name, index, kind, name, x, y, width, height, roles=None, text=None):
    identifier = f"v_{page_name}_{index:02d}"
    spec = {
        "$schema": BASE + "/visualContainer/2.5.0/schema.json",
        "name": identifier,
        "position": {
            "x": x,
            "y": y,
            "z": index,
            "tabOrder": index,
            "width": width,
            "height": height,
        },
        "visual": {"visualType": kind, "drillFilterOtherVisuals": True},
        "howCreated": "Copilot",
    }
    spec["visual"]["visualContainerObjects"] = {
        "title": [
            {
                "properties": {
                    "show": literal(True),
                    "text": literal(name),
                    "fontFamily": literal("Segoe UI Semibold"),
                    "fontSize": literal(12),
                    "fontColor": {"solid": {"color": literal("#102A43")}},
                }
            }
        ],
        "background": [
            {
                "properties": {
                    "show": literal(True),
                    "color": {"solid": {"color": literal("#FFFFFF")}},
                    "transparency": literal(0),
                }
            }
        ],
        "border": [
            {
                "properties": {
                    "show": literal(True),
                    "color": {"solid": {"color": literal("#DFE7F1")}},
                    "radius": literal(8),
                }
            }
        ],
    }
    if roles:
        spec["visual"]["query"] = {
            "queryState": {
                role: {"projections": values} for role, values in roles.items()
            }
        }
    if kind == "pageNavigator":
        spec["visual"]["objects"] = navigation_objects()
    if text is not None:
        spec["visual"]["objects"] = {
            "general": [
                {
                    "properties": {
                        "paragraphs": [
                            {
                                "textRuns": [
                                    {
                                        "value": text,
                                        "textStyle": {
                                            "fontFamily": "Segoe UI",
                                            "fontSize": "12pt",
                                            "color": "#334E68",
                                        },
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        }
    write_json(
        REPORT / "pages" / page_name / "visuals" / identifier / "visual.json", spec
    )


def report_page(
    key, display_name, subtitle, cards, charts, details, *, slicers=(), note=""
):
    page_name = "estate_" + key
    PAGES.append(page_name)
    page = {
        "$schema": BASE + "/page/2.0.0/schema.json",
        "name": page_name,
        "displayName": display_name,
        "displayOption": "FitToWidth",
        "height": 1148,
        "width": 1600,
        "objects": {
            "background": [
                {
                    "properties": {
                        "color": {"solid": {"color": literal("#F3F6FB")}},
                        "transparency": literal(0),
                    }
                }
            ]
        },
        "howCreated": "Copilot",
    }
    write_json(REPORT / "pages" / page_name / "page.json", page)
    number = 0

    def add(kind, label, x, y, w, h, roles=None, text=None):
        nonlocal number
        visual(page_name, number, kind, label, x, y, w, h, roles=roles, text=text)
        number += 1

    add(
        "textbox",
        "FABRIC ESTATE ATLAS  /  " + display_name,
        24,
        16,
        1552,
        88,
        text=subtitle,
    )
    add("pageNavigator", "Explore the estate", 24, 112, 1552, 104)
    add(
        "card",
        "Evidence readiness",
        24,
        224,
        1552,
        76,
        {"Values": [projection(MEASURE_TABLE, "Model Status", is_measure=True)]},
    )
    for index, (entity, name) in enumerate(slicers):
        width = 1552 / max(1, len(slicers))
        add(
            "slicer",
            name,
            24 + index * width,
            308,
            width - 12,
            72,
            {"Values": [projection(entity, name)]},
        )
    card_y = 392 if slicers else 308
    for index, metric in enumerate(cards):
        width = 1552 / len(cards)
        add(
            "card",
            metric,
            24 + index * width,
            card_y,
            width - 12,
            100,
            {"Values": [projection(MEASURE_TABLE, metric, is_measure=True)]},
        )
    chart_y = card_y + 116
    for index, (label, entity, category, metric) in enumerate(charts):
        width = 1552 / len(charts)
        add(
            "clusteredBarChart",
            label,
            24 + index * width,
            chart_y,
            width - 12,
            244,
            {
                "Category": [projection(entity, category)],
                "Y": [projection(MEASURE_TABLE, metric, is_measure=True)],
            },
        )
    detail_y = chart_y + (260 if charts else 0)
    if details:
        add(
            "tableEx",
            "Evidence explorer - select a chart or slicer to investigate",
            24,
            detail_y,
            1552,
            200,
            {
                "Values": [
                    projection(entity, name, is_measure=entity == MEASURE_TABLE)
                    for entity, name in details
                ]
            },
        )
    add("textbox", "How to read this page", 24, 1048, 1552, 76, text=note)


def emit_pages():
    m = lambda value: (MEASURE_TABLE, value)
    report_page(
        "01",
        "01 Estate",
        "What evidence do we have, how fresh is it, and where must we avoid confident conclusions?",
        [
            "Workspaces Observed",
            "Items Observed",
            "Datasets With Rows",
            "Datasets Without Rows",
        ],
        [
            (
                "Retained observations by domain",
                "Dataset",
                "Domain",
                "Retained Observations",
            ),
            (
                "Evidence confidence - observation counts, not estate completeness",
                "Observation Context",
                "Coverage Status",
                "Retained Observations",
            ),
        ],
        [
            ("Dataset", "Label"),
            ("Dataset", "Profiled Rows"),
            ("Dataset", "Availability"),
            ("Dataset", "Latest Exact Observation"),
            ("Dataset", "Latest Source Date"),
        ],
        note="All counts are retained evidence, not certified current tenant inventory. Empty tables do not prove absence. Date-only legacy observations have no exact collection timestamp.",
    )
    report_page(
        "02",
        "02 Confidence",
        "Inspect collection failures, invalid history, date precision and the age of retained evidence before interpreting business counts.",
        [
            "Retained Observations",
            "Legacy Observations",
            "Exact Collection Times",
            "Hours Since Exact Collection",
        ],
        [
            (
                "Collection outcomes",
                "Collection Health",
                "Coverage Status",
                "Collection Health Rows",
            ),
            (
                "Domain collection evidence",
                "Domain Coverage",
                "Analysis",
                "Domain Coverage Rows",
            ),
        ],
        [
            ("Dataset", "Label"),
            ("Dataset", "Delta Version"),
            ("Dataset", "Latest Exact Observation"),
            ("Dataset", "Latest Source Date"),
            ("Dataset", "Profiled At"),
        ],
        slicers=[("Collection Date", "Date")],
        note="Collection Date is an exact UTC collection day only. Source Folder Date is a partition day, not collection time. Historical failures remain visible even after later success; there is no cross-table transaction.",
    )
    report_page(
        "03",
        "03 Workspaces",
        "Explore observed workspaces and item types, then inspect the retained names and source coverage.",
        ["Workspaces Observed", "Items Observed", "Models Observed"],
        [
            ("Observed item types", "Item Inventory", "Item Type", "Items Observed"),
            (
                "Workspace inventory state observations",
                "Workspace Catalog",
                "State",
                "Workspace Catalog Rows",
            ),
        ],
        [
            ("Workspace", "Entity ID"),
            ("Workspace", "Label"),
            ("Item Inventory", "Item Name"),
            ("Item Inventory", "Item Type"),
            ("Item Inventory", "Inventory Source"),
            ("Item Inventory", "Coverage Status"),
        ],
        slicers=[("Workspace", "Label"), ("Collection Date", "Date")],
        note="Labels use retained descriptive evidence, not authoritative current or historical names. Multiple sources/dates can describe the same item. Workspace filters do not invent scope for records without workspace IDs.",
    )
    report_page(
        "04",
        "04 Access",
        "Review observed grants and permission-poll outcomes. Select exactly one permission mode; grants are not effective access.",
        [
            "Scoped Grant Observations",
            "Permission Polls - Failed",
            "Permission Polls - Deferred",
            "Completed Healthy Cycles",
        ],
        [
            (
                "Retained permission-poll outcomes",
                "Permission Polls",
                "Resource Outcome",
                "Permission Polls Rows",
            ),
            (
                "Observed grant principal types",
                "Permission Grants",
                "Principal Type",
                "Permission Grants Rows",
            ),
        ],
        [
            ("Permission Grants", "Mode"),
            ("Permission Grants", "Workspace ID"),
            ("Permission Grants", "Item ID"),
            ("Permission Grants", "Principal Type"),
            ("Permission Grants", "Permissions JSON"),
            m("Scoped Grant Observations"),
        ],
        slicers=[("Permission Mode", "Mode"), ("Workspace", "Label")],
        note="Scoped and Tenant evidence is never an implicit fallback. Missing/failed/deferred polls mean unknown access, not no access. No group expansion or effective-access calculation. Workspace roles and broad/public sharing are separate sources.",
    )
    report_page(
        "05",
        "05 Activity",
        "Understand observed operations and workloads over provider event dates without exposing actor names or IP addresses.",
        ["Activity Events Rows", "Actor Keys Observed"],
        [
            (
                "Recorded operations",
                "Activity Events",
                "Operation",
                "Activity Events Rows",
            ),
            (
                "Recorded workloads",
                "Activity Events",
                "Workload",
                "Activity Events Rows",
            ),
        ],
        [
            ("Activity Events", "Event Time UTC"),
            ("Activity Events", "Operation"),
            ("Activity Events", "Workload"),
            ("Activity Events", "Workspace ID"),
            ("Activity Events", "Is Success"),
        ],
        slicers=[("Event Date", "Date"), ("Workspace", "Label")],
        note="Actor keys are pseudonyms, not anonymous people or unique human users. Provider event time is distinct from collection time. This is collected Power BI activity, not every Fabric/Azure audit service.",
    )
    report_page(
        "06",
        "06 Reliability",
        "Separate successful empty polls from job or refresh outcomes, failures and missing collection.",
        [
            "Successful Empty Job Polls",
            "Job History Rows",
            "Refresh History Rows",
            "Mean Refresh Seconds",
        ],
        [
            ("Job-poll coverage", "Job Polls", "Coverage Status", "Job Polls Rows"),
            (
                "Retained refresh status",
                "Refresh History",
                "Status",
                "Refresh History Rows",
            ),
        ],
        [
            ("Job Polls", "Workspace ID"),
            ("Job Polls", "Item ID"),
            ("Job Polls", "Item Type"),
            ("Job Polls", "Record Count"),
            ("Job Polls", "Coverage Status"),
        ],
        slicers=[("Workspace", "Label"), ("Collection Date", "Date")],
        note="The profiled job polls succeeded and returned zero job records; that is scoped evidence, not proof no jobs ran tenant-wide. Refresh tables currently have no rows. Null durations remain unknown, not zero.",
    )
    report_page(
        "07",
        "07 Capacity",
        "Explore capacity metadata and historic provider metrics. Choose one metric and one source-folder date; mixed units are never summed.",
        [
            "Capacities Observed",
            "Capacity Metrics Rows",
            "Provider Metric Average",
            "Provider Metric Peak",
        ],
        [
            (
                "Selected provider value by capacity",
                "Capacity",
                "Label",
                "Provider Metric Average",
            ),
            (
                "Selected provider value by query day",
                "Metric Query Date",
                "Date",
                "Provider Metric Average",
            ),
        ],
        [
            ("Capacity Metrics", "Metric Date"),
            ("Capacity Metrics", "Metric Name"),
            ("Capacity Metrics", "Timepoint Raw"),
            ("Capacity Metrics", "Metric Value"),
            ("Capacity Metrics", "Source Date"),
        ],
        slicers=[
            ("Capacity Metrics", "Metric Name"),
            ("Source Folder Date", "Date"),
            ("Capacity", "Label"),
        ],
        note="Inspect metric-query dates before treating this as current capacity health. Values retain provider scale/units. Naive provider timepoints have unknown UTC. Source-folder day and metric-query day differ.",
    )
    report_page(
        "08",
        "08 Connectivity",
        "Inspect caller-visible connections and any returned gateway/datasource evidence without exporting connection paths or credentials.",
        [
            "Connections Observed",
            "Gateway Inventory Rows",
            "Gateway Datasources Rows",
            "Gateway Status Rows",
        ],
        [
            (
                "Observed connectivity types",
                "Connection Inventory",
                "Connectivity Type",
                "Connection Inventory Rows",
            ),
            (
                "Observed connection types",
                "Connection Inventory",
                "Connection Type",
                "Connection Inventory Rows",
            ),
        ],
        [
            ("Connection Inventory", "Connection Name"),
            ("Connection Inventory", "Connection Type"),
            ("Connection Inventory", "Connectivity Type"),
            ("Connection Inventory", "Privacy Level"),
            ("Connection Inventory", "Gateway ID"),
        ],
        note="Connections are caller-visible, not tenant-complete. A connection's gateway ID does not prove gateway inventory or live connectivity. Gateway tables currently contain no observations; no credentials/paths are included.",
    )
    report_page(
        "09",
        "09 Schema",
        "Explore scanner-returned semantic models, tables, columns and measures. This is not physical Lakehouse/Warehouse schema discovery.",
        ["Models Observed", "Tables Observed", "Columns Observed", "Measures Observed"],
        [
            (
                "Returned model schema coverage",
                "Semantic Model Catalog",
                "Schema Coverage",
                "Semantic Model Catalog Rows",
            ),
            (
                "Observed column data types",
                "Model Columns",
                "Data Type",
                "Columns Observed",
            ),
        ],
        [
            ("Model Columns", "Workspace ID"),
            ("Model Columns", "Item ID"),
            ("Model Columns", "Table Name"),
            ("Model Columns", "Column Name"),
            ("Model Columns", "Data Type"),
            ("Model Columns", "Is Hidden"),
        ],
        slicers=[
            ("Workspace", "Label"),
            ("Item", "Label"),
            ("Source Folder Date", "Date"),
        ],
        note="Distinct object counts include model/workspace/table context, avoiding repeated-snapshot inflation. Missing schema is not an empty model. Expression text is excluded, and the relationship table currently has no rows.",
    )
    report_page(
        "10",
        "10 Lineage",
        "Investigate declared upstream/downstream links and unresolved/static evidence. No relationship is presented as proof of runtime execution.",
        [
            "Upstream Pairs Observed",
            "Unresolved Lineage Rows",
            "Lineage Diagnostics Rows",
            "Runtime Verified Lineage Rows",
        ],
        [
            (
                "Lineage evidence types",
                "Lineage Edges",
                "Evidence Type",
                "Lineage Edges Rows",
            ),
            (
                "Resolution of retained references",
                "Lineage Edges",
                "Resolution",
                "Lineage Edges Rows",
            ),
        ],
        [
            ("Lineage Edges", "Workspace ID"),
            ("Lineage Edges", "Item ID"),
            ("Lineage Edges", "Direction"),
            ("Lineage Edges", "Related Item ID"),
            ("Lineage Edges", "Relation Type"),
            ("Lineage Edges", "Evidence Type"),
            ("Lineage Edges", "Resolution"),
        ],
        slicers=[
            ("Workspace", "Label"),
            ("Item", "Label"),
            ("Evidence Source", "Source Path"),
        ],
        note="Select a single evidence source for a historical graph interpretation. Do not union all historical edges as current lineage or double-count mirrored upstream/downstream rows. Unknown target workspaces are not inferred.",
    )
    report_page(
        "11",
        "11 Governance",
        "Inspect observed tenant settings and allowed/excluded group rules separately from delegated effective policy.",
        [
            "Tenant Settings Rows",
            "Setting Group Rules Rows",
            "Delegated Overrides Rows",
        ],
        [
            (
                "Observed tenant setting states",
                "Tenant Settings",
                "Enabled",
                "Tenant Settings Rows",
            ),
            (
                "Security group rule observations",
                "Setting Group Rules",
                "Group Rule",
                "Setting Group Rules Rows",
            ),
        ],
        [
            ("Tenant Settings", "Setting Name"),
            ("Tenant Settings", "Title"),
            ("Tenant Settings", "Setting Group"),
            ("Tenant Settings", "Enabled"),
            ("Tenant Settings", "Enabled Group Count"),
            ("Tenant Settings", "Excluded Group Count"),
        ],
        slicers=[("Source Folder Date", "Date"), ("Setting", "Label")],
        note="These are historical settings, not computed inheritance, precedence or effective policy. Select a source-folder day before comparing settings. Delegated scope/override tables currently have no rows.",
    )
    report_page(
        "12",
        "12 Licensing",
        "Understand retained directory/license evidence without publishing names, UPNs or mail. Select one source-folder date for license-unit totals.",
        [
            "Directory Users Observed",
            "Directory Groups Observed",
            "Licensed Users Observed",
            "License Units - Single Date",
        ],
        [
            (
                "License assignments observed by SKU",
                "License SKU",
                "Label",
                "User Licenses Rows",
            ),
            (
                "Directory account-state observations",
                "Directory Users",
                "Account Enabled",
                "Directory Users Rows",
            ),
        ],
        [
            ("Subscribed SKUs", "SKU Part Number"),
            ("Subscribed SKUs", "Capability Status"),
            ("Subscribed SKUs", "Enabled Units"),
            ("Subscribed SKUs", "Consumed Units"),
            ("Subscribed SKUs", "Source Date"),
        ],
        slicers=[("Source Folder Date", "Date")],
        note="Directory IDs remain sensitive and are not anonymous. Membership collection may be optional/capped and is not group nesting or effective authorization. License-unit totals are never summed across multiple source days.",
    )
    report_page(
        "13",
        "13 Change",
        "Inspect retained Git metadata and deployment-pipeline visibility without triggering a deployment or assuming current synchronization.",
        [
            "Git Workspaces Observed",
            "Deployment Pipelines Rows",
            "Deployment Polls Rows",
            "Deployment Operations Rows",
        ],
        [
            (
                "Workspace Git provider observations",
                "Git Connections",
                "Provider Type",
                "Git Connections Rows",
            ),
            (
                "Deployment operation observations",
                "Deployment Operations",
                "Status",
                "Deployment Operations Rows",
            ),
        ],
        [
            ("Git Connections", "Workspace ID"),
            ("Git Connections", "Provider Type"),
            ("Git Connections", "Repository Name"),
            ("Git Connections", "Branch Name"),
            ("Git Connections", "Connection State"),
            ("Git Connections", "Source Date"),
        ],
        slicers=[("Workspace", "Label"), ("Source Folder Date", "Date")],
        note="Git metadata is retained evidence, not a live synchronization test. Owners/directories are hashed; URLs/secrets are excluded. Deployment history needs pipeline Admin and exposes up to 20 recent deployments.",
    )
    report_page(
        "14",
        "14 Organization",
        "Keep apps, domains, tags, workspace roles and broad/public sharing visible as collection questions even when their tables have no rows.",
        [
            "App Inventory Rows",
            "Domain Inventory Rows",
            "Tag Inventory Rows",
            "Public Sharing Rows",
        ],
        [
            (
                "Organizational dataset availability",
                "Dataset",
                "Availability",
                "Dataset Count",
            ),
            (
                "All-domain coverage observations",
                "Domain Coverage",
                "Analysis",
                "Domain Coverage Rows",
            ),
        ],
        [
            ("Dataset", "Label"),
            ("Dataset", "Domain"),
            ("Dataset", "Availability"),
            ("Dataset", "Profiled Rows"),
        ],
        note="No rows is not a clean bill of health. Domain collection omits domains without workspaces; tag definitions do not contain item assignments; app inventory is not audience membership; sharing links are not verified live.",
    )
    report_page(
        "15",
        "Workspace detail",
        "Workspace drillthrough: retained item metadata, permission outcomes, job coverage and lineage evidence for the selected workspace.",
        [
            "Items Observed",
            "Permission Polls - Failed",
            "Successful Empty Job Polls",
            "Upstream Pairs Observed",
        ],
        [
            (
                "Item types in this workspace",
                "Item Inventory",
                "Item Type",
                "Items Observed",
            ),
            (
                "Permission polling in this workspace",
                "Permission Polls",
                "Resource Outcome",
                "Permission Polls Rows",
            ),
        ],
        [
            ("Workspace", "Entity ID"),
            ("Item Inventory", "Item Name"),
            ("Item Inventory", "Item Type"),
            ("Item Inventory", "Coverage Status"),
        ],
        slicers=[("Permission Mode", "Mode")],
        note="Open from a workspace Entity ID in the workspace explorer. Filter context is retained. Historical evidence and partial permissions remain historical/partial; no effective-access inference is performed.",
    )
    detail_path = REPORT / "pages" / PAGES[-1] / "page.json"
    detail = json.loads(detail_path.read_text())
    workspace_field = field("Workspace", "Entity ID")
    detail.update(
        {
            "type": "Drillthrough",
            "visibility": "HiddenInViewMode",
            "filterConfig": {
                "filters": [
                    {
                        "name": "workspace_scope",
                        "type": "Categorical",
                        "field": workspace_field,
                    }
                ]
            },
            "pageBinding": {
                "name": "workspace_detail",
                "type": "Drillthrough",
                "referenceScope": "Default",
                "acceptsFilterContext": "Default",
                "parameters": [
                    {
                        "name": "workspace",
                        "boundFilter": "workspace_scope",
                        "fieldExpr": workspace_field,
                    }
                ],
            },
        }
    )
    write_json(detail_path, detail)
    write_json(
        REPORT / "pages" / "pages.json",
        {
            "$schema": BASE + "/pagesMetadata/1.0.0/schema.json",
            "pageOrder": PAGES,
            "activePageName": PAGES[0],
        },
    )
    write_json(
        REPORT / "version.json",
        {"$schema": BASE + "/versionMetadata/1.0.0/schema.json", "version": "2.0.0"},
    )
    # 3.3 is the published schema; the starter used an unpublished 3.4 URI.
    report_file = REPORT / "report.json"
    document = json.loads(report_file.read_text())
    document["$schema"] = BASE + "/report/3.3.0/schema.json"
    document.setdefault("settings", {})["exportDataMode"] = "AllowSummarized"
    write_json(report_file, document)


def main():
    MEASURES.clear()
    TABLES.clear()
    RELATIONSHIPS.clear()
    PAGES.clear()
    emit_model()
    emit_pages()
    write_json(
        PROJECT / "analysis" / "model-manifest.json",
        {
            "fact_tables": 48,
            "model_tables": TABLES,
            "measures": MEASURES,
            "relationships": [list(value) for value in RELATIONSHIPS],
            "pages": PAGES,
            "additional_physical_tables": [PREFIX + name for name in DERIVED_SCHEMAS],
            "source_expression": "DirectLake - Fabric Estate",
        },
    )
    print(
        f"Generated {len(TABLES)} Direct Lake tables, {len(RELATIONSHIPS)} relationships, {len(MEASURES)} measures and {len(PAGES)} new pages."
    )


if __name__ == "__main__":
    main()
