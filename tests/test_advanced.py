import pytest

from invesha import advanced, corporate, merger
from invesha.core import InputError
from invesha.examples import COMPANY, MERGER
from invesha.sectors import get_sector


def inputs(**kw):
    return corporate.CompanyInputs(**{**COMPANY, **kw})


def test_scenarios_are_ordered_and_weighted():
    p = inputs()
    cases = advanced.scenarios(p, get_sector(p.sector))
    assert [c.name for c in cases] == ["Bear", "Base", "Bull"]
    assert cases[0].equity < cases[1].equity < cases[2].equity
    assert sum(c.probability for c in cases) == pytest.approx(1.0)
    base = advanced.equity_value(p, get_sector(p.sector))
    assert cases[1].equity == pytest.approx(base)


def test_monte_carlo_is_reproducible_and_brackets_the_base_case():
    p = inputs(simulations=500)
    sector = get_sector(p.sector)
    a = advanced.monte_carlo(p, sector, benchmark=p.share_price)
    b = advanced.monte_carlo(p, sector, benchmark=p.share_price)
    assert a.values == b.values
    assert a.p10 < a.p50 < a.p90
    base_per_share = advanced.equity_value(p, sector) / p.shares
    assert a.p10 < base_per_share < a.p90
    assert 0 <= a.prob_above <= 1
    assert sum(a.counts) <= a.runs


def test_reverse_dcf_recovers_the_market_value():
    p = inputs()
    sector = get_sector(p.sector)
    mcap = p.shares * p.share_price
    r = advanced.reverse_dcf(p, sector, mcap)
    shifted = advanced._shift_growth(p, r["delta"])
    assert advanced.equity_value(shifted, sector) == pytest.approx(mcap, rel=1e-4)
    assert advanced.reverse_dcf(p, sector, 1e9) is None  # no growth path reaches this


def test_lbo_model_attribution_adds_up_and_debt_amortises():
    p = inputs()
    sector = get_sector(p.sector)
    proj = corporate.project(p)
    d = advanced.lbo_model(p, proj, sector)
    assert d.senior + d.junior + d.equity == pytest.approx(d.entry_ev + d.fees)
    assert sum(d.attribution.values()) == pytest.approx(d.exit_equity)
    assert d.senior_bal[-1] < d.senior
    assert all(x >= 0 for x in d.senior_bal + d.junior_bal)
    higher_exit = advanced.lbo_model(p, proj, sector, exit_multiple=d.exit_multiple + 2)
    assert higher_exit.irr > d.irr
    assert advanced.lbo_model(inputs(ebitda_margin=-0.1, margin_target=0.1), proj, sector) is None


@pytest.mark.parametrize(
    ("lev", "cover", "band"),
    [(0.5, 20, "AA / A"), (1.5, 9, "A / BBB"), (2.5, 6, "BBB / BB"), (4, 3.5, "BB / B"), (6, 2, "B- or below")],
)
def test_credit_bands(lev, cover, band):
    ebitda = 100.0
    debt = lev * ebitda
    rate = ebitda / cover / debt
    p = inputs(revenue=1000, ebitda_margin=0.1, debt=debt, cash=0, interest_rate=min(rate, 0.5))
    assert advanced.credit_profile(p, corporate.project(p))["band"] == band


def test_company_report_has_deal_desk_sections():
    r = corporate.analyse_inputs(COMPANY)
    titles = {t.title for t in r.tables}
    assert {
        "Scenario analysis",
        "Monte Carlo simulation",
        "Reverse DCF: what the market price implies",
        "LBO sources and uses",
        "LBO debt schedule and credit statistics",
        "Credit profile",
    } <= titles
    assert any(t.startswith("LBO IRR sensitivity") for t in titles)
    assert len(r.summary) >= 5
    assert r.data["mc_p10"] < r.data["mc_p90"]
    assert sum(1 for t in r.tiles if t.label == "LBO IRR") == 1


def test_merger_by_hand():
    d = merger.model(merger.MergerInputs(**MERGER))
    price = 60 * 1.3 * 4
    stock, debt, fees = price * 0.5, price * 0.3, price * 0.02
    cash = price - stock - debt + fees
    new_shares = stock / 210
    ni = 92.25 * 1.1 + 18 * 1.12 + 15 * 0.5 * 0.75 - (debt * 0.095 + cash * 0.06 + 4) * 0.75
    eps = ni / (10 + new_shares)
    assert d.pf_eps[0] == pytest.approx(eps)
    assert d.accretion[0] == pytest.approx(eps / (92.25 * 1.1 / 10) - 1)
    assert d.target_ownership == pytest.approx(new_shares / (10 + new_shares))
    # breakeven synergies make year-1 EPS neutral
    be = merger.model(merger.MergerInputs(**{**MERGER, "synergies": d.breakeven_synergies}))
    assert be.accretion[0] == pytest.approx(0, abs=1e-9) or d.breakeven_synergies == 0


def test_merger_report_and_branches():
    r = merger.analyse_inputs(MERGER)
    assert r.verdict == "ACCRETIVE"
    assert r.summary
    dil = merger.analyse_inputs(
        {**MERGER, "acquirer_share_price": 80.0, "pct_stock": 1.0, "pct_debt": 0.0, "synergies": 0, "premium": 0.6}
    )
    assert dil.verdict == "DILUTIVE"
    areas = {s.area for s in dil.suggestions}
    assert {"Accretion", "Price"} <= areas
    big = merger.analyse_inputs({**MERGER, "target_shares": 60.0, "pct_stock": 1.0, "pct_debt": 0.0})
    assert any(s.area == "Structure" for s in big.suggestions)
    lev = merger.analyse_inputs({**MERGER, "pct_stock": 0.0, "pct_debt": 1.0, "target_shares": 20.0})
    assert any(s.area == "Financing" for s in lev.suggestions)
    with pytest.raises(InputError, match="cannot exceed"):
        merger.analyse_inputs({**MERGER, "pct_stock": 0.8, "pct_debt": 0.5})
    with pytest.raises(InputError, match="deal name"):
        merger.analyse_inputs({**MERGER, "name": " "})
