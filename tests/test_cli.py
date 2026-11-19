"""The command the reviewer runs."""

import json

from risk_agents.cli import main


def args(tmp_path, *extra):
    return [
        "--out",
        str(tmp_path / "expedientes.jsonl"),
        "--traces",
        str(tmp_path / "trazas.jsonl"),
        *extra,
    ]


def test_runs_the_whole_batch_with_the_rules(tmp_path, capsys):
    assert main(args(tmp_path, "--llm", "reglas")) == 0
    assert len((tmp_path / "expedientes.jsonl").read_text().splitlines()) == 25
    summary = json.loads((tmp_path / "resumen_corrida.json").read_text())
    assert summary["por_estado"] == {"completo": 23, "sin_datos": 1, "omitido": 1}
    assert summary["modelo"] == "reglas"
    out = capsys.readouterr().out
    assert "C-20261101-016" in out and "alto" in out


def test_one_case_only(tmp_path):
    assert main(args(tmp_path, "--llm", "reglas", "--only", "C-20261101-011")) == 0
    lines = (tmp_path / "expedientes.jsonl").read_text().splitlines()
    assert [json.loads(line)["caso_id"] for line in lines] == ["C-20261101-011"]


def test_groq_without_a_key_explains_what_to_do(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert main(args(tmp_path)) == 2
    err = capsys.readouterr().err
    assert "GROQ_API_KEY" in err and "--llm reglas" in err
    assert not (tmp_path / "expedientes.jsonl").exists()


def test_a_missing_database_is_reported(tmp_path, capsys):
    assert main(args(tmp_path, "--llm", "reglas", "--db", str(tmp_path / "no.db"))) == 2
    assert "no.db" in capsys.readouterr().err
