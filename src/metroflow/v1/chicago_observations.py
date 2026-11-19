"""Strict Chicago CTA-probe segment-speed observation and road-candidate adapter.

Research-only opt-in. Source is public historical Traffic Tracker 4g9f-3jbs.
Raw speeds are *estimated arterial segment speeds from CTA bus GPS*, not
traffic volume, lane turning discharge, individual vehicle trajectories or
directly KCMB car-class velocities.

No network calls in this module. No implicit UTC conversions or geodata fixes.
See docs/research/KCMB_FIELD_OBSERVATION_THEORY_R1_R10_20261119_KO.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
import heapq
import math
from typing import Mapping, Sequence
import xml.etree.ElementTree as ET


_MPH_TO_MPS = 0.44704
_MILE_TO_METRES = 1609.344
_EARTH_RADIUS_METRES = 6371000.0
_CLOCK_START = 7 * 6
_CLOCK_END = 9 * 6


@dataclass(frozen=True, slots=True)
class ChicagoSegment:
    segment_id: str
    street: str
    direction: str
    from_street: str
    to_street: str
    length_m: float
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float


@dataclass(frozen=True, slots=True)
class SpeedSample:
    day: str
    split: str
    local_time: str
    slot: int
    speed_mps: float
    bus_count: int
    message_count: int


@dataclass(frozen=True, slots=True)
class ExcludedSpeed:
    split: str
    local_time: str
    slot: int
    reason: str


@dataclass(frozen=True, slots=True)
class ChicagoObservedSet:
    segment: ChicagoSegment
    calibration: tuple[SpeedSample, ...]
    holdout: tuple[SpeedSample, ...]
    excluded_rows: tuple[ExcludedSpeed, ...]
    calibration_day: str
    holdout_day: str


@dataclass(frozen=True, slots=True)
class OsmRoadCandidate:
    start_offset_m: float
    end_offset_m: float
    path_length_m: float
    relative_length_error: float
    node_path: tuple[str, ...]
    way_ids: tuple[str, ...]
    osm_oneway_verified: bool = False
    lane_pocket_geometry_verified: bool = False


def _number(row: Mapping[str, object], field: str) -> float:
    try:
        value=row[field]
        if isinstance(value, bool):
            raise ValueError("boolean source value")
        x=float(value)
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"missing or invalid Chicago {field}") from exc
    if not math.isfinite(x):
        raise ValueError(f"nonfinite Chicago {field}")
    return x


def _integer(row: Mapping[str, object], field: str) -> int:
    value=_number(row, field)
    if value < 0 or not value.is_integer():
        raise ValueError(f"invalid Chicago {field} probe count")
    return int(value)


def _distance_m(a: tuple[float,float], b: tuple[float,float]) -> float:
    lat1,lon1=map(math.radians,a)
    lat2,lon2=map(math.radians,b)
    z=math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*_EARTH_RADIUS_METRES*math.asin(math.sqrt(min(1.,max(0.,z))))


def _parse_site(row: Mapping[str, object]) -> ChicagoSegment:
    for field in ("segment_id","street","direction","from_street","to_street"):
        if field not in row or not str(row[field]).strip():
            raise ValueError(f"missing Chicago site identity: {field}")
    length=_number(row,"length")*_MILE_TO_METRES
    if length<=0:
        raise ValueError("positive Chicago segment length required")
    x=ChicagoSegment(
        str(row["segment_id"]),str(row["street"]),str(row["direction"]),
        str(row["from_street"]),str(row["to_street"]),length,
        _number(row,"start_latitude"),_number(row,"start_longitude"),
        _number(row,"end_latitude"),_number(row,"end_longitude"),
    )
    if not (-90<=x.start_lat<=90 and -90<=x.end_lat<=90 and
            -180<=x.start_lon<=180 and -180<=x.end_lon<=180):
        raise ValueError("invalid geographic endpoint")
    if _distance_m((x.start_lat,x.start_lon),(x.end_lat,x.end_lon))>x.length_m*1.05:
        raise ValueError("Chicago endpoint distance exceeds reported segment length")
    return x


def _validate_day(day: str) -> date:
    try:
        day_obj=date.fromisoformat(day)
        if day_obj.isoformat()!=day:
            raise ValueError("noncanonical day")
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid calibration/holdout local date") from exc
    return day_obj


def parse_observation_days(
    calibration_rows: Sequence[Mapping[str,object]],
    holdout_rows: Sequence[Mapping[str,object]],
    *,
    calibration_day: str = "2026-04-20",
    holdout_day: str = "2026-04-27",
    segment_id: str = "1221",
) -> ChicagoObservedSet:
    """Normalize one 10-minute-proxy site, strict day/segment split and units."""
    cal_date=_validate_day(calibration_day)
    hold_date=_validate_day(holdout_day)
    if cal_date>=hold_date or cal_date.weekday()!=hold_date.weekday():
        raise ValueError("invalid overlapping date/split or changed weekday")
    if not str(segment_id).strip():
        raise ValueError("nonempty segment identity required")
    segment=None
    parsed={}
    excluded=[]
    for split,day,rows in (
        ("calibration",calibration_day,calibration_rows),
        ("holdout",holdout_day,holdout_rows),
    ):
        if isinstance(rows,(str,bytes)) or not isinstance(rows,(list,tuple)) or not rows:
            raise ValueError("nonempty bounded source rows required")
        if len(rows)>5000:
            raise ValueError("source sample row budget exceeded")
        seen_slots=set()
        accepted=[]
        for row in rows:
            if not isinstance(row,Mapping):
                raise ValueError("source rows must be mappings")
            site=_parse_site(row)
            if site.segment_id!=str(segment_id):
                raise ValueError("segment identity mismatch")
            if segment is None:
                segment=site
            else:
                if (site.segment_id,site.street,site.direction,
                    site.from_street,site.to_street)!=(
                    segment.segment_id,segment.street,segment.direction,
                    segment.from_street,segment.to_street):
                    raise ValueError("source street/direction/site identity mismatch")
                if abs(site.length_m-segment.length_m)>1e-6 or (
                    _distance_m((site.start_lat,site.start_lon),
                                (segment.start_lat,segment.start_lon))>30 or
                    _distance_m((site.end_lat,site.end_lon),
                                (segment.end_lat,segment.end_lon))>30):
                    raise ValueError("source segment length/endpoints changed")
            try:
                raw_time=str(row["time"])
                stamp=datetime.fromisoformat(raw_time)
            except (KeyError,TypeError,ValueError) as exc:
                raise ValueError("invalid local observation clock") from exc
            if stamp.tzinfo is not None:
                raise ValueError("timezone offset unverified in Chicago source")
            if stamp.date().isoformat()!=day:
                raise ValueError("source local date differs from declared split")
            slot=stamp.hour*6+stamp.minute//10
            if not _CLOCK_START <= slot < _CLOCK_END:
                raise ValueError("source clock outside allowed 07:00–09:00 window")
            if slot in seen_slots:
                raise ValueError("duplicate Chicago time slot")
            seen_slots.add(slot)
            speed=_number(row,"speed")
            buses=_integer(row,"bus_count")
            probes=_integer(row,"message_count")
            if speed < 0 and speed != -1:
                raise ValueError("invalid negative Chicago source speed")
            if speed == -1:
                excluded.append(ExcludedSpeed(split,raw_time,slot,"NO_SPEED_ESTIMATE"))
                continue
            if buses==0 or probes==0:
                excluded.append(ExcludedSpeed(split,raw_time,slot,"NO_PROBE_SUPPORT"))
                continue
            accepted.append(SpeedSample(day,split,raw_time,slot,
                                        speed*_MPH_TO_MPS,buses,probes))
        parsed[split]=tuple(sorted(accepted,key=lambda item:item.slot))
    if not parsed["calibration"] or not parsed["holdout"]:
        raise ValueError("no supported calibration/holdout speed observations")
    assert segment is not None
    return ChicagoObservedSet(segment,parsed["calibration"],parsed["holdout"],
                              tuple(excluded),calibration_day,holdout_day)


def _mae(x: Sequence[float],y: Sequence[float]) -> float:
    return math.fsum(abs(a-b) for a,b in zip(x,y))/len(x)


def _rmse(x: Sequence[float],y: Sequence[float]) -> float:
    return math.sqrt(math.fsum((a-b)**2 for a,b in zip(x,y))/len(x))


def evaluate_speed_only(observations: ChicagoObservedSet) -> dict:
    """Observed speed-proxy baseline, NOT vehicle counts or KCMB calibration."""
    if not isinstance(observations,ChicagoObservedSet):
        raise ValueError("normalized observations required")
    calibration=observations.calibration
    holdout=observations.holdout
    avg=math.fsum(x.speed_mps for x in calibration)/len(calibration)
    by_cal={x.slot:x.speed_mps for x in calibration}
    by_hold={x.slot:x.speed_mps for x in holdout}
    matching=sorted(set(by_cal)&set(by_hold))
    if not matching:
        raise ValueError("no comparable within-day nominal clock bins")
    observed=[by_hold[t] for t in matching]
    constant=[avg]*len(matching)
    lookup=[by_cal[t] for t in matching]
    # W1 calibration-vs-holdout requires equal valid unpaired sample sizes.
    empirical_w1=(math.fsum(abs(a-b) for a,b in zip(
        sorted(x.speed_mps for x in calibration),
        sorted(x.speed_mps for x in holdout)))/len(calibration)
        if len(calibration)==len(holdout) else None)
    return {
        "status":"REAL_FIELD_SPEED_ONLY_SCORED",
        "observable":"CTA_GPS_ESTIMATED_SEGMENT_SPEED",
        "site_id":observations.segment.segment_id,
        "calibration_day":observations.calibration_day,
        "holdout_day":observations.holdout_day,
        "calibration_count":len(calibration),
        "holdout_count":len(holdout),
        "shared_clock_bins":len(matching),
        "calibration_speed_mean_mps":avg,
        "holdout_speed_mean_mps":math.fsum(x.speed_mps for x in holdout)/len(holdout),
        "equilibrium_baseline_holdout_mae_mps":_mae(constant,observed),
        "equilibrium_baseline_holdout_rmse_mps":_rmse(constant,observed),
        "time_bin_template_holdout_mae_mps":_mae(lookup,observed),
        "time_bin_template_holdout_rmse_mps":_rmse(lookup,observed),
        "calibration_holdout_speed_w1_mps":empirical_w1,
        "source_uncertainty":"single_holdout_day_correlated_bins",
        "source_probe_counts_are_vehicle_counts":False,
        "flow_geh":None,
        "physical_model_class_parameters_identified":False,
        "predictive_model":"scalar equilibrium-compatible speed baseline, not a physical KCMB runtime",
        "paired_clock_slots":matching,
    }


def match_named_osm_path(
    osm_bytes: bytes,
    segment: ChicagoSegment,
    *,
    street_token: str = "Halsted",
    max_endpoint_m: float = 30.,
    max_length_relative_error: float = .1,
) -> OsmRoadCandidate:
    """Candidate match on named OSM highway way nodes; NOT one-way lane proof."""
    if not isinstance(segment,ChicagoSegment):
        raise ValueError("normalized Chicago segment required")
    if not isinstance(osm_bytes,bytes) or not 1<=len(osm_bytes)<=10_000_000:
        raise ValueError("OSM fixture byte-size/path budget exceeded")
    if not isinstance(street_token,str) or not street_token.strip():
        raise ValueError("explicit nonempty OSM street token required")
    if not math.isfinite(max_endpoint_m) or max_endpoint_m<=0 or (
            not math.isfinite(max_length_relative_error) or
            not 0<=max_length_relative_error<1):
        raise ValueError("invalid geographic match tolerance")
    direction=segment.direction
    if direction not in ("NB","SB","EB","WB"):
        raise ValueError("unrecognized segment travel direction")
    if (direction=="NB" and segment.end_lat<=segment.start_lat or
        direction=="SB" and segment.end_lat>=segment.start_lat or
        direction=="EB" and segment.end_lon<=segment.start_lon or
        direction=="WB" and segment.end_lon>=segment.start_lon):
        raise ValueError("official direction inconsistent with segment endpoints")
    try:
        root=ET.fromstring(osm_bytes)
    except ET.ParseError as exc:
        raise ValueError("invalid OSM fixture XML") from exc
    nodes={}
    for item in root.findall("node"):
        if "lat" in item.attrib and "lon" in item.attrib:
            nodes[item.attrib["id"]]=(float(item.attrib["lat"]),float(item.attrib["lon"]))
    graph={}
    needle=street_token.casefold()
    for way in root.findall("way"):
        tags={x.attrib.get("k"):x.attrib.get("v") for x in way.findall("tag")}
        if "highway" not in tags or needle not in tags.get("name","").casefold():
            continue
        refs=[x.attrib["ref"] for x in way.findall("nd")]
        wayid=way.attrib.get("id","unidentified")
        for a,b in zip(refs,refs[1:]):
            if a not in nodes or b not in nodes:continue
            weight=_distance_m(nodes[a],nodes[b])
            if weight<=0:continue
            graph.setdefault(a,[]).append((b,weight,wayid))
            graph.setdefault(b,[]).append((a,weight,wayid))
    if not graph:
        raise ValueError("no named street path in OSM fixture")
    start=(segment.start_lat,segment.start_lon)
    end=(segment.end_lat,segment.end_lon)
    def candidates(target):
        return sorted(((_distance_m(nodes[n],target),n) for n in graph),
                      key=lambda x:(x[0],x[1]))[:8]
    sources=[x for x in candidates(start) if x[0]<=max_endpoint_m]
    targets=[x for x in candidates(end) if x[0]<=max_endpoint_m]
    if not sources or not targets:
        raise ValueError("OSM endpoint distance outside spatial match tolerance")
    results=[]
    ends={n:delta for delta,n in targets}
    for initial_distance,initial in sources:
        queue=[(0.,initial)]
        best={initial:0.}
        parent={}
        while queue:
            length,u=heapq.heappop(queue)
            if length>best.get(u,float("inf"))+1e-8:continue
            for v,w,wayid in graph.get(u,()):
                total=length+w
                if total<best.get(v,float("inf"))-1e-9:
                    best[v]=total
                    parent[v]=(u,wayid)
                    heapq.heappush(queue,(total,v))
        for end_distance,end_id in targets:
            if end_id not in best:continue
            path=[end_id]
            ways=[]
            current=end_id
            while current!=initial:
                previous,wid=parent[current]
                path.append(previous)
                ways.append(wid)
                current=previous
            path.reverse()
            ways.reverse()
            length=best[end_id]
            rel=length/segment.length_m-1
            if abs(rel)<=max_length_relative_error:
                score=initial_distance+end_distance+abs(length-segment.length_m)
                results.append((score,initial_distance,end_distance,length,
                                rel,tuple(path),tuple(dict.fromkeys(ways))))
    if not results:
        raise ValueError("named OSM street has no connected length-compatible match")
    _,start_d,end_d,length,rel,nodes_path,wayids=min(results,key=lambda x:(x[0],x[5]))
    return OsmRoadCandidate(start_d,end_d,length,rel,nodes_path,wayids,
                            osm_oneway_verified=False,
                            lane_pocket_geometry_verified=False)
