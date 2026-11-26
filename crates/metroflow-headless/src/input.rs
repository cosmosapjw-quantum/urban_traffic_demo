use rayon::prelude::*;
use std::{
    fs,
    path::Path,
    str::{FromStr, SplitWhitespace},
};
pub type Result<T> = std::result::Result<T, String>;
pub const FOOTPRINT: [f64; 3] = [5., 10., 12.];
#[derive(Clone, Copy, Debug)]
pub struct Road {
    pub travel: f64,
    pub entry: f64,
    pub exit: f64,
    pub storage: f64,
}
#[derive(Clone, Copy, Debug)]
pub struct Group {
    pub forward: u32,
    pub backward: Option<u32>,
    pub purpose: u32,
    pub mass: f64,
    pub origin: f64,
    pub destination: f64,
    pub class: u8,
    pub phase_group: u32,
}
#[derive(Clone, Debug)]
pub struct Input {
    pub roads: Vec<Road>,
    pub paths: Vec<Vec<u32>>,
    pub passage: Vec<Vec<f64>>,
    pub windows: Vec<[f64; 4]>,
    pub groups: Vec<Group>,
    pub dwell: f64,
}
fn read<T: FromStr>(s: &mut SplitWhitespace<'_>) -> Result<T> {
    s.next()
        .ok_or("truncated input".to_owned())?
        .parse()
        .map_err(|_| "invalid token".to_owned())
}
fn pos(x: f64) -> bool {
    x.is_finite() && x > 0.
}
fn nonneg(x: f64) -> bool {
    x.is_finite() && x >= 0.
}
impl Input {
    pub fn load(network: &Path, passages: &Path) -> Result<Self> {
        let a = fs::read_to_string(network).map_err(|e| e.to_string())?;
        let b = fs::read_to_string(passages).map_err(|e| e.to_string())?;
        Self::parse(&a, &b)
    }
    pub fn parse(network: &str, passages: &str) -> Result<Self> {
        let mut n = network.split_whitespace();
        let mut p = passages.split_whitespace();
        let (l, r, g, w): (usize, usize, usize, usize) =
            (read(&mut n)?, read(&mut n)?, read(&mut n)?, read(&mut n)?);
        let dwell = read(&mut n)?;
        if l == 0
            || r == 0
            || w == 0
            || [l, r, g, w]
                .iter()
                .any(|&x| x >= u32::MAX as usize || x > network.len())
            || !nonneg(dwell)
        {
            return Err("invalid dimensions".into());
        }
        let mut roads = Vec::with_capacity(l);
        for _ in 0..l {
            let q = Road {
                travel: read(&mut n)?,
                entry: read(&mut n)?,
                exit: read(&mut n)?,
                storage: read(&mut n)?,
            };
            if ![q.travel, q.entry, q.exit, q.storage]
                .iter()
                .copied()
                .all(pos)
            {
                return Err("invalid road".into());
            }
            roads.push(q);
        }
        let mut paths = Vec::with_capacity(r);
        for _ in 0..r {
            let len: usize = read(&mut n)?;
            if len == 0 || len > u16::MAX as usize {
                return Err("invalid path length".into());
            }
            let v = (0..len)
                .map(|_| read::<u32>(&mut n))
                .collect::<Result<Vec<_>>>()?;
            if v.iter().any(|&x| x as usize >= l) || v.windows(2).any(|x| x[0] == x[1]) {
                return Err("invalid route".into());
            }
            paths.push(v)
        }
        if read::<usize>(&mut p)? != r {
            return Err("passage count differs".into());
        }
        let mut passage = Vec::with_capacity(r);
        for path in &paths {
            if read::<usize>(&mut p)? != path.len() {
                return Err("passage shape".into());
            }
            let v = (0..path.len())
                .map(|_| read::<f64>(&mut p))
                .collect::<Result<Vec<_>>>()?;
            if !v.iter().copied().all(pos) {
                return Err("invalid passage".into());
            }
            passage.push(v);
        }
        let mut windows = Vec::with_capacity(w);
        for _ in 0..w {
            let v: [f64; 4] = [read(&mut n)?, read(&mut n)?, read(&mut n)?, read(&mut n)?];
            if !v.iter().copied().all(nonneg)
                || v[1] < v[0]
                || v[3] < v[2]
                || v[1] > 86400.
                || v[3] > 86400.
            {
                return Err("invalid profile".into());
            }
            windows.push(v)
        }
        let mut groups = Vec::with_capacity(g);
        for _ in 0..g {
            let forward: u32 = read(&mut n)?;
            let back: i64 = read(&mut n)?;
            let purpose: u32 = read(&mut n)?;
            let mass = read(&mut n)?;
            let origin = read(&mut n)?;
            let destination = read(&mut n)?;
            let class: u8 = read(&mut n)?;
            let phase_group = read(&mut n)?;
            if forward as usize >= r
                || back < -1
                || back >= r as i64
                || purpose as usize >= w
                || class >= 3
                || !pos(mass)
                || !nonneg(origin)
                || !nonneg(destination)
                || back >= 0 && windows[purpose as usize][3] <= windows[purpose as usize][2]
            {
                return Err("invalid group".into());
            }
            groups.push(Group {
                forward,
                backward: (back >= 0).then_some(back as u32),
                purpose,
                mass,
                origin,
                destination,
                class,
                phase_group,
            });
        }
        if n.next().is_some() || p.next().is_some() {
            return Err("trailing tokens".into());
        }
        Ok(Self {
            roads,
            paths,
            passage,
            windows,
            groups,
            dwell,
        })
    }
    // One path scan, not repeated for every access subcohort. Independent
    // indexed map; the caller retains the original deterministic ordinal.
    pub fn route_bounds(&self) -> Vec<[f64; 2]> {
        self.paths
            .par_iter()
            .map(|path| {
                path.iter().fold([f64::INFINITY; 2], |mut b, &i| {
                    let r = self.roads[i as usize];
                    b[0] = b[0].min(r.storage);
                    b[1] = b[1].min(10. * r.entry);
                    b
                })
            })
            .collect()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parser_fail_closed() {
        let n = "1 1 1 1 0\n1 1 1 12\n1 0\n0 0 0 0\n0 -1 0 1 0 0 2 0";
        let x = Input::parse(n, "1\n1 1").unwrap();
        assert_eq!(x.route_bounds(), vec![[12., 10.]]);
        assert!(Input::parse(n, "1\n1 NaN").is_err());
        assert!(Input::parse(n, "1\n1 1 extra").is_err());
        assert!(Input::parse(&n.replace("1 1 1 12", "1 1 1 -12"), "1\n1 1").is_err());
    }
}
