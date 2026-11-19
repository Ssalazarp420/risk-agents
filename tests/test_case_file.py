"""Case files that are decided in code, and validation against the official schema."""

import pytest

from risk_agents.case_file import (
    incomplete_file,
    investigated_file,
    no_data_file,
    skipped_file,
    validate,
)
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


METRICS = {
    "depositos_aprobados": 21.6,
    "retiros_aprobados": 69.02,
    "monto_apostado": 87.25,
    "ggr": 7.13,
    "bonos_otorgados": 43.2,
    "n_apuestas": 40,
}
RING = Case("C-20261101-016", "J101070", "2026-10-31", 0.952)
CONCLUSION = {
    "hallazgos": [{"descripcion": "Comparte dispositivo", "evidencia": "cuentas_relacionadas"}],
    "nivel_preocupacion": "alto",
    "derivar_a": ["riesgo"],
    "resumen": "Anillo de cuentas.",
    "cuentas_relacionadas": ["J101084", "J100146"],
    "alertas_calidad_datos": ["alerta del agente"],
}


class TestInvestigatedFile:
    def build(self, conclusion=CONCLUSION, seen=("J101084", "J100146"), alerts=("del código",)):
        return investigated_file(RING, METRICS, conclusion, frozenset(seen), list(alerts))

    def test_follows_the_schema(self):
        assert validate(self.build()) == []

    def test_code_fields_come_from_the_code(self):
        file = self.build()
        assert file["estado_investigacion"] == "completo"
        assert file["metricas_90d_usd"] == METRICS
        assert (file["caso_id"], file["jugador_id"]) == ("C-20261101-016", "J101070")

    def test_judgement_fields_come_from_the_agent(self):
        file = self.build()
        for field in ("hallazgos", "nivel_preocupacion", "derivar_a", "resumen"):
            assert file[field] == CONCLUSION[field]

    def test_accounts_the_tools_never_returned_are_dropped_with_an_alert(self):
        file = self.build(seen=("J101084",))
        assert file["cuentas_relacionadas"] == ["J101084"]
        assert any("J100146" in a and "descart" in a for a in file["alertas_calidad_datos"])

    def test_the_player_cannot_be_related_to_itself_and_repeats_are_removed(self):
        conclusion = {**CONCLUSION, "cuentas_relacionadas": ["J101084", "J101070", "J101084"]}
        file = self.build(conclusion=conclusion, seen=("J101084", "J101070"))
        assert file["cuentas_relacionadas"] == ["J101084"]

    def test_alerts_are_code_first_then_agent_without_repeats(self):
        conclusion = {**CONCLUSION, "alertas_calidad_datos": ["del código", "del agente"]}
        file = self.build(conclusion=conclusion)
        assert file["alertas_calidad_datos"] == ["del código", "del agente"]


class TestIncompleteFile:
    def test_follows_the_schema_and_keeps_the_metrics(self):
        file = incomplete_file(RING, METRICS, "límite de pasos", ["del código"])
        assert validate(file) == []
        assert file["estado_investigacion"] == "incompleto"
        assert file["metricas_90d_usd"] == METRICS
        assert file["nivel_preocupacion"] is None
        assert "límite de pasos" in file["resumen"]
        assert file["alertas_calidad_datos"][0] == "del código"
        assert any("límite de pasos" in a for a in file["alertas_calidad_datos"][1:])

    def test_a_very_long_reason_still_fits(self):
        file = incomplete_file(RING, None, "x" * 2000, [])
        assert validate(file) == []
        assert len(file["resumen"]) <= 800
