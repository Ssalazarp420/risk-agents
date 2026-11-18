"""Loading casos_del_dia.csv into typed cases."""

from pathlib import Path

import pytest

from risk_agents.cases import Case, CaseFileError, load_cases

CASES_PATH = Path(__file__).resolve().parent.parent / "datos" / "casos_del_dia.csv"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "casos.csv"
    path.write_text(text)
    return path


def test_loads_the_real_file_in_order():
    cases = load_cases(CASES_PATH)
    assert len(cases) == 25
    assert cases[0] == Case("C-20261101-001", "J101602", "2026-10-31", 0.87)
    assert cases[-1].caso_id == "C-20261101-025"


def test_score_is_a_number(tmp_path):
    path = write(tmp_path, "caso_id,jugador_id,fecha_corte,score\nC-1,J1,2026-10-31,0.713\n")
    assert load_cases(path)[0].score == 0.713


def test_surrounding_spaces_are_removed(tmp_path):
    path = write(tmp_path, "caso_id,jugador_id,fecha_corte,score\n C-1 , J1 ,2026-10-31, 0.5\n")
    assert load_cases(path)[0] == Case("C-1", "J1", "2026-10-31", 0.5)


def test_a_missing_column_is_named(tmp_path):
    path = write(tmp_path, "caso_id,jugador_id,score\nC-1,J1,0.5\n")
    with pytest.raises(CaseFileError, match="fecha_corte"):
        load_cases(path)


@pytest.mark.parametrize(
    ("row", "problem"),
    [
        ("C-1,J1,2026-10-31,alto", "score"),
        ("C-1,J1,31/10/2026,0.5", "fecha_corte"),
        (",J1,2026-10-31,0.5", "caso_id"),
        ("C-1,,2026-10-31,0.5", "jugador_id"),
    ],
)
def test_a_malformed_row_names_the_line_and_the_field(tmp_path, row, problem):
    path = write(tmp_path, f"caso_id,jugador_id,fecha_corte,score\nC-0,J0,2026-10-31,0.5\n{row}\n")
    with pytest.raises(CaseFileError, match=rf"line 3.*{problem}"):
        load_cases(path)
