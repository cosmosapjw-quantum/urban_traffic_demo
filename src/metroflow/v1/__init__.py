"""Lazy compatibility facade. Native CLI never imports Python physics.
Historical exports remain available for explicit reference use.
"""
from importlib import import_module

_EXPORTS = {
    'AccessLaw': ('.access', 'AccessLaw'),
    'DelayAtom': ('.access', 'DelayAtom'),
    'compile_access': ('.access', 'compile_access'),
    'DelayLaw': ('.journey', 'DelayLaw'),
    'JourneyBoundary': ('.journey', 'JourneyBoundary'),
    'JourneyModel': ('.journey', 'JourneyModel'),
    'JourneyState': ('.journey', 'JourneyState'),
    'PacketNetwork': ('..packet_network', 'PacketNetwork'),
    'CitySnapshot': ('.city', 'CitySnapshot'),
    'CityContractError': ('.city', 'CityContractError'),
    'PortalRef': ('.city', 'PortalRef'),
    'compile_city': ('.city', 'compile_city'),
    'load_city': ('.city', 'load_city'),
    'ActivityMeasure': ('.activity', 'ActivityMeasure'),
    'ActivityPatch': ('.activity', 'ActivityPatch'),
    'compile_activity': ('.activity', 'compile_activity'),
    'intrazonal_law': ('.activity', 'intrazonal_law'),
    'activity_access': ('.access', 'activity_access'),
    'EntryPortal': ('.development', 'EntryPortal'),
    'compile_entry': ('.development', 'compile_entry'),
    'select_entries': ('.development', 'select_entries'),
    'Amounts': ('.demand', 'Amounts'),
    'ModeShare': ('.demand', 'ModeShare'),
    'Cohort': ('.demand', 'Cohort'),
    'TripLeg': ('.demand', 'TripLeg'),
    'TripSchedule': ('.demand', 'TripSchedule'),
    'DemandLedger': ('.demand', 'DemandLedger'),
    'compile_daily_demand': ('.demand', 'compile_daily_demand'),
    'initial_ledger': ('.demand', 'initial_ledger'),
    'advance_requests': ('.demand', 'advance_requests'),
    'release_trip': ('.demand', 'release_trip'),
    'complete_trip': ('.demand', 'complete_trip'),
    'demand_report': ('.demand', 'demand_report'),
    'DepartureWindow': ('.schedules', 'DepartureWindow'),
    'DepartureProfile': ('.schedules', 'DepartureProfile'),
    'DepartureBatch': ('.demand', 'DepartureBatch'),
    'iter_departures': ('.demand', 'iter_departures'),
    'VehicleClass': ('.kinetics', 'VehicleClass'),
    'ClassMass': ('.kinetics', 'ClassMass'),
    'BulkState': ('.kinetics', 'BulkState'),
    'KineticEnvironment': ('.kinetics', 'KineticEnvironment'),
    'BulkStep': ('.kinetics', 'BulkStep'),
    'PassagePrediction': ('.kinetics', 'PassagePrediction'),
    'compile_bulk': ('.kinetics', 'compile_bulk'),
    'coefficients': ('.kinetics', 'coefficients'),
    'advance_bulk': ('.kinetics', 'advance_bulk'),
    'predict_passage': ('.kinetics', 'predict_passage'),
    'pair_compatibility': ('.kinetics', 'pair_compatibility'),
    'latent_reference': ('.kinetics', 'latent_reference'),
    'LanePartition': ('.lanegroups', 'LanePartition'),
    'LaneGroupContract': ('.lanegroups', 'LaneGroupContract'),
    'compile_lanegroups': ('.lanegroups', 'compile_lanegroups'),
    'packet_model': ('.lanegroups', 'packet_model'),
    'lane_bulk_inputs': ('.lanegroups', 'lane_bulk_inputs'),
    'allocate_node': ('.nodes', 'allocate_node'),
    'validate_signal_conflicts': ('.nodes', 'validate_signal_conflicts'),
    'BoundaryFlux': ('.transport', 'BoundaryFlux'),
    'TransportState': ('.transport', 'TransportState'),
    'TransportModel': ('.transport', 'TransportModel'),
    'CostKey': ('.observations', 'CostKey'),
    'CostObservation': ('.observations', 'CostObservation'),
    'completed_route_observations': ('.observations', 'completed_route_observations'),
    'conditional_eta_error': ('.observations', 'conditional_eta_error'),
    'PriorCost': ('.information', 'PriorCost'),
    'Channel': ('.information', 'Channel'),
    'Report': ('.information', 'Report'),
    'InformationState': ('.information', 'InformationState'),
    'DeliveredCost': ('.information', 'DeliveredCost'),
    'DecisionObservation': ('.information', 'DecisionObservation'),
    'InformationModel': ('.information', 'InformationModel'),
    'RoutingLink': ('.routing', 'RoutingLink'),
    'Preference': ('.routing', 'Preference'),
    'DecisionBoundary': ('.routing', 'DecisionBoundary'),
    'RouteCommitment': ('.routing', 'RouteCommitment'),
    'RouteGeometry': ('.routing', 'RouteGeometry'),
    'RouteAlternative': ('.routing', 'RouteAlternative'),
    'RoutingState': ('.routing', 'RoutingState'),
    'RoutingDecision': ('.routing', 'RoutingDecision'),
    'RoutingModel': ('.routing', 'RoutingModel'),
    'path_size_probabilities': ('.routing', 'path_size_probabilities'),
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module, __name__), attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
