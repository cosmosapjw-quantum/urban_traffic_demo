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
