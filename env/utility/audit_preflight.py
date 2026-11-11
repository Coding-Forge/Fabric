"""Check that the monitor module output exists before the audit notebook builds audit_events_splunk.

Pure Python with no imports from the app, so notebooks/audit_events_splunk.ipynb embeds this file as is.
"""

# folder under Files/<PATH_IN_LAKEHOUSE>/ -> (module that writes it, what the table loses without it)
REQUIRED_SOURCES = {
    "activity": ("Activity", "the audit events themselves"),
}

OPTIONAL_SOURCES = {
    "graph": ("Graph", "user display names"),
    "lineage_edges": ("Catalog", "upstream/downstream lineage"),
    "catalog/scans": ("Catalog", "item names from the scanner"),
    "jobs": ("ItemJobs", "run history"),
    "itemdefinitions": ("ItemJobs", "sources and destinations"),
    "jobactivityruns": ("ItemJobs", "rows and bytes copied"),
    "controlplane": ("ControlPlane", "owner, item state, last run, failure reason and recent activity"),
}


def check_sources(has_data, required=None, optional=None):
    """has_data(folder) -> bool. Returns (missing_required, missing_optional, report_lines)."""
    required = REQUIRED_SOURCES if required is None else required
    optional = OPTIONAL_SOURCES if optional is None else optional
    lines = []
    missing_required = []
    missing_optional = []
    for group, sources, bucket in (("required", required, missing_required), ("optional", optional, missing_optional)):
        for folder, (module, effect) in sources.items():
            if has_data(folder):
                lines.append(f"OK       {folder}")
            else:
                bucket.append(folder)
                lines.append(f"MISSING  {folder} ({group}): run the {module} module; without it the table loses {effect}")
    return missing_required, missing_optional, lines
