"""Data layer: BTS On-Time download, UTC conversion, monthly Parquet layer, quality checks, queries.

Modules:
    csv_io              -- read the BTS CSV / zip.
    feature_contract    -- leakage guard: forbidden fields and the "T hours before departure" contract.
    time_conversion     -- local hhmm -> UTC (scalar and vectorised), DST policy.
    airports            -- OurAirports loader and IATA -> IANA time zone map.
    utc_check           -- UTC quality check on real data (CLI).
    size_measurement    -- one-month size measurement (CLI).
    iem_matching        -- IEM ASOS station <-> IATA matching check (CLI).
    download_ontime     -- single-month BTS download (network; also used by download_range).
    download_range      -- multi-month download and processing driver (CLI).
    download_iem        -- IEM ASOS/METAR download for the 30 target airports (network; CLI).
    inputs              -- ``require_file``: missing input files are errors, never silently ignored.
    tables              -- column groups of the layer tables, scheduled density, surrogate key, atomic writes.
    layer               -- month -> partitioned Parquet tables: flights / flight_labels / flight_keys / density (CLI).
    metar               -- downloaded IEM CSV files -> cleaned ``metar`` table (CLI).
    weather_join        -- leak-free T-before-departure weather join + labelled oracle variant (CLI).
    quality             -- layer data quality checks (CLI).
    query               -- DuckDB views over the layer (CLI).
"""
