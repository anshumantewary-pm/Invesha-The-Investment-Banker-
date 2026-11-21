import io
import json
import shutil
import subprocess
import warnings
import zipfile

import pytest

from invesha import cli, excel
from invesha.examples import EXAMPLES
from invesha.xlsx import Workbook, col_letter

openpyxl = pytest.importorskip("openpyxl")


@pytest.mark.parametrize("kind", ["company", "project", "startup"])
def test_workbook_opens_with_formulas(kind):
    data = excel.build(kind, EXAMPLES[kind])
    assert zipfile.ZipFile(io.BytesIO(data)).testzip() is None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames[:2] == ["Summary", "Inputs"]
    assert "Suggestions" in wb.sheetnames
    formulas = sum(
        1 for ws in wb for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")
    )
    assert formulas > 100


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_formulas_recalculate_to_engine_values(tmp_path):
    src = tmp_path / "company.xlsx"
    src.write_bytes(excel.build("company", EXAMPLES["company"]))
    out = tmp_path / "out"
    subprocess.run(
        ["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), str(src)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cached = openpyxl.load_workbook(src, data_only=True)
        fresh = openpyxl.load_workbook(out / "company.xlsx", data_only=True)
    for sheet, cell in (("Valuation", "B13"), ("Valuation", "B19"), ("Valuation", "C19"), ("Model", "G19")):
        assert fresh[sheet][cell].value == pytest.approx(cached[sheet][cell].value, rel=1e-9)


def test_xlsx_helpers():
    assert col_letter(1) == "A"
    assert col_letter(27) == "AA"
    wb = Workbook()
    assert wb.add("a/b").name == "ab"
    assert wb.add("ab").name == "ab (2)"
    with pytest.raises(ValueError):
        excel.build("nope", {})


def test_cli(tmp_path, capsys):
    for kind in EXAMPLES:
        f = tmp_path / f"{kind}.json"
        f.write_text(json.dumps(EXAMPLES[kind]), encoding="utf-8")
        assert cli.main([kind, "--file", str(f), "--xlsx", str(tmp_path / f"{kind}.xlsx")]) == 0
        assert "VERDICT" in capsys.readouterr().out
        assert (tmp_path / f"{kind}.xlsx").stat().st_size > 1000
    assert cli.main(["company", "--file", str(tmp_path / "company.json"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["kind"] == "company"
    assert cli.main(["example", "startup"]) == 0
    assert json.loads(capsys.readouterr().out)["name"]
    assert cli.main(["sectors"]) == 0
    assert "technology" in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**EXAMPLES["company"], "revenue": -1}), encoding="utf-8")
    assert cli.main(["company", "--file", str(bad)]) == 2
    assert cli.main(["company", "--file", str(tmp_path / "missing.json")]) == 2


def test_cli_samples_list(capsys):
    assert cli.main(["samples"]) == 0
    out = capsys.readouterr().out
    assert "company:saas" in out
    assert "merger:bolt_on" in out


def test_cli_example_accepts_samples(capsys):
    assert cli.main(["example", "company:saas"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "Cloudpeak Software Ltd"
    assert cli.main(["example", "company:nope"]) == 2
    assert cli.main(["example", "bogus"]) == 2


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_merger_workbook_formulas_recalculate(tmp_path):
    src = tmp_path / "merger.xlsx"
    src.write_bytes(excel.build("merger", EXAMPLES["merger"]))
    out = tmp_path / "out"
    subprocess.run(
        ["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), str(src)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cached = openpyxl.load_workbook(src, data_only=True)["Accretion model"]
        fresh = openpyxl.load_workbook(out / "merger.xlsx", data_only=True)["Accretion model"]
    for cell in ("B3", "B10", "B18", "C18", "B20", "C20", "B22"):
        assert fresh[cell].value == pytest.approx(cached[cell].value, rel=1e-9)
