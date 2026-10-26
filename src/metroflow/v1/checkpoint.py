"""Whitelisted structured JSON checkpoints; no pickle or arbitrary imports."""
from dataclasses import fields, is_dataclass
import json
import math
import os
from pathlib import Path

from . import runtime, information, observations, routing, transport, demand, schedules, activity, access, journey, accessibility, development
from .. import packet_network
from .city import reject

_MODULES = (runtime, information, observations, routing, transport, packet_network, demand, schedules, activity, access, journey, accessibility, development)
_TYPES = {cls.__module__ + '.' + cls.__name__: cls for module in _MODULES
          for cls in vars(module).values() if isinstance(cls, type) and is_dataclass(cls)
          and cls.__module__ == module.__name__}


def encode(value):
    if is_dataclass(value):
        return {'type':type(value).__module__ + '.' + type(value).__name__,
                'fields':{f.name:encode(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, tuple):
        return {'tuple':[encode(v) for v in value]}
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            reject('NaN checkpoint', 'CONTRACT_ERROR')
        return {'float':'+inf' if value > 0 else '-inf'}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    reject('unsupported checkpoint value', 'CONTRACT_ERROR')


def decode(value):
    if not isinstance(value, dict):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        reject('invalid checkpoint value', 'CONTRACT_ERROR')
    if set(value) == {'tuple'}:
        return tuple(decode(v) for v in value['tuple'])
    if set(value) == {'float'} and value['float'] in ('+inf', '-inf'):
        return math.inf if value['float'] == '+inf' else -math.inf
    if set(value) == {'type', 'fields'} and value['type'] in _TYPES:
        cls = _TYPES[value['type']]
        if set(value['fields']) != {f.name for f in fields(cls)}:
            reject('checkpoint schema fields differ', 'CONTRACT_ERROR')
        return cls(**{k:decode(v) for k,v in value['fields'].items()})
    reject('unknown checkpoint type/schema', 'CONTRACT_ERROR')


def save_checkpoint(path, model, state):
    model.check(state)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w') as stream:
        json.dump({'schema':'C01_world_v1', 'state':encode(state)}, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def load_checkpoint(path, model):
    try:
        data = json.loads(Path(path).read_text(), parse_constant=lambda _:reject('nonfinite JSON', 'CONTRACT_ERROR'))
        if set(data) != {'schema', 'state'} or data['schema'] != 'C01_world_v1':
            reject('checkpoint schema mismatch', 'CONTRACT_ERROR')
        state = decode(data['state'])
        model.check(state)
        return state
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        reject('malformed checkpoint: ' + str(exc), 'CONTRACT_ERROR')
