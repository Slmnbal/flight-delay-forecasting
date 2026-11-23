"""iem_matching tests (offline, fake station list)."""

from datetime import date

import pytest

from flight_delay.data import iem_matching as im
from flight_delay.data.airports import load_ourairports

OA = (
    "id,ident,type,latitude_deg,longitude_deg,iata_code,scheduled_service\n"
    "1,KORD,large_airport,41.9786,-87.9048,ORD,yes\n"
    "2,KATL,large_airport,33.6367,-84.4281,ATL,yes\n"
    "3,KDEN,large_airport,39.8617,-104.6732,DEN,yes\n"
    "4,KSEA,large_airport,47.4490,-122.3093,SEA,yes\n"
    "5,PANC,large_airport,61.1744,-149.9964,ANC,yes\n"
)
IEM = (
    "stid,station_name,lat,lon,archive_begin\n"
    "ORD,CHICAGO O'HARE,41.995,-87.934,1973-01-01\n"
    "KATL,ATLANTA,33.6301,-84.4418,1948-01-01\n"
    "DEN,DENVER,39.8466,-104.6560,2010-05-01\n"
    "SEA,WRONG LOCATION,35.0,-100.0,1948-01-01\n"
    "ANC,ANCHORAGE,61.1689,-150.0278,2030-01-01\n"
)


def _setup(tmp_path):
    (tmp_path / "oa.csv").write_text(OA, encoding="utf-8")
    (tmp_path / "iem.csv").write_text(IEM, encoding="utf-8")
    return load_ourairports(tmp_path / "oa.csv"), im.read_station_list(tmp_path / "iem.csv")


def test_match_statuses(tmp_path):
    airports, stations = _setup(tmp_path)
    results = {
        m.iata: m
        for m in im.match_stations(
            ["ORD", "ATL", "DEN", "SEA", "ANC", "LAX"], airports, stations, study_start=date(2024, 1, 1)
        )
    }
    assert results["ORD"].status == "matched" and results["ORD"].rule == "iata"
    assert results["ATL"].status == "matched" and results["ATL"].rule == "K+iata"
    assert results["DEN"].status == "matched"
    assert results["SEA"].status == "location_mismatch"
    assert results["ANC"].status == "archive_insufficient"
    assert results["LAX"].status == "not_found"  # not in OurAirports -> never silently skipped


def test_every_target_gets_a_result(tmp_path):
    airports, stations = _setup(tmp_path)
    assert len(im.match_stations(["ORD", "ZZZ", "ATL"], airports, stations)) == 3


def test_unrecognised_station_columns_raise(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(ValueError):
        im.read_station_list(path)


def test_haversine_known_distance():
    # ORD-ATL is roughly 975 km (rough; not a tight bound)
    distance = im.haversine_km(41.9786, -87.9048, 33.6367, -84.4281)
    assert 900 < distance < 1050


def test_report_markdown_contains_checklist(tmp_path):
    airports, stations = _setup(tmp_path)
    markdown = im.report_markdown(im.match_stations(["ORD"], airports, stations))
    assert "IEM matching checklist" in markdown and "| ORD |" in markdown
