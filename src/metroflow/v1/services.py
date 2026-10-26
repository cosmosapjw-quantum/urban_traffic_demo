"""B01 fixed services on the sole T04 PacketNetwork, with separate person/cargo ledgers.

Scheduled bus runs are finite service records, not per-passenger trajectories.
A run waits until its whole vehicle mass has reached a stop; this is an explicit
step-boundary aggregate closure. Stop dwell occurs off-road at declared bays.
"""

from dataclasses import dataclass, replace, asdict
import hashlib
import json
import math
from .city import reject
from .transport import TransportModel
from ..ordered_network import Route


def nonnegative(*values):
    return all(math.isfinite(x) and x >= 0 for x in values)


@dataclass(frozen=True, slots=True)
class BusRun:
    id: str
    legs: tuple[tuple[str, ...], ...]
    departures_s: tuple[float, ...]
    capacity_persons: float
    dwell_s: float = 5.0
    allowed_links: frozenset[str] = frozenset()

    def __post_init__(self):
        if (
            not self.id
            or not self.legs
            or len(self.legs) != len(self.departures_s)
            or any(not leg for leg in self.legs)
            or not nonnegative(*self.departures_s, self.capacity_persons, self.dwell_s)
            or self.capacity_persons <= 0
            or any(a > b for a, b in zip(self.departures_s, self.departures_s[1:]))
        ):
            reject("invalid fixed bus schedule/capacity/dwell")


@dataclass(frozen=True, slots=True)
class PassengerCohort:
    id: str
    run_id: str
    origin_stop: int
    destination_stop: int
    available_s: float
    persons: float

    def __post_init__(self):
        if (
            not self.id
            or not self.run_id
            or not isinstance(self.origin_stop, int)
            or not isinstance(self.destination_stop, int)
            or not 0 <= self.origin_stop < self.destination_stop
            or not nonnegative(self.available_s, self.persons)
        ):
            reject("invalid passenger cohort; transfers unsupported", "UNSUPPORTED_REQUEST")


@dataclass(frozen=True, slots=True)
class FreightRun:
    id: str
    links: tuple[str, ...]
    departure_s: float
    vehicles: float
    cargo_kg: float
    gross_kg_per_vehicle: float
    max_gross_kg: float
    allowed_links: frozenset[str]

    def __post_init__(self):
        if (
            not self.id
            or not self.links
            or not nonnegative(
                self.departure_s,
                self.vehicles,
                self.cargo_kg,
                self.gross_kg_per_vehicle,
                self.max_gross_kg,
            )
            or self.vehicles <= 0
            or self.gross_kg_per_vehicle > self.max_gross_kg
            or self.cargo_kg > self.vehicles * self.gross_kg_per_vehicle
            or not set(self.links) <= self.allowed_links
        ):
            reject("freight weight, cargo or permitted link violation")


@dataclass(frozen=True, slots=True)
class CarRun:
    id: str
    links: tuple[str, ...]
    departure_s: float
    vehicles: float

    def __post_init__(self):
        if (
            not self.id
            or not self.links
            or not nonnegative(self.departure_s, self.vehicles)
            or self.vehicles <= 0
        ):
            reject("invalid aggregate car source")


@dataclass(frozen=True, slots=True)
class RunState:
    leg: int = 0
    phase: str = "STOP"
    ready_s: float = 0.0
    completed_leg_veh: float = 0.0
    delay_s: float = 0.0


@dataclass(frozen=True, slots=True)
class PassengerState:
    waiting: float
    onboard: float = 0.0
    arrived: float = 0.0
    wait_person_s: float = 0.0
    arrival_person_s: float = 0.0


@dataclass(frozen=True, slots=True)
class ServiceState:
    model_id: str
    road: object
    buses: tuple[RunState, ...]
    passengers: tuple[PassengerState, ...]
    freight_released: tuple[bool, ...]
    freight_completed: tuple[float, ...]
    cars_released: tuple[bool, ...] = ()


class ServiceModel:
    def __init__(
        self,
        contract,
        buses,
        passengers,
        freight,
        *,
        bus_class,
        freight_class,
        step_s=0.1,
        templates=(),
        entry_speeds=None,
        record_budget=100000,
        cars=(),
        car_class=None,
    ):
        self.buses, self.passengers, self.freight = tuple(buses), tuple(passengers), tuple(freight)
        self.cars = tuple(cars)
        if self.cars and car_class is None:
            reject("car physical class required")
        if len({c.id for c in self.cars}) != len(self.cars):
            reject("duplicate car source")
        self.step_s = step_s
        if (
            bus_class.name == freight_class.name
            or len({b.id for b in self.buses}) != len(self.buses)
            or len({p.id for p in self.passengers}) != len(self.passengers)
            or len({f.id for f in self.freight}) != len(self.freight)
        ):
            reject("distinct classes and unique service IDs required")
        runs = {b.id: b for b in self.buses}
        for p in self.passengers:
            if p.run_id not in runs or p.destination_stop > len(runs[p.run_id].legs):
                reject("unknown bus run/stop or unsupported transfer", "UNSUPPORTED_REQUEST")
        routes = []
        classes = {}
        groups = {g.id: g for g in contract.groups}
        for b in self.buses:
            if not set(e for leg in b.legs for e in leg) <= b.allowed_links:
                reject("bus permitted link violation")
            for a, c in zip(b.legs, b.legs[1:]):
                if (
                    groups[a[-1]].head != groups[c[0]].tail
                    or (a[-1], c[0]) not in contract.allowed_turns
                ):
                    reject("bus stop must preserve legal adjacent turn")
            for j, leg in enumerate(b.legs):
                tag = f"bus:{b.id}:{j}"
                routes.append(Route(tag, leg))
                classes[tag] = bus_class
        for f in self.freight:
            tag = "freight:" + f.id
            routes.append(Route(tag, f.links))
            classes[tag] = freight_class
        for c in self.cars:
            tag = "car:" + c.id
            routes.append(Route(tag, c.links))
            classes[tag] = car_class
        transport = TransportModel(
            contract,
            routes,
            classes,
            (),
            max_step_s=step_s,
            templates=templates,
            entry_speeds=entry_speeds,
            record_budget=record_budget,
        )
        self.network = transport.network
        self.identity = hashlib.sha256(
            json.dumps(
                [
                    transport.identity,
                    [asdict(x) for x in self.buses],
                    [asdict(x) for x in self.passengers],
                    [asdict(x) for x in self.freight],
                    [asdict(x) for x in self.cars],
                ],
                sort_keys=True,
                default=lambda x: sorted(x),
            ).encode()
        ).hexdigest()

    def initial(self):
        return ServiceState(
            self.identity,
            self.network.initial(),
            tuple(RunState() for _ in self.buses),
            tuple(PassengerState(p.persons) for p in self.passengers),
            tuple(False for _ in self.freight),
            tuple(0.0 for _ in self.freight),
            tuple(False for _ in self.cars),
        )

    def check(self, s):
        if (
            s.model_id != self.identity
            or len(s.buses) != len(self.buses)
            or len(s.passengers) != len(self.passengers)
        ):
            reject("service checkpoint identity mismatch")
        self.network.check(s.road)
        for p, v in zip(self.passengers, s.passengers):
            if not nonnegative(v.waiting, v.onboard, v.arrived) or not math.isclose(
                v.waiting + v.onboard + v.arrived, p.persons, abs_tol=1e-8
            ):
                reject("person conservation failure", "IMPLEMENTATION_ERROR")
        for b in self.buses:
            load = math.fsum(
                v.onboard for p, v in zip(self.passengers, s.passengers) if p.run_id == b.id
            )
            if load > b.capacity_persons + 1e-8:
                reject("overcapacity boarding", "IMPLEMENTATION_ERROR")

    def step(self, s):
        try:
            return self._step(s)
        except Exception as exc:
            exc.checkpoint = s
            raise

    def _step(self, s):
        self.check(s)
        t = s.road.time_s
        end = t + self.step_s
        buses = list(s.buses)
        people = list(s.passengers)
        released = list(s.freight_released)
        cars_released = list(s.cars_released)
        completed = list(s.freight_completed)
        offers = []
        for i, (b, v) in enumerate(zip(self.buses, buses)):
            if v.phase != "STOP" or t + 1e-10 < max(v.ready_s, b.departures_s[v.leg]):
                continue
            load = math.fsum(x.onboard for p, x in zip(self.passengers, people) if p.run_id == b.id)
            # Same-stop simultaneous cohorts share the residual capacity proportionally.
            eligible = [
                k
                for k, (p, x) in enumerate(zip(self.passengers, people))
                if p.run_id == b.id
                and p.origin_stop == v.leg
                and p.available_s <= t + 1e-10
                and x.waiting > 0
            ]
            total = math.fsum(people[k].waiting for k in eligible)
            fraction = min(1.0, max(0.0, b.capacity_persons - load) / total) if total else 0.0
            for k in eligible:
                x = people[k]
                amount = x.waiting * fraction
                people[k] = replace(
                    x,
                    waiting=x.waiting - amount,
                    onboard=x.onboard + amount,
                    wait_person_s=x.wait_person_s + amount * (t - self.passengers[k].available_s),
                )
            offers.append((f"bus:{b.id}:{v.leg}", 1.0, t))
            buses[i] = replace(
                v, phase="ROAD", delay_s=v.delay_s + max(0.0, t - b.departures_s[v.leg])
            )
        for i, f in enumerate(self.freight):
            if not released[i] and t + 1e-10 >= f.departure_s:
                offers.append(("freight:" + f.id, f.vehicles, f.vehicles * t))
                released[i] = True
        for i, c in enumerate(self.cars):
            if not cars_released[i] and t + 1e-10 >= c.departure_s:
                offers.append(("car:" + c.id, c.vehicles, c.vehicles * t))
                cars_released[i] = True
        try:
            road, events = self.network.advance_interval(s.road, self.step_s, offers)
        except Exception as exc:
            exc.checkpoint = s
            raise
        for i, (b, v) in enumerate(zip(self.buses, buses)):
            if v.phase != "ROAD":
                continue
            mass = v.completed_leg_veh + math.fsum(
                e.mass for e in events if e.destination is None and e.tag == f"bus:{b.id}:{v.leg}"
            )
            if mass < 1 - 1e-9:
                buses[i] = replace(v, completed_leg_veh=mass)
                continue
            stop = v.leg + 1
            for k, (p, x) in enumerate(zip(self.passengers, people)):
                if p.run_id == b.id and p.destination_stop == stop:
                    people[k] = replace(
                        x,
                        onboard=0.0,
                        arrived=x.arrived + x.onboard,
                        arrival_person_s=x.arrival_person_s + x.onboard * end,
                    )
            buses[i] = replace(
                v,
                leg=stop,
                phase="DONE" if stop == len(b.legs) else "STOP",
                ready_s=end + b.dwell_s,
                completed_leg_veh=0.0,
            )
        for i, f in enumerate(self.freight):
            completed[i] += math.fsum(
                e.mass for e in events if e.destination is None and e.tag == "freight:" + f.id
            )
        result = ServiceState(
            self.identity,
            road,
            tuple(buses),
            tuple(people),
            tuple(released),
            tuple(completed),
            tuple(cars_released),
        )
        self.check(result)
        return result

    def advance(self, s, until_s):
        if (
            not nonnegative(until_s)
            or until_s < s.road.time_s
            or not math.isclose(
                (until_s - s.road.time_s) / self.step_s,
                round((until_s - s.road.time_s) / self.step_s),
                abs_tol=1e-7,
            )
        ):
            reject("service horizon must align with fixed step")
        for _ in range(round((until_s - s.road.time_s) / self.step_s)):
            s = self.step(s)
        return s

    def report(self, s):
        self.check(s)
        bus_class = (
            self.network.vehicle_classes["bus:" + self.buses[0].id + ":0"].name
            if self.buses
            else None
        )
        bus_road = math.fsum(
            c.released - c.completed for c in s.road.class_ledger if c.name == bus_class
        )
        bus_stops = math.fsum(1 if v.phase != "ROAD" else v.completed_leg_veh for v in s.buses)
        if not math.isclose(bus_road + bus_stops, len(self.buses), abs_tol=1e-8):
            reject("bus fleet stock failure", "IMPLEMENTATION_ERROR")
        return dict(
            time_s=s.road.time_s,
            scheduled_bus_vehicles=len(self.buses),
            bus_road_vehicles=bus_road,
            bus_stop_or_finished_vehicles=bus_stops,
            completed_bus_vehicles=sum(v.phase == "DONE" for v in s.buses),
            waiting_persons=math.fsum(p.waiting for p in s.passengers),
            onboard_persons=math.fsum(p.onboard for p in s.passengers),
            arrived_persons=math.fsum(p.arrived for p in s.passengers),
            wait_person_s=math.fsum(
                p.wait_person_s + p.waiting * max(0.0, s.road.time_s - c.available_s)
                for c, p in zip(self.passengers, s.passengers)
            ),
            freight_completed_vehicles=math.fsum(s.freight_completed),
            cargo_delivered_kg=math.fsum(
                f.cargo_kg * v / f.vehicles for f, v in zip(self.freight, s.freight_completed)
            ),
            cargo_unfinished_kg=math.fsum(
                f.cargo_kg * (1 - v / f.vehicles) for f, v in zip(self.freight, s.freight_completed)
            ),
            road_released_veh=s.road.released,
            road_completed_veh=s.road.completed,
        )
