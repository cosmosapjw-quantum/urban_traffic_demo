# Task B Exact Contract Rows

DATE: 2026-08-10
STATUS: PRE_RESET_DESIGN_CONTRACT
BRIEF_SHA256: `41585f436832e37d734b80bd52c195ca7b922170cadf4d2b69894bb8609fcf6c`

This file removes schema/count/mapping choices from implementation time. A
future replay may begin only after an independent reviewer accepts these rows as
a faithful, least-authority interpretation of the controlling brief.

## Exact private records

All ten records are exact frozen/slotted dataclasses and reject subclasses
before field access. Field order and annotations are:

```text
_ContentSeal(
  schema_version: str, sha256: str, blake2b_256: str,
  canonical_byte_count: int, record_count: int)
_ValidationReceipt(
  registry_schema_version: str, authority_kind: str,
  authority_schema_version: str, public_fingerprint: str,
  policy_versions: tuple[tuple[str,str],...],
  source_bindings: tuple[tuple[str,_ContentSeal],...],
  content_leaves: tuple[tuple[str,_ContentSeal],...])
_Task5InvocationSnapshot(
  target_population: int, urbanized_area_hex: str, style_id: str, seed: int)
_Task5TerrainProjection(
  width_m: float, height_m: float, cell_size_m: float, tile_size_m: float,
  seed: int, style_id: str, barrier_seam_x_mm: int|None, fingerprint: str)
_Task5NetworkProjection(
  target_population: int, urbanized_area_hex: str, style_id: str, seed: int,
  schema_version: str, extent_mm: tuple[int,int,int,int], width_m: float,
  height_m: float, centers_mm: tuple[tuple[int,int],...],
  terrain: _Task5TerrainProjection, network_fingerprint: str,
  terrain_fingerprint: str, scale_fingerprint: str, style_fingerprint: str)
_Task5BlocksProjection(
  schema_version: str, source_network_fingerprint: str,
  extent_mm: tuple[int,int,int,int],
  block_rows: tuple[tuple[object,...],...],
  access_index_payload: tuple[object,...], blocks_fingerprint: str)
_Task5CsrProjection(
  node_rows: tuple[tuple[object,...],...],
  link_rows: tuple[tuple[object,...],...],
  turn_rows: tuple[tuple[object,...],...],
  bridge_rows: tuple[tuple[object,...],...],
  node_index_rows: tuple[tuple[int,int],...],
  link_index_rows: tuple[tuple[int,int],...],
  turn_index_rows: tuple[tuple[tuple[int,int],int],...],
  arrays: tuple[tuple[str,np.ndarray],...],
  topology_cache_key: tuple[object,...])
_Task5CompiledProjection(
  schema_version: str, numeric_profile_policy_version: str,
  source_network_fingerprint: str, source_blocks_fingerprint: str,
  terrain_fingerprint: str, scale_fingerprint: str, style_fingerprint: str,
  geometry_fingerprint: str, section_fingerprint: str,
  node_interface_fingerprint: str, turn_authority_fingerprint: str,
  compiled_fingerprint: str,
  numeric_profile_rows: tuple[tuple[object,...],...],
  road_crosswalk_rows: tuple[tuple[object,...],...],
  structure_group_rows: tuple[tuple[object,...],...],
  failure_group_rows: tuple[tuple[object,...],...], csr: _Task5CsrProjection)
_Task5FullSealSet(
  network_current: _ContentSeal, blocks_current: _ContentSeal,
  compiled_authority_leaves: tuple[tuple[str,_ContentSeal],...])
_VerifiedTask5SourceSnapshot(
  schema_version: str, invocation: _Task5InvocationSnapshot,
  network: _Task5NetworkProjection, blocks: _Task5BlocksProjection,
  compiled: _Task5CompiledProjection, full_seals: _Task5FullSealSet)
```

The historical scaffold's `_Task5CsrProjection.arrays: Any` is not authority.
An annotation-only owning RED must require `np.ndarray` before array behavior is
implemented. Seeds are exact non-bool built-in integers and may be negative.

## Exact mapping admission

`allowed_mapping_leaves` is an exact tuple of the actual mapping leaf objects
and admission is by identity (`value is leaf`), never equality or a global type
token. An admitted value is either an exact `dict` or an exact
`MappingProxyType` whose finite exact-proxy chain terminates in an exact dict;
backing inspection must invoke no mapping behavior. Equal-but-unlisted objects,
dict subclasses, arbitrary mappings, malformed/cyclic backing, and any caller
behavior fail before iteration/equality/hashing. The exact per-leaf set is:

| Leaf | Identity-admitted mapping objects |
|---|---|
| `compiled.metadata` | current exact `topology.metadata` dict only |
| `compiled.csr_mappings` | current exact node/link dicts and turn mapping-proxy object |
| `static.immutable_csr_mappings` | the three current exact mapping-proxy objects |
| every other receipt leaf | none |

This narrows authority; it does not turn an arbitrary exact dict/proxy into a
capability. Future source-owned capture must type-check the leaf before passing
its identity to the generic serializer.

## Exact 30 leaf counts

Let `N,L,T,B` denote node/link/turn/bridge row counts and `len(...)` the exact
declared tuple/mapping row count. Scalar fingerprints/digests do not add rows.

| # | Leaf | `record_count` |
|---:|---|---|
| 1 | `network.current` | `len(nodes)+len(roads)+len(endpoint_incidence)+len(tile_coordinates)+len(seam_diagnostics)+2` |
| 2 | `blocks.current` | `len(embedding_edges)+len(ramp_incidence)+len(half_edges)+len(boundaries)+len(faces)+len(blocks)+len(tile_clips)+1+len(tile_coordinates)` |
| 3 | `compiled.csr_arrays` | `12` |
| 4 | `compiled.csr_entities` | `N+L+T+B` |
| 5 | `compiled.csr_mappings` | `len(node_map)+len(link_map)+len(turn_map)+1` |
| 6 | `compiled.geometry_catalog` | `1+len(centerlines)+len(assignments)` |
| 7 | `compiled.header` | `1` |
| 8 | `compiled.metadata` | `len(metadata_items)+len(topology.metadata)` |
| 9 | `compiled.node_interface_catalog` | `1+len(interfaces)` |
| 10 | `compiled.numeric_and_crosswalks` | sum of the four numeric/crosswalk tuple lengths |
| 11 | `compiled.section_catalog` | `1+len(profiles)+len(assignments)` |
| 12 | `compiled.topology_entities` | `N+L+T+B` |
| 13 | `task5.blocks_projection` | `len(block_rows)+1` |
| 14 | `task5.compiled_projection` | four policy/crosswalk tuple lengths + four CSR entity tuple lengths + three map-row lengths + `12` |
| 15 | `task5.network_projection` | `len(centers_mm)+2` |
| 16 | `compiled.aggregate` | `13` |
| 17 | `invocation.current` | `1` |
| 18 | `static.block_access_index` | `1` |
| 19 | `static.block_land_use` | `len(block_land_use_rows)` |
| 20 | `static.capacity_certificate` | `1` |
| 21 | `static.fingerprint_set` | `1` |
| 22 | `static.header` | `1` |
| 23 | `static.immutable_csr_arrays` | `12` |
| 24 | `static.immutable_csr_entities` | `N+L+T+B` |
| 25 | `static.immutable_csr_header` | `1` |
| 26 | `static.immutable_csr_mappings` | `len(node_map)+len(link_map)+len(turn_map)+1` |
| 27 | `static.numeric_and_crosswalks` | sum of the four numeric/crosswalk tuple lengths |
| 28 | `static.poi_catalog` | `1+len(pois)` |
| 29 | `static.routing_dependency_key` | `1` |
| 30 | `static.taz_catalog` | `1+len(tazs)+len(block_map)+len(node_owner_map)+len(conflict_rows)` |

The six-style test owns independent literal payload constructors and formulas;
production seal helpers may not supply expected values.

## Registry malformed-incumbent disposition

All lookup and registration work, including descriptor/input copying and stored
candidate reconstruction, occurs inside the single module `RLock`. Lookup of a
malformed/stale candidate atomically deletes it and returns `MISS`. Registration
against a malformed stored candidate atomically deletes the incumbent and
re-raises the unchanged exact exception type/message from defensive
reconstruction without inserting the contender; only a subsequent exhaustive
caller registration may insert. Supported unequal incumbents raise
`ValueError("validation receipt key collision")` and remain unchanged.

`RLock._is_owned()` may be used only by test spies to observe scope. Production
correctness must not depend on that private method.
