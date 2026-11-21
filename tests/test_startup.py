import pytest

from invesha import startup
from invesha.core import InputError
from invesha.examples import STARTUP


def test_simulation_by_hand():
    p = startup.StartupInputs(
        name="x",
        months=12,
        starting_customers=100,
        new_customers=10,
        new_customer_growth=0,
        arpu=1.0,
        arpu_growth=0,
        churn=0.1,
        gross_margin=0.5,
        cac=2.0,
        fixed_costs=10,
        fixed_cost_growth=0,
        cash=100,
    )
    m = startup.simulate(p)
    assert m.customers[0] == pytest.approx(100 - 10 + 10)
    assert m.mrr[0] == pytest.approx(100)
    assert m.ebitda[0] == pytest.approx(50 - 20 - 10)
    assert m.cash[0] == pytest.approx(120)


def test_example_report():
    r = startup.analyse_inputs(STARTUP)
    assert r.verdict == "RAISE NOW"
    assert r.data["runway"] == 8
    assert r.data["breakeven"] == 19
    assert r.data["post_money"] > 0
    assert {c.kind for c in r.charts} == {"line", "bars", "donut"}


def test_funded_and_unit_economics_branches():
    funded = startup.analyse_inputs({**STARTUP, "cash": 5000.0, "funding": []})
    assert funded.verdict in ("FUNDED TO BREAK-EVEN", "FUNDED FOR THE PLAN")
    weak = startup.analyse_inputs({**STARTUP, "cac": 20.0, "churn": 0.08, "raise_amount": 0.0})
    areas = {s.area for s in weak.suggestions}
    assert {"Unit economics", "Retention"} <= areas
    assert weak.data["ltv_cac"] < 3
    slow = startup.analyse_inputs({**STARTUP, "cash": 3000.0, "funding": [], "fixed_costs": 60.0, "new_customers": 5})
    assert any(s.title == "No break-even within the plan" for s in slow.suggestions)


def test_validation():
    with pytest.raises(InputError, match="funding"):
        startup.analyse_inputs({**STARTUP, "funding": [{"month": 3}]})
    with pytest.raises(InputError, match="months"):
        startup.analyse_inputs({**STARTUP, "months": 6})
