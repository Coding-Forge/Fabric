"""Conservative, nonexecuting analysis of literal notebook data references."""

import ast
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import Scope, traverse_scope

_FILES = frozenset({"csv", "json", "parquet", "orc", "text", "delta"})
_IO_BOUNDARIES = frozenset({"read", "write", "readStream", "writeStream"})


def notebook_references(notebook: dict) -> dict:
    """Find supported potential reads/writes, never actual execution evidence.

    References remain unresolved table names/paths, not Fabric IDs. Unsupported
    syntax and dynamic arguments produce fixed diagnostics, not guessed edges.
    No notebook code, imports, SQL or interpolation is executed.
    """
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        raise TypeError("Invalid notebook cells")
    metadata = notebook.get("metadata", {})
    if not isinstance(metadata, dict):
        raise TypeError("Invalid notebook metadata")
    language_info = metadata.get("language_info", {})
    if not isinstance(language_info, dict):
        raise TypeError("Invalid notebook language metadata")
    default_language = language_info.get("name", "python")
    references = []
    diagnostics = []

    def diagnostic(cell, line, reason):
        value = {"cell": cell, "line": line, "reason": reason}
        if value not in diagnostics:
            diagnostics.append(value)

    def reference(cell, line, operation, kind, value):
        if not isinstance(value, str) or not value.strip():
            diagnostic(cell, line, "dynamic_or_missing_target")
            return
        entry = {
            "cell": cell,
            "line": line,
            "operation": operation,
            "kind": kind,
            "reference": value,
            "resolution": "unresolved",
        }
        if entry not in references:
            references.append(entry)

    def sql_references(text, cell, line):
        try:
            # Command fallback logs SQL; zero context prevents source disclosure.
            statements = sqlglot.parse(text, read="spark", error_message_context=0)
            for statement in statements:
                if statement is None:
                    continue
                supported = (
                    exp.Query,
                    exp.Insert,
                    exp.Create,
                    exp.Update,
                    exp.Delete,
                    exp.Merge,
                )
                if not isinstance(statement, supported) or (
                    isinstance(statement, exp.Create)
                    and statement.args.get("kind") != "TABLE"
                ):
                    diagnostic(cell, line, "unsupported_sql_statement")
                    continue
                target = None
                if not isinstance(statement, exp.Query):
                    target = statement.this
                    if isinstance(target, exp.Schema):
                        target = target.this
                    if not isinstance(target, exp.Table):
                        diagnostic(cell, line, "unsupported_sql_target")
                        continue
                cte_refs = set()
                for scope in traverse_scope(statement):
                    for node, source in scope.selected_sources.values():
                        if isinstance(source, Scope):
                            cte_refs.add(id(node))
                # DML targets/USING tables are not always visited as query scopes.
                with_clause = statement.args.get("with_")
                cte_names = (
                    {cte.alias_or_name for cte in with_clause.expressions}
                    if with_clause
                    else set()
                )
                for table in statement.find_all(exp.Table):
                    if id(table) in cte_refs or (
                        table is not target and not table.db and table.name in cte_names
                    ):
                        continue
                    if any(
                        not isinstance(part, exp.Identifier) for part in table.parts
                    ):
                        diagnostic(cell, line, "unsupported_sql_table_expression")
                        continue
                    kind = "table"
                    value = ".".join(part.sql(dialect="spark") for part in table.parts)
                    if (
                        not table.catalog
                        and table.db.lower() in _FILES
                        and "/" in table.name
                    ):
                        kind, value = "path", table.name
                    operation = "write" if table is target else "read"
                    reference(cell, line, operation, kind, value)
                    if table is target and isinstance(
                        statement, (exp.Update, exp.Delete, exp.Merge)
                    ):
                        reference(cell, line, "read", kind, value)
        except (SqlglotError, RecursionError, ValueError):
            diagnostic(cell, line, "unresolved_sql")

    def literal(node):
        return (
            node.value
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            else None
        )

    def attributes(node):
        result = []
        formats = []
        while isinstance(node, (ast.Call, ast.Attribute)):
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "format"
                    and not any(name in _IO_BOUNDARIES for name in result)
                ):
                    formats.append(
                        literal(node.args[0])
                        if node.args
                        else next(
                            (
                                literal(k.value)
                                for k in node.keywords
                                if k.arg == "source"
                            ),
                            None,
                        )
                    )
                node = node.func
            else:
                result.append(node.attr)
                node = node.value
        return result, node, formats

    for cell_index, cell in enumerate(cells, 1):
        if not isinstance(cell, dict):
            raise TypeError("Invalid notebook cell")
        if cell.get("cell_type") not in ("code", "markdown", "raw"):
            raise ValueError("Invalid notebook cell type")
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source")
        if isinstance(source, list) and all(isinstance(s, str) for s in source):
            source = "".join(source)
        if not isinstance(source, str):
            raise TypeError("Invalid notebook cell source")
        lines = source.splitlines()
        first = next((i for i, line in enumerate(lines) if line.strip()), None)
        if first is None:
            continue
        magic = lines[first].strip()
        metadata = cell.get("metadata", {})
        if not isinstance(metadata, dict):
            raise TypeError("Invalid notebook cell metadata")
        language = metadata.get("language", default_language)
        if re.fullmatch(r"%%sql\s*", magic) or language in ("sql", "sparksql"):
            sql = "\n".join(lines[first + 1 :]) if magic.startswith("%%sql") else source
            sql_references(
                sql, cell_index, first + (2 if magic.startswith("%%sql") else 1)
            )
            continue
        if magic == "%%pyspark":
            lines[first] = ""
        elif magic.startswith("%") or (
            language and language not in ("python", "pyspark")
        ):
            diagnostic(cell_index, first + 1, "unsupported_cell_language_or_magic")
            continue
        try:
            tree = ast.parse("\n".join(lines))
        except (SyntaxError, ValueError, RecursionError):
            diagnostic(cell_index, 1, "unresolved_python_syntax")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            method = node.func.attr
            attrs, root, formats = attributes(node.func.value)
            spark = isinstance(root, ast.Name) and root.id == "spark"
            boundary = next((name for name in attrs if name in _IO_BOUNDARIES), None)
            reader = spark and boundary == "read"
            writer = boundary in ("write", "writeStream")
            value = (
                literal(node.args[0])
                if node.args
                else next(
                    (
                        literal(k.value)
                        for k in node.keywords
                        if k.arg in ("path", "tableName", "name", "sqlQuery")
                    ),
                    None,
                )
            )
            if spark and not attrs and method == "sql":
                if value is None:
                    diagnostic(cell_index, node.lineno, "dynamic_sql")
                else:
                    sql_references(value, cell_index, node.lineno)
            elif (reader or (spark and not attrs)) and method == "table":
                reference(cell_index, node.lineno, "read", "table", value)
            elif reader and method in (_FILES | {"load"}):
                if method == "load" and any(f not in _FILES for f in formats):
                    diagnostic(cell_index, node.lineno, "unsupported_or_dynamic_format")
                else:
                    reference(cell_index, node.lineno, "read", "path", value)
            elif writer and method in {"saveAsTable", "insertInto"}:
                reference(cell_index, node.lineno, "write", "table", value)
            elif writer and method in (_FILES | {"save", "start"}):
                if method in ("save", "start") and any(
                    f not in _FILES for f in formats
                ):
                    diagnostic(cell_index, node.lineno, "unsupported_or_dynamic_format")
                else:
                    reference(cell_index, node.lineno, "write", "path", value)
            elif spark and boundary == "readStream":
                diagnostic(cell_index, node.lineno, "unsupported_streaming_pattern")
            elif method in {
                "readStream",
                "writeTo",
                "merge",
                "open",
                "read_sql",
                "read_csv",
                "read_parquet",
            }:
                diagnostic(cell_index, node.lineno, "unsupported_io_pattern")
            elif reader and method not in {"format", "option", "options", "schema"}:
                diagnostic(cell_index, node.lineno, "unsupported_reader_pattern")
            elif writer and method not in {
                "format",
                "option",
                "options",
                "mode",
                "partitionBy",
                "bucketBy",
                "sortBy",
                "outputMode",
                "trigger",
                "queryName",
            }:
                diagnostic(cell_index, node.lineno, "unsupported_writer_pattern")
            elif attrs and attrs[0] == "fs":
                diagnostic(cell_index, node.lineno, "unsupported_filesystem_call")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open"
            ):
                diagnostic(cell_index, node.lineno, "unsupported_io_pattern")

    return {
        "schemaVersion": 1,
        "evidence": "static_inference",
        "runtimeVerified": False,
        "coverage": "Supported literal Python/Spark and Spark SQL patterns only; not exhaustive",
        "references": references,
        "diagnostics": diagnostics,
    }
