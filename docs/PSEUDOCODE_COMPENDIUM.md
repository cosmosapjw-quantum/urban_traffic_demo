# Pseudocode Compendium

## 전체 tick loop
1. update external conditions
2. spawn trips from schedules
3. fast traffic tick
4. medium nav tick (conditional / periodic)
5. accessibility tick
6. slow development tick
7. learning tick
8. logging / observables / view-state emit

## mesoscopic core
FOR each edge:
  compute effective cost
  compute sending / receiving

FOR each node:
  gather incoming demands
  gather outgoing supplies
  compute feasible movement flows

FOR each edge:
  update queue / stock

FOR each active trip:
  advance progress
  if decision node:
    choose next edge/path

## reroute
IF hard event on route:
  reroute
ELSE IF ETA degradation > threshold AND refractory window satisfied:
  reroute
ELSE:
  continue

## lagged land-use
IF accessibility tick:
  recompute zonal skim / cache

IF development tick:
  read lagged accessibility
  update relocation / redevelopment
