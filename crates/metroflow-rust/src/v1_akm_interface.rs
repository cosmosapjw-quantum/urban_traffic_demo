//! Scoped service-boundary crossing primitive, not unused capacity credit.
use crate::core_error::{CoreError,CoreResult};
#[derive(Clone,Copy,Debug,PartialEq)]
pub(crate) struct Crossing {pub progress:f64,pub amount:f64,pub done:bool}
pub(crate) fn increment(m:f64,a:f64,send:f64,receive:f64,metres:f64,ell:f64)->CoreResult<Crossing>{
    let bad=|s|CoreError::value(s);
    if !m.is_finite()||m<=0.||!ell.is_finite()||ell<=0.||!a.is_finite()||!(0. ..1.).contains(&a)||
        [send,receive,metres].iter().any(|x|x.is_nan()||*x<0.){
        return Err(bad("invalid interface progress or quotas"))
    }
    let remaining=m*(1.-a);
    if remaining<=0.||!remaining.is_finite(){return Err(bad("nonrepresentable crossing remainder"))}
    let q=remaining.min(send).min(receive).min(metres/ell);
    if q==remaining{return Ok(Crossing{progress:1.,amount:q,done:true})}
    if q==0.{return Ok(Crossing{progress:a,amount:0.,done:false})}
    let progress=a+q/m;
    if !progress.is_finite()||progress<=a||progress>=1.{return Err(bad("nonrepresentable positive partial crossing"))}
    Ok(Crossing{progress,amount:q,done:false})
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn partial_interface_uses_current_quota_and_finishes_once(){
        let mut a=0.;
        for n in 0..4{
            let x=increment(1.,a,0.25,0.5,6.,12.).unwrap();
            assert_eq!(x.amount,0.25);
            assert_eq!(x.progress,(n+1)as f64/4.);
            assert_eq!(x.done,n==3);a=x.progress;
        }
    }
    #[test]
    fn arbitrary_partial_count_and_metres(){
        for a in [0.,0.125,0.5,0.875]{
            for s in [0.,0.125,0.375,1.]{for r in [0.,0.125,0.375,1.]{
                for b in [0.,1.5,4.5,12.]{
                    let x=increment(1.,a,s,r,b,12.).unwrap();
                    assert!(x.amount<=s&&x.amount<=r&&x.amount*12.<=b);
                    assert!((x.progress-a-x.amount).abs()<1e-15);
                    assert_eq!(x.done,x.progress==1.);
                }
            }}
        }
        assert!(increment(1.,1.,1.,1.,12.,12.).is_err());
    }
    #[test]
    fn interface_zero_quota_retains_reservation(){
        let x=increment(1.,0.5,1.,0.,12.,12.).unwrap();
        assert_eq!(x,Crossing{progress:0.5,amount:0.,done:false});
    }
}
