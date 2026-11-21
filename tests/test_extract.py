import pytest

from invesha.extract import _chronological, _is_period, classify


@pytest.mark.parametrize(
    ("label", "concept"),
    [
        ("Revenue from operations", "revenue"),
        ("Net sales", "revenue"),
        ("Total income", "total_income"),
        ("Finance costs", "interest"),
        ("Depreciation and amortisation expense", "da"),
        ("Profit before tax", "pbt"),
        ("Total tax expense", "tax"),
        ("Profit for the year", "net_income"),
        ("Basic EPS", "eps"),
        ("Purchase of property, plant and equipment", "capex"),
        ("Trade receivables", "receivables"),
        ("Inventories", "inventory"),
        ("Trade payables", "payables"),
        ("Cash and cash equivalents", "cash"),
        ("Non-current borrowings", "borrowings_lt"),
        ("Current borrowings", "borrowings_st"),
        ("Total equity", "equity"),
        ("Paying customers", "customers"),
        ("New customers", "new_customers"),
        ("MRR", "mrr"),
        ("Plant load factor", "utilisation"),
        ("Tariff", "tariff"),
        ("Loan tenor (years)", "tenor"),
        ("(i) Revenue from operations", "revenue"),
        ("2.1 Other income", "other_income"),
    ],
)
def test_classify_common_line_items(label, concept):
    assert classify(label) == concept


@pytest.mark.parametrize(
    "label", ["Revenue growth %", "Other comprehensive income", "Cash flow from operations", "Random note"]
)
def test_classify_rejects_look_alikes(label):
    assert classify(label) not in ("revenue", "cash")


@pytest.mark.parametrize("cell", ["FY24", "FY2024", "2023-24", "Mar-24", "Q1FY25", "Jan-24", 2024.0, "M12", "2024 (A)"])
def test_period_headers(cell):
    assert _is_period(cell)


@pytest.mark.parametrize("cell", ["24", 24.0, "Revenue", 1500.0, None])
def test_not_periods(cell):
    assert not _is_period(cell)


def test_chronological_ordering():
    assert _chronological(["2023-24", "2021-22", "2022-23"]) == [1, 2, 0]
    assert _chronological(["Mar-24", "Jan-24", "Feb-24"]) == [1, 2, 0]
    assert _chronological(["a", "b"]) == [0, 1]
