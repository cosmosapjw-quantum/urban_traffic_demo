"""V1 finite-response road owner with a Python serialization boundary.

Only construction, validation and dataclass snapshots use Python. The complete
road tick (motion, junction filling, queues, marks and ledgers) executes in Rust.
The reference object supplies the immutable contract and remains an oracle.
"""
from ..packet_network import State, Cell, Packet, Pending, Part, ClassLedger, Event
from ..active_suffix.common import BudgetExceeded
from .transport import FiniteResponseMotion


class NativeRoadNetwork:
    def __init__(self, reference):
        from _metroflow_rust import V1Road

        if not reference.physical_storage or type(reference.motion) is not FiniteResponseMotion:
            raise ValueError("native V1 road requires the declared finite-response physical law")
        self.reference = reference
        self.tags = tuple(sorted(reference.routes))
        self.tag_index = {tag: i for i, tag in enumerate(self.tags)}
        self.class_index = {name: i for i, name in enumerate(reference.class_names)}
        templates = {c.vehicle.name: c for c in reference.motion.templates}
        speeds = dict(reference.motion.entry_speeds)
        classes = []
        for name in reference.class_names:
            c = templates[name]
            v = c.vehicle
            classes.append([v.preferred_mps, v.response_s, v.accel_mps2,
                            v.brake_mps2, v.min_gap_m, v.headway_s, v.length_m,
                            c.latent, c.restart_s_inv, c.hazard_s_inv,
                            c.gap_scale_m, speeds[name], v.length_m + reference.standing_gap_m])
        self.native = V1Road(
            reference._unprojected_identity, reference.dt,
            [[g.physics.length_m, g.physics.speed_mps, g.physics.entry_rate,
              g.physics.exit_rate, reference.space_capacities_m[g.id], g.priority]
             for g in reference.groups],
            [(g.signal.cycle_s, g.signal.green_s, g.signal.offset_s) if g.signal else None
             for g in reference.groups],
            [([reference.index[g] for g in reference.routes[tag]],
              self.class_index[reference.vehicle_classes[tag].name]) for tag in self.tags],
            classes,
            [list(inc) for _, inc in sorted(reference.incoming.items())],
            [(reference.index[g], a, b, factor) for g, a, b, factor in reference.windows],
            reference.record_budget, reference.event_budget, reference.preserve_entry_intervals,
            reference.entry_projection_width_s,
        )
        self._last = None

    def __getattr__(self, name):
        return getattr(self.reference, name)

    def projection_diagnostics(self):
        """Latest valid native proposal, not a checkpointed physical bound."""
        return self.native.projection_diagnostics()

    def _encode(self, state):
        def part(p):
            path = self.routes[p.tag]
            offset = len(path) - len(p.remaining)
            if offset < 0 or path[offset:] != p.remaining:
                raise ValueError("native checkpoint contains a non-route suffix")
            return (self.tag_index[p.tag], offset, p.mass, p.birth_moment,
                    p.entry_start_s, p.entry_end_s)

        return (
            state.model_id, state.time_s,
            [([c.progress_m, c.activity, c.admitted, c.completed, c.entry_moment,
               c.exit_moment, c.vehicle_metres, c.speed_mps],
              [(p.target_m, [part(x) for x in p.parts]) for p in c.packets],
              [(self.class_index[k], v) for k, v in c.latent]) for c in state.cells],
            [[(p.born_s, [part(x) for x in p.parts]) for p in queue] for queue in state.pending],
            [state.released, state.completed, state.birth_moment, state.exit_moment,
             state.source_wait_seconds, state.transfer_hold_seconds, state.pre_entry_seconds],
            [[c.released, c.completed, c.source_wait_seconds, c.exit_queue_seconds,
              c.transfer_hold_seconds] for c in state.class_ledger],
        )

    def snapshot(self):
        binding, t, cells, pending, totals, ledger = self.native.snapshot()
        if binding != self.identity:
            raise ValueError("native snapshot model binding differs")

        def part(row):
            tag, offset, mass, birth, a, b = row
            name = self.tags[tag]
            return Part(name, self.routes[name][offset:], mass, birth, a, b)

        out = []
        for v, packets, latent in cells:
            progress, activity, admitted, completed, entry, exit_, metres, speed = v
            out.append(Cell(progress, activity,
                            tuple(Packet(target, tuple(part(p) for p in ps)) for target, ps in packets),
                            admitted, completed, entry, exit_, metres, speed,
                            tuple((self.class_names[k], value) for k, value in latent)))
        state = State(self.identity, t, tuple(out),
                      tuple(tuple(Pending(born, tuple(part(p) for p in ps))
                                  for born, ps in queue) for queue in pending),
                      *totals,
                      tuple(ClassLedger(name, *values) for name, values in zip(self.class_names, ledger)))
        self._last = state
        return state

    def restore(self, state):
        self.reference.check(state)
        self.native.restore(self._encode(state))
        self._last = state

    def initial(self, start_s=0.0):
        self.native.reset(start_s)
        return self.snapshot()

    def check(self, state):
        # Independent reference validation at the public snapshot boundary.
        return self.reference.check(state)

    def _offers(self, offers):
        result = []
        for offer in offers:
            if len(offer) not in (3, 5):
                raise ValueError("source offer needs mass/birth and optional interval")
            tag, mass, birth = offer[:3]
            if tag not in self.tag_index:
                raise ValueError("unknown native source tag")
            a, b = offer[3:] if len(offer) == 5 else (None, None)
            result.append((self.tag_index[tag], mass, birth, a, b))
        return result

    def _events(self, rows):
        return tuple(Event(self.tags[tag], self.groups[source].id,
                           self.groups[dest].id if dest is not None else None,
                           mass, start, end, birth)
                     for tag, source, dest, mass, start, end, birth in rows)

    def advance_interval(self, state, dt_s, offers=()):
        if state is not self._last:
            self.restore(state)
        try:
            events = self.native.step(dt_s, self._offers(offers))
        except MemoryError as cause:
            exc = BudgetExceeded(str(cause))
            exc.checkpoint = state
            raise exc from cause
        except ArithmeticError as exc:
            exc.checkpoint = state
            raise
        out = self.snapshot()
        return out, self._events(events)

    def step_measures(self, state, offers=()):
        return self.advance_interval(state, self.dt, offers)

    def step(self, state, offers=()):
        return self.step_measures(state, ((tag, mass, mass * state.time_s) for tag, mass in offers))

    def advance_batch(self, state, intervals):
        """Execute predeclared (dt, offers) intervals without Python tick callbacks.

        Each completed interval is a valid checkpoint. Failure exposes the last
        successful native state, matching the ordinary per-interval contract.
        This API is for explicit road-boundary offers, not future service truth.
        """
        if state is not self._last:
            self.restore(state)
        encoded = [(dt, self._offers(offers)) for dt, offers in intervals]
        try:
            events = self.native.advance_batch(encoded)
        except (MemoryError, ArithmeticError, ValueError) as cause:
            checkpoint = self.snapshot()
            exc = BudgetExceeded(str(cause)) if isinstance(cause, MemoryError) else cause
            exc.checkpoint = checkpoint
            if exc is cause:
                raise
            raise exc from cause
        return self.snapshot(), tuple(self._events(rows) for rows in events)
