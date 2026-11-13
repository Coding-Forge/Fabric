"""Code-derived I/O is potential and unresolved, never observed execution."""

import unittest
from unittest.mock import patch

from env.utility.notebook_references import notebook_references
from env.utility.notebook_relationships import notebook_lakehouse_relationships


def notebook(*sources):
    return {"cells": [{"cell_type": "code", "source": source} for source in sources]}


def refs(analysis):
    return {(r["operation"], r["kind"], r["reference"]) for r in analysis["references"]}


class NotebookReferenceTests(unittest.TestCase):
    def test_literal_spark_table_file_and_writer_chains(self):
        result = notebook_references(
            notebook(
                'spark.table("db.source")\n'
                'spark.read.table(tableName="db.second")\n'
                'spark.read.format("delta").load("Files/input")\n'
                'spark.read.parquet(path="abfss://lake/source")\n'
                'df.write.mode("overwrite").saveAsTable("db.output")\n'
                'df.write.insertInto("db.append")\n'
                'df.write.format("delta").save("Files/output")\n'
                'spark.read.table("db.chained").write.parquet("Files/chained")\n'
                'df.write.saveAsTable(name="db.named")'
            )
        )
        self.assertEqual(
            refs(result),
            {
                ("read", "table", "db.source"),
                ("read", "table", "db.second"),
                ("read", "path", "Files/input"),
                ("read", "path", "abfss://lake/source"),
                ("write", "table", "db.output"),
                ("write", "table", "db.append"),
                ("write", "path", "Files/output"),
                ("read", "table", "db.chained"),
                ("write", "path", "Files/chained"),
                ("write", "table", "db.named"),
            },
        )
        self.assertFalse(result["runtimeVerified"])
        self.assertEqual(result["evidence"], "static_inference")
        self.assertTrue(
            all(r["resolution"] == "unresolved" for r in result["references"])
        )
        self.assertEqual(result["diagnostics"], [])

    def test_sql_ctes_are_not_physical_tables_and_insert_has_write_direction(self):
        result = notebook_references(
            notebook(
                "%%sql\nWITH recent AS (SELECT * FROM bronze.events)\n"
                "INSERT INTO gold.summary SELECT * FROM recent JOIN silver.users u ON 1=1"
            )
        )
        self.assertEqual(
            refs(result),
            {
                ("read", "table", "bronze.events"),
                ("read", "table", "silver.users"),
                ("write", "table", "gold.summary"),
            },
        )
        self.assertEqual(result["diagnostics"], [])

    def test_sql_merge_update_delete_and_create_table_as_select(self):
        for sql in (
            "MERGE INTO gold.dst d USING silver.src s ON d.id=s.id WHEN MATCHED THEN UPDATE SET v=s.v",
            "UPDATE gold.dst SET v=2 WHERE id IN (SELECT id FROM silver.src)",
            "DELETE FROM gold.dst WHERE id IN (SELECT id FROM silver.src)",
        ):
            with self.subTest(sql=sql):
                result = notebook_references(notebook(f"spark.sql({sql!r})"))
                self.assertEqual(
                    refs(result),
                    {
                        ("read", "table", "gold.dst"),
                        ("write", "table", "gold.dst"),
                        ("read", "table", "silver.src"),
                    },
                )
        result = notebook_references(
            notebook(
                "%%sql\nCREATE TABLE gold.out AS SELECT * FROM delta.`abfss://lake/source`"
            )
        )
        self.assertEqual(
            refs(result),
            {
                ("write", "table", "gold.out"),
                ("read", "path", "abfss://lake/source"),
            },
        )

    def test_dynamic_strings_jdbc_unknown_io_and_languages_are_not_guessed(self):
        result = notebook_references(
            notebook(
                "spark.read.table(table_variable)\n"
                'spark.sql(f"SELECT * FROM {table_variable}")\n'
                'spark.read.format("jdbc").load("server-not-a-file")\n'
                "notebookutils.fs.cp(source, destination)\n"
                'pd.read_csv("not-supported")',
                "%%spark\nval x = 1",
                "%run helper",
            )
        )
        self.assertEqual(result["references"], [])
        reasons = {d["reason"] for d in result["diagnostics"]}
        self.assertTrue(
            {
                "dynamic_or_missing_target",
                "dynamic_sql",
                "unsupported_or_dynamic_format",
                "unsupported_filesystem_call",
                "unsupported_io_pattern",
                "unsupported_cell_language_or_magic",
            }
            <= reasons
        )

    def test_comments_markdown_and_strings_are_not_executed_or_regex_matched(self):
        source = (
            '# spark.read.table("comment")\n'
            "text = 'spark.read.table(\"inside-string\")'\n"
            '__import__("os").system("NEVER_EXECUTE")\n'
            'if False:\n    spark.read.table("potential-not-executed")'
        )
        doc = notebook(source.splitlines(keepends=True))
        doc["cells"].insert(
            0, {"cell_type": "markdown", "source": 'spark.table("markdown")'}
        )
        with patch("os.system", side_effect=AssertionError("Code must not run")):
            result = notebook_references(doc)
        self.assertEqual(refs(result), {("read", "table", "potential-not-executed")})
        self.assertEqual(result["references"][0]["cell"], 2)
        self.assertEqual(result["references"][0]["line"], 5)

    def test_invalid_sql_and_command_fallback_do_not_log_source(self):
        with patch("sqlglot.parser.logger.warning") as log:
            result = notebook_references(
                notebook(
                    'spark.sql("VACUUM SYNTHETIC_PRIVATE_PATH")',
                    'spark.sql("SELECT * FROM")',
                )
            )
        self.assertEqual(result["references"], [])
        self.assertGreaterEqual(len(result["diagnostics"]), 2)
        self.assertNotIn("SYNTHETIC_PRIVATE_PATH", str(log.call_args_list))


class NotebookRelationshipTests(unittest.TestCase):
    def test_declared_lakehouses_are_deduplicated_without_inventing_workspace_or_io(
        self,
    ):
        default = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
        other = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        workspace = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        doc = notebook('spark.table("db.input")')
        doc["metadata"] = {
            "dependencies": {
                "lakehouse": {
                    "default_lakehouse": default,
                    "default_lakehouse_name": "SYNTHETIC_PRIVATE_NAME",
                    "known_lakehouses": [
                        {"id": default.lower()},
                        {"id": other, "workspaceId": workspace},
                        {"id": other, "workspaceId": workspace},
                    ],
                }
            }
        }
        result = notebook_lakehouse_relationships(doc)
        self.assertTrue(result["complete"])
        self.assertEqual(
            result["relationships"],
            [
                {
                    "relation": "default_lakehouse",
                    "itemId": default.lower(),
                    "workspaceId": None,
                },
                {
                    "relation": "known_lakehouse",
                    "itemId": other,
                    "workspaceId": workspace,
                },
            ],
        )
        self.assertNotIn("SYNTHETIC_PRIVATE_NAME", str(result))
        self.assertEqual(
            refs(notebook_references(doc)), {("read", "table", "db.input")}
        )
        self.assertEqual(
            doc["metadata"]["dependencies"]["lakehouse"]["default_lakehouse"], default
        )

    def test_absent_declarations_are_empty_but_malformed_metadata_is_not_success(self):
        for doc in ({}, {"metadata": {}}, {"metadata": {"dependencies": None}}):
            with self.subTest(doc=doc):
                result = notebook_lakehouse_relationships(doc)
                self.assertTrue(result["complete"])
                self.assertEqual(result["relationships"], [])
        for value in (
            {"default_lakehouse": "SYNTHETIC_PRIVATE_INVALID_ID"},
            {"known_lakehouses": {}},
            {"known_lakehouses": ["SYNTHETIC_PRIVATE_INVALID_ENTRY"]},
            {"known_lakehouses": [{"id": None}]},
            {
                "default_lakehouse": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "default_lakehouse_workspace_id": "SYNTHETIC_PRIVATE_INVALID_ID",
            },
        ):
            with self.subTest(value=value):
                result = notebook_lakehouse_relationships(
                    {"metadata": {"dependencies": {"lakehouse": value}}}
                )
                self.assertFalse(result["complete"])
                self.assertTrue(result["diagnostics"])
                self.assertNotIn("SYNTHETIC_PRIVATE", str(result))
        for doc in (None, {"metadata": []}, {"metadata": {"dependencies": []}}):
            with self.subTest(doc=doc):
                self.assertFalse(notebook_lakehouse_relationships(doc)["complete"])

    def test_conflicting_workspace_declarations_are_diagnosed(self):
        lakehouse = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        result = notebook_lakehouse_relationships(
            {
                "metadata": {
                    "dependencies": {
                        "lakehouse": {
                            "default_lakehouse": lakehouse,
                            "default_lakehouse_workspace_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                            "known_lakehouses": [
                                {
                                    "id": lakehouse,
                                    "workspaceId": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                                }
                            ],
                        }
                    }
                }
            }
        )
        self.assertFalse(result["complete"])
        self.assertEqual(
            result["diagnostics"][0]["reason"], "conflicting_configured_workspace"
        )


if __name__ == "__main__":
    unittest.main()
