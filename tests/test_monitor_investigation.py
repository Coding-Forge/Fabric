"""Offline execution tests for scoped, bounded investigation rendering."""

import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from notebooks import monitor_investigation as investigation
from notebooks.build_monitor_notebooks import generated_notebooks

WORKSPACE = "00000000-0000-0000-0000-000000000001"
ITEM = "00000000-0000-0000-0000-000000000002"
OTHER = "00000000-0000-0000-0000-000000000003"


class Expression:
    def __init__(self, evaluate):
        self.evaluate = evaluate

    def __eq__(self, value):
        return Expression(lambda row: self.evaluate(row) == value)

    def __ne__(self, value):
        return Expression(
            lambda row: self.evaluate(row) is not None and self.evaluate(row) != value
        )

    def __and__(self, other):
        return Expression(lambda row: self.evaluate(row) and other.evaluate(row))

    def __or__(self, other):
        return Expression(lambda row: self.evaluate(row) or other.evaluate(row))

    def desc_nulls_first(self):
        return self, True

    def asc(self):
        return self, False

    def isNotNull(self):
        return Expression(lambda row: self.evaluate(row) is not None)

    def contains(self, value):
        return Expression(
            lambda row: self.evaluate(row) is not None and value in self.evaluate(row)
        )


class Minimum:
    def __init__(self, column):
        self.column = column

    def alias(self, name):
        self.name = name
        return self


class GroupedFrame:
    def __init__(self, frame, keys):
        self.frame, self.keys = frame, keys

    def agg(self, *aggregates):
        groups = {}
        for row in self.frame.rows:
            groups.setdefault(tuple(row.get(key) for key in self.keys), []).append(row)
        values = []
        for key, rows in groups.items():
            result = dict(zip(self.keys, key))
            for aggregate in aggregates:
                known = [
                    row[aggregate.column]
                    for row in rows
                    if row.get(aggregate.column) is not None
                ]
                result[aggregate.name] = min(known) if known else None
            values.append(result)
        return Frame(self.frame.schema, values, self.frame.limits)


class Frame:
    def __init__(self, name, rows, limits):
        self.schema = name
        self.rows = rows
        self.limits = limits

    def filter(self, expression):
        return Frame(
            self.schema,
            [row for row in self.rows if expression.evaluate(row)],
            self.limits,
        )

    def orderBy(self, *columns):
        rows = self.rows[:]
        for expression, descending in reversed(columns):
            known = [row for row in rows if expression.evaluate(row) is not None]
            unknown = [row for row in rows if expression.evaluate(row) is None]
            known.sort(key=expression.evaluate, reverse=descending)
            rows = unknown + known
        return Frame(self.schema, rows, self.limits)

    def limit(self, number):
        self.limits.append(number)
        return Frame(self.schema, self.rows[:number], self.limits)

    def collect(self):
        return self.rows

    def groupBy(self, *keys):
        return GroupedFrame(self, keys)

    def join(self, other, key, how):
        values = []
        fields = {field for row in other.rows for field in row} - {key}
        for row in self.rows:
            matches = [entry for entry in other.rows if entry[key] == row[key]]
            if matches:
                values.extend({**row, **entry} for entry in matches)
            elif how == "left":
                values.append({**row, **dict.fromkeys(fields)})
        if not other.rows:
            for row in values:
                row["workspace_name_hint"] = None
        return Frame(self.schema, values, self.limits)


def observation(identity, **values):
    return {
        "workspace_id": WORKSPACE,
        "item_id": ITEM,
        "observation_id": identity,
        "observed_at_utc": "2026-01-01T00:00:00.000000Z",
        "source_path": identity + ".json",
        "source_sha256": identity,
        "coverage_status": "success",
        **values,
    }


class InvestigationTests(unittest.TestCase):
    def render(self, tables, *, discover=False, **parameters):
        spark = MagicMock()
        spark.catalog.tableExists.side_effect = lambda name: (
            name.removeprefix("monitor_") in tables
        )
        displayed, limits = {}, []
        spark.createDataFrame.side_effect = lambda rows, schema: Frame(
            schema, rows, limits
        )
        functions = SimpleNamespace(
            col=lambda name: Expression(lambda row: row.get(name)),
            lower=lambda expression: Expression(
                lambda row: (
                    expression.evaluate(row).lower()
                    if expression.evaluate(row) is not None
                    else None
                )
            ),
            min=Minimum,
        )
        modules = {
            "pyspark": SimpleNamespace(),
            "pyspark.sql": SimpleNamespace(functions=functions),
        }
        options = {
            "prefix": "monitor_",
            "workspace_id": "" if discover else WORKSPACE,
            "item_id": "" if discover else ITEM,
            "permission_mode": "Scoped",
            **parameters,
        }
        output = io.StringIO()
        with (
            patch.dict("sys.modules", modules),
            patch.object(
                investigation,
                "read_curated",
                side_effect=lambda session, prefix, name: Frame(
                    name, tables[name], limits
                ),
            ) as read,
            redirect_stdout(output),
        ):
            render = (
                investigation.run_investigation
                if discover
                else investigation.render_investigation
            )
            render(
                spark,
                lambda frame: displayed.update({frame.schema: frame.rows}),
                **options,
            )
        return displayed, output.getvalue(), read, limits

    def test_discovery_deduplicates_history_and_automatically_investigates_unique_item(
        self,
    ):
        tables = {
            "inventory": [
                observation(
                    "workspace",
                    item_id=WORKSPACE,
                    item_type="Workspace",
                    item_name="Monitoring",
                ),
                observation("first", item_type="Notebook", item_name="Analysis"),
                observation("repeat", item_type="Notebook", item_name="Analysis"),
            ],
            "job_resources": [observation("poll", coverage_status="failed")],
        }
        displayed, output, _, limits = self.render(tables, discover=True)
        discovered = displayed[investigation.DISCOVERY_SCHEMA]
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["workspace_name_hint"], "Monitoring")
        self.assertEqual(discovered[0]["resource_number"], 1)
        self.assertEqual(displayed["job_resources"][0]["coverage_status"], "failed")
        self.assertEqual(len(displayed["inventory"]), 2)
        self.assertIn("investigating automatically", output)
        self.assertTrue(all(limit == 201 for limit in limits))

    def test_ambiguous_discovery_shows_choices_without_arbitrary_investigation(self):
        rows = [
            observation("one", item_type="Notebook", item_name="One"),
            observation("two", item_type="Notebook", item_name="Two", item_id=OTHER),
        ]
        displayed, output, read, _ = self.render({"inventory": rows}, discover=True)
        self.assertEqual(len(displayed[investigation.DISCOVERY_SCHEMA]), 2)
        self.assertNotIn("inventory", displayed)
        self.assertIn("Multiple resources", output)
        self.assertEqual(read.call_count, 1)
        displayed, output, _, _ = self.render(
            {"inventory": rows},
            discover=True,
            resource_number=2,
        )
        self.assertEqual(displayed["inventory"][0]["item_id"], OTHER)
        self.assertIn("Numbering can change", output)

    def test_discovery_filters_match_historical_names_and_type_case_insensitively(self):
        rows = [
            observation(
                "workspace",
                item_id=WORKSPACE,
                item_type="Workspace",
                item_name="North Hub",
            ),
            observation("renamed", item_type="Notebook", item_name="Old Analysis"),
            observation("new-name", item_type="Notebook", item_name="New Name"),
            observation(
                "wrong-type",
                item_type="DataPipeline",
                item_name="Old Analysis",
                item_id=OTHER,
            ),
            observation(
                "other-workspace",
                workspace_id=OTHER,
                item_type="Notebook",
                item_name="Old Analysis",
            ),
        ]
        displayed, _, _, _ = self.render(
            {"inventory": rows},
            discover=True,
            workspace_search="NORTH",
            item_search="old ANALYSIS",
            item_type="notebook",
        )
        discovered = displayed[investigation.DISCOVERY_SCHEMA]
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["item_name_hint"], "Old Analysis")
        self.assertEqual(len(displayed["inventory"]), 2)

    def test_unknown_names_do_not_block_id_discovery_and_partial_id_filters_work(self):
        rows = [
            observation("unnamed", item_type="Notebook", item_name=None),
            observation("other-workspace", item_type="Notebook", workspace_id=OTHER),
            observation("other-item", item_type="Notebook", item_id=OTHER),
        ]
        displayed, _, _, _ = self.render(
            {"inventory": rows}, discover=True, workspace_id=WORKSPACE, item_id=ITEM
        )
        selected = displayed[investigation.DISCOVERY_SCHEMA][0]
        self.assertIsNone(selected["item_name_hint"])
        self.assertIsNone(selected["workspace_name_hint"])
        displayed, output, _, _ = self.render(
            {"inventory": rows}, discover=True, workspace_id=WORKSPACE
        )
        self.assertEqual(len(displayed[investigation.DISCOVERY_SCHEMA]), 2)
        self.assertIn("Multiple resources", output)

    def test_discovery_empty_missing_and_truncated_results_remain_explicit(self):
        displayed, output, read, _ = self.render({}, discover=True)
        self.assertFalse(displayed)
        self.assertIn("Discovery NOT PUBLISHED / UNKNOWN", output)
        read.assert_not_called()
        for rows in ([], [observation("workspace", item_type="Workspace")]):
            displayed, output, _, _ = self.render({"inventory": rows}, discover=True)
            self.assertFalse(displayed)
            self.assertIn("No matching retained items", output)
        rows = [
            observation("one", item_type="Notebook"),
            observation("two", item_id=OTHER, item_type="Notebook"),
        ]
        displayed, output, read, limits = self.render(
            {"inventory": rows}, discover=True, max_rows=1
        )
        self.assertEqual(len(displayed[investigation.DISCOVERY_SCHEMA]), 1)
        self.assertIn("Discovery TRUNCATED", output)
        self.assertIn("Multiple resources", output)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(limits, [2])

    def test_manual_opt_out_bypasses_inventory_discovery(self):
        displayed, output, _, _ = self.render(
            {"job_resources": [observation("poll")]},
            discover=True,
            auto_discover=False,
            workspace_id=WORKSPACE,
            item_id=ITEM,
        )
        self.assertIn("job_resources", displayed)
        self.assertNotIn(investigation.DISCOVERY_SCHEMA, displayed)
        self.assertNotIn("Discovering", output)
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.render({}, discover=True, auto_discover=False)

    def test_invalid_discovery_parameters_and_unshown_selection_are_rejected(self):
        for parameters in (
            {"auto_discover": "true"},
            {"workspace_id": "invalid"},
            {"item_search": None},
            {"resource_number": True},
            {"resource_number": -1},
            {"resource_number": 1001},
        ):
            with (
                self.subTest(parameters=parameters),
                self.assertRaises((TypeError, ValueError)),
            ):
                self.render({}, discover=True, **parameters)
        with self.assertRaisesRegex(ValueError, "not in the displayed"):
            self.render(
                {"inventory": [observation("one", item_type="Notebook")]},
                discover=True,
                resource_number=2,
            )

    def test_generated_default_execution_uses_discovery_without_required_ids(self):
        artifact = generated_notebooks()["23_monitor_investigation.ipynb"]
        namespace = {
            "spark": MagicMock(),
            "display": MagicMock(),
            "run_investigation": MagicMock(),
        }
        config, _, execute = [
            "".join(cell["source"])
            for cell in artifact["cells"]
            if cell["cell_type"] == "code"
        ]
        exec(compile(config, "investigation_parameters", "exec"), namespace)  # noqa: S102 - Trusted generated cell.
        exec(compile(execute, "investigation_execution", "exec"), namespace)  # noqa: S102 - Trusted generated cell with mocked Fabric entry point.
        call = namespace["run_investigation"].call_args.kwargs
        self.assertTrue(call["auto_discover"])
        self.assertEqual((call["workspace_id"], call["item_id"]), ("", ""))

    def test_scopes_facts_by_both_ids_and_preserves_history_and_provenance(self):
        history = [
            observation("old", status="Succeeded"),
            observation(
                "failed",
                coverage_status="failed",
                observed_at_utc="2026-01-02T00:00:00.000000Z",
                record_count=None,
            ),
            observation("other-workspace", workspace_id=OTHER),
            observation("other-item", item_id=OTHER),
        ]
        displayed, output, _, _ = self.render(
            {
                name: history
                for name in ("inventory", "job_resources", "job_observations")
            }
        )
        for rows in displayed.values():
            self.assertEqual([row["observation_id"] for row in rows], ["failed", "old"])
            self.assertEqual(rows[1]["source_path"], "old.json")
            self.assertIsNone(rows[0]["record_count"])
        self.assertIn("NOT current state", output)
        self.assertIn("No matching", self.render({"activity_events": []})[1])

    def test_access_mode_and_optional_cycle_never_union_other_scopes(self):
        grants = [
            observation("scoped-old", mode="Scoped", cycle_id="old"),
            observation("scoped-new", mode="Scoped", cycle_id="new"),
            observation("tenant", mode="Tenant", cycle_id="new"),
            observation("other", mode="Scoped", cycle_id="new", workspace_id=OTHER),
        ]
        tables = {
            name: grants for name in ("permission_resources", "permission_grants")
        }
        tables["permission_cycles"] = grants[:3]
        displayed, output, _, _ = self.render(tables, permission_cycle_id="new")
        for rows in displayed.values():
            self.assertEqual([row["observation_id"] for row in rows], ["scoped-new"])
        self.assertIn("Explicit historical cycle: new", output)
        displayed, output, _, _ = self.render(tables)
        self.assertEqual(len(displayed["permission_grants"]), 2)
        self.assertIn("NOT a merged access list", output)
        displayed, _, _, _ = self.render(tables, permission_mode="Tenant")
        self.assertEqual(displayed["permission_grants"][0]["observation_id"], "tenant")

    def test_direct_incoming_links_require_explicit_target_workspace_and_item(self):
        edges = [
            observation("owned", evidence_type="configuration_metadata"),
            observation(
                "incoming",
                workspace_id=OTHER,
                item_id=OTHER,
                related_workspace_id=WORKSPACE,
                related_item_id=ITEM,
                evidence_type="static_inference",
            ),
            observation(
                "unresolved-workspace",
                item_id=OTHER,
                related_workspace_id=None,
                related_item_id=ITEM,
            ),
            observation(
                "different-target",
                item_id=OTHER,
                related_workspace_id=OTHER,
                related_item_id=ITEM,
            ),
        ]
        displayed, output, _, _ = self.render({"lineage_edges": edges})
        self.assertEqual(
            {row["observation_id"] for row in displayed["lineage_edges"]},
            {"owned", "incoming"},
        )
        self.assertEqual(
            displayed["lineage_edges"][0]["evidence_type"], "static_inference"
        )
        self.assertIn("not transitive lineage", output)

    def test_activity_coverage_is_analysis_wide_and_missing_tables_stay_unknown(self):
        displayed, output, read, _ = self.render(
            {
                "estate_coverage": [
                    observation(
                        "activity", analysis="activity", coverage_status="invalid"
                    ),
                    observation("catalog", analysis="catalog"),
                ],
                "activity_events": [
                    observation("match"),
                    observation("unattributed", item_id=None),
                ],
            }
        )
        self.assertEqual(len(displayed["estate_coverage"]), 1)
        self.assertEqual(displayed["estate_coverage"][0]["coverage_status"], "invalid")
        self.assertEqual(len(displayed["activity_events"]), 1)
        self.assertIn("NOT PUBLISHED / UNKNOWN", output)
        self.assertEqual(read.call_count, 2)

    def test_each_section_is_bounded_and_unknown_time_precedes_latest_known(self):
        rows = [
            observation("old"),
            observation(
                "unknown", observed_at_utc=None, coverage_status="legacy_unverified"
            ),
            observation("new", observed_at_utc="2026-01-02T00:00:00.000000Z"),
        ]
        displayed, output, _, limits = self.render({"inventory": rows}, max_rows=2)
        self.assertEqual(
            [row["observation_id"] for row in displayed["inventory"]],
            ["unknown", "new"],
        )
        self.assertEqual(limits, [3])
        self.assertIn("TRUNCATED to 2", output)

    def test_invalid_parameters_fail_before_reading_any_tables(self):
        for parameters in (
            {"workspace_id": ""},
            {"item_id": "../other"},
            {"permission_mode": "Both"},
            {"max_rows": True},
            {"max_rows": 0},
            {"max_rows": 1001},
            {"prefix": "other_"},
            {"permission_cycle_id": None},
        ):
            with (
                self.subTest(parameters=parameters),
                self.assertRaises((ValueError, TypeError)),
            ):
                self.render({}, **parameters)

    def test_existing_table_contract_errors_are_not_hidden_as_missing(self):
        spark = MagicMock()
        with (
            patch.dict(
                "sys.modules",
                {
                    "pyspark": SimpleNamespace(),
                    "pyspark.sql": SimpleNamespace(functions=MagicMock()),
                },
            ),
            patch.object(
                investigation,
                "read_curated",
                side_effect=ValueError("Invalid contract"),
            ),
            redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(ValueError, "Invalid contract"),
        ):
            investigation.render_investigation(
                spark,
                MagicMock(),
                prefix="monitor_",
                workspace_id=WORKSPACE,
                item_id=ITEM,
                permission_mode="Scoped",
            )
