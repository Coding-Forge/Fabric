import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_estate_report
from deltalake import DeltaTable, write_deltalake
from estate_model import (
    COMMON,
    DERIVED_SCHEMAS,
    SCHEMAS,
    build_dimensions,
    frame,
)
from refresh_report_lookups import assert_owned, ownership


def fixture():
    sources = {name: frame([], COMMON | schema) for name, schema in SCHEMAS.items()}
    profile = {
        "profiled_at_utc": "2026-11-06T16:00:00+00:00",
        "datasets": {
            name: {
                "row_count": 0,
                "delta_version": 0,
                "cache_sha256": "fixture",
                "time_ranges": {"observed_at_utc": {"max": None}},
            }
            for name in SCHEMAS
        },
    }
    return sources, profile


def row(identity, **values):
    return {
        "schema_version": 1,
        "observation_id": identity,
        "source_path": "source.json",
        "source_sha256": "source-hash",
        "record_sha256": "record-hash",
        "coverage_status": "legacy_unverified",
        "module": "fixture",
        **values,
    }


class ObservationModelTests(unittest.TestCase):
    def test_historical_rows_do_not_duplicate_dimension_keys(self):
        sources, profile = fixture()
        sources["inventory"] = frame(
            [
                row(
                    "first",
                    workspace_id="w",
                    item_id="i",
                    item_name="First",
                    item_type="Report",
                    observed_at_utc="2026-11-01T10:00:00Z",
                ),
                row(
                    "second",
                    workspace_id="w",
                    item_id="i",
                    item_name="Renamed",
                    item_type="Report",
                    observed_at_utc="2026-11-02T10:00:00Z",
                ),
            ],
            COMMON | SCHEMAS["inventory"],
        )
        dimensions = build_dimensions(sources, profile)
        self.assertEqual(dimensions["context"].num_rows, 2)
        self.assertEqual(dimensions["workspace"].num_rows, 1)
        self.assertEqual(dimensions["item"].num_rows, 1)
        self.assertEqual(dimensions["item"].to_pylist()[0]["label"], "Renamed")

    def test_same_item_identifier_in_different_workspaces_stays_distinct(self):
        sources, profile = fixture()
        sources["inventory"] = frame(
            [
                row("first", workspace_id="w1", item_id="i", item_type="Report"),
                row("second", workspace_id="w2", item_id="i", item_type="Report"),
            ],
            COMMON | SCHEMAS["inventory"],
        )
        dimensions = build_dimensions(sources, profile)
        self.assertEqual(dimensions["item"].num_rows, 2)
        self.assertEqual(
            len(set(dimensions["context"].column("item_key").to_pylist())), 2
        )

    def test_unresolved_lineage_target_does_not_inherit_source_workspace(self):
        sources, profile = fixture()
        sources["lineage_edges"] = frame(
            [
                row(
                    "edge",
                    workspace_id="w1",
                    item_id="i",
                    related_item_id="other",
                    related_type="SemanticModel",
                ),
            ],
            COMMON | SCHEMAS["lineage_edges"],
        )
        dimensions = build_dimensions(sources, profile)
        context = dimensions["context"].to_pylist()[0]
        self.assertIsNone(context["related_workspace_key"])
        target = next(
            value
            for value in dimensions["item"].to_pylist()
            if value["entity_id"] == "other"
        )
        self.assertIsNone(target["workspace_id"])

    def test_partition_and_event_dates_never_invent_exact_collection_time(self):
        sources, profile = fixture()
        sources["activity_events"] = frame(
            [
                row(
                    "event",
                    source_date="2026-11-02",
                    event_time_utc="2026-11-01T23:59:00Z",
                ),
            ],
            COMMON | SCHEMAS["activity_events"],
        )
        context = build_dimensions(sources, profile)["context"].to_pylist()[0]
        self.assertIsNone(context["observed_at"])
        self.assertIsNone(context["observed_date_key"])
        self.assertEqual(context["source_date_key"], 20261102)
        self.assertEqual(context["event_date_key"], 20261101)

    def test_duplicate_observation_across_datasets_is_rejected(self):
        sources, profile = fixture()
        for dataset in ("inventory", "job_resources"):
            sources[dataset] = frame([row("duplicate")], COMMON | SCHEMAS[dataset])
        with self.assertRaisesRegex(ValueError, "globally unique"):
            build_dimensions(sources, profile)

    def test_missing_source_is_not_silently_an_empty_table(self):
        sources, profile = fixture()
        del sources["inventory"]
        with self.assertRaisesRegex(ValueError, "All 48"):
            build_dimensions(sources, profile)

    def test_preview_lookup_schema_and_custom_ownership_survive_delta_roundtrip(self):
        sources, profile = fixture()
        dimensions = build_dimensions(sources, profile)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workspace"
            write_deltalake(
                str(path), dimensions["workspace"], description=ownership("workspace")
            )
            assert_owned(DeltaTable(str(path)), "workspace")
            with self.assertRaisesRegex(ValueError, "unowned"):
                assert_owned(DeltaTable(str(path)), "item")
        self.assertEqual(set(dimensions), set(DERIVED_SCHEMAS))


class ReportLayoutTests(unittest.TestCase):
    def test_navigation_has_room_for_two_text_rows_without_overlapping_content(self):
        for slicers in ((), (("Permission Mode", "Mode"),)):
            with self.subTest(slicers=slicers), tempfile.TemporaryDirectory() as root:
                report = Path(root)
                with (
                    patch.object(build_estate_report, "REPORT", report),
                    patch.object(build_estate_report, "PAGES", []),
                ):
                    build_estate_report.report_page(
                        "01",
                        "01 Estate",
                        "Subtitle",
                        ["Items Observed"],
                        [("Items", "Item", "Label", "Items Observed")],
                        [("Workspace", "Label")],
                        slicers=slicers,
                        note="Evidence notes",
                    )
                page_dir = report / "pages/estate_01"
                page = json.loads((page_dir / "page.json").read_text())
                visuals = [
                    json.loads(path.read_text())
                    for path in (page_dir / "visuals").glob("*/visual.json")
                ]
                navigator = next(
                    visual
                    for visual in visuals
                    if visual["visual"]["visualType"] == "pageNavigator"
                )
                objects = navigator["visual"]["objects"]

                def value(properties, name):
                    return float(
                        properties[name]["expr"]["Literal"]["Value"].rstrip("D")
                    )

                layout = objects["layout"][0]["properties"]
                text = objects["text"][0]["properties"]
                title = navigator["visual"]["visualContainerObjects"]["title"][0][
                    "properties"
                ]
                rows = value(layout, "rowCount")
                required_height = (
                    value(title, "fontSize") * 4 / 3
                    + rows
                    * (
                        value(text, "fontSize") * 4 / 3
                        + value(text, "topMargin")
                        + value(text, "bottomMargin")
                    )
                    + (rows - 1) * value(layout, "cellPadding")
                    + 16
                )
                self.assertGreaterEqual(
                    navigator["position"]["height"], required_height
                )
                rectangles = [visual["position"] for visual in visuals]
                for index, first in enumerate(rectangles):
                    self.assertLessEqual(first["x"] + first["width"], page["width"])
                    self.assertLessEqual(first["y"] + first["height"], page["height"])
                    for second in rectangles[index + 1 :]:
                        overlap = (
                            first["x"] < second["x"] + second["width"]
                            and second["x"] < first["x"] + first["width"]
                            and first["y"] < second["y"] + second["height"]
                            and second["y"] < first["y"] + first["height"]
                        )
                        self.assertFalse(overlap, (first, second))


if __name__ == "__main__":
    unittest.main()
