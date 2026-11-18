"""Optional KCMB: finite, realizability-preserving kinetic/conservative corridor.

The authoritative MetroFlow V1 packet engine is unchanged.  This *different*
physical model has no strict per-vehicle FIFO, lane change or junction solver.
Its six stored fields per class/cell are vehicle-equivalent moments (veh):
    (m0,m1,j0,j1,z0,z1), j=E[(v/U)*1_sigma], z=E[(v/U)^2*1_sigma].
Exact local micro Markov generator -> matrix exponential; conservative
per-class finite-volume cell transfers. Units: metres, seconds, vehicles.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from typing import Sequence

_FIELDS = 6
_VERSION = "kcmb_6moment_corridor_v1"
_CEILING = 2_000_000


def _finite(x: float, name: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError(f"{name} must be finite numeric")
    return float(x)


@dataclass(frozen=True, slots=True)
class KCMBClass:
    name: str
    vmax_mps: float
    footprint_m: float
    alpha_per_s: float
    nu_per_s: float
    tau_s: float
    source_p: float = 1.0
    source_speed_fraction: float = 0.0

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("named physical class required")
        for key in ("vmax_mps", "footprint_m", "alpha_per_s", "nu_per_s",
                    "tau_s", "source_p", "source_speed_fraction"):
            v = _finite(getattr(self, key), key)
            if (key in ("vmax_mps", "footprint_m", "tau_s") and v <= 0 or
                key in ("alpha_per_s", "nu_per_s") and v < 0 or
                key in ("source_p", "source_speed_fraction") and not 0 <= v <= 1):
                raise ValueError(f"invalid {key}")
            object.__setattr__(self, key, v)


@dataclass(frozen=True, slots=True)
class KCMBConfig:
    cells: int
    cell_length_m: float
    lanes: int
    dt_s: float
    capacity_veh_per_s: float
    backward_wave_mps: float
    classes: tuple[KCMBClass, ...]

    def __post_init__(self):
        if (isinstance(self.cells, bool) or not isinstance(self.cells, int)
            or self.cells < 1 or isinstance(self.lanes, bool)
            or not isinstance(self.lanes, int) or self.lanes < 1):
            raise ValueError("positive integer cells and lanes required")
        if not isinstance(self.classes, tuple) or not 1 <= len(self.classes) <= 8:
            raise ValueError("1 to 8 kinetic classes required")
        if any(not isinstance(c, KCMBClass) for c in self.classes):
            raise ValueError("invalid class type")
        if len({c.name for c in self.classes}) != len(self.classes):
            raise ValueError("duplicate class name")
        for key in ("cell_length_m", "dt_s", "capacity_veh_per_s", "backward_wave_mps"):
            v = _finite(getattr(self, key), key)
            if v <= 0:
                raise ValueError(f"{key} must be positive")
            object.__setattr__(self, key, v)
        max_wave = max(self.backward_wave_mps, *(c.vmax_mps for c in self.classes))
        if max_wave * self.dt_s / self.cell_length_m > 1.0:
            raise ValueError("kinetic corridor CFL violation")
        if self.cells * len(self.classes) * _FIELDS + 3*len(self.classes) > _CEILING:
            raise ValueError("fixed moment state budget exceeded")
        space = self.lanes * self.cell_length_m
        if not math.isfinite(space) or space <= 0:
            raise ValueError("nonfinite lane metres")


@dataclass(frozen=True, slots=True)
class KCMBSnapshot:
    model_id: str
    tick: int
    moments: tuple[float, ...]
    pending: tuple[float, ...]
    released: tuple[float, ...]
    completed: tuple[float, ...]


def _mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    n = len(a)
    return [[math.fsum(a[i][k] * b[k][j] for k in range(n))
             for j in range(n)] for i in range(n)]


def _kinetic_transition(c: KCMBClass, dt: float) -> tuple[float, ...]:
    """Positive uniformization matrix exponential of a 6-field Markov generator.

    The physical dimensionless velocity is u=v/U.  q >= all exit rates makes
    P=I+A/q entrywise nonnegative.  Small Poisson mean and squaring avoid
    large-rate underflow. The *exact semigroup* preserves realizability by its
    microscopic Markov origin; positivity of a truncated matrix polynomial
    alone is not a proof of moment realizability. Check the error against RK4.
    """
    a, n, g = c.alpha_per_s, c.nu_per_s, 1.0/c.tau_s
    A = [
        [-a, n, 0., 0., 0., 0.],
        [a, -n, 0., 0., 0., 0.],
        [0., 0., -(g+a), n, 0., 0.],
        [0., g, a, -(g+n), 0., 0.],
        [0., 0., 0., 0., -(2*g+a), n],
        [0., 0., 0., 2*g, a, -(2*g+n)],
    ]
    q = max(-A[i][i] for i in range(_FIELDS))
    if not math.isfinite(q * dt):
        raise ValueError("nonfinite kinetic rate/time product")
    if q*dt > 1e6:
        raise ValueError("kinetic rate/time precomputation budget exceeded")
    powers = max(0, math.ceil(math.log2(q*dt/2))) if q*dt > 2 else 0
    h = dt / (2**powers)
    rate = q*h
    P = [[(float(i == j) + A[i][j]/q) for j in range(_FIELDS)]
         for i in range(_FIELDS)]
    ident = [[float(i == j) for j in range(_FIELDS)] for i in range(_FIELDS)]
    term = ident
    weight = math.exp(-rate)
    M = [[weight * ident[i][j] for j in range(_FIELDS)] for i in range(_FIELDS)]
    cdf = weight
    for k in range(1, 129):
        term = _mul(term, P)
        weight *= rate / k
        cdf += weight
        for i in range(_FIELDS):
            for j in range(_FIELDS):
                M[i][j] += weight * term[i][j]
        if 1.0 - cdf < 8e-16 and weight < 1e-16:
            break
    else:
        raise ArithmeticError("uniformization convergence budget")
    for _ in range(powers):
        M = _mul(M, M)
    if any(v < 0 or not math.isfinite(v) for row in M for v in row):
        raise ArithmeticError("nonpositive/nonfinite kinetic propagator")
    return tuple(v for row in M for v in row)


def _micro_point(mass: float, p: float, u: float) -> tuple[float, ...]:
    """A physically realizable inlet measure: Bernoulli sigma, fixed speed u."""
    return (mass*(1-p), mass*p, mass*(1-p)*u, mass*p*u,
            mass*(1-p)*u*u, mass*p*u*u)


def _validate_class_moments(x: Sequence[float], tol: float) -> None:
    m0,m1,j0,j1,z0,z1 = x
    if any(not math.isfinite(v) for v in x):
        raise ValueError("nonfinite kinetic moment")
    for m,j,z in ((m0,j0,z0),(m1,j1,z1)):
        if (m < -tol or j < -tol or z < -tol or j > m+tol or
            z > j+tol or j*j > m*z + tol*max(1.0, m)):
            raise ValueError("nonrealizable class-conditioned velocity moments")


class KCMBCorridor:
    """Explicit opt-in comparator. No implicit replacement/fallback of V1."""

    def __init__(self, config: KCMBConfig, *, backend: str = "python"):
        if not isinstance(config, KCMBConfig):
            raise ValueError("KCMBConfig required")
        if backend not in ("python", "rust"):
            raise ValueError("backend must be python or rust")
        self.config = config
        self.backend = backend
        self.classes = len(config.classes)
        self.state_scalars = config.cells*self.classes*_FIELDS + 3*self.classes
        identity_bytes = json.dumps({"version":_VERSION,"config":asdict(config)},
                                    sort_keys=True,separators=(",",":")).encode()
        self.model_id = _VERSION + ":" + sha256(identity_bytes).hexdigest()
        self._transitions = tuple(_kinetic_transition(c,config.dt_s) for c in config.classes)
        self._native = None
        if backend=="rust":
            try:
                from _metroflow_rust import NativeKCMBCorridor
            except ImportError as exc:
                raise RuntimeError("opt-in Rust KCMB backend unavailable") from exc
            self._native = NativeKCMBCorridor(
                config.cells, self.classes, config.cell_length_m, config.dt_s,
                config.lanes * config.cell_length_m, config.capacity_veh_per_s,
                config.backward_wave_mps,
                [c.vmax_mps for c in config.classes],
                [c.footprint_m for c in config.classes],
                [list(m) for m in self._transitions],
                [c.source_p for c in config.classes],
                [c.source_speed_fraction for c in config.classes],
            )

    def initial(self) -> KCMBSnapshot:
        c = self.classes
        return KCMBSnapshot(self.model_id,0,
                            (0.,)*(self.config.cells*c*_FIELDS),
                            (0.,)*c, (0.,)*c, (0.,)*c)

    def initial_profile(self, masses_by_cell: Sequence[Sequence[float]], *,
                        latent: Sequence[float] | None = None,
                        speed_fraction: Sequence[float] | None = None) -> KCMBSnapshot:
        c = self.classes
        if len(masses_by_cell) != self.config.cells or any(len(x)!=c for x in masses_by_cell):
            raise ValueError("invalid profile state shape")
        latent = tuple(latent) if latent is not None else tuple(x.source_p for x in self.config.classes)
        speed_fraction = (tuple(speed_fraction) if speed_fraction is not None else
                          tuple(x.source_speed_fraction for x in self.config.classes))
        if len(latent)!=c or len(speed_fraction)!=c:
            raise ValueError("profile distribution shape")
        if any(not 0 <= _finite(v,"latent") <= 1 for v in latent) or any(
                not 0 <= _finite(v,"velocity") <= 1 for v in speed_fraction):
            raise ValueError("initial physical distribution outside [0,1]")
        fields=[]
        initial_totals=[0.]*c
        for row in masses_by_cell:
            space=0.
            for index,(amount,cl,p,u) in enumerate(zip(
                    row,self.config.classes,latent,speed_fraction)):
                m=_finite(amount,"initial mass")
                if m<0:
                    raise ValueError("negative initial mass")
                space+=m*cl.footprint_m
                initial_totals[index]+=m
                fields.extend(_micro_point(m,p,u))
            if space>self.config.lanes*self.config.cell_length_m+1e-10:
                raise ValueError("initial state exceeds lane storage")
        return KCMBSnapshot(self.model_id,0,tuple(fields),(0.,)*c,
                            tuple(initial_totals),(0.,)*c)

    def _checked(self, state: KCMBSnapshot) -> None:
        k=self.classes
        if (not isinstance(state,KCMBSnapshot) or state.model_id != self.model_id):
            raise ValueError("KCMB state identity mismatch")
        if (isinstance(state.tick,bool) or not isinstance(state.tick,int) or state.tick<0 or
            len(state.moments)!=self.config.cells*k*_FIELDS or
            len(state.pending)!=k or len(state.released)!=k or len(state.completed)!=k):
            raise ValueError("invalid KCMB state shape")
        space=self.config.lanes*self.config.cell_length_m
        active=[0.]*k
        for i in range(self.config.cells):
            occupied=0.
            for a,c in enumerate(self.config.classes):
                x=state.moments[(i*k+a)*_FIELDS:(i*k+a+1)*_FIELDS]
                _validate_class_moments(x,1e-10*max(1.,sum(x[:2])))
                mass=x[0]+x[1]
                occupied+=mass*c.footprint_m
                active[a]+=mass
            if occupied>space+1e-9*max(1.,space):
                raise ValueError("KCMB state exceeds physical lane storage")
        for index in range(k):
            p,r,d = state.pending[index],state.released[index],state.completed[index]
            if not all(math.isfinite(z) and z>=-1e-11 for z in (p,r,d)):
                raise ValueError("invalid state ledger")
            if abs(r-(p+d+active[index])) > 1e-9*max(1.,r):
                raise ValueError("KCMB state vehicle conservation ledger mismatch")

    def cell_class_mass(self,state:KCMBSnapshot,i:int,a:int)->float:
        self._checked_shape(state)
        if not 0<=i<self.config.cells or not 0<=a<self.classes:
            raise IndexError("cell/class outside registered domain")
        off=(i*self.classes+a)*_FIELDS
        return state.moments[off]+state.moments[off+1]

    def _checked_shape(self,state:KCMBSnapshot)->None:
        if not isinstance(state,KCMBSnapshot) or state.model_id!=self.model_id:
            raise ValueError("state identity mismatch")
        if len(state.moments)!=self.config.cells*self.classes*_FIELDS:
            raise ValueError("state shape mismatch")

    def cell_occupied_metres(self,state:KCMBSnapshot,i:int)->float:
        return math.fsum(self.cell_class_mass(state,i,a)*c.footprint_m
                         for a,c in enumerate(self.config.classes))

    def moment_observables(self,state:KCMBSnapshot):
        self._checked_shape(state)
        ans=[]
        for i in range(self.config.cells):
            row=[]
            for a,c in enumerate(self.config.classes):
                off=(i*self.classes+a)*_FIELDS
                m0,m1,j0,j1,z0,z1=state.moments[off:off+_FIELDS]
                row.append((m0+m1,m1,c.vmax_mps*(j0+j1),
                            c.vmax_mps*j1, c.vmax_mps**2*(z0+z1)))
            ans.append(tuple(row))
        return tuple(ans)

    def _python_step(self,state:KCMBSnapshot,offers:tuple[float,...],green:float):
        cfg=self.config
        n,k=cfg.cells,self.classes
        old=state.moments
        evolved=[0.]*len(old)
        masses=[[0.]*k for _ in range(n)]
        sends=[[0.]*k for _ in range(n)]
        free=[0.]*n
        cap=cfg.capacity_veh_per_s*cfg.dt_s
        wave=min(1.,cfg.backward_wave_mps*cfg.dt_s/cfg.cell_length_m)
        for i in range(n):
            occupied=0.
            for a,c in enumerate(cfg.classes):
                off=(i*k+a)*_FIELDS
                mat=self._transitions[a]
                for r in range(_FIELDS):
                    evolved[off+r]=math.fsum(mat[r*_FIELDS+j]*old[off+j]
                                             for j in range(_FIELDS))
                vals=evolved[off:off+_FIELDS]
                m=vals[0]+vals[1]
                masses[i][a]=m
                occupied+=m*c.footprint_m
                sends[i][a]=min(m, cfg.dt_s/cfg.cell_length_m *
                                c.vmax_mps*(vals[2]+vals[3]))
            total=math.fsum(sends[i])
            if total>cap:
                sends[i]=[v*cap/total for v in sends[i]]
            free[i]=max(0.,cfg.lanes*cfg.cell_length_m-occupied)*wave
        transferred=[[0.]*k for _ in range(n)]
        for i in range(n-1):
            offered_here=sends[i]
            mass=math.fsum(offered_here)
            metres=math.fsum(v*c.footprint_m for v,c in zip(offered_here,cfg.classes))
            ratio=min(1.,cap/mass if mass>0 else 1.,
                      free[i+1]/metres if metres>0 else 1.)
            transferred[i]=[v*ratio for v in offered_here]
        outgoing=[v*green for v in sends[-1]]
        transferred[-1]=outgoing
        arriving=[state.pending[a]+offers[a] for a in range(k)]
        incoming_total=math.fsum(arriving)
        incoming_metres=math.fsum(x*c.footprint_m for x,c in zip(arriving,cfg.classes))
        src_ratio=min(1.,cap/incoming_total if incoming_total>0 else 1.,
                      free[0]/incoming_metres if incoming_metres>0 else 1.)
        accepted=[x*src_ratio for x in arriving]
        nxt=[0.]*len(evolved)
        for i in range(n):
            for a,c in enumerate(cfg.classes):
                off=(i*k+a)*_FIELDS
                m=masses[i][a]
                take=transferred[i][a]
                remain=1.-take/m if m>0 else 1.
                for r in range(_FIELDS):
                    nxt[off+r]=evolved[off+r]*remain
                if i>0:
                    prev=(i-1)*k+a
                    pm=masses[i-1][a]
                    frac=transferred[i-1][a]/pm if pm>0 else 0.
                    for r in range(_FIELDS):
                        nxt[off+r]+=evolved[prev*_FIELDS+r]*frac
                else:
                    injected=_micro_point(accepted[a],c.source_p,c.source_speed_fraction)
                    for r in range(_FIELDS):
                        nxt[off+r]+=injected[r]
        pending=tuple(max(0.,a-b) for a,b in zip(arriving,accepted))
        completed=tuple(a+b for a,b in zip(state.completed,outgoing))
        released=tuple(a+b for a,b in zip(state.released,offers))
        return (tuple(nxt),pending,released,completed,tuple(accepted),tuple(outgoing))

    def step(self,state:KCMBSnapshot,offers:Sequence[float],*,green:float=1.):
        self._checked(state)
        offers=tuple(_finite(v,"offered mass") for v in offers)
        green=_finite(green,"exit green")
        if len(offers)!=self.classes or any(v<0 for v in offers) or not 0<=green<=1:
            raise ValueError("invalid offered class masses or exit green gate")
        if self._native is None:
            fields,pending,released,completed,accepted,outgoing=self._python_step(state,offers,green)
        else:
            fields,pending,released,completed,accepted,outgoing=self._native.step(
                list(state.moments),list(state.pending),list(state.released),
                list(state.completed),list(offers),green)
        nxt=KCMBSnapshot(self.model_id,state.tick+1,tuple(fields),tuple(pending),
                         tuple(released),tuple(completed))
        self._checked(nxt)
        residuals=[]
        for a in range(self.classes):
            amount=math.fsum((nxt.pending[a],nxt.completed[a],*
                 (nxt.moments[(i*self.classes+a)*_FIELDS]+
                  nxt.moments[(i*self.classes+a)*_FIELDS+1]
                  for i in range(self.config.cells))))
            residuals.append(abs(nxt.released[a]-amount))
        receipt={"accepted_by_class":tuple(accepted),
                 "completed_by_class":tuple(outgoing),
                 "mass_error_max_veh":max(residuals),
                 "state_scalar_capacity":self.state_scalars,
                 "model_id":self.model_id,
                 "backend":self.backend}
        return nxt,receipt

    def to_bytes(self,state:KCMBSnapshot)->bytes:
        self._checked(state)
        return json.dumps({"format":_VERSION,**asdict(state)},sort_keys=True,
                          separators=(",",":"),allow_nan=False).encode()

    def from_bytes(self,data:bytes)->KCMBSnapshot:
        # Validate bounded size before deserialization to avoid allocating a
        # huge adversarial or corrupt JSON document during checkpoint recovery.
        max_bytes=4096 + 64*self.state_scalars
        if not isinstance(data,(bytes,bytearray)) or len(data)>max_bytes:
            raise ValueError("KCMB checkpoint byte-size budget exceeded")
        try:
            obj=json.loads(data)
            if set(obj)!={"format","model_id","tick","moments","pending","released","completed"}:
                raise ValueError("invalid KCMB checkpoint shape")
            if obj["format"]!=_VERSION or obj["model_id"]!=self.model_id:
                raise ValueError("KCMB checkpoint identity differs")
            state=KCMBSnapshot(obj["model_id"],obj["tick"],tuple(obj["moments"]),
                 tuple(obj["pending"]),tuple(obj["released"]),tuple(obj["completed"]))
            self._checked(state)
            return state
        except (ValueError,TypeError,KeyError) as exc:
            raise ValueError("invalid KCMB checkpoint format/identity/state") from exc
