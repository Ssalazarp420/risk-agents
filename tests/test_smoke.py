import json
from pathlib import Path

import risk_agents

ROOT = Path(__file__).resolve().parent.parent


def test_package_imports():
    assert risk_agents.__doc__


def test_input_files_are_present():
    for path in (
        "datos/transacciones.db",
        "datos/casos_del_dia.csv",
        "datos/casos_referencia.json",
        "esquema_expediente.json",
    ):
        assert (ROOT / path).is_file(), path


def test_reference_cases_follow_the_schema():
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "esquema_expediente.json").read_text())
    validator = Draft202012Validator(schema)
    for case in json.loads((ROOT / "datos/casos_referencia.json").read_text()):
        assert not list(validator.iter_errors(case)), case["caso_id"]
