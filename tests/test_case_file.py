"""Case files that are decided in code, and validation against the official schema."""

import pytest

from risk_agents.case_file import no_data_file, skipped_file, validate
from risk_agents.cases import Case

CASE = Case("C-20261101-004", "J103871", "2026-10-31", 0.81)
DUPLICATE = Case("C-20261101-018", "J102078", "2026-10-31", 0.825)


class TestNoDataFile:
    def test_follows_the_schema(self):
        assert validate(no_data_file(CASE, ["alerta"])) == []

    def test_has_no_metrics_and_no_conclusion(self):
        file = no_data_file(CASE, ["J103871 no existe en jugadores"])
        assert file["estado_investigacion"] == "sin_datos"
        assert file["metricas_90d_usd"] is None
        assert file["nivel_preocupacion"] is None
        assert file["hallazgos"] == []
        assert file["cuentas_relacionadas"] == []
        assert file["derivar_a"] == []
        assert file["alertas_calidad_datos"] == ["J103871 no existe en jugadores"]
        assert "J103871" in file["resumen"]

    def test_copies_the_case_identifiers(self):
        file = no_data_file(CASE, [])
        assert (file["caso_id"], file["jugador_id"], file["fecha_corte"]) == (
            "C-20261101-004",
            "J103871",
            "2026-10-31",
        )


class TestSkippedFile:
    def test_follows_the_schema(self):
        assert validate(skipped_file(DUPLICATE, "C-20261101-014", ["alerta"])) == []

    def test_points_to_the_original_case(self):
        file = skipped_file(DUPLICATE, "C-20261101-014", [])
        assert file["estado_investigacion"] == "omitido"
        assert file["metricas_90d_usd"] is None
        assert file["nivel_preocupacion"] is None
        assert "C-20261101-014" in file["resumen"]


class TestValidate:
    def test_reports_every_problem_with_its_location(self):
        file = no_data_file(CASE, [])
        file["nivel_preocupacion"] = "critico"
        file["resumen"] = "x" * 801
        file["campo_extra"] = 1
        errors = validate(file)
        assert len(errors) == 3
        assert any(e.startswith("nivel_preocupacion:") for e in errors)
        assert any(e.startswith("resumen:") for e in errors)
        assert any("campo_extra" in e for e in errors)

    @pytest.mark.parametrize("bad_date", ["31/10/2026", "2026-13-01"])
    def test_checks_the_date_format(self, bad_date):
        file = no_data_file(CASE, [])
        file["fecha_corte"] = bad_date
        assert any(e.startswith("fecha_corte:") for e in validate(file))
