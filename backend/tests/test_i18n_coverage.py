"""Tests for the i18n coverage report script."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_i18n_coverage as coverage  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_neutral_values_do_not_need_translation():
    assert coverage.is_neutral("Homepage.button.github", "GitHub")
    assert coverage.is_neutral("Expenses.exportJson", "JSON")
    assert coverage.is_neutral("ExpenseForm.amount", "{amount}")
    assert coverage.is_neutral("Attachments.extension", ".csv")
    assert coverage.is_neutral("Stats.percent", "%")
    assert not coverage.is_neutral("Common.save", "Save")
    assert coverage.is_neutral("Custom.key", "Same", {"Custom.*": "brand name"})


def test_coverage_counts_only_valid_translations():
    base = {"A": "Hello", "B": "pysplit", "C": "Text"}
    locale = {"A": "Hallo", "B": "pysplit", "C": "Text"}
    report = coverage.coverage({"A", "B", "C"}, base, locale)
    assert (report.translated, report.total, report.neutral) == (2, 3, 1)
    assert report.english == ["C"]

    missing = coverage.coverage({"A"}, base, {})
    assert (missing.translated, missing.total) == (0, 1)
    assert missing.missing == ["A"]


def test_empty_and_whitespace_values_are_not_translated():
    base = {"A": "Hello", "B": "World", "C": "Text"}
    locale = {"A": "", "B": "   ", "C": "Hallo"}
    report = coverage.coverage({"A", "B", "C"}, base, locale)
    assert report.translated == 1
    assert sorted(report.empty) == ["A", "B"]


def test_signature_mismatch_is_not_translated():
    base = {
        "A": "Hi <em>{name}</em>",
        "B": "Join {code}",
        "C": "Hello {name}",
    }
    locale = {
        "A": "Hallo <strong>{name}</strong>",
        "B": "Beitreten",
        "C": "Hallo {name}",
    }
    report = coverage.coverage({"A", "B", "C"}, base, locale)
    assert report.translated == 1
    assert sorted(report.signature_mismatch) == ["A", "B"]


def test_allowlist_requires_a_reason(tmp_path):
    allowlist = tmp_path / "allowlist.json"

    write_json(allowlist, ["Greeting"])
    with pytest.raises(SystemExit) as error:
        coverage.load_allowlist(allowlist)
    assert "reasons" in str(error.value)

    write_json(allowlist, {"Greeting": "   "})
    with pytest.raises(SystemExit) as error:
        coverage.load_allowlist(allowlist)
    assert "non-empty reason" in str(error.value)

    write_json(allowlist, {"Greeting": "kept English on purpose"})
    assert coverage.load_allowlist(allowlist) == {"Greeting": "kept English on purpose"}


def test_main_is_report_only_unless_a_floor_is_set(tmp_path, monkeypatch, capsys):
    write_json(
        tmp_path / "en-US.json",
        {"Greeting": "Hello", "Brand": "pysplit", "Untranslated": "Same text"},
    )
    write_json(
        tmp_path / "de-DE.json",
        {"Greeting": "Hallo", "Brand": "pysplit", "Untranslated": "Same text"},
    )
    monkeypatch.setattr(coverage, "CATALOGUES", tmp_path)
    monkeypatch.setattr(coverage, "collect", lambda: ({"Greeting", "Brand", "Untranslated"}, {}))

    assert coverage.main([]) == 0
    assert "de-DE" in capsys.readouterr().out

    assert coverage.main(["--min", "70"]) == 1
    assert "below --min 70%" in capsys.readouterr().err


def test_strict_rejects_english_empty_and_signature_mismatch(tmp_path, monkeypatch, capsys):
    write_json(
        tmp_path / "en-US.json",
        {
            "Greeting": "Hello",
            "Tagged": "Hi <em>{name}</em>",
            "Brand": "pysplit",
            "Empty": "Text",
        },
    )
    write_json(
        tmp_path / "de-DE.json",
        {
            "Greeting": "Hello",
            "Tagged": "Hallo <strong>{name}</strong>",
            "Brand": "pysplit",
            "Empty": "",
        },
    )
    monkeypatch.setattr(coverage, "CATALOGUES", tmp_path)
    monkeypatch.setattr(coverage, "collect", lambda: ({"Greeting", "Tagged", "Brand", "Empty"}, {}))

    assert coverage.main(["--strict"]) == 1
    err = capsys.readouterr().err
    assert "non-allowlisted value(s) still equal to en-US" in err
    assert "placeholder/markup signature mismatch" in err
    assert "empty/non-string used value(s)" in err
    assert "Greeting" in err
    assert "Tagged" in err
    assert "Empty" in err


def test_strict_accepts_allowlisted_english(tmp_path, monkeypatch, capsys):
    write_json(
        tmp_path / "en-US.json",
        {"Greeting": "Hello", "Brand": "pysplit"},
    )
    write_json(
        tmp_path / "de-DE.json",
        {"Greeting": "Hello", "Brand": "pysplit"},
    )
    allowlist = tmp_path / "allowlist.json"
    write_json(allowlist, {"Greeting": "kept English on purpose"})
    monkeypatch.setattr(coverage, "CATALOGUES", tmp_path)
    monkeypatch.setattr(coverage, "collect", lambda: ({"Greeting", "Brand"}, {}))

    assert coverage.main(["--strict", "--allowlist", str(allowlist)]) == 0
    assert "fully and safely translated" in capsys.readouterr().out


def test_baseline_and_allowlist_files(tmp_path, monkeypatch, capsys):
    write_json(
        tmp_path / "en-US.json",
        {"Greeting": "Hello", "Brand": "pysplit"},
    )
    write_json(tmp_path / "de-DE.json", {"Greeting": "Hello", "Brand": "pysplit"})
    monkeypatch.setattr(coverage, "CATALOGUES", tmp_path)
    monkeypatch.setattr(coverage, "collect", lambda: ({"Greeting", "Brand"}, {}))

    baseline = tmp_path / "baseline.json"
    write_json(baseline, {"locales": {"de-DE": 80}})
    assert coverage.main(["--baseline", str(baseline)]) == 1
    assert "below baseline 80%" in capsys.readouterr().err

    write_json(baseline, {"de-DE": 40})
    assert coverage.main(["--baseline", str(baseline)]) == 0

    allowlist = tmp_path / "allowlist.json"
    write_json(allowlist, {"Greeting": "kept English on purpose"})
    assert coverage.main(["--allowlist", str(allowlist)]) == 0


def test_baseline_fails_on_signature_mismatch_even_without_regression(
    tmp_path, monkeypatch, capsys
):
    write_json(tmp_path / "en-US.json", {"Greeting": "Hi <em>{name}</em>"})
    write_json(tmp_path / "de-DE.json", {"Greeting": "Hallo <strong>{name}</strong>"})
    monkeypatch.setattr(coverage, "CATALOGUES", tmp_path)
    monkeypatch.setattr(coverage, "collect", lambda: ({"Greeting"}, {}))

    baseline = tmp_path / "baseline.json"
    write_json(baseline, {"de-DE": 0})
    assert coverage.main(["--baseline", str(baseline)]) == 1
    assert "signature mismatch" in capsys.readouterr().err
