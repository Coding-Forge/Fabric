"""Offline Catalog lineage wiring contracts, not M/DAX execution or rendering."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "pbip-local" / "Catalog"
MODEL = ROOT / "Schema.SemanticModel" / "definition"
PAGES = ROOT / "Schema.Report" / "definition" / "pages"
PAGE = PAGES / "lineage"
TABLES = ("Lineage Workspaces", "Lineage Items", "Lineage Edges", "Lineage Diagnostics")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def fields(source, kind):
    return set(re.findall(rf"^\t{kind} (?:'([^']+)'|([^ =\n]+))", source, re.MULTILINE))


class CatalogLineageReportTests(unittest.TestCase):
    def visual(self, name):
        return read_json(PAGE / "visuals" / name / "visual.json")

    def test_page_registration_navigation_and_layout(self):
        registry = read_json(PAGES / "pages.json")
        self.assertEqual(registry["pageOrder"].count("lineage"), 1)
        self.assertIn(registry["activePageName"], registry["pageOrder"])
        for name in registry["pageOrder"]:
            self.assertTrue((PAGES / name / "page.json").is_file())
        page = read_json(PAGE / "page.json")
        self.assertEqual(page["displayName"], "Lineage")
        documents = list((PAGE / "visuals").glob("*/visual.json"))
        names = set()
        positions = []
        for path in documents:
            doc = read_json(path)
            self.assertEqual(doc["name"], path.parent.name)
            self.assertNotIn(doc["name"], names)
            names.add(doc["name"])
            p = doc["position"]
            self.assertGreater(p["width"], 0)
            self.assertGreater(p["height"], 0)
            self.assertGreaterEqual(p["x"], 0)
            self.assertGreaterEqual(p["y"], 0)
            self.assertLessEqual(p["x"] + p["width"], page["width"])
            self.assertLessEqual(p["y"] + p["height"], page["height"])
            for other in positions:
                self.assertTrue(
                    p["x"] + p["width"] <= other["x"]
                    or other["x"] + other["width"] <= p["x"]
                    or p["y"] + p["height"] <= other["y"]
                    or other["y"] + other["height"] <= p["y"],
                    f"Overlapping visual: {doc['name']}",
                )
            positions.append(p)
        self.assertEqual(
            self.visual("lin_nav")["visual"]["visualType"], "pageNavigator"
        )

    def test_visual_bindings_resolve_to_model_columns_and_measures(self):
        contracts = {}
        model = (MODEL / "model.tmdl").read_text()
        for name in TABLES:
            self.assertIn(f"ref table '{name}'", model)
            source = (MODEL / "tables" / f"{name}.tmdl").read_text()
            contracts[name] = {
                kind: {
                    quoted or plain for quoted, plain in fields(source, kind.lower())
                }
                for kind in ("Column", "Measure")
            }
        for path in (PAGE / "visuals").glob("*/visual.json"):
            doc = read_json(path)
            for node in objects(doc):
                for kind in ("Column", "Measure"):
                    if kind not in node:
                        continue
                    field = node[kind]
                    ref = field["Expression"]["SourceRef"]
                    # The only alias is the fixed Direction filter's source.
                    entity = ref.get(
                        "Entity", "Lineage Edges" if ref.get("Source") == "e" else None
                    )
                    self.assertIn(entity, contracts, path)
                    self.assertIn(field["Property"], contracts[entity][kind], path)
                if "queryRef" in node:
                    kind, field = next(iter(node["field"].items()))
                    entity = field["Expression"]["SourceRef"]["Entity"]
                    self.assertEqual(node["queryRef"], f"{entity}.{field['Property']}")

    def test_direction_tables_preserve_identity_and_only_filter_direction(self):
        for name, direction in (
            ("lin_upstream", "upstream"),
            ("lin_downstream", "downstream"),
        ):
            doc = self.visual(name)
            projections = doc["visual"]["query"]["queryState"]["Values"]["projections"]
            properties = [p["field"]["Column"]["Property"] for p in projections]
            for required in (
                "Query Item Id",
                "Related Item Id",
                "Related Workspace Id",
                "Relation Type",
                "Resolution",
                "Observed At UTC",
            ):
                self.assertIn(required, properties)
            filters = doc["filterConfig"]["filters"]
            self.assertEqual(len(filters), 1)
            self.assertEqual(filters[0]["field"]["Column"]["Property"], "Direction")
            condition = filters[0]["filter"]["Where"][0]["Condition"]["In"]
            self.assertEqual(
                condition["Expressions"][0]["Column"]["Property"], "Direction"
            )
            self.assertEqual(
                condition["Values"], [[{"Literal": {"Value": f"'{direction}'"}}]]
            )
        for name, entity, prop in (
            ("lin_workspace", "Lineage Workspaces", "Workspace"),
            ("lin_item", "Lineage Items", "Item"),
        ):
            doc = self.visual(name)
            field = doc["visual"]["query"]["queryState"]["Values"]["projections"][0][
                "field"
            ]["Column"]
            self.assertEqual(
                field,
                {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop},
            )

    def test_diagnostics_cannot_be_hidden_by_item_relationships_or_saved_filters(self):
        relations = (MODEL / "relationships.tmdl").read_text()
        self.assertNotIn("'Lineage Diagnostics'", relations)
        for block in relations.split("relationship ")[1:]:
            if "'Lineage " in block:
                self.assertNotIn("bothDirections", block)
        self.assertIn("fromColumn: 'Lineage Edges'.'Item Key'", relations)
        self.assertIn("toColumn: 'Lineage Items'.'Item Key'", relations)
        self.assertIn("fromColumn: 'Lineage Items'.'Workspace Id'", relations)
        self.assertIn("toColumn: 'Lineage Workspaces'.'Workspace Id'", relations)
        for name in ("lin_health", "lin_files", "lin_errors_count", "lin_coverage"):
            for node in objects(self.visual(name)):
                self.assertNotIn("filter", node)
                self.assertNotIn("syncGroup", node)
        for path in (PAGE / "page.json", PAGES.parent / "report.json"):
            for node in objects(read_json(path)):
                self.assertNotIn("filter", node)
        diagnostics = (MODEL / "tables" / "Lineage Diagnostics.tmdl").read_text()
        self.assertIn("REMOVEFILTERS()", diagnostics)
        self.assertIn("Selected observations may be stale", diagnostics)
        self.assertIn("NO RETURNED WORKSPACE OBSERVATIONS", diagnostics)

    def test_snapshot_selection_precedes_expansion_and_preserves_empty_observations(
        self,
    ):
        source = (MODEL / "expressions.tmdl").read_text()
        lineage = source.split("expression LineageData =")[1].split("\n\tlineageTag:")[
            0
        ]
        self.assertIn('Table.Group(CandidateTable, {"Workspace Id"}', lineage)
        self.assertIn('{"Observed At UTC", Order.Descending}', lineage)
        self.assertIn('{"Scan Id", Order.Descending}', lineage)
        self.assertLess(
            lineage.index("Groups = Table.Group"), lineage.index("ItemRows =")
        )
        self.assertLess(
            lineage.index("Groups = Table.Group"), lineage.index("EdgeRows =")
        )
        self.assertIn("List.Transform(Selected", lineage)
        self.assertIn("no supported items observed", lineage)
        self.assertIn("Rejected / unreadable snapshot", lineage)
        self.assertIn("Lineage folder unavailable", lineage)
        self.assertIn("No lineage snapshot files", lineage)
        self.assertIn("List.Difference(a[Document][requestedWorkspaceIds]", lineage)
        self.assertIn("Record.HasFields", lineage)
        for name in TABLES:
            table = (MODEL / "tables" / f"{name}.tmdl").read_text()
            schema = re.search(
                r"type table \[(.*?)\], MissingField.UseNull", table, re.DOTALL
            )
            self.assertIsNotNone(schema, name)
            types = re.findall(r"=\s*([^,\n]+)", schema[1])
            self.assertTrue(types, name)
            self.assertTrue(all(t.startswith("nullable ") for t in types), name)
        catalog = "\n".join(p.read_text() for p in MODEL.rglob("*.tmdl"))
        self.assertNotIn(
            'Folder.Files("C:\\Projects\\Tests\\monitor\\catalog\\scans")', catalog
        )
        self.assertIn(
            'expression CatalogOutputPath = "C:\\Projects\\Tests\\monitor-poc-output"',
            source,
        )


class CatalogLineageGraphsTests(unittest.TestCase):
    def visual(self, name):
        return read_json(PAGES / "lineage_graphs" / "visuals" / name / "visual.json")

    def test_gallery_visuals_use_verified_roles_and_same_canonical_link_measure(self):
        registered = read_json(PAGES.parent / "report.json")["publicCustomVisuals"]
        expected = {
            "lg_sankey": (
                "sankey02300D1BE6F5427989F3DE31CCA9E0F32020",
                {
                    "Source": ("Column", ["Source"]),
                    "Destination": ("Column", ["Consumer"]),
                    "Weight": ("Measure", ["Graph Link Weight"]),
                },
            ),
            "lg_chord": (
                "ChordChart1444757060245",
                {
                    "Category": ("Column", ["Source"]),
                    "Series": ("Column", ["Consumer"]),
                    "Y": ("Measure", ["Graph Link Weight"]),
                },
            ),
            "lg_network": (
                "ZoomChartsDrillDownNetworkProA2D748C23BD44BE2BB019402882BCA19",
                {
                    "Nodes": ("Column", ["Source", "Consumer"]),
                    "Size": ("Measure", ["Graph Link Weight"]),
                },
            ),
        }
        links = (MODEL / "tables" / "Lineage Graph Links.tmdl").read_text()
        declared = {
            kind: {a or b for a, b in fields(links, kind.lower())}
            for kind in ("Column", "Measure")
        }
        for name, (visual_type, roles) in expected.items():
            doc = self.visual(name)
            self.assertIn(visual_type, registered)
            self.assertEqual(doc["visual"]["visualType"], visual_type)
            state = doc["visual"]["query"]["queryState"]
            self.assertEqual(set(state), set(roles))
            for role, (kind, properties) in roles.items():
                projections = state[role]["projections"]
                self.assertEqual(len(projections), len(properties))
                for projection, prop in zip(projections, properties, strict=True):
                    self.assertIn(prop, declared[kind])
                    self.assertEqual(
                        projection["field"],
                        {
                            kind: {
                                "Expression": {
                                    "SourceRef": {"Entity": "Lineage Graph Links"}
                                },
                                "Property": prop,
                            }
                        },
                    )
                    self.assertEqual(
                        projection["queryRef"], f"Lineage Graph Links.{prop}"
                    )
            for node in objects(doc):
                self.assertNotIn("filter", node)

    def test_graph_page_bindings_layout_and_diagnostics(self):
        root = PAGES / "lineage_graphs"
        registry = read_json(PAGES / "pages.json")
        self.assertEqual(registry["pageOrder"].count("lineage_graphs"), 1)
        page = read_json(root / "page.json")
        contracts = {}
        for name in (*TABLES, "Lineage Graph Links", "Lineage Graph Nodes"):
            source = (MODEL / "tables" / f"{name}.tmdl").read_text()
            contracts[name] = {
                kind: {a or b for a, b in fields(source, kind.lower())}
                for kind in ("Column", "Measure")
            }
        positions = []
        for path in (root / "visuals").glob("*/visual.json"):
            doc = read_json(path)
            self.assertEqual(doc["name"], path.parent.name)
            p = doc["position"]
            self.assertLessEqual(p["x"] + p["width"], page["width"])
            self.assertLessEqual(p["y"] + p["height"], page["height"])
            for other in positions:
                self.assertTrue(
                    p["x"] + p["width"] <= other["x"]
                    or other["x"] + other["width"] <= p["x"]
                    or p["y"] + p["height"] <= other["y"]
                    or other["y"] + other["height"] <= p["y"]
                )
            positions.append(p)
            for node in objects(doc):
                self.assertNotIn("filter", node)
                self.assertNotIn("syncGroup", node)
                for kind in ("Column", "Measure"):
                    if kind in node:
                        field = node[kind]
                        entity = field["Expression"]["SourceRef"]["Entity"]
                        self.assertIn(field["Property"], contracts[entity][kind])
        for name in ("lg_health", "lg_errors"):
            entities = [
                n["SourceRef"]["Entity"]
                for n in objects(self.visual(name))
                if "SourceRef" in n
            ]
            self.assertEqual(entities, ["Lineage Diagnostics"])
        self.assertIn("two category levels", json.dumps(self.visual("lg_note")))
        self.assertIn("not rows/bytes", json.dumps(self.visual("lg_note")))

    def test_canonical_graph_uses_upstream_only_and_endpoint_identities(self):
        source = (MODEL / "expressions.tmdl").read_text()
        graph = source.split("expression LineageGraphData =")[1]
        self.assertIn(
            'Table.SelectRows(#"Lineage Edges", each [Direction] = "upstream")', graph
        )
        self.assertIn('"datasource|" else "item|"', graph)
        self.assertIn('"Consumer Key" = "item|" & e[Query Item Id]', graph)
        self.assertIn('Table.Group(NodeCandidates, {"Node Key"}', graph)
        self.assertIn('" [" & [Node Key] & "]"', graph)
        self.assertIn(
            'Table.Group(Consumers, {"Source Key", "Consumer Key", "Consumer Workspace Id", "Source", "Consumer"}',
            graph,
        )
        self.assertNotIn("Folder.Files", graph)
        self.assertNotIn("Web.Contents", graph)
        links = (MODEL / "tables" / "Lineage Graph Links.tmdl").read_text()
        weight = links.split("measure 'Graph Link Weight' =")[1].split(
            "\n\t\tformatString:"
        )[0]
        self.assertIn("'Lineage Graph Links'[Source Key] IN Focus", weight)
        self.assertIn("|| 'Lineage Graph Links'[Consumer Key] IN Focus", weight)
        self.assertNotIn("COALESCE", weight)
        relations = (MODEL / "relationships.tmdl").read_text()
        self.assertNotIn("'Lineage Graph Nodes'", relations)
        self.assertIn(
            "fromColumn: 'Lineage Graph Links'.'Consumer Workspace Id'", relations
        )
        for name in ("Lineage Graph Links", "Lineage Graph Nodes"):
            self.assertIn(f"ref table '{name}'", (MODEL / "model.tmdl").read_text())


if __name__ == "__main__":
    unittest.main()
