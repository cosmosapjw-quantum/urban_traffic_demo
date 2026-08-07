# Morphology Control Table

Fingerprint: `1886967f606d2ddb76ae885840eb0421776c69079b5f13d766bffad14575b433`

One pinned envelope applied to every arm. Metrics are measured on the
OSMnx-equivalent simplified graph, because the reference corpus reports
values after degree-2 interstitial nodes are contracted.

| arm | cases | all-7 pass | orientation_order | orientation_entropy | median_segment_length_m | circuity | mean_node_degree | dead_end_share | four_way_share |
|---|---|---|---|---|---|---|---|---|---|
| standard | 10 | 0 | 10/10 | 10/10 | 10/10 | 10/10 | 0/10 | 10/10 | 10/10 |
| sidecar_local_fabric | 30 | 15 | 30/30 | 30/30 | 20/30 | 30/30 | 30/30 | 25/30 | 20/30 |
| sidecar_local_fabric_planar | 30 | 0 | 30/30 | 30/30 | 0/30 | 30/30 | 30/30 | 30/30 | 25/30 |
| realistic_synthetic_v1 | 30 | 0 | 30/30 | 30/30 | 30/30 | 30/30 | 0/30 | 0/30 | 30/30 |
| growth_fabric_v1 | 30 | 30 | 30/30 | 30/30 | 30/30 | 30/30 | 30/30 | 30/30 | 30/30 |
| osm | 5 | 5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |

## Instrument limits

- `orientation_order` bounds `[0.0016, 1.0000]` - upper_bound_inert, VACUOUS
- `orientation_entropy` bounds `[1.6664, 3.5835]` - upper_bound_inert
- `median_segment_length_m` bounds `[42.8000, 140.6400]`
- `circuity` bounds `[1.0000, 1.3644]` - lower_bound_inert
- `mean_node_degree` bounds `[2.0368, 4.2576]`
- `dead_end_share` bounds `[0.0216, 0.3456]`
- `four_way_share` bounds `[0.1112, 0.6912]`

## Skipped cases

- `standard:grid_core/17:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:grid_core/29:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:grid_core/41:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:grid_core/44:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:grid_core/53:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:river_constrained/17:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:river_constrained/29:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:river_constrained/41:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:river_constrained/44:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:river_constrained/53:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:superblock_mixed/17:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:superblock_mixed/29:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:superblock_mixed/41:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:superblock_mixed/44:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:superblock_mixed/53:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:organic/17:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:organic/29:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:organic/41:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:organic/44:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `standard:organic/53:ValueError:standard preview_mode supports only ring_radial or polycentric_tod; use a sidecar preview_mode for other morphology styles`
- `osm:paris.osm:ValueError:lanes:forward leaves no backward traffic lane`
- `osm:prague.osm:ValueError:unsupported oneway value 'alternating'`

## Claim boundary

Diagnostic street-morphology comparison against a pinned reference
corpus. Not empirical traffic, demand, route-choice, land-use or
named-city validation. Passing this table authorizes no runtime default
change on its own.
