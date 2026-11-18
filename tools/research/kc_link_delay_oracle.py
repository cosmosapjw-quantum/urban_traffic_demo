#!/usr/bin/env python3
"""Research-only delayed cumulative-count link with finite storage.

One homogeneous FIFO fluid lane, fixed free-flow/backward lags and one
commodity. Not equivalent to full V1 finite-response packet network.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path


@dataclass
class DelayedLink:
    free_ticks: int
    backward_ticks: int
    storage_veh: float
    capacity_per_tick: float

    def __post_init__(self):
        if not (isinstance(self.free_ticks,int) and self.free_ticks>=1 and
                isinstance(self.backward_ticks,int) and self.backward_ticks>=1 and
                self.storage_veh>0 and self.capacity_per_tick>0):
            raise ValueError("positive discrete link delays/storage/capacity")
        self._in=deque([0.]*(self.free_ticks+1),maxlen=self.free_ticks+1)
        self._out=deque([0.]*(self.backward_ticks+1),maxlen=self.backward_ticks+1)
        self.pending=0.
        self.total_offered=0.

    def step(self,offer_veh=0.,outlet_open=True):
        if not math.isfinite(offer_veh) or offer_veh<0:
            raise ValueError("nonnegative finite offered mass required")
        self.pending+=offer_veh
        self.total_offered+=offer_veh
        Ain,Aout=self._in[-1],self._out[-1]
        lagged_in,lagged_out=self._in[0],self._out[0]
        demand=min(self.capacity_per_tick,max(0.,lagged_in-Aout))
        receiving=min(self.capacity_per_tick,max(0.,lagged_out+self.storage_veh-Ain))
        enter=min(self.pending,receiving)
        leave=demand if outlet_open else 0.
        self.pending-=enter
        self._in.append(Ain+enter)
        self._out.append(Aout+leave)
        occupancy=self._in[-1]-self._out[-1]
        assert -1e-10<=occupancy<=self.storage_veh+1e-10
        assert abs(self.total_offered-(self.pending+occupancy+self._out[-1]))<1e-8
        return dict(enter=enter,leave=leave,occupancy=occupancy,
                    ready_queue=max(0.,lagged_in-Aout),
                    vacancy=max(0.,lagged_out+self.storage_veh-Ain),
                    retained_cumulative_scalars=len(self._in)+len(self._out),
                    pending=self.pending,completed=self._out[-1])


def demo():
    link=DelayedLink(free_ticks=3,backward_ticks=5,storage_veh=12.,
                     capacity_per_tick=1.)
    checkpoints=[]
    for n in range(150):
        rec=link.step(3. if n<40 else 0.,outlet_open=n>=60)
        if n in (0,4,39,59,69,149):
            checkpoints.append((n,rec))
    return dict(lagged_state_scalars=len(link._in)+len(link._out),
                pending=link.pending,admitted=link._in[-1],
                completed=link._out[-1],samples=checkpoints)


if __name__=="__main__":
    import sys
    if len(sys.argv)!=2: raise SystemExit("usage: kc_link_delay_oracle.py output.json")
    result=demo()
    Path(sys.argv[1]).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="samples"}))
