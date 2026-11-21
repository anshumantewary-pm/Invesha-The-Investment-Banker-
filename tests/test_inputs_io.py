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
        ("a.csv", b"nothing,here\n", "no recognised inputs"),
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
    from invesha.project import ProjectInputs
    from invesha.startup import StartupInputs

    classes = {"company": CompanyInputs, "project": ProjectInputs, "startup": StartupInputs}
    for kind in FORMS:
        names = {f.name for f in dc_fields(classes[kind])}
        assert {f[0] for f in fields(kind)} <= names
