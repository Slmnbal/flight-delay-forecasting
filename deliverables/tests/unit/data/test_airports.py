"""airports tests: OurAirports loader and IATA -> IANA time zone map. Offline."""

import pytest

from flight_delay.data import airports

NY, LA = "America/New_York", "America/Los_Angeles"

OA_CSV = (
    "id,ident,type,name,latitude_deg,longitude_deg,iata_code,scheduled_service\n"
    "1,KJFK,large_airport,John F Kennedy,40.6398,-73.7789,JFK,yes\n"
    "2,KXXX,small_airport,Old record,40.0,-73.0,JFK,no\n"
    "3,KLAX,large_airport,Los Angeles,33.9425,-118.4081,LAX,yes\n"
    "4,KZZZ,small_airport,No IATA,35.0,-100.0,,no\n"
)


def test_load_ourairports_unique_and_deterministic(tmp_path):
    path = tmp_path / "airports.csv"
    path.write_text(OA_CSV, encoding="utf-8")
    df = airports.load_ourairports(path)
    assert sorted(df["iata"]) == ["JFK", "LAX"]
    assert df.set_index("iata").loc["JFK", "icao"] == "KJFK"  # large + scheduled wins
    assert airports.load_ourairports(path).equals(df)  # a second run gives the same result


def test_tz_map_manual_has_priority_and_missing_are_not_invented(tmp_path):
    path = tmp_path / "airports.csv"
    path.write_text(OA_CSV, encoding="utf-8")
    df = airports.load_ourairports(path)
    tz_map, missing = airports.build_tz_map(df, ["JFK", "ZZZ"], manual={"JFK": NY})
    assert tz_map == {"JFK": NY}
    assert missing == [{"iata": "ZZZ", "reason": "not in OurAirports"}]


def test_tz_map_invalid_iana_is_rejected(tmp_path):
    path = tmp_path / "airports.csv"
    path.write_text(OA_CSV, encoding="utf-8")
    df = airports.load_ourairports(path)
    tz_map, missing = airports.build_tz_map(df, ["JFK"], manual={"JFK": "Mars/Olympus"})
    assert tz_map == {} and "invalid IANA" in missing[0]["reason"]


def test_tz_map_with_timezonefinder(tmp_path):
    pytest.importorskip("timezonefinder")
    path = tmp_path / "airports.csv"
    path.write_text(OA_CSV, encoding="utf-8")
    tz_map, missing = airports.build_tz_map(airports.load_ourairports(path), ["JFK", "LAX"])
    assert tz_map == {"JFK": NY, "LAX": LA} and missing == []
