"""download_iem tests: planning, URL, validation, stop-at-first-error, station matching. NO network (injected fetcher)."""

import json
import urllib.parse
from datetime import date

import pytest

from flight_delay.data import download_iem as di
from flight_delay.data import metar


def _good_body(station: str, rows: int = 3) -> bytes:
    lines = ["station,valid,tmpf"] + [f"{station},2025-07-01 0{i}:00,70" for i in range(rows)]
    return ("\n".join(lines) + "\n").encode()


class FakeFetcher:
    def __init__(self, fail_on_call: int | None = None, body_for_call: dict[int, bytes] | None = None):
        self.urls: list[str] = []
        self.fail_on_call = fail_on_call
        self.body_for_call = body_for_call or {}

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        call = len(self.urls)
        if call == self.fail_on_call:
            raise OSError("simulated network error")
        if call in self.body_for_call:
            return self.body_for_call[call]
        station = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["station"][0]
        return _good_body(station)


def _requests(stations=("ORD", "ATL"), start=date(2025, 7, 1), end=date(2025, 7, 31)):
    return di.plan_requests({s: s for s in stations}, start, end)


# ---------------------------------------------------------------- planning
def test_year_chunks_split_at_calendar_years():
    chunks = di.year_chunks(date(2023, 9, 1), date(2026, 8, 31))
    assert chunks == [
        (date(2023, 9, 1), date(2023, 12, 31)),
        (date(2024, 1, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 8, 31)),
    ]
    assert di.year_chunks(date(2025, 7, 1), date(2025, 7, 31)) == [(date(2025, 7, 1), date(2025, 7, 31))]
    with pytest.raises(ValueError):
        di.year_chunks(date(2025, 2, 1), date(2025, 1, 1))


def test_plan_for_the_full_range_and_the_station_year_limit():
    stations = {f"A{i:02d}": f"A{i:02d}" for i in range(30)}
    requests = di.plan_requests(stations, date(2023, 9, 1), date(2026, 8, 31))
    assert len(requests) == 30 * 4
    assert requests[0].filename == "A00_20230901_20231231.csv"
    volume = di.check_station_year_limit(requests)
    assert 89 < volume < 91  # about 30 stations x 3 years (computed from days, not hard-coded in the code)
    with pytest.raises(ValueError, match="station-years"):
        di.check_station_year_limit(requests, limit=50)


def test_request_url_has_the_expected_parameters():
    url = di.build_request_url("ORD", date(2025, 7, 1), date(2025, 7, 31))
    parts = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parts.query)
    assert url.startswith(di.BASE_URL + "?")
    assert query["station"] == ["ORD"]
    assert query["data"] == list(metar.IEM_VARIABLES)
    assert (query["year1"], query["month1"], query["day1"]) == (["2025"], ["7"], ["1"])
    assert (query["year2"], query["month2"], query["day2"]) == (["2025"], ["8"], ["1"])  # end + 1 day
    assert query["tz"] == ["Etc/UTC"] and query["format"] == ["onlycomma"] and query["missing"] == ["M"]
    assert query["report_type"] == ["3", "4"]
    # year boundary
    end_of_year = urllib.parse.parse_qs(
        urllib.parse.urlparse(di.build_request_url("ORD", date(2025, 1, 1), date(2025, 12, 31))).query
    )
    assert (end_of_year["year2"], end_of_year["month2"], end_of_year["day2"]) == (["2026"], ["1"], ["1"])


# ---------------------------------------------------------------- validation
def test_validate_csv_text():
    assert (
        di.validate_csv_text("#comment\nstation,valid,tmpf\nORD,2025-07-01 00:00,70\nORD,2025-07-01 01:00,71\n", "ORD")
        == 2
    )
    with pytest.raises(ValueError, match="Empty"):
        di.validate_csv_text("\n", "ORD")
    with pytest.raises(ValueError, match="header"):
        di.validate_csv_text("<html>Error</html>\n", "ORD")
    with pytest.raises(ValueError, match="No observations"):
        di.validate_csv_text("station,valid,tmpf\n", "ORD")
    with pytest.raises(ValueError, match="another station"):
        di.validate_csv_text("station,valid,tmpf\nATL,2025-07-01 00:00,70\n", "ORD")


# ---------------------------------------------------------------- run (injected fetcher)
def test_run_downloads_waits_between_real_requests_and_writes_summary(tmp_path):
    sleeps: list[float] = []
    fetcher = FakeFetcher()
    summary = di.run(
        _requests(),
        tmp_path / "out",
        fetch=fetcher,
        wait_sec=2.5,
        sleep=sleeps.append,
        summary_path=tmp_path / "out" / "s.json",
        log=lambda s: None,
    )
    assert [r["status"] for r in summary["requests"]] == ["downloaded", "downloaded"]
    assert sleeps == [2.5]  # none before the first request
    assert (tmp_path / "out" / "ATL_20250701_20250731.csv").is_file()
    assert summary["requests"][0]["rows"] == 3 and len(summary["requests"][0]["sha256"]) == 64
    assert not summary["has_error"] and summary["not_attempted"] == 0
    assert json.loads((tmp_path / "out" / "s.json").read_text(encoding="utf-8"))["requests"][0]["iata"] == "ATL"
    assert not list((tmp_path / "out").glob("*.part"))


def test_run_stops_at_the_first_error_without_retry(tmp_path):
    fetcher = FakeFetcher(fail_on_call=2)
    summary = di.run(
        _requests(("ATL", "DEN", "ORD")), tmp_path, fetch=fetcher, wait_sec=0, sleep=lambda s: None, log=lambda s: None
    )
    assert [r["status"] for r in summary["requests"]] == ["downloaded", "error"]
    assert "simulated network error" in summary["requests"][1]["error"]
    assert summary["has_error"] and summary["not_attempted"] == 1
    assert len(fetcher.urls) == 2  # the failed request was NOT retried, the third was not attempted
    assert not (tmp_path / "DEN_20250701_20250731.csv").exists()


def test_run_rejects_an_invalid_response_and_writes_no_file(tmp_path):
    fetcher = FakeFetcher(body_for_call={1: b"<html>Server error</html>"})
    summary = di.run(_requests(("ORD",)), tmp_path, fetch=fetcher, wait_sec=0, sleep=lambda s: None, log=lambda s: None)
    assert summary["requests"][0]["status"] == "error" and "header" in summary["requests"][0]["error"]
    assert not list(tmp_path.glob("*.csv"))


def test_run_skips_existing_files(tmp_path):
    requests = _requests(("ORD",))
    (tmp_path / requests[0].filename).write_text("station,valid\nORD,2025-07-01 00:00\n", encoding="utf-8")
    fetcher = FakeFetcher()
    summary = di.run(requests, tmp_path, fetch=fetcher, sleep=lambda s: None, log=lambda s: None)
    assert summary["requests"][0]["status"] == "skipped_exists" and fetcher.urls == []


# ---------------------------------------------------------------- station matching (offline)
def _station_files(tmp_path, with_atl=True):
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-87.9048, 41.9786]},
            "properties": {"sid": "ORD", "network": "IL_ASOS", "archive_begin": "1990-01-01T00:00:00Z"},
        }
    ]
    airports = [
        "ident,type,latitude_deg,longitude_deg,iata_code,scheduled_service",
        "KORD,large_airport,41.9786,-87.9048,ORD,yes",
    ]
    if with_atl:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-84.4281, 33.6367]},
                "properties": {"sid": "ATL", "network": "GA_ASOS", "archive_begin": "1990-01-01T00:00:00Z"},
            }
        )
    airports.append("KATL,large_airport,33.6367,-84.4281,ATL,yes")
    geojson = tmp_path / "stations.geojson"
    geojson.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    csv = tmp_path / "airports.csv"
    csv.write_text("\n".join(airports) + "\n", encoding="utf-8")
    return csv, geojson


def test_resolve_stations_matches_offline(tmp_path):
    csv, geojson = _station_files(tmp_path)
    assert di.resolve_stations(["ORD", "ATL"], csv, geojson, date(2023, 9, 1)) == {"ORD": "ORD", "ATL": "ATL"}


def test_resolve_stations_stops_if_a_target_is_not_matched(tmp_path):
    csv, geojson = _station_files(tmp_path, with_atl=False)
    with pytest.raises(ValueError, match="ATL"):
        di.resolve_stations(["ORD", "ATL"], csv, geojson, date(2023, 9, 1))


def test_resolve_stations_missing_files_are_errors(tmp_path):
    csv, geojson = _station_files(tmp_path)
    with pytest.raises(FileNotFoundError, match="IEM station list"):
        di.resolve_stations(["ORD"], csv, tmp_path / "missing.geojson", None)


def test_cli_dry_run_prints_the_plan_and_writes_nothing(tmp_path, capsys):
    csv, geojson = _station_files(tmp_path)
    targets = tmp_path / "targets.txt"
    targets.write_text("ORD\nATL\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    code = di.main(
        [
            "--start",
            "2025-07-01",
            "--end",
            "2025-07-31",
            "--targets-file",
            str(targets),
            "--ourairports",
            str(csv),
            "--stations-file",
            str(geojson),
            "--out-dir",
            str(out_dir),
            "--only",
            "ORD",
            "--dry-run",
        ]
    )
    printed = capsys.readouterr().out
    assert code == 0 and "1 requests" in printed and "ORD_20250701_20250731.csv" in printed
    assert not out_dir.exists()
