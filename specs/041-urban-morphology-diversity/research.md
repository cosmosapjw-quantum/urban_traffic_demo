# Research Basis

## Evidence used

- Boeing (2019), *Urban spatial order: street network orientation,
  configuration, and entropy*, Applied Network Science 4:67,
  https://doi.org/10.1007/s41109-019-0189-1
  - 100-city OpenStreetMap/OSMnx comparison.
  - Defines 36-bin orientation entropy and orientation-order.
  - Reports median street length, circuity, mean degree, dead-end share, and
    four-way intersection share.
  - Explicitly describes single grids, offset/multiple grids, and highly
    disordered networks as different configurations rather than one ranking.
- Strano et al. (2013), *Urban street networks: a comparative analysis of ten
  European cities*, Environment and Planning B 40(6),
  https://doi.org/10.1068/b38216
  - Supports primal, approximately planar street-network comparison and
    distinguishes city families through geometry and centrality distributions.
- Lee et al. (2017), *Morphology of travel routes and the organization of
  cities*, Nature Communications 8:2229,
  https://doi.org/10.1038/s41467-017-02374-7
  - Shows a continuum between mono- and polycentric route organization and
    distinguishes hub-spoke infrastructure from more dispersed organization.
- OpenStreetMap export documentation,
  https://www.openstreetmap.org/export
  - Raw OSM data is ODbL. This PR therefore keeps real-city values as cited
    reference metrics and leaves raw XML to the existing offline importer.

## Claim boundary

- The reference corpus is `REFERENCE_ONLY`: it is observed data transcribed
  from a peer-reviewed table, not a calibration target and not validation that
  a generated map reproduces a named city.
- Generated signatures are `DIAGNOSTIC`: they demonstrate structural diversity
  and catch collapse, but do not establish urban realism by themselves.
