//! Frozen-target passage used by the historical projection, in Rust.
use crate::input::Result;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct Kinetics {
    pub preferred_mps: f64,
    pub response_s: f64,
    pub accel_mps2: f64,
    pub brake_mps2: f64,
    pub entry_mps: f64,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct Geometry {
    pub length_m: f64,
    pub cap_mps: f64,
}
impl Kinetics {
    fn valid(self) -> bool {
        [
            self.preferred_mps,
            self.response_s,
            self.accel_mps2,
            self.brake_mps2,
        ]
        .iter()
        .all(|x| x.is_finite() && *x > 0.)
            && self.entry_mps.is_finite()
            && self.entry_mps >= 0.
    }
    pub fn characteristic(self, v0: f64, target: f64, t: f64) -> (f64, f64) {
        let diff = target - v0;
        let lim = if diff >= 0. {
            self.accel_mps2
        } else {
            self.brake_mps2
        };
        let acc = if diff >= 0. { lim } else { -lim };
        let sat = ((diff.abs() - lim * self.response_s) / lim).max(0.);
        let first = t.min(sat);
        let mut dx = v0 * first + 0.5 * acc * first * first;
        let mut v = v0 + acc * first;
        let rem = t - first;
        if rem > 0. {
            let change = -(-rem / self.response_s).exp_m1();
            dx += target * rem + (v - target) * self.response_s * change;
            v += (target - v) * change;
        }
        (dx, v.max(0.))
    }
    pub fn passage(self, v0: f64, target: f64, length: f64) -> Result<(f64, f64)> {
        if !self.valid()
            || ![v0, target, length]
                .iter()
                .all(|x| x.is_finite() && *x >= 0.)
        {
            return Err("invalid passage inputs".into());
        }
        if length == 0. {
            return Ok((0., v0));
        }
        if target == 0. {
            let sat = ((v0 - self.brake_mps2 * self.response_s) / self.brake_mps2).max(0.);
            let (dx, v) = self.characteristic(v0, 0., sat);
            if length >= dx + v * self.response_s {
                return Ok((f64::INFINITY, 0.));
            }
        }
        let mut hi = (length / v0.max(target).max(1e-12)).max(1.);
        for _ in 0..256 {
            if self.characteristic(v0, target, hi).0 >= length {
                let mut lo = 0.;
                // 100 iterations match the old scalar oracle, stop at adjacent binary64 endpoints.
                for _ in 0..100 {
                    let m = (lo + hi) / 2.;
                    if m == lo || m == hi {
                        break;
                    }
                    if self.characteristic(v0, target, m).0 >= length {
                        hi = m
                    } else {
                        lo = m
                    }
                }
                return Ok((hi, self.characteristic(v0, target, hi).1));
            }
            hi *= 2.;
            if !hi.is_finite() {
                break;
            }
        }
        Err("passage bracket overflow".into())
    }
}
pub fn route_passages(
    paths: &[Vec<u32>],
    geometry: &[Geometry],
    model: Kinetics,
) -> Result<Vec<Vec<f64>>> {
    if !model.valid()
        || geometry.iter().any(|g| {
            !g.length_m.is_finite() || g.length_m <= 0. || !g.cap_mps.is_finite() || g.cap_mps <= 0.
        })
    {
        return Err("invalid geometry".into());
    }
    // Sequential response within each route; independent routes evaluated by
    // indexed Rayon. No reassociation of the per-route speed history.
    let results: Vec<Result<Vec<f64>>> = paths
        .par_iter()
        .map(|path| {
            let mut v = model.entry_mps;
            let mut times = Vec::with_capacity(path.len());
            for &e in path {
                let g = geometry.get(e as usize).ok_or("missing link geometry")?;
                let (t, next) = model.passage(v, model.preferred_mps.min(g.cap_mps), g.length_m)?;
                if !t.is_finite() || t <= 0. {
                    return Err("unreachable route".into());
                }
                times.push(t);
                v = next;
            }
            Ok(times)
        })
        .collect();
    results.into_iter().collect()
}
#[cfg(test)]
mod tests {
    use super::*;
    fn m() -> Kinetics {
        Kinetics {
            preferred_mps: 10.,
            response_s: 2.,
            accel_mps2: 2.,
            brake_mps2: 4.,
            entry_mps: 0.,
        }
    }
    #[test]
    fn passage_residual_and_limiting_cases() {
        let k = m();
        assert_eq!(k.passage(10., 10., 200.).unwrap(), (20., 10.));
        assert!(k.passage(0., 0., 1.).unwrap().0.is_infinite());
        for v in [0., 1., 5., 10., 25.] {
            for target in [0.5, 5., 10., 20.] {
                for length in [0.01, 1., 10., 100., 1000.] {
                    let (t, w) = k.passage(v, target, length).unwrap();
                    let (x, y) = k.characteristic(v, target, t);
                    assert!((x - length).abs() < 1e-9 * length.max(1.));
                    assert_eq!(w, y);
                    assert!(w >= 0.);
                }
            }
        }
    }
    #[test]
    fn indexed_route_parallel_replay() {
        let g = [
            Geometry {
                length_m: 100.,
                cap_mps: 10.,
            },
            Geometry {
                length_m: 75.,
                cap_mps: 5.,
            },
        ];
        let paths: Vec<_> = (0..5000)
            .map(|i| if i % 2 == 0 { vec![0, 1] } else { vec![1, 0] })
            .collect();
        let one = rayon::ThreadPoolBuilder::new()
            .num_threads(1)
            .build()
            .unwrap();
        let many = rayon::ThreadPoolBuilder::new()
            .num_threads(8)
            .build()
            .unwrap();
        assert_eq!(
            one.install(|| route_passages(&paths, &g, m()).unwrap()),
            many.install(|| route_passages(&paths, &g, m()).unwrap())
        );
    }
}
