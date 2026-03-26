# CACHE INVALIDATION CONTRACT

## On graph edit
- invalidate route-set cache
- invalidate zonal skim cache
- bump graph version

## On zone/POI edit
- invalidate accessibility-dependent demand cache
- bump landuse version

## On policy/archetype edit
- invalidate only policy-dependent caches
- bump policy version
