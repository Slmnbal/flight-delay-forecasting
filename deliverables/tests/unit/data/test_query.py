"""query (DuckDB) tests; skipped if duckdb is not installed."""

import pytest

pytest.importorskip("duckdb")

from flight_delay.data import query  # noqa: E402


@pytest.fixture
def root(tmp_path, process_fake_month):
    layer_root, _ = process_fake_month(tmp_path)
    return layer_root


def test_view_row_count_and_partition_columns(root):
    df = query.run_query("SELECT count(*) AS n, min(partition_year) AS y, min(partition_month) AS m FROM flights", root)
    assert int(df.loc[0, "n"]) == 4
    assert int(df.loc[0, "y"]) == 2025 and int(df.loc[0, "m"]) == 7


def test_cancelled_filter(root):
    df = query.run_query("SELECT count(*) AS n FROM flight_labels WHERE Cancelled = 1", root)
    assert int(df.loc[0, "n"]) == 1


def test_summary_sql(root):
    df = query.run_query(query.SUMMARY_SQL, root)
    assert len(df) == 1 and int(df.loc[0, "row_count"]) == 4 and int(df.loc[0, "cancelled_count"]) == 1


def test_utc_column_is_read_as_a_timestamp(root):
    df = query.run_query("SELECT min(crs_dep_utc) AS t FROM flights", root)
    assert str(df.loc[0, "t"]).startswith("2025-07-01 14:00")


def test_second_month_is_combined_in_the_view(root, tmp_path, write_ontime_csv, empty_airports, manual_tz):
    from flight_delay.data import layer

    csv = write_ontime_csv(tmp_path / "raw2.csv")
    layer.process_month(csv, 2025, 8, root, ["ORD", "ATL"], empty_airports, manual_tz)
    df = query.run_query("SELECT count(DISTINCT partition_month) AS n_months, count(*) AS n FROM flights", root)
    assert int(df.loc[0, "n_months"]) == 2 and int(df.loc[0, "n"]) == 8


def test_empty_layer_gives_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        query.connect(tmp_path / "missing")


def test_invalid_view_name(root):
    with pytest.raises(ValueError):
        query.connect(root, view_name="x; DROP")
