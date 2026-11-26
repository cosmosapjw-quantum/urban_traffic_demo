//! Exact finite marginal coupling: no Python Fraction or Cartesian OD product.
use crate::input::Result;
use num_rational::BigRational;
use num_traits::{One, ToPrimitive, Zero};
use serde::{Deserialize, Serialize};
use std::cmp::Ordering;
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct Atom {
    pub delay_s: f64,
    pub weight: f64,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct Coupled {
    pub origin_s: f64,
    pub destination_s: f64,
    pub weight: f64,
}
fn canonical(atoms: &[Atom]) -> Result<Vec<(f64, BigRational)>> {
    let mut xs = Vec::with_capacity(atoms.len());
    for a in atoms {
        if !a.delay_s.is_finite() || a.delay_s < 0. || !a.weight.is_finite() || a.weight < 0. {
            return Err("invalid access atom".into());
        }
        if a.weight > 0. {
            xs.push((
                if a.delay_s == 0. { 0. } else { a.delay_s },
                BigRational::from_float(a.weight).ok_or("weight conversion")?,
            ))
        }
    }
    xs.sort_by(|a, b| a.0.total_cmp(&b.0));
    let mut out: Vec<(f64, BigRational)> = Vec::new();
    for (t, w) in xs {
        if let Some(last) = out.last_mut().filter(|x| x.0 == t) {
            last.1 += w
        } else {
            out.push((t, w))
        }
    }
    let total: BigRational = out.iter().map(|x| x.1.clone()).sum();
    if total.is_zero() {
        return Err("empty access law".into());
    }
    for x in &mut out {
        x.1 /= total.clone()
    }
    Ok(out)
}
fn exact(a: &[Atom], b: &[Atom]) -> Result<Vec<(f64, f64, BigRational)>> {
    let a = canonical(a)?;
    let b = canonical(b)?;
    let (mut i, mut j) = (0, 0);
    let (mut x, mut y) = (a[0].1.clone(), b[0].1.clone());
    let mut out = Vec::with_capacity(a.len() + b.len() - 1);
    while i < a.len() && j < b.len() {
        let w = match x.cmp(&y) {
            Ordering::Greater => y.clone(),
            _ => x.clone(),
        };
        if w.is_zero() {
            return Err("nonpositive coupling atom".into());
        }
        out.push((a[i].0, b[j].0, w.clone()));
        x -= w.clone();
        y -= w;
        if x.is_zero() {
            i += 1;
            if i < a.len() {
                x = a[i].1.clone()
            }
        }
        if y.is_zero() {
            j += 1;
            if j < b.len() {
                y = b[j].1.clone()
            }
        }
    }
    if i != a.len()
        || j != b.len()
        || out.len() > a.len() + b.len() - 1
        || out.iter().map(|x| x.2.clone()).sum::<BigRational>() != BigRational::one()
    {
        return Err("coupling census differs".into());
    }
    Ok(out)
}
pub fn couple(a: &[Atom], b: &[Atom]) -> Result<Vec<Coupled>> {
    exact(a, b)?
        .into_iter()
        .map(|(origin_s, destination_s, w)| {
            let weight = w.to_f64().ok_or("weight not representable")?;
            if weight <= 0. {
                return Err("coupling weight underflow".into());
            }
            Ok(Coupled {
                origin_s,
                destination_s,
                weight,
            })
        })
        .collect()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_marginals_900_cases() {
        let mut n = 0;
        for i in 1..=5 {
            for j in 1..=5 {
                for k in 1..=6 {
                    for l in 1..=6 {
                        let a: Vec<_> = (0..i)
                            .map(|x| Atom {
                                delay_s: x as f64,
                                weight: (x + k) as f64,
                            })
                            .collect();
                        let b: Vec<_> = (0..j)
                            .map(|x| Atom {
                                delay_s: 2. * x as f64,
                                weight: ((j - x) * l + 1) as f64,
                            })
                            .collect();
                        let out = exact(&a, &b).unwrap();
                        for (d, w) in canonical(&a).unwrap() {
                            assert_eq!(
                                w,
                                out.iter().filter(|x| x.0 == d).map(|x| x.2.clone()).sum()
                            )
                        }
                        for (d, w) in canonical(&b).unwrap() {
                            assert_eq!(
                                w,
                                out.iter().filter(|x| x.1 == d).map(|x| x.2.clone()).sum()
                            )
                        }
                        assert!(out.len() <= a.len() + b.len() - 1);
                        n += 1;
                    }
                }
            }
        }
        assert_eq!(n, 900);
    }
    #[test]
    fn repeated_atoms_invalid_and_dyadic() {
        let a = [
            Atom {
                delay_s: 0.,
                weight: 0.1,
            },
            Atom {
                delay_s: 0.,
                weight: 0.2,
            },
            Atom {
                delay_s: 1.,
                weight: 0.7,
            },
        ];
        let b = [
            Atom {
                delay_s: 3.,
                weight: 0.4,
            },
            Atom {
                delay_s: 5.,
                weight: 0.6,
            },
        ];
        assert_eq!(couple(&a, &b).unwrap().len(), 3);
        assert!(couple(&[], &b).is_err());
        assert!(couple(
            &[Atom {
                delay_s: 0.,
                weight: -1.
            }],
            &b
        )
        .is_err());
    }
}
