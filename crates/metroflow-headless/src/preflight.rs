//! Stable indexed rank preparation. Vectorization is limited to independent
//! capacity comparisons; event order and floating-point summation are unchanged.
use crate::input::{Input, FOOTPRINT};
use rayon::prelude::*;

fn scalar(m: [f64; 4], s: [f64; 4], r: [f64; 4], c: [f64; 4]) -> bool {
    (0..4).all(|i| m[i] <= r[i] && s[i] <= c[i])
}
#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx")]
unsafe fn avx(m: [f64; 4], s: [f64; 4], r: [f64; 4], c: [f64; 4]) -> bool {
    use std::arch::x86_64::*;
    let a = _mm256_cmp_pd::<_CMP_LE_OQ>(_mm256_loadu_pd(m.as_ptr()), _mm256_loadu_pd(r.as_ptr()));
    let b = _mm256_cmp_pd::<_CMP_LE_OQ>(_mm256_loadu_pd(s.as_ptr()), _mm256_loadu_pd(c.as_ptr()));
    _mm256_movemask_pd(_mm256_and_pd(a, b)) == 15
}
pub fn available() -> bool {
    #[cfg(target_arch = "x86_64")]
    {
        std::is_x86_feature_detected!("avx")
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        false
    }
}
pub fn ranks(input: &Input, mesh: f64, vector: bool) -> Result<Vec<u32>, String> {
    if !mesh.is_finite() || mesh <= 0. {
        return Err("invalid mesh".into());
    }
    let bounds = input.route_bounds();
    let use_avx = vector && available();
    let mut bins = vec![0; input.groups.len()];
    let errors: Vec<Result<(), String>> = bins
        .par_chunks_mut(512)
        .zip(input.groups.par_chunks(512))
        .map(|(out, groups)| {
            for (out, g) in out.chunks_mut(4).zip(groups.chunks(4)) {
                let (mut m, mut s, mut r, mut c) = ([0.; 4], [0.; 4], [0.; 4], [0.; 4]);
                for (i, g) in g.iter().enumerate() {
                    let w = input.windows[g.purpose as usize];
                    let b = ((w[1] - w[0]).max(w[3] - w[2]) / mesh).ceil().max(1.);
                    if b > u32::MAX as f64 {
                        return Err("rank count overflow".into());
                    }
                    out[i] = b as u32;
                    m[i] = g.mass / b;
                    s[i] = m[i] * FOOTPRINT[g.class as usize];
                    let q = bounds[g.forward as usize];
                    c[i] = q[0];
                    r[i] = q[1];
                    if let Some(back) = g.backward {
                        let q = bounds[back as usize];
                        c[i] = c[i].min(q[0]);
                        r[i] = r[i].min(q[1]);
                    }
                }
                #[cfg(target_arch = "x86_64")]
                let ok = if use_avx {
                    // SAFETY: checked CPU support above; all loads are four f64.
                    unsafe { avx(m, s, r, c) }
                } else {
                    scalar(m, s, r, c)
                };
                #[cfg(not(target_arch = "x86_64"))]
                let ok = {
                    let _ = use_avx;
                    scalar(m, s, r, c)
                };
                if !ok {
                    return Err("batch exceeds receiving/storage".into());
                }
            }
            Ok(())
        })
        .collect();
    for e in errors {
        e?;
    }
    Ok(bins)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vector_matches_scalar() {
        for i in 0..=4 {
            let m = [1.; 4];
            let mut c = [5.; 4];
            if i < 4 {
                c[i] = 4.999999999999999;
            }
            let want = scalar(m, [5.; 4], [1.; 4], c);
            #[cfg(target_arch = "x86_64")]
            if available() {
                assert_eq!(want, unsafe { avx(m, [5.; 4], [1.; 4], c) });
            }
            assert_eq!(want, i == 4);
        }
    }
}
