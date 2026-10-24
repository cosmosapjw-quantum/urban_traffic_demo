"""Class-conditioned stopping sight gate for generated ground-road frontage.

Metres/seconds. A stopped obstacle at the proposed junction is the reference,
not a complete conflict/merge safety proof. Only terrain occlusion is resolved.
"""
from dataclasses import dataclass
import math
from .restored_geometry import elevation, minimum_ground_gap


@dataclass(frozen=True, slots=True)
class SightClass:
    name: str = 'car'
    reaction_s: float = 1.0
    brake_mps2: float = 4.0
    eye_m: float = 1.2
    object_m: float = .6
    max_speed_mps: float = 33.3

    def __post_init__(self):
        values=(self.reaction_s,self.brake_mps2,self.eye_m,self.object_m,self.max_speed_mps)
        if not self.name or not all(map(math.isfinite,values)) or self.reaction_s<0:
            raise ValueError('invalid sight class')
        if min(values[1:])<=0:raise ValueError('sight parameters must be positive')


@dataclass(frozen=True, slots=True)
class SightCheck:
    vehicle_class: str
    direction: int
    required_m: float
    clearance_m: float | None
    reason: str | None
    eye: tuple[float,float,float] | None = None
    target: tuple[float,float,float] | None = None


def stopping_distance(speed, reaction, brake, grade=0., margin=2.):
    """Conservative downhill braking lower bound. Not a road-design standard."""
    vals=(speed,reaction,brake,grade,margin)
    if not all(map(math.isfinite,vals)) or min(speed,reaction,grade,margin)<0 or brake<=0:
        raise ValueError('invalid stopping inputs')
    net=brake-9.81*grade/math.sqrt(1+grade*grade)
    if net<=0:return math.inf
    return speed*reaction+speed*speed/(2*net)+margin


def _at(points, lengths, location):
    for k,(lo,hi) in enumerate(zip(lengths,lengths[1:])):
        if hi>=location and hi>lo:
            u=max(0.,min(1.,(location-lo)/(hi-lo)))
            return tuple(a+u*(b-a) for a,b in zip(points[k],points[k+1]))
    return points[-1]


@dataclass(frozen=True, slots=True)
class SightRule:
    classes: tuple[SightClass,...] = (SightClass(),)
    margin_m: float = 2.

    def __post_init__(self):
        if not self.classes or len({x.name for x in self.classes})!=len(self.classes):
            raise ValueError('nonempty unique classes required')
        if not math.isfinite(self.margin_m) or self.margin_m<0:raise ValueError('invalid stopping margin')

    def assess(self,city,road,projection):
        if road.facility!='surface':raise ValueError('sight frontage requires ground surface')
        speeds={'local':8.33,'collector':13.89,'arterial':16.67}
        if road.hierarchy not in speeds:raise ValueError('unsupported frontage road')
        lengths=[0.]
        for a,b in zip(road.points,road.points[1:]):lengths.append(lengths[-1]+math.dist(a,b))
        _,k,u,xy=projection
        position=lengths[k]+u*(lengths[k+1]-lengths[k])
        target_ground=elevation(city.terrain,*xy)
        rows=[]
        for vehicle in self.classes:
            speed=min(speeds[road.hierarchy],vehicle.max_speed_mps)
            needed=stopping_distance(speed,vehicle.reaction_s,vehicle.brake_mps2,
                                     road.max_grade,self.margin_m)
            for direction,lanes in ((0,road.forward_lanes),(1,road.backward_lanes)):
                if lanes<=0:continue
                if not math.isfinite(needed):
                    rows.append(SightCheck(vehicle.name,direction,needed,None,'braking_infeasible'));continue
                at=position-needed if direction==0 else position+needed
                if at<0 or at>lengths[-1]:
                    rows.append(SightCheck(vehicle.name,direction,needed,None,'sight_extent_unknown'));continue
                p=_at(road.points,lengths,at)
                eye=(p[0],p[1],elevation(city.terrain,*p[:2])+vehicle.eye_m)
                target=(*xy,target_ground+vehicle.object_m)
                gap=minimum_ground_gap(city.terrain,(eye,target))
                rows.append(SightCheck(vehicle.name,direction,needed,gap,
                            'sight_obstructed' if gap<0 else None,eye,target))
        return tuple(rows)

    def __call__(self,city,site,road,projection):
        return next((x.reason for x in self.assess(city,road,projection) if x.reason),None)
