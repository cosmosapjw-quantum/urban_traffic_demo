# Hardware Fit Atlas

This diagnostic artifact maps code roles to CPU/Rust/GPU/NN fit. It is not a validation claim or backend authorization.

## Summary

- Report type: hardware_fit_atlas_v1
- Source root: src/metroflow
- Entry count: 1105
- Role tags: array_numeric_core=179, city_generation_topology=338, deterministic_mutation=148, graph_search=125, io_ui_reporting=220, learning_label_surrogate=106, orchestration_state=502, policy_scoring=243
- Hardware fit: cpu_parallel_rust=236, cpu_scalar=465, cpu_simd_numpy=179, custom_cuda_future=126, gpu_tensor_jax=341, gpu_tensor_torch_future=243, keep_python=625, nn_surrogate_candidate=320, no_acceleration=140

## Compact CCoT

- Question: Which code surfaces should move to Rust, stay NumPy/Python, or become GPU/NN candidates?
- Evidence: Scanned 1105 symbols; linked 15 runtime stages; top roles: orchestration_state=502, city_generation_topology=338, policy_scoring=243, io_ui_reporting=220; top fits: keep_python=625, cpu_scalar=465, gpu_tensor_jax=341, nn_surrogate_candidate=320.
- Inference: Backend work should follow role/data-shape evidence, not a single repeated hot-path observation.
- Counterevidence checked: Static fit alone is not accepted as performance evidence; smoke benchmark shares remain diagnostic.
- Decision: Generate 15 decision cards and require measured probes before implementation.
- Falsifier: If linked stage timing and static fit disagree, run a narrower probe before coding a backend.
- Next action: Use decision cards to pick one Rust, NumPy/SIMD, GPU/JAX, or NN label-collection slice.

## Stage Links

| stage | symbols | hardware fit | next probe |
|---|---:|---|---|
| flow_update | 67 | keep_python, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, cpu_scalar, cpu_parallel_rust | Run dense flow batches and split NumPy, optional JAX compile, and steady-state timings. |
| route_candidate_refresh | 104 | nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, cpu_parallel_rust, cpu_simd_numpy, custom_cuda_future, keep_python, no_acceleration, cpu_scalar | Run a copy-inclusive microbench for the linked symbol group. |
| dynamic_potential_recompute | 30 | cpu_parallel_rust, nn_surrogate_candidate, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, gpu_tensor_torch_future, cpu_scalar | Compare cache-hit, Python Dijkstra, Rust Dijkstra, and label extraction time separately. |
| routing_compile_estimate | 162 | cpu_parallel_rust, nn_surrogate_candidate, cpu_simd_numpy, keep_python, gpu_tensor_jax, gpu_tensor_torch_future, custom_cuda_future, cpu_scalar, no_acceleration | Run a copy-inclusive microbench for the linked symbol group. |
| reroute_decision | 30 | nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, cpu_simd_numpy, custom_cuda_future, keep_python, no_acceleration, cpu_scalar, cpu_parallel_rust | Run a copy-inclusive microbench for the linked symbol group. |
| active_agent_update | 31 | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, nn_surrogate_candidate, gpu_tensor_torch_future, keep_python, no_acceleration | Split candidate scoring, budget lookup, action planning, and immutable apply timings. |
| route_candidate_potential | 129 | nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, cpu_parallel_rust, cpu_simd_numpy, custom_cuda_future, keep_python, no_acceleration, cpu_scalar | Compare cache-hit, Python Dijkstra, Rust Dijkstra, and label extraction time separately. |
| route_candidate_path_build | 109 | nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, cpu_parallel_rust, cpu_simd_numpy, custom_cuda_future, keep_python, no_acceleration, cpu_scalar | Run a copy-inclusive microbench for the linked symbol group. |
| route_candidate_metadata | 58 | cpu_parallel_rust, nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, keep_python, no_acceleration, cpu_scalar, cpu_simd_numpy, custom_cuda_future | Batch candidate scoring and measure tensor-friendly array shapes at larger K. |
| active_agent_allocation | 25 | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. |
| active_agent_candidate_selection | 77 | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, custom_cuda_future, keep_python, no_acceleration | Split candidate scoring, budget lookup, action planning, and immutable apply timings. |
| active_agent_pool_write | 34 | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, no_acceleration, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. |
| active_agent_pool_array_write | 44 | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. |
| active_agent_plugin_memory_write | 42 | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. |
| active_agent_movement | 37 | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. |

## Decision Cards

| target | fit | probe | acceptance |
|---|---|---|---|
| flow_update | keep_python, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, cpu_scalar, cpu_parallel_rust | Run dense flow batches and split NumPy, optional JAX compile, and steady-state timings. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| route_candidate_refresh | nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, cpu_parallel_rust, cpu_simd_numpy, custom_cuda_future, keep_python, no_acceleration, cpu_scalar | Run a copy-inclusive microbench for the linked symbol group. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| dynamic_potential_recompute | cpu_parallel_rust, nn_surrogate_candidate, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, gpu_tensor_torch_future, cpu_scalar | Compare cache-hit, Python Dijkstra, Rust Dijkstra, and label extraction time separately. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| routing_compile_estimate | cpu_parallel_rust, nn_surrogate_candidate, cpu_simd_numpy, keep_python, gpu_tensor_jax, gpu_tensor_torch_future, custom_cuda_future, cpu_scalar, no_acceleration | Run a copy-inclusive microbench for the linked symbol group. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| reroute_decision | nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, cpu_simd_numpy, custom_cuda_future, keep_python, no_acceleration, cpu_scalar, cpu_parallel_rust | Run a copy-inclusive microbench for the linked symbol group. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| active_agent_update | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, nn_surrogate_candidate, gpu_tensor_torch_future, keep_python, no_acceleration | Split candidate scoring, budget lookup, action planning, and immutable apply timings. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| route_candidate_potential | nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, cpu_parallel_rust, cpu_simd_numpy, custom_cuda_future, keep_python, no_acceleration, cpu_scalar | Compare cache-hit, Python Dijkstra, Rust Dijkstra, and label extraction time separately. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| route_candidate_path_build | nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, cpu_parallel_rust, cpu_simd_numpy, custom_cuda_future, keep_python, no_acceleration, cpu_scalar | Run a copy-inclusive microbench for the linked symbol group. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| route_candidate_metadata | cpu_parallel_rust, nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, keep_python, no_acceleration, cpu_scalar, cpu_simd_numpy, custom_cuda_future | Batch candidate scoring and measure tensor-friendly array shapes at larger K. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| active_agent_allocation | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| active_agent_candidate_selection | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future, custom_cuda_future, keep_python, no_acceleration | Split candidate scoring, budget lookup, action planning, and immutable apply timings. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| active_agent_pool_write | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, no_acceleration, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| active_agent_pool_array_write | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| active_agent_plugin_memory_write | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |
| active_agent_movement | cpu_scalar, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, keep_python, nn_surrogate_candidate, gpu_tensor_torch_future | Split candidate scoring, budget lookup, action planning, and immutable apply timings. | Open implementation only if the stage exceeds 30% share across three deterministic seeds or a narrow microbench beats baseline including copy/compile. |

## Sample Entries

| symbol | roles | fit | probe |
|---|---|---|---|
| backends.rust_cpu._load_rust_extension | orchestration_state | keep_python | Keep in Python and measure only if it appears in runtime stage timings. |
| backends.rust_cpu.rust_edge_backend_available | orchestration_state | keep_python | Keep in Python and measure only if it appears in runtime stage timings. |
| backends.rust_cpu.rust_flow_backend_available | orchestration_state | keep_python | Keep in Python and measure only if it appears in runtime stage timings. |
| backends.rust_cpu.rust_routing_backend_available | graph_search | cpu_parallel_rust, nn_surrogate_candidate | Measure per-OD graph-search time, cache hit rate, and Rust copy-boundary cost. |
| backends.rust_cpu.rust_reroute_backend_available | policy_scoring | nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future | Collect baseline labels and batch scoring latency before opening NN/GPU work. |
| backends.rust_cpu.rust_agent_backend_available | deterministic_mutation | cpu_scalar, cpu_parallel_rust | Split pack, action planning, and immutable apply timings before backend work. |
| backends.rust_cpu._as_f64_list | array_numeric_core | cpu_simd_numpy | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu._as_f32_list | array_numeric_core | cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu._as_i32_list | array_numeric_core | cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu._as_bool_list | array_numeric_core | cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu._as_f32_routing_list | array_numeric_core | cpu_simd_numpy | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu._as_i32_routing_list | array_numeric_core | cpu_simd_numpy | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu._as_bool_routing_list | array_numeric_core | cpu_simd_numpy | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu._as_i32_agent_list | array_numeric_core | cpu_simd_numpy | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu.evolve_edges_fast_tick_rust | orchestration_state | keep_python | Keep in Python and measure only if it appears in runtime stage timings. |
| backends.rust_cpu.compute_baseline_flow_arrays_rust | array_numeric_core, deterministic_mutation | cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, cpu_scalar, cpu_parallel_rust | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu.compute_dynamic_potential_node_costs_rust | graph_search, array_numeric_core | cpu_parallel_rust, nn_surrogate_candidate, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future | Measure per-OD graph-search time, cache hit rate, and Rust copy-boundary cost. |
| backends.rust_cpu.compute_greedy_route_candidate_rust | graph_search | cpu_parallel_rust, nn_surrogate_candidate | Measure per-OD graph-search time, cache hit rate, and Rust copy-boundary cost. |
| backends.rust_cpu.compute_ranked_route_candidates_rust | graph_search | cpu_parallel_rust, nn_surrogate_candidate | Measure per-OD graph-search time, cache hit rate, and Rust copy-boundary cost. |
| backends.rust_cpu.compute_route_candidate_metadata_rust | graph_search, policy_scoring | cpu_parallel_rust, nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future | Measure per-OD graph-search time, cache hit rate, and Rust copy-boundary cost. |
| backends.rust_cpu.compute_next_link_action_costs_rust | array_numeric_core | cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu.select_route_candidate_index_rust | graph_search, policy_scoring | cpu_parallel_rust, nn_surrogate_candidate, gpu_tensor_jax, gpu_tensor_torch_future | Measure per-OD graph-search time, cache hit rate, and Rust copy-boundary cost. |
| backends.rust_cpu.compute_reroute_decision_rust | array_numeric_core, policy_scoring | cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, nn_surrogate_candidate, gpu_tensor_torch_future | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| backends.rust_cpu.advance_active_agents_rust | array_numeric_core, deterministic_mutation | cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, cpu_scalar, cpu_parallel_rust | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| benchmarks.__getattr__ | io_ui_reporting | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas.HardwareAtlasEntry | io_ui_reporting, orchestration_state | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas.HardwareDecisionCard | io_ui_reporting | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas.build_hardware_atlas | learning_label_surrogate, io_ui_reporting | nn_surrogate_candidate | Collect baseline labels and batch scoring latency before opening NN/GPU work. |
| benchmarks.hardware_atlas.hardware_atlas_to_dict | io_ui_reporting | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas.extract_runtime_stage_timings | io_ui_reporting | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas.link_runtime_stage_timings_to_atlas | io_ui_reporting | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas.format_hardware_atlas_markdown | city_generation_topology, io_ui_reporting | cpu_scalar | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas.render_hardware_atlas_html | io_ui_reporting | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas.write_hardware_atlas_artifact_bundle | io_ui_reporting | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas._iter_atlas_entries | io_ui_reporting | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas._classify_symbol | io_ui_reporting, orchestration_state | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas._node_metrics | io_ui_reporting | keep_python, no_acceleration | Keep in Python and measure only if it appears in runtime stage timings. |
| benchmarks.hardware_atlas._classify_roles | city_generation_topology, graph_search, array_numeric_core, deterministic_mutation, policy_scoring, learning_label_surrogate, io_ui_reporting, orchestration_state | keep_python, cpu_scalar, cpu_parallel_rust, nn_surrogate_candidate, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, gpu_tensor_torch_future | Measure per-OD graph-search time, cache hit rate, and Rust copy-boundary cost. |
| benchmarks.hardware_atlas._classify_data_surface | array_numeric_core, deterministic_mutation, io_ui_reporting, orchestration_state | keep_python, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, cpu_scalar, cpu_parallel_rust | Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state. |
| benchmarks.hardware_atlas._classify_hotspot_signals | graph_search, array_numeric_core, deterministic_mutation, io_ui_reporting, orchestration_state | keep_python, cpu_parallel_rust, cpu_simd_numpy, gpu_tensor_jax, custom_cuda_future, cpu_scalar | Measure per-OD graph-search time, cache hit rate, and Rust copy-boundary cost. |
