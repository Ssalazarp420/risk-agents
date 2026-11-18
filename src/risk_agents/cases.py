"""The cases of the day: casos_del_dia.csv parsed into typed rows."""

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

COLUMNS = ("caso_id", "jugador_id", "fecha_corte", "score")


class CaseFileError(ValueError):
    """casos_del_dia.csv cannot be read as a list of cases."""


@dataclass(frozen=True)
class Case:
    caso_id: str
    jugador_id: str
    fecha_corte: str
    score: float


def load_cases(path: str | Path) -> list[Case]:
    """Read the file in order. A malformed row stops the run: it is an input error."""
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise CaseFileError(f"{path}: missing columns {', '.join(missing)}")
        # Line 1 is the header, so the first case is on line 2.
        return [_parse(row, line) for line, row in enumerate(reader, start=2)]


def _parse(row: dict[str, str], line: int) -> Case:
    values = {c: (row.get(c) or "").strip() for c in COLUMNS}
    for column in ("caso_id", "jugador_id"):
        if not values[column]:
            raise CaseFileError(f"line {line}: empty {column}")
    try:
        dt.date.fromisoformat(values["fecha_corte"])
    except ValueError:
        raise CaseFileError(
            f"line {line}: fecha_corte {values['fecha_corte']!r} is not YYYY-MM-DD"
        ) from None
    try:
        score = float(values["score"])
    except ValueError:
        raise CaseFileError(f"line {line}: score {values['score']!r} is not a number") from None
    return Case(values["caso_id"], values["jugador_id"], values["fecha_corte"], score)
