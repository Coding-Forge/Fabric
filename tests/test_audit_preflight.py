from env.utility.audit_preflight import OPTIONAL_SOURCES, REQUIRED_SOURCES, check_sources


def test_all_sources_present():
    required, optional, lines = check_sources(lambda folder: True)
    assert required == [] and optional == []
    assert all(line.startswith("OK") for line in lines)


def test_missing_required_names_module():
    required, optional, lines = check_sources(lambda folder: folder != "activity")
    assert required == ["activity"]
    assert optional == []
    assert any("run the Activity module" in line for line in lines)


def test_missing_optional_reports_effect():
    required, optional, lines = check_sources(lambda folder: folder in REQUIRED_SOURCES)
    assert required == []
    assert set(optional) == set(OPTIONAL_SOURCES)
    assert any("controlplane" in line and "ControlPlane" in line for line in lines)
