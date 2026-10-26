"""Public V1 facade. The scientific path uses only the Python standard library."""

from .access import AccessLaw, DelayAtom, compile_access
from .journey import DelayLaw, JourneyBoundary, JourneyModel, JourneyState
from ..packet_network import PacketNetwork
from .city import CitySnapshot, CityContractError, PortalRef, compile_city, load_city
from .activity import ActivityMeasure, ActivityPatch, compile_activity, intrazonal_law
from .access import activity_access
from .development import EntryPortal, compile_entry, select_entries

from .demand import (
    Amounts,
    ModeShare,
    Cohort,
    TripLeg,
    TripSchedule,
    DemandLedger,
    compile_daily_demand,
    initial_ledger,
    advance_requests,
    release_trip,
    complete_trip,
    demand_report,
    DepartureBatch,
    iter_departures,
)
from .schedules import DepartureWindow, DepartureProfile


__all__ = [
    "AccessLaw",
    "DelayAtom",
    "compile_access",
    "DelayLaw",
    "JourneyBoundary",
    "JourneyModel",
    "JourneyState",
    "PacketNetwork",
]


__all__ += ["CitySnapshot", "CityContractError", "PortalRef", "compile_city", "load_city"]


__all__ += [
    "ActivityMeasure",
    "ActivityPatch",
    "compile_activity",
    "intrazonal_law",
    "activity_access",
    "EntryPortal",
    "compile_entry",
    "select_entries",
]

__all__ += [
    "Amounts",
    "ModeShare",
    "Cohort",
    "TripLeg",
    "TripSchedule",
    "DemandLedger",
    "compile_daily_demand",
    "initial_ledger",
    "advance_requests",
    "release_trip",
    "complete_trip",
    "demand_report",
    "DepartureWindow",
    "DepartureProfile",
]

__all__ += ["DepartureBatch", "iter_departures"]
