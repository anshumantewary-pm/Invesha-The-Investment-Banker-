import pytest

from invesha.extract import classify


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
