"""Validate local report schemas, bindings, graph and canvas geometry."""

import json
from urllib.parse import urlparse

import jsonschema
import requests
from estate_model import PROJECT
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7


def main():
    manifest = json.loads((PROJECT / "analysis/model-manifest.json").read_text())
    tables = manifest["model_tables"]
    measures = manifest["measures"]
    report = PROJECT / "Monitor.Report/definition"
    cache = {}
    session = requests.Session()

    def schema(url):
        if urlparse(url).hostname != "developer.microsoft.com":
            raise ValueError("Unexpected external schema host")
        if url not in cache:
            published_url = url.replace(
                "/schema.embedded.json", "/schema-embedded.json"
            )
            response = session.get(published_url, timeout=30)
            response.raise_for_status()
            cache[url] = response.json()
            if "$id" in cache[url]:
                cache[cache[url]["$id"]] = cache[url]
        return cache[url]

    def validate_document(path):
        document = json.loads(path.read_text())
        url = document["$schema"]
        spec = schema(url)
        registry = Registry(
            retrieve=lambda uri: Resource.from_contents(
                schema(uri), default_specification=DRAFT7
            )
        )
        jsonschema.Draft7Validator(spec, registry=registry).validate(document)
        return document

    page_index = validate_document(report / "pages/pages.json")
    assert page_index["pageOrder"] == manifest["pages"]
    visual_count = 0
    used_datasets = set()
    for page_name in manifest["pages"]:
        page = validate_document(report / "pages" / page_name / "page.json")
        for path in (report / "pages" / page_name / "visuals").glob("*/visual.json"):
            visual = validate_document(path)
            position = visual["position"]
            assert position["x"] >= 0 and position["y"] >= 0
            assert position["x"] + position["width"] <= page["width"]
            assert position["y"] + position["height"] <= page["height"]
            for role in (
                visual.get("visual", {}).get("query", {}).get("queryState", {}).values()
            ):
                for projection in role["projections"]:
                    field = projection["field"]
                    binding = field.get("Measure", field.get("Column"))
                    entity, name = (
                        binding["Expression"]["SourceRef"]["Entity"],
                        binding["Property"],
                    )
                    assert entity in tables, (path, entity)
                    if "Measure" in field:
                        assert entity == "Estate Measures" and name in measures, (
                            path,
                            name,
                        )
                    else:
                        from estate_model import title

                        assert name in {
                            title(column) for column in tables[entity]["types"]
                        }, (path, name)
                    if tables[entity]["dataset"]:
                        used_datasets.add(tables[entity]["dataset"])
            visual_count += 1
    validate_document(report / "report.json")
    validate_document(report / "version.json")
    # Filter edges run from the one-side lookup to the many-side fact.
    graph = {}
    for source, field, target, target_field in manifest["relationships"]:
        graph.setdefault(target, set()).add(source)
        from estate_model import title

        assert field in {title(name) for name in tables[source]["types"]}
        assert target_field in {title(name) for name in tables[target]["types"]}

    def visit(node, path):
        assert node not in path, f"Relationship cycle at {node}"
        for child in graph.get(node, ()):
            visit(child, path | {node})

    for node in graph:
        visit(node, set())
    print(
        f"PASS: Microsoft JSON schemas, all visual field/measure bindings and bounds; {len(manifest['pages'])} pages / {visual_count} visuals."
    )
    print(
        f"PASS: {len(manifest['relationships'])} acyclic one-direction relationships; {len(tables)} model tables / {len(measures)} measures."
    )
    print("Rendering and DAX engine execution still require Power BI Desktop/Fabric.")


if __name__ == "__main__":
    main()
