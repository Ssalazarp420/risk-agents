import socket
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from risk_agents.data.repository import Repository, connect_read_only

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "datos" / "transacciones.db"

# Same tables as the real database, without indexes.
SCHEMA = """
CREATE TABLE jugadores (jugador_id TEXT PRIMARY KEY, marca TEXT, pais TEXT, moneda TEXT,
    fecha_registro TEXT, alias TEXT, nombre_completo TEXT, documento TEXT, email TEXT,
    telefono TEXT, segmento TEXT, estado_cuenta TEXT);
CREATE TABLE transacciones (tx_id INTEGER PRIMARY KEY, jugador_id TEXT, fecha_hora TEXT,
    tipo TEXT, medio_pago TEXT, monto REAL, moneda TEXT, estado TEXT, nota TEXT);
CREATE TABLE apuestas (apuesta_id INTEGER PRIMARY KEY, jugador_id TEXT, fecha_hora TEXT,
    producto TEXT, detalle TEXT, monto REAL, ganancia REAL, cuota REAL, con_bono INTEGER,
    moneda TEXT);
CREATE TABLE bonos (bono_id INTEGER PRIMARY KEY, jugador_id TEXT, tipo TEXT, monto REAL,
    moneda TEXT, fecha_otorgado TEXT, estado TEXT);
CREATE TABLE dispositivos (jugador_id TEXT, fecha_hora TEXT, device_id TEXT, ip_red TEXT);
CREATE TABLE scores_riesgo (jugador_id TEXT, fecha_corte TEXT, score REAL,
    version_modelo TEXT, factores TEXT);
CREATE TABLE tasas_cambio (moneda TEXT PRIMARY KEY, usd_por_unidad REAL);
"""


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never reach the network or spend money: any connection attempt fails loudly."""

    def blocked(*args, **kwargs):
        raise RuntimeError("network access is blocked in tests")

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture(scope="session")
def repo() -> Repository:
    """The real database, read-only, shared by every test in the run."""
    return Repository(connect_read_only(DB_PATH))


@pytest.fixture
def make_db(tmp_path: Path) -> Callable[[str], Path]:
    """Build a small database file from SQL statements; returns its path."""

    def build(sql: str) -> Path:
        path = tmp_path / "mini.db"
        with sqlite3.connect(path) as conn:
            conn.executescript(SCHEMA + sql)
        conn.close()
        return path

    return build
