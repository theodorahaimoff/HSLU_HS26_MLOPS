import pandas as pd
import pytest

from src.training_pipeline.baselines import baseline_table, reliability_groups


@pytest.fixture
def rows() -> pd.DataFrame:
    """Two segments, two target quarters. Errors chosen by hand."""
    return pd.DataFrame(
        {
            "segment": ["National total", "National total", "Frauen · Alle · Alle Alter", "Frauen · Alle · Alle Alter"],
            "status_t": ["A", "A", "U", "A"],
            "y_rate": [5.0, 5.0, 8.0, 8.0],
            "rate_t3": [5.1, 4.9, 8.4, 8.0],  # seasonal naive errors 0.1, 0.1, 0.4, 0.0
            "rate_t": [5.5, 5.0, 9.0, 7.0],  # persistence errors    0.5, 0.0, 1.0, 1.0
        }
    )


def test_reliability_groups(rows):
    groups = reliability_groups(rows)
    assert groups["National total"] == "all A"
    assert groups["Frauen · Alle · Alle Alter"] == "some U"


def test_baseline_table(rows):
    table = baseline_table(rows, reliability_groups(rows))
    assert table.loc["all segments", "MAE seasonal naive"] == pytest.approx(0.15)
    assert table.loc["all segments", "MAE persistence"] == pytest.approx(0.625)
    assert table.loc["National total", "MAE persistence"] == pytest.approx(0.25)
    assert table.loc["all segments", "better"] == "seasonal naive"
    assert table.loc["all segments", "segments"] == 2
