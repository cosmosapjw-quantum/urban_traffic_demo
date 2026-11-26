//! Exact nonnegative min-plus row kernel. No reassociation, FMA, or fast-math.
pub(crate) fn available() -> bool {
    #[cfg(target_arch = "x86_64")]
    {
        std::is_x86_feature_detected!("avx")
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        false
    }
}
pub(crate) fn scalar(row: &mut [f64], pivot: &[f64], x: f64) {
    for (d, &y) in row.iter_mut().zip(pivot) {
        *d = d.min(x + y)
    }
}
#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx")]
unsafe fn avx(row: &mut [f64], pivot: &[f64], x: f64) {
    use std::arch::x86_64::*;
    let base = _mm256_set1_pd(x);
    let n = row.len() / 4 * 4;
    for i in (0..n).step_by(4) {
        // SAFETY: both slices have equal length and i+4 <= n <= len.
        unsafe {
            let d = _mm256_loadu_pd(row.as_ptr().add(i));
            let y = _mm256_loadu_pd(pivot.as_ptr().add(i));
            let z = _mm256_min_pd(d, _mm256_add_pd(base, y));
            _mm256_storeu_pd(row.as_mut_ptr().add(i), z);
        }
    }
    scalar(&mut row[n..], &pivot[n..], x)
}
pub(crate) fn update(row: &mut [f64], pivot: &[f64], x: f64, vector: bool) {
    assert_eq!(row.len(), pivot.len());
    #[cfg(target_arch = "x86_64")]
    if vector && available() {
        // SAFETY: runtime CPU feature check and equal slice lengths.
        unsafe { avx(row, pivot, x) };
        return;
    }
    let _ = vector;
    scalar(row, pivot, x)
}
pub(crate) fn closure(d: &mut [f64], n: usize, vector: bool) {
    assert_eq!(d.len(), n * n);
    let mut pivot = vec![0.; n];
    for k in 0..n {
        pivot.copy_from_slice(&d[k * n..(k + 1) * n]);
        for row in d.chunks_mut(n) {
            let x = row[k];
            update(row, &pivot, x, vector);
        }
    }
}
#[cfg(feature = "native-cli")]
pub fn benchmark() -> serde_json::Value {
    use std::{hint::black_box, time::Instant};
    let mut results = vec![];
    for n in [16, 64, 128, 256] {
        // Deterministic synthetic positive sparse graph; keep infinities.
        let seed: Vec<_> = (0..n * n)
            .map(|i| {
                let (a, b) = (i / n, i % n);
                if a == b {
                    0.
                } else if (a + b) % 7 == 0 || (a + 1) % n == b {
                    1. + ((a * 31 + b * 17) % 113) as f64 / 7.
                } else {
                    f64::INFINITY
                }
            })
            .collect();
        let mut oracle = seed.clone();
        closure(&mut oracle, n, false);
        let mut scalar = vec![];
        let mut avx = vec![];
        for i in 0..9 {
            for vector in if i % 2 == 0 {
                [false, true]
            } else {
                [true, false]
            } {
                let mut data = seed.clone();
                let t = Instant::now();
                closure(black_box(&mut data), n, vector);
                let elapsed = t.elapsed().as_secs_f64();
                assert!(data
                    .iter()
                    .zip(&oracle)
                    .all(|(a, b)| a.to_bits() == b.to_bits()));
                if vector {
                    avx.push(elapsed)
                } else {
                    scalar.push(elapsed)
                }
            }
        }
        scalar.sort_by(f64::total_cmp);
        avx.sort_by(f64::total_cmp);
        results.push(serde_json::json!({"n":n,"scalar_s":scalar,"avx_s":avx,"scalar_median_s":scalar[4],"avx_median_s":avx[4],"speedup":scalar[4]/avx[4],"bit_exact":true}));
    }
    serde_json::json!({"scope":"nonnegative min-plus synthetic matrices; no full-city acceleration claim","avx_available":available(),"results":results})
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vector_bits_including_tail_and_infinity() {
        for n in 1..257 {
            let pivot: Vec<_> = (0..n)
                .map(|i| {
                    if i % 3 == 0 {
                        f64::INFINITY
                    } else {
                        i as f64 / 7.
                    }
                })
                .collect();
            for x in [0., 1.25, f64::INFINITY] {
                let mut a: Vec<_> = (0..n)
                    .map(|i| {
                        if i % 2 == 0 {
                            f64::INFINITY
                        } else {
                            i as f64 / 3.
                        }
                    })
                    .collect();
                let mut b = a.clone();
                update(&mut a, &pivot, x, false);
                update(&mut b, &pivot, x, true);
                assert!(a.iter().zip(&b).all(|(x, y)| x.to_bits() == y.to_bits()));
            }
        }
    }
}
