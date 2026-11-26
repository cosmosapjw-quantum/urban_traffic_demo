//! Original terrain formulas and embedded mesh. Integer seed uses the MT19937
//! init-by-array and 53-bit uniform conversion used by CPython Random.
//! MT19937 algorithm: Matsumoto & Nishimura (1998), 2002 array initialization.
//! Reference: https://github.com/python/cpython/blob/main/Modules/_randommodule.c
use crate::{
    core_error::{CoreError, CoreResult},
    terrain_validation::{bounds, Landscape, Region, Terrain},
    v1_area::Point,
};
use rayon::prelude::*;
use std::{
    collections::{BTreeMap, BTreeSet},
    f64::consts::PI,
};
fn bad(s: &str) -> CoreError {
    CoreError::value(s)
}
pub(crate) struct Mt {
    state: [u32; 624],
    index: usize,
}
impl Mt {
    pub fn new(seed: u64) -> Self {
        let mut a = [0u32; 624];
        a[0] = 19650218;
        for i in 1..624 {
            a[i] = 1812433253u32
                .wrapping_mul(a[i - 1] ^ (a[i - 1] >> 30))
                .wrapping_add(i as u32)
        }
        let keys = [seed as u32, (seed >> 32) as u32];
        let n = if keys[1] == 0 { 1 } else { 2 };
        let (mut i, mut j) = (1, 0);
        for _ in 0..624 {
            a[i] = (a[i] ^ ((a[i - 1] ^ (a[i - 1] >> 30)).wrapping_mul(1664525)))
                .wrapping_add(keys[j])
                .wrapping_add(j as u32);
            i += 1;
            j = (j + 1) % n;
            if i == 624 {
                a[0] = a[623];
                i = 1
            }
        }
        for _ in 0..623 {
            a[i] = (a[i] ^ ((a[i - 1] ^ (a[i - 1] >> 30)).wrapping_mul(1566083941)))
                .wrapping_sub(i as u32);
            i += 1;
            if i == 624 {
                a[0] = a[623];
                i = 1
            }
        }
        a[0] = 0x80000000;
        Self {
            state: a,
            index: 624,
        }
    }
    fn word(&mut self) -> u32 {
        if self.index == 624 {
            for i in 0..624 {
                let y = (self.state[i] & 0x80000000) | (self.state[(i + 1) % 624] & 0x7fffffff);
                self.state[i] = self.state[(i + 397) % 624]
                    ^ (y >> 1)
                    ^ if y & 1 != 0 { 0x9908b0df } else { 0 };
            }
            self.index = 0
        }
        let mut y = self.state[self.index];
        self.index += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c5680;
        y ^= (y << 15) & 0xefc60000;
        y ^ (y >> 18)
    }
    pub fn random(&mut self) -> f64 {
        let a = self.word() >> 5;
        let b = self.word() >> 6;
        (a as f64 * 67108864. + b as f64) / 9007199254740992.
    }
    fn uniform(&mut self) -> f64 {
        -1. + 2. * self.random()
    }
}
fn region(points: Vec<Point>) -> Region {
    let bounds = bounds(&points);
    Region { points, bounds }
}
fn ellipse(cx: f64, cy: f64, rx: f64, ry: f64, ang: f64) -> Region {
    let (ca, sa) = (ang.cos(), ang.sin());
    region(
        (0..32)
            .map(|k| {
                let a = k as f64 * PI / 16.;
                [
                    cx + ca * rx * a.cos() - sa * ry * a.sin(),
                    cy + sa * rx * a.cos() + ca * ry * a.sin(),
                ]
            })
            .collect(),
    )
}
pub(crate) fn landscape(kind: &str, l: f64, seed: u64) -> CoreResult<Landscape> {
    if !matches!(kind, "flat" | "river" | "coast" | "valley" | "lake")
        || !l.is_finite()
        || l < 1000.
    {
        return Err(bad("landscape domain"));
    }
    let vertical = l / 8000.;
    let phase = (seed % 23) as f64 / 23. * 2. * PI;
    let river = |y: f64| {
        0.48 * l
            + 0.065 * l * (2. * PI * y / l + 0.4).sin()
            + 0.022 * l * (4. * PI * y / l + phase).sin()
    };
    let valley = |x: f64| 0.48 * l + 0.12 * l * (1.6 * PI * x / l - 0.5).sin();
    let shore = |y: f64| {
        0.22 * l + 0.065 * l * (2. * PI * y / l + 0.5).sin() + 0.025 * l * (5. * PI * y / l).sin()
    };
    let samples: Vec<_> = (0..=80)
        .map(|k| -100. + (l + 200.) * k as f64 / 80.)
        .collect();
    let water = match kind {
        "river" => vec![region(
            samples
                .iter()
                .map(|&y| [river(y) - (0.010 + 0.003 * (y / l * 6.).cos()) * l, y])
                .chain(
                    samples
                        .iter()
                        .rev()
                        .map(|&y| [river(y) + (0.010 + 0.003 * (y / l * 6.).cos()) * l, y]),
                )
                .collect(),
        )],
        "valley" => vec![region(
            samples
                .iter()
                .map(|&x| [x, valley(x) - 0.007 * l])
                .chain(samples.iter().rev().map(|&x| [x, valley(x) + 0.007 * l]))
                .collect(),
        )],
        "coast" => vec![region(
            std::iter::once([-100., -100.])
                .chain(samples.iter().map(|&y| [shore(y), y]))
                .chain(std::iter::once([-100., l + 100.]))
                .collect(),
        )],
        "lake" => vec![ellipse(0.51 * l, 0.54 * l, 0.105 * l, 0.15 * l, 0.4)],
        _ => vec![],
    };
    let protected = vec![if kind == "valley" {
        ellipse(0.78 * l, 0.80 * l, 0.14 * l, 0.09 * l, -0.3)
    } else {
        ellipse(0.83 * l, 0.81 * l, 0.10 * l, 0.12 * l, 0.2)
    }];
    let n = 64usize;
    let heights_m = (0..(n + 1) * (n + 1))
        .into_par_iter()
        .map(|k| {
            let (x, y) = (
                (k % (n + 1)) as f64 * l / n as f64,
                (k / (n + 1)) as f64 * l / n as f64,
            );
            let base = 20.
                + 0.001 * x
                + 0.002 * y
                + 4. * vertical * (2. * PI * x / l).sin() * (2. * PI * y / l).sin();
            match kind {
                "flat" => base,
                "river" => {
                    base + 130.
                        * vertical
                        * (-((x - 0.79 * l).powi(2) + (y - 0.73 * l).powi(2))
                            / (2. * (0.14 * l).powi(2)))
                        .exp()
                }
                "coast" => {
                    base + 180. * vertical * ((x - shore(y)) / l).powi(2)
                        + 240.
                            * vertical
                            * (-((x - 0.84 * l).powi(2) + (y - 0.77 * l).powi(2))
                                / (2. * (0.14 * l).powi(2)))
                            .exp()
                }
                "valley" => {
                    base + 620. * vertical * ((y - valley(x)) / (0.52 * l)).powi(2)
                        + 45. * vertical * (-((x - 0.42 * l) / (0.1 * l)).powi(2)).exp()
                }
                _ => {
                    base + 220.
                        * vertical
                        * (-((x - 0.78 * l).powi(2) + (y - 0.78 * l).powi(2))
                            / (2. * (0.18 * l).powi(2)))
                        .exp()
                }
            }
        })
        .collect();
    let terrain = Terrain {
        n,
        spacing_m: l / n as f64,
        heights_m,
        water: vec![],
        protected: vec![],
        bridge_rows: vec![],
    };
    Ok(Landscape {
        terrain,
        water,
        protected,
    })
}
pub(crate) struct Mesh {
    pub xy: BTreeMap<String, Point>,
    pub pairs: BTreeSet<(String, String)>,
    pub chains: Vec<Vec<String>>,
}
impl Mesh {
    fn chain(&mut self, mut nodes: Vec<String>, closed: bool) {
        if closed {
            nodes.push(nodes[0].clone())
        }
        for w in nodes.windows(2) {
            let (a, b) = (&w[0], &w[1]);
            self.pairs.insert(if a < b {
                (a.clone(), b.clone())
            } else {
                (b.clone(), a.clone())
            });
        }
        self.chains.push(nodes);
    }
}
pub(crate) fn mesh(style: &str, l: f64, n: usize, seed: u64) -> CoreResult<Mesh> {
    if !matches!(style, "planned" | "polycentric" | "radial" | "corridor")
        || !(12..=90).contains(&n)
    {
        return Err(bad("mesh domain"));
    }
    let mut m = Mesh {
        xy: BTreeMap::new(),
        pairs: BTreeSet::new(),
        chains: vec![],
    };
    let spacing = l / n as f64;
    let mut rng = Mt::new(seed);
    if style == "radial" {
        let center = [0.49 * l, 0.50 * l];
        m.xy.insert("v0".into(), center);
        let mut prev = vec!["v0".to_string()];
        let mut count = 6usize;
        let mut rings = vec![];
        for k in 1..(n / 2).max(3) {
            let r = k as f64 * spacing;
            while 2. * PI * r / count as f64 > 1.45 * spacing {
                count *= 2
            }
            let ids: Vec<_> = (0..count)
                .map(|j| {
                    let a = j as f64 * 2. * PI / count as f64;
                    let rr = r * (1. + 0.018 * (3. * a + 0.3).sin());
                    let id = format!("r{k}:{j}");
                    m.xy.insert(
                        id.clone(),
                        [center[0] + rr * a.cos(), center[1] + rr * a.sin()],
                    );
                    id
                })
                .collect();
            m.chain(ids.clone(), true);
            if k == 1 {
                for id in &ids {
                    m.chain(vec!["v0".into(), id.clone()], false)
                }
            } else if prev.len() == ids.len() {
                for (a, b) in prev.iter().zip(&ids) {
                    m.chain(vec![a.clone(), b.clone()], false)
                }
            } else {
                for (j, a) in prev.iter().enumerate() {
                    m.chain(vec![a.clone(), ids[2 * j].clone()], false)
                }
            }
            rings.push(count);
            prev = ids;
        }
        for j in 0..96 {
            let mut seq = vec![];
            for (k, &count) in rings.iter().enumerate() {
                let idx = (j as f64 * count as f64 / 96.).round_ties_even() as usize % count;
                if (idx as f64 / count as f64 - j as f64 / 96.).abs() < 1e-10 {
                    seq.push(format!("r{}:{idx}", k + 1))
                }
            }
            if seq.len() > 1 {
                m.chains.push(seq)
            }
        }
    } else {
        let phase = (seed % 19) as f64 / 19. * 2. * PI;
        for j in 1..n {
            for i in 1..n {
                let (mut x, mut y) = (i as f64 * spacing, j as f64 * spacing);
                match style {
                    "planned" => {
                        x += 0.025 * spacing * rng.uniform();
                        y += 0.025 * spacing * rng.uniform();
                    }
                    "corridor" => {
                        y = 0.48 * l
                            + 0.12 * l * (1.6 * PI * x / l - 0.5).sin()
                            + (y - 0.5 * l) * 0.76;
                        x += 0.06 * spacing * rng.uniform();
                        y += 0.06 * spacing * rng.uniform();
                    }
                    _ => {
                        x += 0.028 * l * (PI * x / l).sin() * (2. * PI * y / l + phase).sin()
                            + 0.12 * spacing * rng.uniform();
                        y += 0.025 * l * (2. * PI * x / l + phase).sin() * (PI * y / l).sin()
                            + 0.12 * spacing * rng.uniform();
                    }
                }
                if x > 0. && x < l && y > 0. && y < l {
                    m.xy.insert(format!("g{i}:{j}"), [x, y]);
                }
            }
        }
        for j in 1..n {
            let ids = (1..n)
                .map(|i| format!("g{i}:{j}"))
                .filter(|k| m.xy.contains_key(k))
                .collect();
            m.chain(ids, false);
        }
        for i in 1..n {
            let ids = (1..n)
                .map(|j| format!("g{i}:{j}"))
                .filter(|k| m.xy.contains_key(k))
                .collect();
            m.chain(ids, false);
        }
    }
    Ok(m)
}
pub(crate) fn centers(style: &str, kind: &str, l: f64) -> Vec<Point> {
    if style == "radial" {
        vec![
            [0.49 * l, 0.50 * l],
            [0.72 * l, 0.35 * l],
            [0.28 * l, 0.65 * l],
        ]
    } else if kind == "coast" {
        vec![
            [0.43 * l, 0.40 * l],
            [0.45 * l, 0.72 * l],
            [0.68 * l, 0.38 * l],
        ]
    } else if style == "corridor" || kind == "valley" {
        [0.25, 0.52, 0.76]
            .into_iter()
            .enumerate()
            .map(|(i, x)| {
                [
                    x * l,
                    (0.48
                        + 0.12 * (1.6 * PI * x - 0.5).sin()
                        + if i % 2 == 1 { 0.055 } else { -0.055 })
                        * l,
                ]
            })
            .collect()
    } else if style == "planned" {
        vec![[0.48 * l, 0.46 * l], [0.73 * l, 0.67 * l]]
    } else {
        vec![
            [0.30 * l, 0.43 * l],
            [0.64 * l, 0.38 * l],
            [0.48 * l, 0.71 * l],
        ]
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn integer_mt19937_known_stream() {
        let mut r = Mt::new(17);
        for v in [
            0.5219839097124932f64,
            0.8066907771186791,
            0.9604947743238768,
        ] {
            assert_eq!(r.random().to_bits(), v.to_bits());
        }
    }
    #[test]
    fn substrate_registry_and_landscape() {
        let m = mesh("planned", 8000., 42, 17).unwrap();
        assert_eq!(m.xy.len(), 1681);
        assert_eq!(m.pairs.len(), 3280);
        let l = landscape("river", 8000., 17).unwrap();
        assert_eq!(l.terrain.heights_m.len(), 4225);
        assert_eq!(l.water[0].points.len(), 162);
        l.validate(&l.terrain).unwrap();
    }
}
