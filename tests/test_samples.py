import pytest

from invesha import cli, excel
from invesha.examples import SAMPLES
from invesha.fields import FORMS

CASES = [(kind, item) for kind, items in SAMPLES.items() for item in items]


@pytest.mark.parametrize(("kind", "item"), CASES, ids=[f"{k}-{i['id']}" for k, i in CASES])
def test_every_sample_builds_a_full_report_and_workbook(kind, item):
    inputs = {k: v for k, v in item["inputs"].items() if v is not None}
    report = cli.run(kind, inputs)
    assert report.verdict
    assert report.next_steps
    assert report.tiles
    assert report.tables
    assert excel.build(kind, inputs)[:2] == b"PK"


def test_sample_library_covers_every_model_with_unique_ids():
    assert set(SAMPLES) == set(FORMS)
    for items in SAMPLES.values():
        ids = [i["id"] for i in items]
        assert len(ids) == len(set(ids))
        for i in items:
            assert {"id", "title", "tag", "blurb", "inputs"} <= set(i)


def test_samples_span_different_verdicts():
    verdicts = {
        cli.run("company", {k: v for k, v in i["inputs"].items() if v is not None}).verdict for i in SAMPLES["company"]
    }
    assert {"BUY", "HOLD", "REDUCE"} <= verdicts
