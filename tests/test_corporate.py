import pytest

from invesha import corporate
from invesha.core import InputError
from invesha.examples import COMPANY
from invesha.sectors import get_sector


def simple(**kw):
    base = {
        "name": "Co",
        "sector": "manufacturing",
        "revenue": 100.0,
        "ebitda_margin": 0.20,
        "years": 3,
        "growth": [0.10, 0.10, 0.10],
        "da_pct": 0.05,
        "capex_pct": 0.05,
        "nwc_pct": 0.10,
        "tax_rate": 0.25,
        "debt_weight": 0.0,
        "beta": 1.0,
        "risk_free": 0.05,
        "equity_risk_premium": 0.05,
        "terminal_growth": 0.03,
        "exit_multiple": 10.0,
    }
    base.update(kw)
    return corporate.CompanyInputs(**base)


def test_projection_by_hand():
    proj = corporate.project(simple())
    assert proj.revenue == pytest.approx([110, 121, 133.1])
    assert proj.ebitda[0] == pytest.approx(22.0)
    # EBIT 22 - 5.5 = 16.5; NOPAT 12.375; FCFF = 12.375 + 5.5 - 5.5 - 1.0
    assert proj.fcff[0] == pytest.approx(11.375)


def test_wacc_and_dcf_by_hand():
    p = simple()
    w = corporate.wacc(p, get_sector(p.sector))
    assert w.wacc == pytest.approx(0.10)
    proj = corporate.project(p)
    d = corporate.dcf(proj, 0.10, 0.03, 10.0)
    pv = sum(f / 1.1 ** (i + 1) for i, f in enumerate(proj.fcff))
    assert d.pv_fcff == pytest.approx(pv)
    assert d.tv_gordon == pytest.approx(proj.fcff[-1] * 1.03 / 0.07)
    assert d.ev_exit == pytest.approx(pv + proj.ebitda[-1] * 10 / 1.1**3)
    with pytest.raises(InputError, match="must exceed"):
        corporate.dcf(proj, 0.03, 0.03, 10)


def test_relevered_beta_and_debt_weight_from_market_cap():
    p = simple(beta=None, debt_weight=None, debt=50.0, shares=10.0, share_price=15.0)
    w = corporate.wacc(p, get_sector(p.sector))
    assert w.debt_weight == pytest.approx(0.25)
    assert w.beta == pytest.approx(0.90 * (1 + 0.75 * (0.25 / 0.75)))
    assert (
        corporate.wacc(simple(beta=None, debt_weight=None, debt=10.0), get_sector("manufacturing")).debt_weight == 0.25
    )


def test_example_report_is_complete():
    r = corporate.analyse_inputs(COMPANY)
    assert r.verdict in ("BUY", "HOLD", "REDUCE")
    kinds = {c.kind for c in r.charts}
    assert kinds == {"range", "bars", "line", "waterfall", "donut"}
    assert len(r.tables) >= 6
    assert r.suggestions and r.suggestions[0].priority in ("high", "medium")
    assert r.data["lbo_irr"] is not None
    r.to_dict()


def test_verdicts_buy_and_reduce_and_no_price():
    cheap = corporate.analyse_inputs({**COMPANY, "share_price": 100.0})
    assert cheap.verdict == "BUY"
    rich = corporate.analyse_inputs({**COMPANY, "share_price": 600.0})
    assert rich.verdict == "REDUCE"
    none = corporate.analyse_inputs({k: v for k, v in COMPANY.items() if k not in ("share_price", "shares")})
    assert none.verdict == "Indicative valuation"


def test_suggestion_branches():
    levered = corporate.analyse_inputs(
        {
            **COMPANY,
            "debt": 1200.0,
            "ebitda_margin": 0.08,
            "margin_target": 0.08,
            "growth_start": 0.45,
            "growth_end": 0.40,
            "invested_capital": 5000.0,
        }
    )
    areas = {s.area for s in levered.suggestions}
    assert {"Capital structure", "Operations", "Forecast risk", "Value creation"} <= areas
    high_margin = corporate.analyse_inputs({**COMPANY, "margin_target": 0.35, "debt": 0.0, "terminal_growth": 0.10})
    assert any("above the sector range" in s.title for s in high_margin.suggestions)
    loss = corporate.analyse_inputs({**COMPANY, "ebitda_margin": -0.05, "margin_target": 0.10})
    assert loss.data["lbo_irr"] is None


def test_validation():
    with pytest.raises(InputError, match="growth needs exactly"):
        corporate.analyse_inputs({**COMPANY, "growth": [0.1]})
    with pytest.raises(InputError, match="unknown sector"):
        corporate.analyse_inputs({**COMPANY, "sector": "mining"})
    with pytest.raises(InputError, match="years"):
        corporate.analyse_inputs({**COMPANY, "years": 2})
    with pytest.raises(InputError, match="company name"):
        corporate.analyse_inputs({**COMPANY, "name": " "})
    r = corporate.analyse_inputs({**COMPANY, "growth": [0.1] * 5, "beta": 1.1, "debt_weight": 0.2})
    assert r.tiles
