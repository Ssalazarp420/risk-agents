"""Reproduce every figure in docs/02_datos.md from the raw data (read-only).

Usage: python3 scripts/explorar_datos.py
"""

import csv
import datetime as dt
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "datos" / "transacciones.db"
CASES = ROOT / "datos" / "casos_del_dia.csv"
REFERENCE = ROOT / "datos" / "casos_referencia.json"
WINDOW_DAYS = 90


def connect() -> sqlite3.Connection:
    # mode=ro: the database cannot be modified from this connection.
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def window(cutoff: str, days: int = WINDOW_DAYS) -> tuple[str, str]:
    end = dt.date.fromisoformat(cutoff)
    start = end - dt.timedelta(days=days - 1)
    return f"{start} 00:00:00", f"{end} 23:59:59"


def metrics(db: sqlite3.Connection, player: str, cutoff: str, days: int = WINDOW_DAYS) -> dict:
    lo, hi = window(cutoff, days)
    (currency,) = db.execute(
        "select moneda from jugadores where jugador_id=?", (player,)
    ).fetchone()
    (rate,) = db.execute(
        "select usd_por_unidad from tasas_cambio where moneda=?", (currency,)
    ).fetchone()

    def one(sql: str) -> tuple:
        return db.execute(sql, (player, lo, hi)).fetchone()

    tx = (
        "select coalesce(sum(monto),0) from transacciones"
        " where jugador_id=? and fecha_hora between ? and ?"
    )
    (dep,) = one(tx + " and tipo='deposito' and estado='aprobada'")
    (wd,) = one(tx + " and tipo='retiro' and estado='aprobada'")
    staked, won, n = one(
        "select coalesce(sum(monto),0), coalesce(sum(ganancia),0), count(*) from apuestas"
        " where jugador_id=? and fecha_hora between ? and ?"
    )
    (bonus,) = one(
        "select coalesce(sum(monto),0) from bonos"
        " where jugador_id=? and fecha_otorgado between ? and ?"
    )
    return {
        "depositos_aprobados": round(dep * rate, 2),
        "retiros_aprobados": round(wd * rate, 2),
        "monto_apostado": round(staked * rate, 2),
        "ggr": round((staked - won) * rate, 2),
        "bonos_otorgados": round(bonus * rate, 2),
        "n_apuestas": n,
    }


def section(title: str) -> None:
    print(f"\n== {title}")


def main() -> None:
    db = connect()

    section("Tamaño de las tablas")
    for table in (
        "jugadores",
        "transacciones",
        "apuestas",
        "bonos",
        "dispositivos",
        "scores_riesgo",
    ):
        print(f"{table:15} {db.execute(f'select count(*) from {table}').fetchone()[0]:>8}")
    print("tasas_cambio   ", db.execute("select * from tasas_cambio").fetchall())

    section("Marcas, monedas y estados de cuenta")
    for row in db.execute(
        "select marca, pais, moneda, segmento, estado_cuenta, count(*)"
        " from jugadores group by 1,2,3,4,5"
    ):
        print(row)

    section("Moneda de movimientos distinta a la del jugador (debe ser 0)")
    for table in ("transacciones", "apuestas", "bonos"):
        n = db.execute(
            f"select count(*) from {table} t join jugadores j using(jugador_id)"
            " where t.moneda<>j.moneda"
        ).fetchone()[0]
        print(table, n)

    section("Rango de fechas (la extracción es del 2026-11-10)")
    print(
        "transacciones",
        db.execute("select min(fecha_hora), max(fecha_hora) from transacciones").fetchone(),
    )
    print(
        "apuestas     ",
        db.execute("select min(fecha_hora), max(fecha_hora) from apuestas").fetchone(),
    )
    print(
        "bonos        ",
        db.execute("select min(fecha_otorgado), max(fecha_otorgado) from bonos").fetchone(),
    )
    print(
        "dispositivos ",
        db.execute("select min(fecha_hora), max(fecha_hora) from dispositivos").fetchone(),
    )

    section("Tipos y estados de transacción")
    for row in db.execute("select tipo, estado, count(*) from transacciones group by 1,2"):
        print(row)

    section("Notas de texto libre distintas")
    for row in db.execute(
        "select nota, count(*) n from transacciones where nota <> '' group by 1 order by n desc"
    ):
        print(row)

    section("Casos del día contra la base")
    cases = list(csv.DictReader(CASES.open()))
    seen: dict[tuple[str, str], str] = {}
    for c in cases:
        key = (c["jugador_id"], c["fecha_corte"])
        exists = db.execute(
            "select 1 from jugadores where jugador_id=?", (c["jugador_id"],)
        ).fetchone()
        score = db.execute(
            "select score from scores_riesgo where jugador_id=? and fecha_corte=?", key
        ).fetchone()
        notes = []
        if not exists:
            notes.append("JUGADOR NO EXISTE")
        if key in seen:
            notes.append(f"DUPLICADO de {seen[key]}")
        seen.setdefault(key, c["caso_id"])
        if score and abs(score[0] - float(c["score"])) > 1e-9:
            notes.append(f"score distinto en la base: {score[0]}")
        print(c["caso_id"], c["jugador_id"], c["score"], " ".join(notes))

    section("Jugadores con score >= mínimo del CSV que no están en el CSV")
    cutoff = cases[0]["fecha_corte"]
    min_score = min(float(c["score"]) for c in cases)
    listed = {c["jugador_id"] for c in cases}
    for row in db.execute(
        "select jugador_id, score, factores from scores_riesgo where fecha_corte=? and score>=?"
        " order by score desc",
        (cutoff, min_score),
    ):
        if row[0] not in listed:
            print(row)

    section("Dispositivos compartidos entre jugadores")
    for row in db.execute(
        "select device_id, group_concat(distinct jugador_id) from dispositivos"
        " group by 1 having count(distinct jugador_id) > 1"
    ):
        print(row)
    print(
        "ip_red compartidas (n, máximo de jugadores en una):",
        db.execute(
            "select count(*), max(n) from (select ip_red, count(distinct jugador_id) n"
            " from dispositivos group by 1 having n > 1)"
        ).fetchone(),
    )

    section("Datos personales repetidos")
    for col in ("documento", "email", "telefono", "nombre_completo"):
        n = db.execute(
            f"select count(*) from (select {col} from jugadores group by 1 having count(*) > 1)"
        ).fetchone()[0]
        print(col, n)

    section("Volumen de apuestas: los 3 jugadores con más apuestas")
    for row in db.execute(
        "select jugador_id, count(*) n from apuestas group by 1 order by n desc limit 3"
    ):
        print(row)

    section("Métricas propias contra los casos de referencia (90 y 91 días)")
    for ref in json.loads(REFERENCE.read_text()):
        for days in (90, 91):
            mine = metrics(db, ref["jugador_id"], ref["fecha_corte"], days)
            diff = {
                k: (mine[k], v)
                for k, v in ref["metricas_90d_usd"].items()
                if abs(mine[k] - v) > 0.005
            }
            print(ref["caso_id"], f"{days} días:", diff or "coincide")


if __name__ == "__main__":
    main()
