import json

import pytest

from invesha import excel, inputs_io
from invesha.core import InputError
from invesha.examples import EXAMPLES
from invesha.fields import FORMS, fields


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return a == pytest.approx(b)
    return a == b


@pytest.mark.parametrize("kind", list(EXAMPLES))
def test_templates_round_trip(kind):
    for name, data in (("t.xlsx", inputs_io.template_xlsx(kind)), ("t.csv", inputs_io.template_csv(kind).encode())):
        got = inputs_io.parse_file(kind, name, data)["inputs"]
        for key, value in EXAMPLES[kind].items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                assert got[key] == value
            else:
                assert same(got[key], value), (name, key)


@pytest.mark.parametrize("kind", list(EXAMPLES))
def test_downloaded_model_workbook_re_uploads_every_input(kind):
    got = inputs_io.parse_file(kind, "model.xlsx", excel.build(kind, EXAMPLES[kind]))["inputs"]
    for key, value in EXAMPLES[kind].items():
        assert key in got
        if not isinstance(value, list):
            assert same(got[key], value), key


def test_simple_csv_with_labels_percentages_and_aliases():
    text = (
        "Item;Value\nCompany name;Acme\nSector;Fintech / financial services\nSales;1,200\n"
        "EBITDA margin;18%\nTax rate;25\nCost of debt;0.09\nGrowth per year;20%, 15, 0.1, 9, 8\nmystery;3\n"
    )
    res = inputs_io.parse_file("company", "acme.csv", text.encode())
    got = res["inputs"]
    assert got["name"] == "Acme"
    assert got["sector"] == "fintech"
    assert got["revenue"] == 1200
    assert got["ebitda_margin"] == pytest.approx(0.18)
    assert got["tax_rate"] == pytest.approx(0.25)
    assert got["interest_rate"] == pytest.approx(0.09)
    assert got["growth"] == pytest.approx([0.2, 0.15, 0.1, 0.09, 0.08])
    assert res["ignored"] == ["mystery"]


def test_json_rounds_currency_and_select():
    payload = {"inputs": {"name": "S", "funding": "6=100; 18: 250", "currency": "USD", "months": 24.0}}
    got = inputs_io.parse_file("startup", "s.json", json.dumps(payload).encode())["inputs"]
    assert got["funding"] == [{"month": 6, "amount": 100.0}, {"month": 18, "amount": 250.0}]
    assert got["currency"] == "$"
    assert got["months"] == 24
    got = inputs_io.parse_file("project", "p.json", b'{"repayment": "annuity", "capex": "(5)"}')["inputs"]
    assert got == {"repayment": "annuity", "capex": -5.0}


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("a.pdf", b"x", "upload an Excel"),
        ("a.xls", b"x", "old .xls"),
        ("a.xlsx", b"not a zip", "does not look like an Excel"),
        ("a.json", b"{bad", "not a valid JSON"),
        ("a.json", b"[1, 2]", "object of inputs"),
        ("a.csv", b"nothing,here\n", "could not find any of the figures"),
        ("a.csv", b"sector,mining\n", "unknown sector"),
        ("a.csv", b"revenue,lots\n", "could not read"),
    ],
)
def test_bad_files(name, data, message):
    with pytest.raises(InputError, match=message):
        inputs_io.parse_file("company", name, data)


def test_unknown_model():
    with pytest.raises(InputError):
        inputs_io.parse_file("nope", "a.csv", b"x,1")
    with pytest.raises(InputError):
        inputs_io.template_xlsx("nope")
    with pytest.raises(InputError):
        inputs_io.template_csv("nope")


def test_every_form_field_exists_on_its_inputs_dataclass():
    from dataclasses import fields as dc_fields

    from invesha.corporate import CompanyInputs
    from invesha.merger import MergerInputs
    from invesha.project import ProjectInputs
    from invesha.startup import StartupInputs

    classes = {"company": CompanyInputs, "project": ProjectInputs, "startup": StartupInputs, "merger": MergerInputs}
    for kind in FORMS:
        names = {f.name for f in dc_fields(classes[kind])}
        assert {f[0] for f in fields(kind)} <= names


def approx4(x):
    return pytest.approx(x, abs=1e-4)


FIX = "tests/fixtures/"


def parse(kind, name):
    with open(FIX + name, "rb") as handle:
        return inputs_io.parse_file(kind, name, handle.read())


def test_extracts_model_inputs_from_annual_report_statements():
    r = parse("company", "northstar_statements.xlsx")
    got = r["inputs"]
    assert r["years"] == ["2021-22", "2022-23", "2023-24"]
    assert got["unit"] == "Cr"
    assert got["currency"] == "₹"
    assert got["revenue"] == 1200.0
    assert got["ebitda_margin"] == approx4((123 + 48 + 33) / 1200)  # PBT + D&A + finance costs
    assert got["da_pct"] == approx4((36 / 905 + 41 / 1040 + 48 / 1200) / 3)
    assert got["capex_pct"] == approx4((55 / 905 + 66 / 1040 + 78 / 1200) / 3)
    assert got["nwc_pct"] == approx4((175 + 150 - 135) / 1200)
    assert got["tax_rate"] == approx4(30.75 / 123)
    assert got["debt"] == 350.0
    assert got["cash"] == 90.0
    assert got["interest_rate"] == approx4(33 / 350)
    assert got["shares"] == approx4(92.25 / 9.225)
    assert got["invested_capital"] == approx4(680 + 350 - 90)
    last = 1200 / 1040 - 1
    cagr = (1200 / 905) ** 0.5 - 1
    assert got["growth_start"] == approx4(round((last + cagr) / 2, 4))
    assert set(r["missing"]) == {"name", "sector"}
    methods = {t["field"]: t["method"] for t in r["trace"]}
    assert methods["revenue"] == "found"
    assert methods["ebitda_margin"] == "derived"


def test_extracts_from_simple_us_style_csv():
    got = parse("company", "pnl_simple.csv")["inputs"]
    assert got["currency"] == "$"
    assert got["unit"] == "Mn"
    assert got["revenue"] == 520
    assert got["ebitda_margin"] == approx4(83 / 520)
    assert got["cash"] == 31  # latest year, not the first column
    assert got["debt"] == 70
    assert got["tax_rate"] == approx4(13 / 61)


def test_extracts_startup_metrics_from_monthly_mis():
    r = parse("startup", "startup_mis.csv")
    got = r["inputs"]
    assert got["name"] == "LedgerLoop"
    assert got["starting_customers"] == 156
    assert got["new_customers"] == 29
    assert got["arpu"] == approx4(39 / 156)
    assert got["churn"] == approx4(5 / 132)
    assert got["cac"] == approx4(43.5 / 29)
    assert got["fixed_costs"] == approx4(33)
    assert got["cash"] == 222
    assert r["missing"] == []


def test_extracts_project_terms_from_a_term_sheet():
    r = parse("project", "solar_termsheet.csv")
    got = r["inputs"]
    assert got["capex"] == 450
    assert got["capacity"] == 8760
    assert got["utilisation"] == approx4(0.22)
    assert got["price"] == approx4(0.03)
    assert got["gearing"] == approx4(0.75)
    assert got["tenor"] == 18
    assert got["operating_years"] == 25
    assert r["missing"] == []


def test_extracted_inputs_build_a_model():
    from invesha import cli

    r = parse("company", "northstar_statements.xlsx")
    report = cli.run("company", {**r["inputs"], "name": "Northstar", "sector": "manufacturing"})
    assert report.data["ev"] > 0
    for kind, name in (("startup", "startup_mis.csv"), ("project", "solar_termsheet.csv")):
        assert cli.run(kind, parse(kind, name)["inputs"]).verdict
