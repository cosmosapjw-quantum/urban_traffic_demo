//! AKM research-only local positive kinetic map. Not the native V03 model.
use crate::input::Result;
use serde::{Deserialize,Serialize};

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Moment {
    pub m:[f64;2], pub j:[f64;2], pub z:[f64;2], pub birth:f64,
}
impl Moment {
    pub fn point(m:f64,p:f64,u:f64,t:f64)->Self{
        let mass=[m*(1.-p),m*p];
        Self{m:mass,j:mass.map(|x|x*u),z:mass.map(|x|x*u*u),birth:m*t}
    }
    pub fn mass(self)->f64{self.m[0]+self.m[1]}
    pub fn momentum(self)->f64{self.j[0]+self.j[1]}
    pub fn scaled(self,f:f64)->Self{Self{m:self.m.map(|x|x*f),j:self.j.map(|x|x*f),z:self.z.map(|x|x*f),birth:self.birth*f}}
    pub fn add(self,b:Self)->Self{Self{m:[self.m[0]+b.m[0],self.m[1]+b.m[1]],j:[self.j[0]+b.j[0],self.j[1]+b.j[1]],z:[self.z[0]+b.z[0],self.z[1]+b.z[1]],birth:self.birth+b.birth}}
    pub fn valid(self,t:f64)->bool{
        let mass=self.mass();
        if !mass.is_finite()||!self.birth.is_finite()||self.birth<0.||self.birth>mass*t+1e-10*(mass*t).max(1.){return false}
        for i in 0..2{
            let(m,j,z)=(self.m[i],self.j[i],self.z[i]);
            if ![m,j,z].iter().all(|x|x.is_finite()&&*x>=0.){return false}
            if m==0. {if j!=0.||z!=0.{return false}}
            else{let(j,z)=(j/m,z/m);if j>1.+1e-10||z>j+1e-10||j*j>z+1e-10{return false}}
        }
        true
    }
}
#[derive(Clone,Copy,Debug,Serialize,Deserialize,PartialEq)]
pub struct Rates{pub alpha:f64,pub nu:f64,pub tau:f64,pub target:f64}
impl Rates{
    pub fn valid(self)->bool{self.alpha.is_finite()&&self.alpha>0.&&self.nu.is_finite()&&self.nu>=0.&&(self.alpha+self.nu).is_finite()&&self.tau.is_finite()&&self.tau>0.&&self.target.is_finite()&&(0. ..=1.).contains(&self.target)}
}
/// D04 diagnostic, not the default A network flux. Reconstruct each
/// conditional positive measure at 0 and Z/J. Exact outgoing M and J;
/// sharp lower third moment. Aggregate birth follows mass fraction only.
pub fn split_velocity_selected(x:Moment,c:f64,t:f64)->Result<(Moment,Moment)>{
    if !x.valid(t)||!c.is_finite()||!(0. ..=1.).contains(&c){return Err("invalid velocity flux".into())}
    let (mut r,mut y)=(Moment::default(),Moment::default());
    for i in 0..2{
        let(m,j,z)=(x.m[i],x.j[i],x.z[i]);
        if j==0.{if z!=0.{return Err("zero first moment with positive second".into())}r.m[i]=m;continue}
        if m<=0.||z<=0.{return Err("nonpositive moving mass reconstruction".into())}
        let u=z/j;
        if !u.is_finite()||u<=0.||u>1.+1e-10{return Err("velocity quadrature support".into())}
        let u=u.min(1.);
        // Using the known moments avoids forming J^2 or Z^2 at tiny mass.
        let f=(c*u).min(1.);
        y.m[i]=c*j;y.j[i]=f*j;y.z[i]=f*z;
        r.m[i]=m-y.m[i];r.j[i]=(1.-f)*j;r.z[i]=(1.-f)*z;
        if c>0.&&y.m[i]==0.{return Err("positive velocity flux underflow".into())}
        if r.m[i]<0.{return Err("velocity flux negative remainder".into())}
    }
    let f=if x.mass()>0.{(y.mass()/x.mass()).min(1.)}else{0.};
    y.birth=x.birth*f;r.birth=x.birth-y.birth;
    if !r.valid(t)||!y.valid(t){return Err("velocity split moment cone".into())}
    Ok((r,y))
}
/// Exact switching map on three conditional moment pairs.
fn switch(mut x:Moment,r:Rates,h:f64)->Moment{
    let k=r.alpha+r.nu;let a=-(-k*h).exp_m1();
    let p01=(r.alpha/k)*a;let p10=(r.nu/k)*a;
    let mix=|v:[f64;2]|[(1.-p01)*v[0]+p10*v[1],p01*v[0]+(1.-p10)*v[1]];
    x.m=mix(x.m);x.j=mix(x.j);x.z=mix(x.z);x
}
/// Positive symmetric splitting of the frozen PDMP generator.
pub fn react(x:Moment,r:Rates,h:f64)->Result<Moment>{
    if !r.valid()||!h.is_finite()||h<0.{return Err("invalid kinetic rates or duration".into())}
    if x.mass()==0.||h==0.{return Ok(x)}
    let mut x=switch(x,r,h*0.5);
    let a=(-h/r.tau).exp();
    let b=(-(-h/r.tau).exp_m1())*r.target;
    for i in 0..2{
        let b=if i==0{0.}else{b};let j=x.j[i];
        x.j[i]=a*j+b*x.m[i];
        x.z[i]=a*a*x.z[i]+2.*a*b*j+b*b*x.m[i];
    }
    Ok(switch(x,r,h*0.5))
}
/// Positive integrated distance (in normalized-speed seconds) of the same
/// Strang drift suboperator as react. Frozen coefficients; not a stochastic
/// first-passage law. Small h/tau uses the cancellation-free expansion.
pub fn react_with_distance(x:Moment,r:Rates,h:f64)->Result<(Moment,f64)>{
    if !r.valid()||!h.is_finite()||h<0.{return Err("invalid distance rates/duration".into())}
    let m=x.mass();if m==0.||h==0.{return Ok((react(x,r,h)?,0.))}
    let mid=switch(x,r,h*0.5);
    let xi=h/r.tau;
    let b=if xi<0.001{
        h*xi*(0.5+xi*(-1./6.+xi*(1./24.+xi*(-1./120.+xi/720.))))
    }else{h-r.tau*(-(-xi).exp_m1())};
    let a=h-b;
    let distance=(mid.momentum()/m)*a+r.target*(mid.m[1]/m)*b;
    if !distance.is_finite()||distance< -1e-12*h||distance>h*(1.+1e-12){return Err("mean distance outside speed support".into())}
    Ok((react(x,r,h)?,distance.clamp(0.,h)))
}
/// Exact conditional means under frozen coefficients. The convolution is
/// written with expm1 and the lower exponent to avoid resonance cancellation.
#[derive(Clone,Copy,Debug,PartialEq,Serialize,Deserialize)]
pub struct Mobility{pub p:f64,pub u:f64}
impl Mobility {
    pub fn advance(self,r:Rates,h:f64)->Result<Self>{
        if !r.valid()||!h.is_finite()||h<0.||![self.p,self.u].iter().all(|x|x.is_finite()&&(0. ..=1.).contains(x)){return Err("invalid mobility input".into())}
        if h==0.{return Ok(self)}
        let k=r.alpha+r.nu;let l=1./r.tau;
        let pe=r.alpha/k;let ek=(-k*h).exp();let el=(-l*h).exp();
        let gap=(k-l).abs();
        let cv=if gap==0.{(l*h)*el}else{(-k.min(l)*h).exp()*(-(-gap*h).exp_m1())*(l/gap)};
        let p=pe+(self.p-pe)*ek;
        let u=r.target*pe+(self.u-r.target*pe)*el+r.target*(self.p-pe)*cv;
        if ![p,u].iter().all(|x|x.is_finite()&&*x>=-1e-12&&*x<=1.+1e-12){return Err("nonphysical mobility result".into())}
        // Only roundoff of dimensionless probability/mean, not mass pruning.
        Ok(Self{p:p.clamp(0.,1.),u:u.clamp(0.,1.)})
    }
}

#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn finite_characteristic_drift_distance_matches_integral(){
        let r=Rates{alpha:0.2,nu:0.,tau:2.,target:1.};let x=Moment::point(1.,1.,0.,0.);
        for h in [1e-12,1e-5,0.1,1.,10.,100.]{
            let(y,d)=react_with_distance(x,r,h).unwrap();
            assert_eq!(y,react(x,r,h).unwrap());
            assert!(d>=0.&&d<=h);
            if h>=0.1{assert!((d-(h+2.*(-h/2.).exp_m1())).abs()<1e-12);}
            else{assert!((d/(h*h/4.)-1.).abs()<1e-5);}
        }
    }
    #[test]
    fn selective_velocity_flux_carries_moving_mass_not_stopped_mass(){
        let x=Moment::point(0.5,1.,0.,2.).add(Moment::point(0.5,1.,1.,2.));
        let (r,y)=split_velocity_selected(x,1.,2.).unwrap();
        assert_eq!(y.mass(),0.5);assert_eq!(y.momentum(),0.5);
        assert_eq!(r.momentum(),0.);assert_eq!(r.add(y),x);
        assert!(r.valid(2.)&&y.valid(2.));
        let z=Moment::point(2.,0.,0.,2.);
        assert_eq!(split_velocity_selected(z,1.,2.).unwrap(),(z,Moment::default()));
    }
    #[test]
    fn velocity_flux_cone_and_exact_first_two_outgoing_moments(){
        for a in 0..17{for b in a..17{for k in 0..9{
            let x=Moment::point(0.25,0.2,a as f64/16.,2.).add(Moment::point(0.75,0.8,b as f64/16.,1.));
            let c=k as f64/8.;
            let(r,y)=split_velocity_selected(x,c,2.).unwrap();
            assert!(r.valid(2.)&&y.valid(2.));
            for i in 0..2{
                assert!((y.m[i]-c*x.j[i]).abs()<1e-14);
                assert!((y.j[i]-c*x.z[i]).abs()<1e-14);
                for (v,w) in [(r.m[i]+y.m[i],x.m[i]),(r.j[i]+y.j[i],x.j[i]),(r.z[i]+y.z[i],x.z[i])]{assert!((v-w).abs()<1e-14);}
            }
            assert!((r.birth+y.birth-x.birth).abs()<1e-14);
        }}}
    }
    #[test]
    fn conditional_means_and_cone(){
        for k in 0..32{
            let r=Rates{alpha:0.1+k as f64/31.,nu:0.3,tau:2.,target:0.8};
            let a=Moment::point(3.,0.4,0.6,1.);
            let exact=Mobility{p:0.4,u:0.6}.advance(r,1.).unwrap();
            let mut b=a;
            for _ in 0..200{b=react(b,r,0.005).unwrap();assert!(b.valid(2.));}
            assert!((b.mass()-3.).abs()<1e-11);
            assert!((b.m[1]/b.mass()-exact.p).abs()<1e-12);
            assert!((b.momentum()/b.mass()-exact.u).abs()<3e-6);
            assert_eq!(a.birth,b.birth);
        }
        let r=Rates{alpha:0.2,nu:0.3,tau:2.,target:1.}; // exact resonance
        let x=Mobility{p:1.,u:1.};
        let a=x.advance(r,2.).unwrap();let b=x.advance(r,1.).unwrap().advance(r,1.).unwrap();
        assert!((a.u-b.u).abs()<1e-14);
        assert_eq!(Mobility{p:1.,u:1.}.advance(Rates{alpha:0.2,nu:0.,tau:2.,target:1.},86400.).unwrap(),Mobility{p:1.,u:1.});
    }
    #[test]
    fn drive_switch_and_finite_speed_response_are_distinct(){
        let x=Moment::point(2.,0.,0.,0.);
        let r=Rates{alpha:1.,nu:0.,tau:2.,target:1.};
        let y=react(x,r,1.).unwrap();
        assert!((y.m[1]-2.*(1.-(-1f64).exp())).abs()<1e-13);
        assert!(y.momentum()>0.&&y.momentum()<y.m[1]);
        assert!(y.valid(1.));
        assert_eq!(y.birth,0.);
    }
}
