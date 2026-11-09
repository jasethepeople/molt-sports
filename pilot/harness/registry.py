"""Registry of pilot families. In production this is a contract-frozen JSON."""
from harness.protocol import TestFamily
from families.officiating_crew import CrewTendency
from families.officiating_series import SeriesExtension
from families.temporal_clock import ClockAnomaly

REGISTRY: dict[str, type[TestFamily]] = {
    "OFFICIATING.CREW_TENDENCY": CrewTendency,
    "OFFICIATING.SERIES_EXTENSION": SeriesExtension,
    "TEMPORAL.CLOCK_ANOMALY": ClockAnomaly,
}
