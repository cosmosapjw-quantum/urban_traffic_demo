//! Original V03 packet operations: shadow-only immutable shared-lineage experiment.
//! This module is compiled under cfg(test) only. It is NOT a road engine change.

use super::{Part, PackedTime, PacketParts, portion};
use pyo3::prelude::PyResult;
use std::sync::Arc;


#[derive(Clone, Copy)]
enum LineageOp {
    Scale(f64),
    Restrict { a: PackedTime, b: PackedTime },
    AdvanceOffset,
    RewriteTime { a: PackedTime, b: PackedTime },
}

enum LineageNode {
    Base(Arc<[Part]>),
    Transform { parent: usize, op: LineageOp },
}

#[derive(Default)]
struct LineageArena {
    nodes: Vec<LineageNode>,
}

#[derive(Debug, Clone, Copy)]
struct LineageStats {
    node_count: usize,
    base_rows: usize,
    owned_bytes: usize,
}

impl LineageArena {
    fn base(&mut self, rows: Vec<Part>) -> usize {
        let id = self.nodes.len();
        self.nodes.push(LineageNode::Base(Arc::from(rows.into_boxed_slice())));
        id
    }

    fn push(&mut self, parent: usize, op: LineageOp) -> PyResult<usize> {
        if parent >= self.nodes.len() {
            return Err(super::val("lineage parent outside immutable arena"));
        }
        let id = self.nodes.len();
        self.nodes.push(LineageNode::Transform { parent, op });
        Ok(id)
    }

    fn scale(&mut self, parent: usize, fraction: f64) -> PyResult<usize> {
        if !fraction.is_finite() || !(0.0..=1.0).contains(&fraction) {
            return Err(super::val("nonfinite or nonphysical lineage fraction"));
        }
        self.push(parent, LineageOp::Scale(fraction))
    }

    fn restrict(&mut self, parent: usize, a: f64, b: f64) -> PyResult<usize> {
        if !a.is_finite() || !b.is_finite() || b <= a {
            return Err(super::val("invalid lineage interval boundaries"));
        }
        self.push(parent, LineageOp::Restrict {
            a: PackedTime::new(Some(a))?,
            b: PackedTime::new(Some(b))?,
        })
    }

    fn advance_offset(&mut self, parent: usize) -> PyResult<usize> {
        self.push(parent, LineageOp::AdvanceOffset)
    }

    fn rewrite_time(&mut self, parent: usize, a: f64, b: f64) -> PyResult<usize> {
        if !a.is_finite() || !b.is_finite() || b < a {
            return Err(super::val("invalid physical event time rewrite"));
        }
        self.push(parent, LineageOp::RewriteTime {
            a: PackedTime::new(Some(a))?,
            b: PackedTime::new(Some(b))?,
        })
    }

    fn stats(&self) -> LineageStats {
        let base_rows = self.nodes.iter().map(|node| match node {
            LineageNode::Base(parts) => parts.len(),
            _ => 0,
        }).sum::<usize>();
        LineageStats {
            node_count: self.nodes.len(),
            base_rows,
            owned_bytes: self.nodes.capacity().saturating_mul(std::mem::size_of::<LineageNode>())
                .saturating_add(base_rows.saturating_mul(std::mem::size_of::<Part>())),
        }
    }

    fn visit(
        &self,
        node_id: usize,
        mut emit: impl FnMut(Part) -> PyResult<()>,
    ) -> PyResult<usize> {
        let mut reverse_ops: Vec<LineageOp> = Vec::new();
        let mut cursor = node_id;
        let source: &Arc<[Part]> = loop {
            let node = self.nodes.get(cursor)
                .ok_or_else(|| super::val("invalid lineage node id"))?;
            match node {
                LineageNode::Base(parts) => break parts,
                LineageNode::Transform { parent, op } => {
                    reverse_ops.push(*op);
                    cursor = *parent;
                }
            }
        };
        reverse_ops.reverse();
        let mut emitted = 0;
        'source_row: for &initial in source.iter() {
            let mut p = initial;
            for op in &reverse_ops {
                match *op {
                    LineageOp::Scale(f) => {
                        let m = p.mass * f;
                        if !(m > 0.0) {
                            continue 'source_row;
                        }
                        p.mass = m;
                        p.birth *= f;
                    }
                    LineageOp::Restrict { a, b } => {
                        let (start, end) = (a.unwrap(), b.unwrap());
                        let (pa, pb) = (
                            p.a.option().ok_or_else(|| super::val("lineage Part start absent"))?,
                            p.b.option().ok_or_else(|| super::val("lineage Part end absent"))?,
                        );
                        if !(pa <= start && pb >= end && pb > pa) {
                            continue 'source_row;
                        }
                        p.mass = p.mass * (end-start) / (pb-pa);
                        p.birth = p.birth * (end-start) / (pb-pa);
                        p.a = a;
                        p.b = b;
                    }
                    LineageOp::AdvanceOffset => {
                        p.offset = p.offset.checked_add(1)
                            .ok_or_else(|| super::val("lineage route offset overflow"))?;
                    }
                    LineageOp::RewriteTime { a, b } => {
                        p.a = a;
                        p.b = b;
                    }
                }
            }
            emit(p)?;
            emitted += 1;
        }
        Ok(emitted)
    }

    /// Shadow-only adapter to the original seven-field EventRow shape.
    /// No Vec<EventRow> is created here: the consumer owns each emitted row.
    /// A real V03 integration must additionally preserve source priority,
    /// time/route resolution, receiving supply and original event ordering.
    fn visit_event_rows(
        &self,
        node_id: usize,
        source_cell: usize,
        mut destination: impl FnMut(&Part) -> Option<usize>,
        start_time: f64,
        end_time: f64,
        mut emit: impl FnMut(super::EventRow) -> PyResult<()>,
    ) -> PyResult<usize> {
        if !start_time.is_finite() || !end_time.is_finite() || end_time < start_time {
            return Err(super::val("invalid original event time interval"));
        }
        self.visit(node_id, |p| {
            emit((
                p.tag, source_cell, destination(&p), p.mass,
                start_time, end_time, p.birth,
            ))
        })
    }

    fn materialize(&self, node_id: usize) -> PyResult<Vec<Part>> {
        let mut out = Vec::new();
        self.visit(node_id, |p| {
            if out.len() == out.capacity() {
                out.try_reserve(1)
                    .map_err(|_| super::budget("lineage materialization allocation unavailable"))?;
            }
            out.push(p);
            Ok(())
        })?;
        Ok(out)
    }
}

#[cfg(test)]
mod exact_shadow_tests {
    use super::*;

    fn row(tag: usize, mass: f64, birth: f64, start: f64, end: f64) -> Part {
        Part {
            tag, offset: tag % 4, mass, birth,
            a: PackedTime::new(Some(start)).unwrap(),
            b: PackedTime::new(Some(end)).unwrap(),
        }
    }

    fn signature(p: Part) -> (usize, usize, u64, u64, u64, u64) {
        (p.tag, p.offset, p.mass.to_bits(), p.birth.to_bits(), p.a.unwrap().to_bits(), p.b.unwrap().to_bits())
    }

    #[test]
    fn nested_proportional_split_is_exact_per_field_not_collapsed_fraction() {
        let rows = vec![
            row(3, 0.1, 0.1, -0.0, 2.0),
            row(1, 0.33, 0.19, 0.0, 3.0),
            row(3, 0.0, 0.0, 0.0, 0.0),
            row(5, 0.78, 0.17, 2.0, 4.0),
        ];
        let packed = PacketParts::pack(rows.clone(), |_| Ok(())).unwrap();
        let once = portion(&packed, 0.3).unwrap();
        let twice = portion(&PacketParts::pack(once, |_| Ok(())).unwrap(), 0.7).unwrap();

        let mut arena = LineageArena::default();
        let root = arena.base(rows);
        let first = arena.scale(root, 0.3).unwrap();
        let second = arena.scale(first, 0.7).unwrap();
        let replay = arena.materialize(second).unwrap();
        assert_eq!(replay.iter().copied().map(signature).collect::<Vec<_>>(),
                   twice.iter().copied().map(signature).collect::<Vec<_>>());
        assert_ne!((0.1f64 * 0.3 * 0.7).to_bits(), (0.1f64 * (0.3 * 0.7)).to_bits());
        assert_eq!(arena.stats().base_rows, 4);
        assert_eq!(arena.stats().node_count, 3);
    }

    #[test]
    fn served_and_remainder_share_immutable_input_without_mass_smearing() {
        let parts = (1..=160).map(|i| row(i%13, i as f64/1000.0, i as f64/1700.0, 1.0, 4.0)).collect::<Vec<_>>();
        let mut arena=LineageArena::default();
        let root=arena.base(parts.clone());
        let served=arena.scale(root, 0.29).unwrap();
        let remainder=arena.scale(root, 1.0-0.29).unwrap();
        let served_eager=portion(&PacketParts::pack(parts.clone(), |_| Ok(())).unwrap(),0.29).unwrap();
        let remainder_eager=portion(&PacketParts::pack(parts, |_| Ok(())).unwrap(),1.0-0.29).unwrap();
        assert_eq!(arena.materialize(served).unwrap().into_iter().map(signature).collect::<Vec<_>>(),
                   served_eager.into_iter().map(signature).collect::<Vec<_>>());
        assert_eq!(arena.materialize(remainder).unwrap().into_iter().map(signature).collect::<Vec<_>>(),
                   remainder_eager.into_iter().map(signature).collect::<Vec<_>>());
        assert_eq!(arena.stats().node_count,3);
        assert_eq!(arena.stats().base_rows,160);
        assert!(arena.stats().owned_bytes < 160*2*std::mem::size_of::<Part>());
    }

    #[test]
    fn interval_split_transform_retains_original_order_birth_and_signed_boundary() {
        let original = vec![
            row(2, 0.7, 0.123, -0.0, 3.0),
            row(3, 0.1, 0.023, 0.0, 1.0),
            row(4, 0.3, 0.043, 1.0, 3.0),
            row(5, 0.5, 0.053, 0.0, 0.0),
            row(6, 0.9, 0.063, 2.0, 3.0),
        ];
        let mut expected = Vec::new();
        for &p in &original {
            let (pa,pb)=(p.a.unwrap(), p.b.unwrap());
            if pa <= 0.0 && pb >= 1.0 && pb > pa {
                let mut q=p;
                q.mass = q.mass * (1.0-0.0) / (pb-pa);
                q.birth = q.birth * (1.0-0.0) / (pb-pa);
                q.a=PackedTime::new(Some(0.0)).unwrap();
                q.b=PackedTime::new(Some(1.0)).unwrap();
                expected.push(q);
            }
        }
        let mut arena=LineageArena::default();
        let root=arena.base(original);
        let restricted=arena.restrict(root, 0.0, 1.0).unwrap();
        let actual=arena.materialize(restricted).unwrap();
        assert_eq!(actual.into_iter().map(signature).collect::<Vec<_>>(),
                   expected.into_iter().map(signature).collect::<Vec<_>>());
    }

    #[test]
    fn rewind_mixed_rewrite_keeps_same_metadata_and_all_float_bits() {
        let original=vec![row(0, 0.7, 0.123, -0.0, 3.0),row(3, 0.1, 0.34, 0.0, 0.0)];
        let mut arena=LineageArena::default();
        let root=arena.base(original.clone());
        let child=arena.scale(root,0.5).unwrap();
        let next=arena.advance_offset(child).unwrap();
        let now=arena.rewrite_time(next, -0.0, 5.0).unwrap();
        let mut expected=original;
        for p in &mut expected {
            p.mass*=0.5;
            p.birth*=0.5;
            p.offset+=1;
            p.a=PackedTime::new(Some(-0.0)).unwrap();
            p.b=PackedTime::new(Some(5.0)).unwrap();
        }
        assert_eq!(arena.materialize(now).unwrap().into_iter().map(signature).collect::<Vec<_>>(),
                   expected.into_iter().map(signature).collect::<Vec<_>>());
    }

    #[test]
    fn repeated_deep_trace_uses_iterative_evaluation_and_no_recursive_drop() {
        let mut arena=LineageArena::default();
        let base=arena.base(vec![row(1,0.4,0.2,1.0,2.0)]);
        let mut id=base;
        for _ in 0..20000 {
            id=arena.scale(id,1.0).unwrap();
        }
        let now=arena.materialize(id).unwrap();
        assert_eq!(now.len(),1);
        assert_eq!(signature(now[0]),signature(row(1,0.4,0.2,1.0,2.0)));
        assert_eq!(arena.stats().node_count,20001);
    }

    #[test]
    fn nonfinite_bad_fraction_or_invalid_handle_is_a_real_error() {
        let mut arena=LineageArena::default();
        let base=arena.base(vec![row(0,1.0,0.0,0.0,1.0)]);
        for f in [f64::NAN,f64::INFINITY,-0.1,1.1] {
            assert!(arena.scale(base,f).is_err());
        }
        assert!(arena.scale(999,0.3).is_err());
        assert!(arena.restrict(base,1.0,0.0).is_err());
        assert!(arena.restrict(base,0.0,f64::NAN).is_err());
    }

    #[test]
    fn streamed_rows_are_order_and_bit_identical_to_materialized_reference() {
        let mut arena=LineageArena::default();
        let root=arena.base((1..=64).map(|i| row(i%7, i as f64/1000.0, 0.002*i as f64,0.0,3.0)).collect());
        let child=arena.scale(root,0.25).unwrap();
        let id=arena.rewrite_time(child,0.0,4.0).unwrap();
        let mut observed=Vec::new();
        let count=arena.visit(id,|p| {observed.push(signature(p));Ok(())}).unwrap();
        assert_eq!(count,observed.len());
        let eager=arena.materialize(id).unwrap().into_iter().map(signature).collect::<Vec<_>>();
        assert_eq!(observed,eager);
    }
}


#[cfg(test)]
mod independent_shadow_adversarial_tests {
    use super::*;

    fn row(tag: usize, mass: f64, birth: f64, a: f64, b: f64) -> Part {
        Part {
            tag,
            offset: tag % 5,
            mass, birth,
            a: PackedTime::new(Some(a)).unwrap(),
            b: PackedTime::new(Some(b)).unwrap(),
        }
    }

    fn bits(p: Part) -> (usize, usize, u64, u64, u64, u64) {
        (p.tag,p.offset,p.mass.to_bits(),p.birth.to_bits(),
         p.a.unwrap().to_bits(),p.b.unwrap().to_bits())
    }

    #[test]
    fn deterministic_random_nested_serve_remainder_against_original_portion() {
        let mut seed = 0xF00D_2026_0019u64;
        for size in [1, 2, 19, 61, 160] {
            let mut rows = Vec::new();
            for i in 0..size {
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let mass = f64::from_bits(0x3fb0000000000000 + ((seed >> 7) & 0xffff));
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let birth = f64::from_bits(0x3fb0000000000000 + ((seed >> 9) & 0xffff));
                rows.push(row(i%9, mass, birth, 0.0, 5.0));
            }
            let mut arena = LineageArena::default();
            let root = arena.base(rows.clone());
            let mut id = root;
            let mut eager = rows;
            for step in 0..17 {
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let fraction = if step==8 && size==1 {0.0} else if step==10 {1.0} else {
                    ((seed >> 16) % 1024) as f64 / 1024.0
                };
                id = arena.scale(id, fraction).unwrap();
                let packed = PacketParts::pack(eager, |_|Ok(())).unwrap();
                eager = portion(&packed, fraction).unwrap();
                assert_eq!(arena.materialize(id).unwrap().into_iter().map(bits).collect::<Vec<_>>(),
                           eager.iter().copied().map(bits).collect::<Vec<_>>(),
                           "random nested original portion: size={size}, step={step}");
            }
            assert_eq!(arena.stats().base_rows,size);
            assert_eq!(arena.stats().node_count,18);
        }
    }

    #[test]
    fn distinct_order_and_time_support_survive_nonassociative_rewrites() {
        let mut arena = LineageArena::default();
        let source = vec![
            row(2, 0.7, 0.11, -0.0, 4.0),
            row(3, 0.1, 0.19, 0.0, 2.0),
            row(5, 0.9, 0.07, 1.0, 4.0),
            row(4, 0.3, 0.73, 0.0, 4.0),
        ];
        let root=arena.base(source.clone());
        let scale=arena.scale(root,0.3).unwrap();
        let first=arena.restrict(scale,0.0,2.0).unwrap();
        let second=arena.advance_offset(first).unwrap();
        let third=arena.rewrite_time(second,-0.0,1.75).unwrap();
        let mut reference=portion(&PacketParts::pack(source, |_|Ok(())).unwrap(),0.3).unwrap();
        reference.retain(|p| p.a.unwrap()<=0.0 && p.b.unwrap()>=2.0 && p.b>p.a);
        for p in &mut reference {
            let (pa,pb)=(p.a.unwrap(),p.b.unwrap());
            p.mass=p.mass*(2.0-0.0)/(pb-pa);
            p.birth=p.birth*(2.0-0.0)/(pb-pa);
            p.offset+=1;
            p.a=PackedTime::new(Some(-0.0)).unwrap();
            p.b=PackedTime::new(Some(1.75)).unwrap();
        }
        assert_eq!(arena.materialize(third).unwrap().into_iter().map(bits).collect::<Vec<_>>(),
                   reference.into_iter().map(bits).collect::<Vec<_>>());
    }

    #[test]
    fn subnormal_mass_drop_matches_exact_original_ieee_predicate() {
        let min=f64::from_bits(1);
        let rows=vec![
            row(1,min,min,0.0,1.0),
            row(2,f64::from_bits(2),f64::from_bits(2),0.0,1.0),
            row(3,0.1,0.3,-0.0,1.0),
        ];
        let mut arena=LineageArena::default();
        let root=arena.base(rows.clone());
        let view=arena.scale(root,0.5).unwrap();
        let old=portion(&PacketParts::pack(rows, |_|Ok(())).unwrap(),0.5).unwrap();
        assert_eq!(arena.materialize(view).unwrap().into_iter().map(bits).collect::<Vec<_>>(),
                   old.iter().copied().map(bits).collect::<Vec<_>>());
        assert_eq!(old.len(),2);
    }
}


#[cfg(test)]
mod shadow_storage_benchmark {
    use super::*;
    use std::hint::black_box;
    use std::time::Instant;

    #[test]
    #[ignore]
    fn benchmark_immutable_lineage_vs_eager_retained_rows() {
        // This is a deliberately *independent same-template* storage workload.
        // Unlike actual congested V03, it has no downstream materialization,
        // new source offers, multi-input merge or nonlinear junction dynamics.
        // The fractions are deterministic synthetic inputs, NOT fitted physics.
        let input_rows=160usize;
        let event_count=8192usize;
        let base: Vec<Part>=(0..input_rows).map(|i| Part {
            tag:i%19,
            offset:i%4,
            mass:0.001+(i as f64)*0.000003,
            birth:0.00001+(i as f64)*0.0000023,
            a:PackedTime::new(Some(0.0)).unwrap(),
            b:PackedTime::new(Some(3.0)).unwrap(),
        }).collect();
        let packed=PacketParts::pack(base.clone(), |_|Ok(())).unwrap();

        let eager_begin=Instant::now();
        let mut eager=Vec::with_capacity(event_count);
        for k in 0..event_count {
            let f=((k%61)+1) as f64/64.0;
            let served=portion(&packed,f).unwrap();
            let rest=portion(&packed,1.0-f).unwrap();
            eager.push((served,rest));
        }
        let eager_build_ns=eager_begin.elapsed().as_nanos();
        let eager_row_count:usize=eager.iter().map(|(a,b)|a.len()+b.len()).sum();
        let eager_bytes:usize=eager.iter().map(|(a,b)|a.capacity()+b.capacity()).sum::<usize>()
            .saturating_mul(std::mem::size_of::<Part>());

        let shadow_begin=Instant::now();
        let mut arena=LineageArena::default();
        let root=arena.base(base);
        let mut ids=Vec::with_capacity(event_count);
        for k in 0..event_count {
            let f=((k%61)+1) as f64/64.0;
            let served=arena.scale(root,f).unwrap();
            let rest=arena.scale(root,1.0-f).unwrap();
            ids.push((served,rest));
        }
        let shadow_build_ns=shadow_begin.elapsed().as_nanos();
        let structural_bytes=arena.stats().owned_bytes+
            ids.capacity()*std::mem::size_of::<(usize,usize)>();
        assert_eq!(arena.stats().base_rows,input_rows);
        assert_eq!(arena.stats().node_count,1+event_count*2);
        assert_eq!(eager_row_count,input_rows*event_count*2);
        assert!(structural_bytes < eager_bytes/10);

        // Eager consumers already holding all explicit rows still must read
        // every row: time and data volume are NOT improved by pointer sharing.
        let eager_scan_begin=Instant::now();
        let mut eager_hash=0u64;
        let mut eager_count=0usize;
        for (a,b) in &eager {
            for row in a.iter().chain(b.iter()) {
                eager_count+=1;
                eager_hash=eager_hash.wrapping_mul(0x100000001b3)
                    ^ row.mass.to_bits() ^ row.birth.to_bits();
            }
        }
        let eager_scan_ns=eager_scan_begin.elapsed().as_nanos();

        let shadow_stream_begin=Instant::now();
        let mut shadow_hash=0u64;
        let mut shadow_count=0usize;
        for &(a,b) in &ids {
            for id in [a,b] {
                arena.visit(id,|row| {
                    shadow_count+=1;
                    shadow_hash=shadow_hash.wrapping_mul(0x100000001b3)
                        ^ row.mass.to_bits() ^ row.birth.to_bits();
                    Ok(())
                }).unwrap();
            }
        }
        let shadow_stream_ns=shadow_stream_begin.elapsed().as_nanos();
        assert_eq!(shadow_count,eager_count);
        assert_eq!(shadow_hash,eager_hash);
        black_box((shadow_hash,shadow_count,eager_hash,eager_count));

        println!(
            "V03_LINEAGE_BENCH rows={} events={} eager_copied_rows={} eager_owned_part_bytes={} shadow_node_count={} shadow_retained_bytes={} eager_build_ns={} shadow_build_ns={} eager_scan_ns={} shadow_stream_ns={} checksum_bits={:016x}",
            input_rows,event_count,eager_row_count,eager_bytes,arena.stats().node_count,
            structural_bytes,eager_build_ns,shadow_build_ns,eager_scan_ns,shadow_stream_ns,
            shadow_hash);
    }
}


#[cfg(test)]
mod shadow_event_consumer_tests {
    use super::*;
    use super::super::EventRow;

    fn fingerprint(e: EventRow) -> (usize, usize, Option<usize>, u64, u64, u64, u64) {
        (e.0,e.1,e.2,e.3.to_bits(),e.4.to_bits(),e.5.to_bits(),e.6.to_bits())
    }

    #[test]
    fn event_consumer_stream_is_bit_identical_to_original_eager_event_rows() {
        let rows=(0..48).map(|i| Part {
            tag:i%9,offset:i%3,
            mass:0.1+(i as f64)*0.0031,
            birth:0.02+(i as f64)*0.0022,
            a:PackedTime::new(Some(0.0)).unwrap(),
            b:PackedTime::new(Some(6.0)).unwrap(),
        }).collect::<Vec<_>>();
        let f=0.37;
        let original=portion(&PacketParts::pack(rows.clone(), |_|Ok(())).unwrap(),f).unwrap();
        let expected=original.iter().map(|p| (
            p.tag,7,Some((p.tag+p.offset)%3),p.mass,-0.0,2.5,p.birth
        )).map(fingerprint).collect::<Vec<_>>();
        let mut arena=LineageArena::default();
        let root=arena.base(rows);
        let selected=arena.scale(root,f).unwrap();
        let mut actual=Vec::new();
        let emitted=arena.visit_event_rows(
            selected,7,|p|Some((p.tag+p.offset)%3),-0.0,2.5,
            |row| {actual.push(fingerprint(row));Ok(())}
        ).unwrap();
        assert_eq!(emitted,expected.len());
        assert_eq!(actual,expected);
    }

    #[test]
    fn invalid_event_clock_refused_without_mutating_source_arena() {
        let mut arena=LineageArena::default();
        let root=arena.base(vec![Part {
            tag:1,offset:0,mass:1.0,birth:0.1,
            a:PackedTime::new(Some(0.0)).unwrap(),
            b:PackedTime::new(Some(1.0)).unwrap(),
        }]);
        assert!(arena.visit_event_rows(root,1,|_|None,3.0,2.0,|_|Ok(())).is_err());
        assert!(arena.visit_event_rows(root,1,|_|None,f64::NAN,4.0,|_|Ok(())).is_err());
        assert_eq!(arena.materialize(root).unwrap().len(),1);
    }

    #[test]
    fn fallible_consumer_stops_stream_and_preserves_source_for_retry() {
        let mut arena=LineageArena::default();
        let root=arena.base((0..5).map(|tag| Part {
            tag,offset:tag,mass:0.1+tag as f64/100.0,birth:0.01,
            a:PackedTime::new(Some(0.0)).unwrap(),
            b:PackedTime::new(Some(2.0)).unwrap(),
        }).collect());
        let view=arena.scale(root,0.5).unwrap();
        let before=arena.materialize(view).unwrap();
        let mut attempted=0usize;
        let result=arena.visit_event_rows(view,3,|p|Some(p.offset),0.0,2.0,|_row| {
            attempted+=1;
            if attempted==3 {
                return Err(super::super::val("synthetic downstream receiver failure"));
            }
            Ok(())
        });
        assert!(result.is_err());
        assert_eq!(attempted,3);
        assert_eq!(arena.materialize(view).unwrap().iter().copied()
                   .map(|p|(p.tag,p.mass.to_bits(),p.birth.to_bits()))
                   .collect::<Vec<_>>(),
                   before.iter().copied().map(|p|(p.tag,p.mass.to_bits(),p.birth.to_bits()))
                   .collect::<Vec<_>>());
        // A real network consumer must rollback prior external emissions;
        // the shadow intentionally does not claim transactional atomicity.
    }
}

#[cfg(test)]
mod original_served_stream_oracles {
    use super::*;
    use super::super::served_parts;

    fn fields(p:Part)->(usize,usize,u64,u64,Option<u64>,Option<u64>) {
        (p.tag,p.offset,p.mass.to_bits(),p.birth.to_bits(),
         p.a.option().map(f64::to_bits),p.b.option().map(f64::to_bits))
    }

    #[test]
    fn original_portion_vs_served_iterator_are_exact_for_mixed_and_uniform() {
        let mut rows=Vec::new();
        rows.push(Part {tag:3,offset:1,mass:0.1,birth:0.3,
            a:PackedTime::new(Some(-0.0)).unwrap(),b:PackedTime::new(Some(2.0)).unwrap()});
        rows.push(Part {tag:4,offset:2,mass:f64::from_bits(1),birth:f64::from_bits(1),
            a:PackedTime::new(Some(0.0)).unwrap(),b:PackedTime::new(Some(2.0)).unwrap()});
        for i in 0..159usize {
            rows.push(Part {tag:i%9,offset:i%3,
                mass:(i as f64+1.0)/1300.0,
                birth:(i as f64+0.2)/5300.0,
                a:PackedTime::new(Some(0.0)).unwrap(),
                b:PackedTime::new(Some(if i%3==0 {2.0} else {3.0})).unwrap()});
        }
        let mixed=PacketParts::pack(rows.clone(), |_|Ok(())).unwrap();
        let uniform=PacketParts::pack(rows.iter().copied().map(|mut p|{
            p.a=PackedTime::new(Some(0.0)).unwrap();
            p.b=PackedTime::new(Some(1.0)).unwrap(); p
        }).collect(), |_|Ok(())).unwrap();
        for packet in [&mixed,&uniform] {
            for fraction in [0.0,1.0,0.3,0.7,f64::from_bits(1),-0.0] {
                let eager=portion(packet,fraction).unwrap();
                let streamed=served_parts(packet,fraction).collect::<Vec<_>>();
                assert_eq!(eager.iter().copied().map(fields).collect::<Vec<_>>(),
                           streamed.iter().copied().map(fields).collect::<Vec<_>>());
                let eager_sum=super::super::sum(eager.iter().map(|p|p.mass));
                let stream_sum=super::super::sum(served_parts(packet,fraction).map(|p|p.mass));
                assert_eq!(eager_sum.to_bits(),stream_sum.to_bits());
            }
        }
    }

    #[test]
    fn deterministic_random_head_stream_preserves_ieee_first_birth_moment_and_sum() {
        let mut seed=0x2026_1120_aabb_u64;
        for len in [1usize,17,128,1024] {
            let mut rows=Vec::new();
            for i in 0..len {
                seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let mass=f64::from_bits(0x3fb0000000000000+(seed&0xffff));
                seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let birth=f64::from_bits(0x3fa0000000000000+(seed&0xffff));
                rows.push(Part{tag:i%11,offset:i%4,mass,birth,
                    a:PackedTime::new(Some(0.0)).unwrap(),
                    b:PackedTime::new(Some(2.0)).unwrap()});
            }
            let pack=PacketParts::pack(rows, |_|Ok(())).unwrap();
            for step in 0..23 {
                let fraction=((step*71+17)%1024) as f64/1024.0;
                let eager=portion(&pack,fraction).unwrap();
                let got=served_parts(&pack,fraction).collect::<Vec<_>>();
                assert_eq!(eager.iter().copied().map(fields).collect::<Vec<_>>(),
                    got.iter().copied().map(fields).collect::<Vec<_>>());
                assert_eq!(
                    super::super::sum(eager.iter().map(|p|p.mass)).to_bits(),
                    super::super::sum(served_parts(&pack,fraction).map(|p|p.mass)).to_bits()
                );
            }
        }
    }
}
