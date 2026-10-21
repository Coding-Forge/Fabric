"""Offline PBIR integration contracts, not M/DAX execution or schema validation.

These tests parse the real report JSON and inspect the bounded Collection Status
M partition's nullable-table contract. Field contracts are deliberately scoped to
the new pages and About diagnostics, not a substitute for loading the TMDL model.
No native model parser/evaluator or cached Microsoft schemas are available in the
repository's test tooling.
"""

import copy
import json
import re
import unittest
from collections import Counter
from pathlib import Path

from tests.fabric_helpers import deny_network

ROOT = Path(__file__).resolve().parents[1] / "pbip-local" / "MonitorRaw"
REPORT = ROOT / "MonitorRaw.Report"
PAGES = REPORT / "definition" / "pages"
ABOUT, CONNECTIONS, DEPLOYMENTS, PERMISSIONS, JOBS = (
    f"page{number:016d}" for number in (8, 9, 10, 11, 12)
)
INTEGRATION_PAGES = (ABOUT, CONNECTIONS, DEPLOYMENTS, PERMISSIONS, JOBS)
NEW_TABLES = (
    (
        PERMISSIONS,
        "ip_table",
        "Item Permissions",
        [
            "Workspace Id",
            "Item Id",
            "Item Type",
            "Principal Type",
            "Principal Label",
            "Principal Id",
            "Permissions",
            "Additional Permissions",
            "Observed At UTC",
        ],
    ),
    (
        PERMISSIONS,
        "ip_scope",
        "Item Permission Scope",
        [
            "Item Type",
            "Collection Outcome",
            "HTTP Status",
            "Returned Access Details",
            "Observed At UTC",
            "Workspace Id",
            "Item Id",
            "Cycle Id",
        ],
    ),
    (
        JOBS,
        "fjh_table",
        "Fabric Job History",
        [
            "Workspace Id",
            "Item Id",
            "Item Type",
            "Job Instance Id",
            "Status",
            "Job Type",
            "Invoke Type",
            "Start UTC",
            "End UTC",
            "Duration Minutes",
            "Observed At UTC",
        ],
    ),
    (
        JOBS,
        "fjh_scope",
        "Fabric Job Scope",
        [
            "Workspace Id",
            "Item Id",
            "Item Type",
            "Coverage",
            "Returned Job Observations",
            "Attempt UTC",
        ],
    ),
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def objects(value):
    """Walk JSON objects, including nested filter expressions and query state."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


class MonitorRawReportTests(unittest.TestCase):
    def setUp(self):
        for guard in deny_network():
            guard.start()
            self.addCleanup(guard.stop)

    def visual(self, page, name):
        return read_json(PAGES / page / "visuals" / name / "visual.json")

    def assert_role(self, document, role, kind, entity, properties):
        projections = document["visual"]["query"]["queryState"][role]["projections"]
        actual = []
        for projection in projections:
            self.assertEqual(set(projection["field"]), {kind})
            field = projection["field"][kind]
            self.assertEqual(field["Expression"], {"SourceRef": {"Entity": entity}})
            prop = field["Property"]
            self.assertEqual(projection["queryRef"], f"{entity}.{prop}")
            actual.append(prop)
        # Order is presentation-only, but missing/duplicate fields are not.
        self.assertCountEqual(actual, properties)

    def assert_unfiltered(self, document):
        for node in objects(document):
            # Desktop keeps filter-pane metadata even when no filter is applied.
            self.assertNotIn("filter", node, "Unexpected saved filter expression")
            self.assertNotIn(
                "syncGroup", node, "Unexpected cross-page slicer synchronization"
            )

    def assert_no_unprojected_fields(self, document):
        """Sort/format expressions must not introduce hidden payload bindings."""
        state = document["visual"].get("query", {}).get("queryState", {})
        projected = [
            projection["field"]
            for role in state.values()
            for projection in role["projections"]
        ]
        for node in objects(document):
            for kind in ("Column", "Measure"):
                if kind in node:
                    self.assertIn({kind: node[kind]}, projected)

    def assert_collection_status_nullable_contract(self, document):
        """Static M nullable-table contract only; not native M validation."""
        parts = re.split(
            r"(?m)^[ \t]*partition[ \t]+'Collection Status'[ \t]*=[ \t]*m[ \t]*$",
            document,
        )
        self.assertEqual(len(parts), 2, "Expected one Collection Status M partition")
        declarations, partition = parts
        partition = re.split(r"(?m)^[ \t]*annotation\b", partition, maxsplit=1)[0]
        source = re.fullmatch(
            r"\s*mode:\s*import\s+source\s*=\s*(?P<m>.*?)\s*",
            partition,
            re.DOTALL,
        )
        self.assertIsNotNone(source, "Expected the import partition's M source")
        constructor = re.fullmatch(
            r"Table\.FromRecords\s*\(\s*\{(?P<records>[^{}]*)\}\s*,\s*"
            r"type\s+table\s*\[(?P<fields>[^\[\]]*)\]\s*,\s*"
            r"MissingField\.UseNull\s*\)",
            source["m"],
        )
        # Other collectors omit permission metadata. UseNull is required for
        # those absent record fields, not merely a formatting preference.
        self.assertIsNotNone(
            constructor, "Expected typed Table.FromRecords with MissingField.UseNull"
        )
        self.assertEqual(
            re.sub(r"\s+", "", constructor["records"]).split(","),
            [
                "FabricConnectionsData[Status]",
                "FabricDeploymentData[Status]",
                "FabricItemPermissionsData[Status]",
                "FabricItemJobsData[Status]",
            ],
        )
        # Consume the entire bounded field list: never collect DAX references,
        # annotations, or only the subset that happens to match nullable types.
        field = (
            r'(?P<name>#"(?:[^"]|"")*"|[A-Za-z_][A-Za-z_0-9]*)\s*=\s*'
            r"(?:(?P<nullable>nullable)\s+)?"
            r"(?P<primitive>text|number|logical|datetime)"
        )
        anonymous_field = re.sub(r"\?P<[^>]+>", "?:", field)
        self.assertRegex(
            constructor["fields"],
            rf"\A\s*{field}(?:\s*,\s*{anonymous_field})*\s*\Z",
        )
        names = []
        for match in re.finditer(field, constructor["fields"]):
            name = match["name"]
            if name.startswith('#"'):
                name = name[2:-1].replace('""', '"')
            names.append(name)
            self.assertEqual(match["nullable"], "nullable", f"{name} must be nullable")

        # Read only column child properties, not measures or annotations.
        source_columns = []
        for column in re.finditer(
            r"(?m)^(?P<indent>[ \t]+)column[ \t]+[^\n]+\n"
            r"(?P<body>(?:(?P=indent)[ \t]+[^\n]*\n|[ \t]*\n)*)",
            declarations,
        ):
            columns = re.findall(
                r"(?m)^[ \t]*sourceColumn:[ \t]*([^\n]+)", column["body"]
            )
            self.assertEqual(len(columns), 1, "Expected one sourceColumn per column")
            source_columns.append(columns[0].strip())
        self.assertTrue(source_columns, "Expected semantic column declarations")
        self.assertEqual(len(names), len(set(names)), "Duplicate M fields")
        self.assertCountEqual(names, source_columns)

    def test_job_visual_fields_exist_in_the_saved_semantic_model(self):
        """Resolve saved visual bindings, not just their expected JSON shape."""
        model = ROOT / "MonitorRaw.SemanticModel" / "definition"
        for path in (PAGES / JOBS).glob("visuals/*/visual.json"):
            for node in objects(read_json(path)):
                for kind in ("Column", "Measure"):
                    if kind not in node:
                        continue
                    field = node[kind]
                    entity = field["Expression"]["SourceRef"]["Entity"]
                    document = (model / "tables" / f"{entity}.tmdl").read_text(
                        encoding="utf-8"
                    )
                    declarations = re.findall(
                        rf"(?m)^\t{kind.lower()} (?:'([^']+)'|([^\s=]+))(?=\s|$)",
                        document,
                    )
                    names = {quoted or bare for quoted, bare in declarations}
                    with self.subTest(visual=path.parent.name, field=field["Property"]):
                        self.assertIn(field["Property"], names)

        jobs = (model / "tables" / "Fabric Job History.tmdl").read_text(
            encoding="utf-8"
        )
        source_columns = re.findall(r"(?m)^\t\tsourceColumn: (.+)$", jobs)
        projection = re.search(
            r'Table\.SelectColumns\(#"Expanded jobs", \{([^}]+)\}\)', jobs
        )
        self.assertIsNotNone(projection)
        projected = re.findall(r'"([^"]+)"', projection[1])
        self.assertCountEqual(
            source_columns, projected + ["Job Date", "Duration Minutes"]
        )
        self.assertRegex(
            jobs,
            r'Table\.Distinct\(Sorted, \{"Workspace Id", "Item Id", "Job Instance Id"\}\)',
        )
        self.assertNotIn("failureReason", jobs)

    def test_empty_job_and_permission_lists_are_filtered_before_fact_expansion(self):
        """Static empty-list admission contract; does not execute native M."""
        tables = ROOT / "MonitorRaw.SemanticModel" / "definition" / "tables"
        for table in ("Fabric Job History", "Item Permissions"):
            document = (tables / f"{table}.tmdl").read_text(encoding="utf-8")
            with self.subTest(table=table):
                self.assertRegex(
                    document,
                    r"NonEmpty\s*=\s*Table\.SelectRows\(Files,\s*"
                    r"each not List\.IsEmpty\(\[Json\]\[records\]\)\)",
                )
                if table == "Fabric Job History":
                    self.assertIn('Table.ExpandRecordColumn(NonEmpty, "Json"', document)
                    self.assertIn(
                        'Table.ExpandListColumn(#"Expanded parent", "records")',
                        document,
                    )
                else:
                    self.assertIn(
                        'Table.ExpandListColumn(Table.AddColumn(NonEmpty, "Item"',
                        document,
                    )

    def test_collection_status_m_table_fields_are_all_nullable(self):
        """Static missing-metadata/type contract; no M engine is executed."""
        document = (
            ROOT
            / "MonitorRaw.SemanticModel"
            / "definition"
            / "tables"
            / "Collection Status.tmdl"
        ).read_text(encoding="utf-8")
        self.assert_collection_status_nullable_contract(document)
        # Equivalent lexical spellings must not make this a whitespace snapshot.
        spaced = document.replace(" = nullable ", "  = \t nullable   ")
        spaced = spaced.replace("Module  =", '#"Module"  =')
        self.assert_collection_status_nullable_contract(spaced)

    def test_collection_status_contract_rejects_nonnullable_and_missing_field_mutations(
        self,
    ):
        """In-memory regressions demonstrate static checks, not M execution."""
        document = (
            ROOT
            / "MonitorRaw.SemanticModel"
            / "definition"
            / "tables"
            / "Collection Status.tmdl"
        ).read_text(encoding="utf-8")
        for identifier in (
            "Module",
            "State",
            '#"Has Snapshot"',
            '#"Latest Run Complete"',
            '#"Error Count"',
            "Coverage",
        ):
            mutated, count = re.subn(
                rf"({re.escape(identifier)}\s*=\s*)nullable\s+",
                r"\1",
                document,
            )
            self.assertEqual(count, 1)
            with (
                self.subTest(nonnullable=identifier),
                self.assertRaisesRegex(AssertionError, "must be nullable"),
            ):
                self.assert_collection_status_nullable_contract(mutated)
        for before, after in (
            ("MissingField.UseNull", "MissingField.Error"),
            (", MissingField.UseNull", ""),
            ("FabricItemPermissionsData[Status]", "FabricItemJobsData[Status]"),
            ('#"Permission Expected Targets"', '#"Unknown Permission Field"'),
        ):
            self.assertEqual(document.count(before), 1)
            with (
                self.subTest(mutation=before, replacement=after),
                self.assertRaises(AssertionError),
            ):
                self.assert_collection_status_nullable_contract(
                    document.replace(before, after)
                )

    def test_page_registry_has_no_orphans_duplicates_or_missing_new_pages(self):
        registry = read_json(PAGES / "pages.json")
        order = registry["pageOrder"]
        discovered = {path.parent.name for path in PAGES.glob("*/page.json")}
        self.assertEqual(len(order), len(set(order)))
        self.assertEqual(set(order), discovered)
        self.assertIn(registry["activePageName"], discovered)
        for page in INTEGRATION_PAGES:
            self.assertIn(page, order)
            document = read_json(PAGES / page / "page.json")
            self.assertEqual(document["name"], page)
            self.assertNotEqual(document.get("visibility"), "HiddenInViewMode")
            visuals = list((PAGES / page).glob("visuals/*/visual.json"))
            self.assertTrue(visuals, page)
            names = [read_json(path)["name"] for path in visuals]
            self.assertEqual(len(names), len(set(names)))
            for path, name in zip(visuals, names):
                self.assertEqual(name, path.parent.name)
                self.assert_no_unprojected_fields(read_json(path))
        # Also catch dropped/extra visuals, not just a page with one surviving card.
        for page, expected in (
            (
                PERMISSIONS,
                {
                    "card": 5,
                    "slicer": 4,
                    "tableEx": 3,
                    "textbox": 1,
                    "clusteredBarChart": 1,
                },
            ),
            (
                JOBS,
                {
                    "card": 5,
                    "slicer": 4,
                    "tableEx": 3,
                    "textbox": 1,
                    "clusteredBarChart": 1,
                    "clusteredColumnChart": 1,
                },
            ),
        ):
            with self.subTest(page=page):
                actual = Counter(
                    read_json(path)["visual"]["visualType"]
                    for path in (PAGES / page).glob("visuals/*/visual.json")
                )
                self.assertEqual(actual, expected)

    def test_report_links_to_this_projects_semantic_model(self):
        reference = read_json(REPORT / "definition.pbir")["datasetReference"]
        self.assertEqual(set(reference), {"byPath"})
        target = (REPORT / reference["byPath"]["path"]).resolve()
        self.assertEqual(target, (ROOT / "MonitorRaw.SemanticModel").resolve())
        self.assertTrue((target / "definition.pbism").is_file())
        self.assertTrue((target / "definition" / "model.tmdl").is_file())
        # Artifact existence only: this is not TMDL declaration validation.
        for table in {contract[2] for contract in NEW_TABLES} | {"Collection Status"}:
            self.assertTrue(
                (target / "definition" / "tables" / f"{table}.tmdl").is_file()
            )

    def test_cards_and_health_visuals_bind_explicit_measures_not_implicit_counts(self):
        contracts = (
            (CONNECTIONS, "cnx_card_count", "Connections", "Connection Count"),
            (
                CONNECTIONS,
                "cnx_card_gateway",
                "Connections",
                "Connections With Gateway Id",
            ),
            (
                CONNECTIONS,
                "cnx_status",
                "Collection Status",
                "Connections Collection Status",
            ),
            (
                DEPLOYMENTS,
                "dpo_card_pipelines",
                "Deployment Pipelines",
                "Visible Pipeline Count",
            ),
            (
                DEPLOYMENTS,
                "dpo_card_count",
                "Deployment Operations",
                "Deployment Operation Count",
            ),
            (
                DEPLOYMENTS,
                "dpo_card_failed",
                "Deployment Operations",
                "Failed Deployment Operations",
            ),
            (
                DEPLOYMENTS,
                "dpo_card_executing",
                "Deployment Operations",
                "Executing Deployment Operations",
            ),
            (
                DEPLOYMENTS,
                "dpo_card_duration",
                "Deployment Operations",
                "Average Deployment Duration (min)",
            ),
            (
                DEPLOYMENTS,
                "dpo_status",
                "Collection Status",
                "Deployment Collection Status",
            ),
            (ABOUT, "about_card_errors", "Capacity Metrics", "Load Errors"),
            (PERMISSIONS, "ip_card_grants", "Item Permissions", "Observed Grant Count"),
            (PERMISSIONS, "ip_card_items", "Item Permissions", "Items With Grants"),
            (
                PERMISSIONS,
                "ip_card_principals",
                "Item Permissions",
                "Principals With Grants",
            ),
            (
                PERMISSIONS,
                "ip_card_scope",
                "Collection Status",
                "Permission Successful Target Count",
            ),
            (
                PERMISSIONS,
                "ip_card_expected",
                "Collection Status",
                "Permission Expected Target Count",
            ),
            (
                PERMISSIONS,
                "ip_status",
                "Collection Status",
                "Permission Coverage Warning",
            ),
            (JOBS, "fjh_card_count", "Fabric Job History", "Fabric Job Count"),
            (JOBS, "fjh_card_failed", "Fabric Job History", "Failed Fabric Jobs"),
            (JOBS, "fjh_card_running", "Fabric Job History", "Running Fabric Jobs"),
            (JOBS, "fjh_card_canceled", "Fabric Job History", "Canceled Fabric Jobs"),
            (
                JOBS,
                "fjh_card_duration",
                "Fabric Job History",
                "Average Fabric Job Duration (min)",
            ),
            (JOBS, "fjh_status", "Collection Status", "Fabric Jobs Collection Status"),
        )
        for page, name, entity, measure in contracts:
            with self.subTest(visual=name):
                self.assert_role(
                    self.visual(page, name), "Values", "Measure", entity, [measure]
                )

    def test_chart_axes_and_slicers_use_fact_fields_including_historical_date(self):
        contracts = (
            (
                CONNECTIONS,
                "cnx_bar_type",
                "Connections",
                "Connectivity Type",
                "Connection Count",
            ),
            (
                DEPLOYMENTS,
                "dpo_bar_status",
                "Deployment Operations",
                "Status",
                "Deployment Operation Count",
            ),
            (
                DEPLOYMENTS,
                "dpo_col_date",
                "Deployment Operations",
                "Execution Date",
                "Deployment Operation Count",
            ),
            (
                PERMISSIONS,
                "ip_bar_principal",
                "Item Permissions",
                "Principal Type",
                "Observed Grant Count",
            ),
            (
                JOBS,
                "fjh_bar_status",
                "Fabric Job History",
                "Status",
                "Fabric Job Count",
            ),
            (
                JOBS,
                "fjh_col_date",
                "Fabric Job History",
                "Job Date",
                "Fabric Job Count",
            ),
        )
        for page, name, entity, column, measure in contracts:
            with self.subTest(visual=name):
                document = self.visual(page, name)
                self.assert_role(document, "Category", "Column", entity, [column])
                self.assert_role(document, "Y", "Measure", entity, [measure])

        slicers = (
            (CONNECTIONS, "cnx_slicer_type", "Connections", "Connectivity Type"),
            (CONNECTIONS, "cnx_slicer_gateway", "Connections", "Gateway Assignment"),
            (DEPLOYMENTS, "dpo_slicer_date", "Deployment Operations", "Execution Date"),
            (
                DEPLOYMENTS,
                "dpo_slicer_pipeline",
                "Deployment Operations",
                "Pipeline Name",
            ),
            (DEPLOYMENTS, "dpo_slicer_status", "Deployment Operations", "Status"),
            (DEPLOYMENTS, "dpo_slicer_type", "Deployment Operations", "Type"),
            (PERMISSIONS, "ip_slicer_workspace", "Item Permissions", "Workspace Id"),
            (PERMISSIONS, "ip_slicer_item", "Item Permissions", "Item Id"),
            (PERMISSIONS, "ip_slicer_type", "Item Permissions", "Item Type"),
            (PERMISSIONS, "ip_slicer_principal", "Item Permissions", "Principal Type"),
            (JOBS, "fjh_slicer_workspace", "Fabric Job History", "Workspace Id"),
            (JOBS, "fjh_slicer_type", "Fabric Job History", "Item Type"),
            (JOBS, "fjh_slicer_status", "Fabric Job History", "Status"),
            (JOBS, "fjh_slicer_date", "Fabric Job History", "Job Date"),
        )
        for page, name, entity, column in slicers:
            with self.subTest(visual=name):
                document = self.visual(page, name)
                self.assertEqual(document["visual"]["visualType"], "slicer")
                self.assert_role(document, "Values", "Column", entity, [column])

    def test_inventory_uses_ui_label_and_only_safe_metadata_columns(self):
        document = self.visual(CONNECTIONS, "cnx_table")
        self.assert_role(
            document,
            "Values",
            "Column",
            "Connections",
            [
                "Connection Label",
                "Connection Id",
                "Connectivity Type",
                "Connection Type",
                "Privacy Level",
                "Gateway Assignment",
                "Gateway Id",
            ],
        )

    def test_history_exposes_parent_identity_and_about_exposes_load_diagnostics(self):
        contracts = (
            (
                DEPLOYMENTS,
                "dpo_table",
                "Deployment Operations",
                [
                    "Pipeline Name",
                    "Pipeline Id",
                    "Operation Id",
                    "Status",
                    "Type",
                    "Source Stage Id",
                    "Target Stage Id",
                    "Execution Start UTC",
                    "Execution End UTC",
                    "Duration Minutes",
                    "Observed At UTC",
                ],
            ),
            (
                DEPLOYMENTS,
                "dpo_table_pipelines",
                "Deployment Pipelines",
                ["Pipeline Name", "Pipeline Id"],
            ),
            (
                ABOUT,
                "about_collection_status",
                "Collection Status",
                [
                    "Module",
                    "State",
                    "Last Attempt UTC",
                    "Snapshot UTC",
                    "Snapshot Row Count",
                    "Error Count",
                    "Load Error",
                ],
            ),
        )
        for page, name, entity, columns in (*contracts, *NEW_TABLES):
            with self.subTest(visual=name):
                self.assert_role(
                    self.visual(page, name), "Values", "Column", entity, columns
                )
        # Descending outcome is intentional: failures must not be sorted away.
        self.assertEqual(
            self.visual(PERMISSIONS, "ip_scope")["visual"]["query"]["sortDefinition"],
            {
                "sort": [
                    {
                        "field": {
                            "Column": {
                                "Expression": {
                                    "SourceRef": {"Entity": "Item Permission Scope"}
                                },
                                "Property": "Collection Outcome",
                            }
                        },
                        "direction": "Descending",
                    }
                ],
                "isDefaultSort": True,
            },
        )
        # User-facing scope limitations must stay visible, not just in tooltips.
        for page, name, phrases in (
            (
                PERMISSIONS,
                "ip_text",
                (
                    "newest finished with successful observations",
                    "including empty success",
                    "otherwise newest useful in-progress",
                    "No cross-cycle grant carry-forward",
                    "not effective access or a point-in-time snapshot",
                    "Failed, deferred and unvisited targets do NOT mean no access",
                    "No Graph group expansion",
                    "Slicers filter grants/principals only",
                    "Warning, target counts and known-target coverage stay global",
                    "unknown identities are not fabricated",
                ),
            ),
            (
                JOBS,
                "fjh_text",
                (
                    "polling gaps cannot be recovered",
                    "even for deselected items",
                    "may omit unvisited targets",
                    "Raw failure payloads excluded",
                ),
            ),
        ):
            document = self.visual(page, name)
            self.assertEqual(document["visual"]["visualType"], "textbox")
            text = " ".join(
                run["value"]
                for node in objects(document)
                for run in node.get("textRuns", [])
            )
            for phrase in phrases:
                with self.subTest(visual=name, limitation=phrase):
                    self.assertIn(phrase, text)

    def test_about_filter_metadata_is_allowed_but_filter_definitions_are_rejected(self):
        for name in ("about_card_errors", "about_collection_status"):
            document = self.visual(ABOUT, name)
            self.assert_unfiltered(document)
            filters = document["filterConfig"]["filters"]
            self.assertTrue(filters)
            for index in range(len(filters)):
                mutated = copy.deepcopy(document)
                mutated["filterConfig"]["filters"][index]["filter"] = {"Version": 2}
                with (
                    self.subTest(visual=name, filter_index=index),
                    self.assertRaisesRegex(AssertionError, "saved filter expression"),
                ):
                    self.assert_unfiltered(mutated)

    def test_no_saved_filters_hide_health_or_restrict_retained_history(self):
        # A saved relative-date/status filter can silently hide old operations,
        # future API status values, or failed/never-run health diagnostics.
        paths = [REPORT / "definition" / "report.json"]
        for page in INTEGRATION_PAGES:
            paths.append(PAGES / page / "page.json")
            paths.extend((PAGES / page).glob("visuals/*/visual.json"))
        for path in paths:
            with self.subTest(artifact=path.relative_to(REPORT)):
                self.assert_unfiltered(read_json(path))

        # Structural isolation, not a DAX evaluation: the warning/counts must
        # bind only disconnected diagnostics, never principal-filtered grants.
        for name, measure in (
            ("ip_status", "Permission Coverage Warning"),
            ("ip_card_scope", "Permission Successful Target Count"),
            ("ip_card_expected", "Permission Expected Target Count"),
        ):
            document = self.visual(PERMISSIONS, name)
            with self.subTest(global_coverage=name):
                self.assert_role(
                    document, "Values", "Measure", "Collection Status", [measure]
                )
                self.assert_no_unprojected_fields(document)
                self.assert_unfiltered(document)
        # Inspect relationship endpoint declarations only, not M/DAX source.
        # Diagnostics and scope must remain independent of fact slicers.
        relationships = (
            ROOT / "MonitorRaw.SemanticModel" / "definition" / "relationships.tmdl"
        ).read_text(encoding="utf-8")
        for line in relationships.splitlines():
            key, separator, endpoint = line.strip().partition(":")
            if separator and key in ("fromColumn", "toColumn"):
                table = endpoint.strip().rsplit(".", 1)[0].strip("'")
                self.assertNotIn(
                    table,
                    {"Collection Status", "Item Permission Scope", "Fabric Job Scope"},
                )

    def test_new_page_contracts_reject_projection_and_ancestor_filter_mutations(self):
        # Mutate parsed production JSON only in memory. These demonstrate that
        # the contracts reject dangerous rewiring, not M/DAX runtime behavior.
        for page, name, entity, columns in NEW_TABLES:
            original = self.visual(page, name)
            for mutation in ("missing parent", "duplicate", "raw payload", "measure"):
                document = copy.deepcopy(original)
                projections = document["visual"]["query"]["queryState"]["Values"][
                    "projections"
                ]
                if mutation == "missing parent":
                    # Workspace Id disambiguates cross-workspace items.
                    projections[:] = [
                        projection
                        for projection in projections
                        if projection["field"]["Column"]["Property"] != "Workspace Id"
                    ]
                elif mutation == "duplicate":
                    projections.append(copy.deepcopy(projections[0]))
                elif mutation == "raw payload":
                    projections[0]["field"]["Column"]["Property"] = "failureReason"
                    projections[0]["queryRef"] = f"{entity}.failureReason"
                else:
                    projections[0]["field"]["Measure"] = projections[0]["field"].pop(
                        "Column"
                    )
                with (
                    self.subTest(visual=name, mutation=mutation),
                    self.assertRaises(AssertionError),
                ):
                    self.assert_role(document, "Values", "Column", entity, columns)

        for page, name, entity, column in (
            (PERMISSIONS, "ip_slicer_principal", "Item Permissions", "Principal Type"),
            (JOBS, "fjh_slicer_date", "Fabric Job History", "Job Date"),
        ):
            document = copy.deepcopy(self.visual(page, name))
            projection = document["visual"]["query"]["queryState"]["Values"][
                "projections"
            ][0]
            projection["field"]["Column"]["Expression"]["SourceRef"]["Entity"] = (
                "Calendar"
            )
            projection["queryRef"] = f"Calendar.{column}"
            with (
                self.subTest(visual=name, mutation="wrong source"),
                self.assertRaises(AssertionError),
            ):
                self.assert_role(document, "Values", "Column", entity, [column])

        for page, name, entity, measure in (
            (PERMISSIONS, "ip_card_grants", "Item Permissions", "Observed Grant Count"),
            (JOBS, "fjh_card_count", "Fabric Job History", "Fabric Job Count"),
            (
                PERMISSIONS,
                "ip_status",
                "Collection Status",
                "Permission Coverage Warning",
            ),
            (
                PERMISSIONS,
                "ip_card_scope",
                "Collection Status",
                "Permission Successful Target Count",
            ),
            (
                PERMISSIONS,
                "ip_card_expected",
                "Collection Status",
                "Permission Expected Target Count",
            ),
            (JOBS, "fjh_status", "Collection Status", "Fabric Jobs Collection Status"),
        ):
            document = self.visual(page, name)
            field = document["visual"]["query"]["queryState"]["Values"]["projections"][
                0
            ]["field"]
            field["Column"] = field.pop("Measure")
            with (
                self.subTest(visual=name, mutation="implicit column"),
                self.assertRaises(AssertionError),
            ):
                self.assert_role(document, "Values", "Measure", entity, [measure])
            document = self.visual(page, name)
            projection = document["visual"]["query"]["queryState"]["Values"][
                "projections"
            ][0]
            projection["field"]["Measure"]["Property"] = "Snapshot Row Count"
            projection["queryRef"] = f"{entity}.Snapshot Row Count"
            with (
                self.subTest(visual=name, mutation="wrong counted field"),
                self.assertRaises(AssertionError),
            ):
                self.assert_role(document, "Values", "Measure", entity, [measure])

        for page, name, entity, _columns in NEW_TABLES:
            document = self.visual(page, name)
            document["visual"]["query"]["sortDefinition"] = {
                "sort": [
                    {
                        "field": {
                            "Column": {
                                "Expression": {"SourceRef": {"Entity": entity}},
                                "Property": "failureReason",
                            }
                        },
                        "direction": "Ascending",
                    }
                ]
            }
            with (
                self.subTest(visual=name, mutation="hidden payload sort"),
                self.assertRaises(AssertionError),
            ):
                self.assert_no_unprojected_fields(document)

        for page in (PERMISSIONS, JOBS):
            for path in (
                REPORT / "definition" / "report.json",
                PAGES / page / "page.json",
                PAGES
                / page
                / "visuals"
                / ("ip_status" if page == PERMISSIONS else "fjh_status")
                / "visual.json",
            ):
                document = read_json(path)
                document["filterConfig"] = {"filters": [{"filter": {"Version": 2}}]}
                with (
                    self.subTest(page=page, ancestor=path.name),
                    self.assertRaises(AssertionError),
                ):
                    self.assert_unfiltered(document)
