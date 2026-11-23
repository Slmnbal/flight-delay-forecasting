"""feature_contract tests: forbidden field rejection and knowledge-time rules. Offline."""

import pytest
from pydantic import ValidationError

from flight_delay.data import feature_contract as fc
from flight_delay.data.feature_contract import FeatureContract, FeatureSpec, LeakageError

# All forbidden fields from research report section 6.3
REQUIRED_FORBIDDEN = [
    "DepTime",
    "DepDelay",
    "DepDel15",
    "DepDelayMinutes",
    "DepartureDelayGroups",
    "TaxiOut",
    "WheelsOff",
    "WheelsOn",
    "TaxiIn",
    "ArrTime",
    "ActualElapsedTime",
    "AirTime",
    "CarrierDelay",
    "WeatherDelay",
    "NASDelay",
    "SecurityDelay",
    "LateAircraftDelay",
    "CancellationCode",
    "Cancelled",
    "Diverted",
    "Div1Airport",
    "Div2TailNum",
    "DivArrDelay",
    "DivReachedDest",
    "DivAirportLandings",
    "ArrDelay",
    "ArrDelayMinutes",
    "ArrDel15",
    "ArrivalDelayGroups",
]


@pytest.mark.parametrize("name", REQUIRED_FORBIDDEN)
def test_forbidden_field_names(name):
    assert fc.forbidden_reason(name) is not None
    assert fc.forbidden_reason(name.lower()) is not None  # case-insensitive
    assert fc.forbidden_reason(f"  {name.upper()} ") is not None


@pytest.mark.parametrize(
    "name",
    [
        "CRSDepTime",
        "CRSArrTime",
        "CRSElapsedTime",
        "Distance",
        "Origin",
        "Dest",
        "DayOfWeek",
        "Month",
        "Reporting_Airline",
    ],
)
def test_schedule_fields_are_not_forbidden(name):
    assert fc.forbidden_reason(name) is None


def test_validate_columns_rejects_forbidden():
    with pytest.raises(LeakageError) as e:
        fc.validate_columns(["CRSDepTime", "Distance", "TaxiOut", "Div1Airport"])
    assert "TaxiOut" in str(e.value) and "Div1Airport" in str(e.value)
    fc.validate_columns(["CRSDepTime", "Distance", "Month"])  # a clean set passes


def test_contract_schedule_features_pass():
    contract = FeatureContract(horizon_hours=2, features=fc.schedule_features())
    assert "CRSDepTime" in contract.feature_names()
    fc.validate_columns(contract.feature_names())  # no forbidden names in the default set


@pytest.mark.parametrize("name", REQUIRED_FORBIDDEN)
def test_contract_forbidden_name_is_rejected(name):
    with pytest.raises(ValidationError) as e:
        FeatureContract(
            horizon_hours=2,
            features=[FeatureSpec(name=name, source="bts_ontime", knowledge_time="schedule", source_columns=(name,))],
        )
    assert "forbidden" in str(e.value)


def test_contract_feature_derived_from_forbidden_column_is_rejected():
    # even if declared 'schedule', a feature derived from DepDelay is rejected
    with pytest.raises(ValidationError) as e:
        FeatureContract(
            horizon_hours=2,
            features=[
                FeatureSpec(
                    name="delay_mean",
                    source="derived",
                    knowledge_time="schedule",
                    source_columns=("DepDelay",),
                )
            ],
        )
    assert "DepDelay" in str(e.value)


def test_previous_leg_delay_allowed_only_if_ready_before_horizon():
    def build(minutes):
        return FeatureContract(
            horizon_hours=2,
            features=[
                FeatureSpec(
                    name="previous_leg_arr_delay",
                    source="derived",
                    knowledge_time="past_realized",
                    source_columns=("ArrDelay",),
                    ready_minutes_before=minutes,
                )
            ],
        )

    build(120)  # T = 2 hours = 120 min: allowed exactly on the boundary
    build(300)
    with pytest.raises(ValidationError):
        build(60)  # ready 60 min before departure: too late for T = 2 hours
    with pytest.raises(ValidationError):
        build(None)


def test_observed_weather_must_be_before_horizon():
    valid = FeatureSpec(
        name="metar_temp_T", source="iem_asos", knowledge_time="observation_before_T", ready_minutes_before=150
    )
    FeatureContract(horizon_hours=2, features=[valid])
    late = FeatureSpec(
        name="metar_temp_late", source="iem_asos", knowledge_time="observation_before_T", ready_minutes_before=30
    )
    with pytest.raises(ValidationError):
        FeatureContract(horizon_hours=2, features=[late])


def test_oracle_weather_only_in_oracle_experiment():
    spec = FeatureSpec(name="metar_temp_observed", source="iem_asos", knowledge_time="oracle")
    with pytest.raises(ValidationError) as e:
        FeatureContract(horizon_hours=2, features=[spec])
    assert "oracle_experiment" in str(e.value)
    FeatureContract(horizon_hours=2, oracle_experiment=True, features=[spec])  # labelled experiment: allowed


def test_oracle_does_not_launder_bts_leakage():
    # even with oracle_experiment=True a BTS forbidden field cannot pass
    with pytest.raises(ValidationError):
        FeatureContract(
            horizon_hours=2,
            oracle_experiment=True,
            features=[FeatureSpec(name="TaxiOut", source="iem_asos", knowledge_time="oracle")],
        )
    with pytest.raises(ValidationError):
        FeatureContract(
            horizon_hours=2,
            oracle_experiment=True,
            features=[FeatureSpec(name="x", source="bts_ontime", knowledge_time="oracle")],
        )


def test_duplicate_name_and_unknown_field_are_rejected():
    spec = FeatureSpec(name="Distance", source="bts_ontime", knowledge_time="schedule")
    with pytest.raises(ValidationError):
        FeatureContract(horizon_hours=2, features=[spec, spec])
    with pytest.raises(ValidationError):
        FeatureSpec(name="Distance", source="bts_ontime", knowledge_time="schedule", extra_field=1)


def test_horizon_must_be_positive():
    with pytest.raises(ValidationError):
        FeatureContract(horizon_hours=0, features=[])
