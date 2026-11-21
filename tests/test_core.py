import pytest

from invesha.core import InputError, annuity_payment, fade, fmt_value, from_dict, irr, npv, number, solve
from invesha.corporate import CompanyInputs


def test_npv_and_irr_known_values():
    flows = [-1000, 300, 300, 300, 300, 300]
    assert npv(0.10, flows) == pytest.approx(137.236, abs=1e-3)
    assert irr(flows) == pytest.approx(0.152382, abs=1e-5)
    assert irr([100, 50]) is None
    assert irr([-100, -50]) is None
    with pytest.raises(InputError):
        npv(-1.5, flows)


def test_annuity_solve_and_fade():
    assert annuity_payment(1000, 0.1, 3) == pytest.approx(402.1148, abs=1e-4)
    assert annuity_payment(900, 0.0, 3) == 300
    with pytest.raises(InputError):
        annuity_payment(100, 0.1, 0)
    assert solve(lambda x: x * x, 9, 0, 10) == pytest.approx(3, abs=1e-5)
    assert solve(lambda x: x, 50, 0, 10) is None
    assert fade(0.2, 0.1, 3) == pytest.approx([0.2, 0.15, 0.1])
    assert fade(0.2, 0.1, 1) == [0.1]


def test_from_dict_and_number_validation():
    with pytest.raises(InputError, match="unknown input"):
        from_dict(CompanyInputs, {"name": "x", "bogus": 1})
    with pytest.raises(InputError, match="missing required"):
        from_dict(CompanyInputs, {"name": "x"})
    with pytest.raises(InputError):
        number("a", "1")
    with pytest.raises(InputError):
        number("a", float("nan"))
    with pytest.raises(InputError, match="at most"):
        number("a", 5, high=1)


def test_fmt_value():
    assert fmt_value(0.123, "pct") == "12.3%"
    assert fmt_value(2.5, "x") == "2.50x"
    assert fmt_value(-1234.5, "money", "₹", "Cr") == "-₹1,234.5 Cr"
    assert fmt_value(0.035, "price", "₹") == "₹0.0350"
    assert fmt_value(None, "money") == "-"
    assert fmt_value("text", "money") == "text"
    assert fmt_value(1234, "int") == "1,234"
    assert fmt_value(1.5, "num") == "1.50"
