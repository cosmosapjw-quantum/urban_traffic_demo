//! Extended nonnegative real scalar: finite JSON number or explicit
//! "+inf". Null is not an observation, and finite spelling is unchanged.
use serde::de::Error as _;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
#[derive(Clone, Copy, Debug)]
struct Cost(f64);
impl Serialize for Cost {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        if self.0 == f64::INFINITY {
            s.serialize_str("+inf")
        } else if self.0.is_finite() && self.0 >= 0. {
            s.serialize_f64(self.0)
        } else {
            Err(serde::ser::Error::custom(
                "invalid extended nonnegative cost",
            ))
        }
    }
}
impl<'de> Deserialize<'de> for Cost {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        #[serde(untagged)]
        enum Repr {
            Number(f64),
            Text(String),
        }
        match Repr::deserialize(d)? {
            Repr::Number(x) if x.is_finite() && x >= 0. => Ok(Self(x)),
            Repr::Text(s) if s == "+inf" => Ok(Self(f64::INFINITY)),
            _ => Err(D::Error::custom(
                "expected nonnegative finite number or +inf",
            )),
        }
    }
}
pub fn serialize<S: Serializer>(x: &f64, s: S) -> Result<S::Ok, S::Error> {
    Cost(*x).serialize(s)
}
pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<f64, D::Error> {
    Ok(Cost::deserialize(d)?.0)
}
pub mod pairs {
    use super::*;
    pub fn serialize<S: Serializer>(v: &[(String, f64)], s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeSeq;
        let mut seq = s.serialize_seq(Some(v.len()))?;
        for (k, x) in v {
            seq.serialize_element(&(k, Cost(*x)))?;
        }
        seq.end()
    }
    pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<Vec<(String, f64)>, D::Error> {
        Ok(Vec::<(String, Cost)>::deserialize(d)?
            .into_iter()
            .map(|(k, x)| (k, x.0))
            .collect())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn infinity_is_not_null_and_finite_spelling_stays_unchanged() {
        assert_eq!(
            serde_json::to_string(&Cost(f64::INFINITY)).unwrap(),
            "\"+inf\""
        );
        assert_eq!(serde_json::to_string(&Cost(1.25)).unwrap(), "1.25");
        assert_eq!(
            serde_json::from_str::<Cost>("\"+inf\"").unwrap().0,
            f64::INFINITY
        );
        for bad in ["null", "\"NaN\"", "\"-inf\"", "-1", "\"1\""] {
            assert!(serde_json::from_str::<Cost>(bad).is_err());
        }
    }
}
