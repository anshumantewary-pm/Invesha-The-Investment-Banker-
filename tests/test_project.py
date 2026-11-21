import pytest

from invesha import project
from invesha.core import InputError, npv
from invesha.examples import PROJECT


def test_sculpted_debt_hits_target_dscr_when_cash_flow_binds():
    r = project.model(project.ProjectInputs(**PROJECT))
    dscrs = [x for x in r.dscr if x is not None]
    assert min(dscrs) == pytest.approx(1.30, abs=1e-6)
    assert max(dscrs) == pytest.approx(1.30, abs=1e-6)
    assert r.debt_balance[PROJECT["tenor"] - 1] == pytest.approx(0, abs=1e-6)
    assert r.llcr == pytest.approx(npv(PROJECT["debt_rate"], r.cfads[: PROJECT["tenor"]], start=1) / r.debt)


def test_annuity_repayment_has_level_debt_service():
    p = project.ProjectInputs(**{**PROJECT, "repayment": "annuity", "gearing": 0.5})
    r = project.model(p)
    service = [x for x in r.debt_service if x > 0]
    assert max(service) == pytest.approx(min(service), rel=1e-6)
    assert r.debt == pytest.approx(0.5 * r.total_cost, rel=1e-6)


def test_report_and_verdicts():
    rep = project.analyse_inputs(PROJECT)
    assert rep.verdict == "RESTRUCTURE"
    assert rep.data["breakeven_price"] > PROJECT["price"]
    good = project.analyse_inputs({**PROJECT, "price": 0.05})
    assert good.verdict == "INVEST"
    bad = project.analyse_inputs({**PROJECT, "price": 0.02, "repayment": "annuity", "gearing": 0.9})
    assert bad.verdict == "DO NOT INVEST"
    assert any(s.area == "Bankability" for s in bad.suggestions)


def test_no_construction_period_and_terminal_value():
    r = project.analyse_inputs({**PROJECT, "construction_years": 0, "terminal_value": 50.0, "depreciation_years": 10})
    assert r.data["equity_irr"] is not None


def test_validation():
    with pytest.raises(InputError, match="tenor"):
        project.analyse_inputs({**PROJECT, "tenor": 40})
    with pytest.raises(InputError, match="repayment"):
        project.analyse_inputs({**PROJECT, "repayment": "bullet"})
    with pytest.raises(InputError, match="depreciation"):
        project.analyse_inputs({**PROJECT, "depreciation_years": 0})
    with pytest.raises(InputError, match="project name"):
        project.analyse_inputs({**PROJECT, "name": ""} | {"name": " "})
