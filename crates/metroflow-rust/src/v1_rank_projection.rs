//! Separate research closure: causal right-endpoint marked rank remapping.
use super::*;
const MAX_BINS:usize=16;
#[derive(Clone,Copy,Default)]
pub(super) struct Acc { hi:f64,lo:f64 }
impl Acc{
    pub(super) fn add(&mut self,x:f64)->CoreResult<()>{
        if !finite_nonnegative(x){return Err(arithmetic("rank remap nonfinite or negative summand"))}
        let t=self.hi+x;
        if !t.is_finite(){return Err(arithmetic("rank remap sum overflow"))}
        self.lo+=if self.hi>=x{(self.hi-t)+x}else{(x-t)+self.hi};
        if !self.lo.is_finite(){return Err(arithmetic("rank remap correction overflow"))}
        self.hi=t;Ok(())
    }
    pub(super) fn value(self)->f64{self.hi+self.lo}
}
#[derive(Clone,Copy)]
struct Grid{lo:f64,ends:[f64;MAX_BINS],n:usize,sparse:bool}
impl Grid{
    fn fraction(self,p:Part,k:usize)->f64{
        let(a,b)=(p.a.unwrap(),p.b.unwrap());
        if self.n==1{return 1.}
        let r=self.ends[k];
        let l=if k==0{self.lo}else{self.ends[k-1]};
        if a==b{return f64::from(a<=r&&(k==0||a>l))}
        ((b.min(r)-a.max(l)).max(0.)/(b-a)).min(1.)
    }
    fn delay(self,p:Part,k:usize)->f64{
        let(a,b)=(p.a.unwrap(),p.b.unwrap());let r=self.ends[k];
        if a==b{return (r-a).max(0.)}
        let l=if k==0{self.lo}else{self.ends[k-1]};
        (r-(a.max(l)+0.5*(b.min(r)-a.max(l)))).max(0.)
    }
}
fn grid(len:usize,get:&impl Fn(usize)->Part,bins:usize,dt:f64)->CoreResult<Grid>{
    if !(1..=MAX_BINS).contains(&bins)||!dt.is_finite()||dt<=0.{return Err(val("rank bins/dt outside domain"))}
    let(mut lo,mut hi)=(f64::INFINITY,f64::NEG_INFINITY);
    let mut exact=[0.;MAX_BINS];let mut n=0;let mut sparse=true;
    for i in 0..len{
        let p=get(i);
        if compact_indices(p.tag,p.offset).is_none()||!p.mass.is_finite()||p.mass<=0.||!finite_nonnegative(p.birth){return Err(val("invalid marked rank source"))}
        let(Some(a),Some(b))=(p.a.option(),p.b.option())else{return Err(val("rank remap needs explicit clocks"))};
        if a<0.||b<a||!a.is_finite()||!b.is_finite(){return Err(val("invalid rank clocks"))}
        lo=lo.min(a);hi=hi.max(b);
        if sparse {
            if a!=b {sparse=false}
            else if !exact[..n].contains(&a){if n==bins{sparse=false}else{exact[n]=a;n+=1}}
        }
    }
    if len==0{return Ok(Grid{lo:0.,ends:exact,n:0,sparse:true})}
    if hi-lo>dt+1e-8{return Err(val("rank remap spans more than one tick"))}
    if sparse{exact[..n].sort_unstable_by(f64::total_cmp);return Ok(Grid{lo,ends:exact,n,sparse:true})}
    let mut ends=[0.;MAX_BINS];let mut n=0;let mut prev=lo;
    for k in 1..=bins{let x=if k==bins{hi}else{lo+(hi-lo)*(k as f64/bins as f64)};
        if x>prev||n==0&&k==bins{ends[n]=x;n+=1;prev=x;}
    }
    Ok(Grid{lo,ends,n,sparse:false})
}
// Explicit two-pass count and emit. Cached integer keys avoid repeated packed
// payload decoding in the sort comparator; source ordinal resolves ties.
// All output vectors reserved once with actual cardinality. No per-row maps.
#[cfg(test)]
pub(super) fn project(len:usize,get:impl Fn(usize)->Part,target:f64,bins:usize,dt:f64,record_budget:usize,scratch:usize,work:&mut RoadWorkBudget)->CoreResult<(Vec<Packet>,f64)>{
    let bytes=len.saturating_mul(std::mem::size_of::<(u64,u32)>());
    work.interval(scratch.saturating_add(bytes))?;
    let mut workspace=checkpoint_vec(len)?;
    project_with(len,get,target,bins,dt,record_budget,scratch.saturating_add(bytes),work,&mut workspace)
}
pub(super) fn project_with(len:usize,get:impl Fn(usize)->Part,target:f64,bins:usize,dt:f64,record_budget:usize,scratch:usize,work:&mut RoadWorkBudget,order:&mut Vec<(u64,u32)>)->CoreResult<(Vec<Packet>,f64)>{
    let grid=grid(len,&get,bins,dt)?;
    if len==0{return Ok((vec![],0.))}
    if len>u32::MAX as usize{return Err(budget("rank source ordinal overflow"))}
    if order.capacity()<len{return Err(budget("rank workspace capacity too small"))}
    let shell=grid.n*std::mem::size_of::<Packet>()+grid.n*96;
    let base=scratch.saturating_add(shell).saturating_add(128*1024);
    work.interval(base)?;
    order.clear();
    for i in 0..len{let p=get(i);let (tag,offset)=compact_indices(p.tag,p.offset).unwrap();order.push((((tag as u64)<<32)|offset as u64,i as u32));}
    order.sort_unstable();
    let mut counts=[0usize;MAX_BINS];
    for group in order.chunk_by(|a,b|a.0==b.0){
        if grid.n==1{counts[0]+=1;continue}
        let mut mask=0u32;
        for &(_,i) in group{
            let p=get(i as usize);
            for k in 0..grid.n{
                let f=grid.fraction(p,k);
                if f>0.&&p.mass*f>0.{mask|=1<<k}
                else if f>0.&&p.birth*f>0.{return Err(arithmetic("rank remap mass underflow with birth"))}
            }
        }
        for k in 0..grid.n{counts[k]+=usize::from(mask&(1<<k)!=0);}
    }
    let records=counts.iter().try_fold(0usize,|a,&b|a.checked_add(b)).ok_or_else(||budget("rank output count overflow"))?;
    if records>record_budget{return Err(budget("rank projection record budget"))}
    let bytes=records.checked_mul(std::mem::size_of::<CorePart>()).ok_or_else(||budget("rank output bytes overflow"))?;
    work.interval(base.saturating_add(bytes))?;
    let mut core:[Vec<CorePart>;MAX_BINS]=std::array::from_fn(|_|Vec::new());
    for k in 0..grid.n{core[k]=checkpoint_vec(counts[k])?;if core[k].capacity()!=counts[k]{return Err(budget("rank output exact allocation differs"))}}
    let(mut all,mut delay)=(Acc::default(),Acc::default());let mut bin_totals=[Acc::default();MAX_BINS];
    for group in order.chunk_by(|a,b|a.0==b.0){
        let mut ms=[Acc::default();MAX_BINS];let mut bs=[Acc::default();MAX_BINS];
        let(mut old_m,mut old_b)=(Acc::default(),Acc::default());
        for &(_,i) in group{
            let p=get(i as usize);old_m.add(p.mass)?;old_b.add(p.birth)?;
            for k in 0..grid.n{let f=grid.fraction(p,k);if f>0.{
                let m=p.mass*f;let b=p.birth*f;
                ms[k].add(m)?;bs[k].add(b)?;delay.add(m*grid.delay(p,k))?;
            }}
        }
        let(mut new_m,mut new_b)=(Acc::default(),Acc::default());let key=group[0].0;
        for k in 0..grid.n{
            let(m,b)=(ms[k].value(),bs[k].value());new_m.add(m)?;new_b.add(b)?;
            if m>0.{core[k].push(CorePart{tag:(key>>32)as u32,offset:key as u32,mass:m,birth:b});all.add(m)?;bin_totals[k].add(m)?;}
        }
        // Per immutable route/offset, relative finite floating error plus
        // four subnormal ULPs. Fail closed, never silently lose a mark.
        let close=|a:f64,b:f64|(a-b).abs()<=1e-10*a.max(b)+4.*f64::from_bits(1);
        if !close(old_m.value(),new_m.value())||!close(old_b.value(),new_b.value()){return Err(arithmetic("rank per-mark conservation differs"))}
    }
    order.clear();
    let mut out=checkpoint_vec(grid.n)?;
    if out.capacity()!=grid.n{return Err(budget("rank packet exact allocation differs"))}
    let mut actual=0;
    for k in 0..grid.n{
        if core[k].len()!=counts[k]{return Err(arithmetic("rank output census differs"))}
        if core[k].is_empty(){continue}
        actual+=core[k].len();
        let a=PackedTime::new(Some(grid.ends[k]))?;
        let parts=PacketParts::Uniform{a,b:a,rows:Arc::new(std::mem::take(&mut core[k]))};
        work.retain_interval(parts.allocated_bytes().saturating_add(96+std::mem::size_of::<Packet>()));
        out.push(Packet{target,parts});
    }
    work.end_interval();
    crate::v1_trace::add("rank.cells",1);
    crate::v1_trace::add("rank.sparse_exact_point_cells",u64::from(grid.sparse));
    crate::v1_trace::add("rank.in_rows",len as u64);
    crate::v1_trace::add("rank.out_rows",actual as u64);
    crate::v1_trace::add("rank.out_packets",out.len()as u64);
    // Quantized upward diagnostic, not a global accumulated error certificate.
    crate::v1_trace::add("rank.local_delay_milliveh_s_ceil",(1000.*delay.value()).ceil()as u64);
    crate::v1_trace::add("rank.local_generic_prefix_bound_milliveh_ceil",(250.*bin_totals.iter().map(|a|a.value()).fold(0.,f64::max)).ceil()as u64);
    Ok((out,all.value()))
}
#[cfg(test)]
mod tests {
    use super::*;
    fn p(tag:usize,a:f64,b:f64,m:f64)->Part{Part{tag,offset:1,mass:m,birth:m*3.,a:PackedTime::new(Some(a)).unwrap(),b:PackedTime::new(Some(b)).unwrap()}}
    fn work()->RoadWorkBudget{RoadWorkBudget{limit:Some(10_000_000),base:0,transfer_exclusive_cell_scratch:0,source_key_growth:0,events:0,event_candidate_live_bound:None,incoming:0,incoming_page_cells:0,incoming_cell_rows:None,incoming_live_pages:0,incoming_descriptor_live_bytes:None,compact_events:false,compact_incoming:false,timed_incoming_control_bytes:None,timed_referenced_rows:None,packed_ref_saved:None,interval_retained:0,interval_transient:0,service_events:None}}
    #[test] fn all_atoms_and_intervals_no_fallback_and_marked_conservation(){
        let parts=[p(2,0.,4.,2.),p(1,1.,1.,3.),p(2,2.,2.,1.),p(1,4.,6.,2.),p(1,5.,5.,1.)];
        let mut w=work();
        let (out,added)=project(parts.len(),|i|parts[i],50.,3,10.,100,0,&mut w).unwrap();
        assert_eq!(added,9.);assert!(out.len()<=3);
        let mut prev=-1.;
        for pkt in &out{assert_eq!(pkt.target,50.);for x in &pkt.parts{assert_eq!(x.a.0,x.b.0);assert!(x.a.unwrap()>=prev);prev=x.a.unwrap();}}
        for (tag,m) in [(1,6.),(2,3.)]{assert!((sum(out.iter().flat_map(|p|p.parts.iter()).filter(|r|r.tag==tag).map(|r|r.mass))-m).abs()<1e-12);assert!((sum(out.iter().flat_map(|p|p.parts.iter()).filter(|r|r.tag==tag).map(|r|r.birth))-3.*m).abs()<1e-12);}
        let mut w=work();let (out,_)=project(parts.len(),|i|parts[i],50.,1,10.,100,0,&mut w).unwrap();
        assert_eq!(out.len(),1);assert_eq!(out[0].parts.len(),2);assert!(out[0].parts.iter().all(|p|p.a.unwrap()==6.));
    }
    #[test] fn sparse_point_clocks_are_unchanged_and_budget_fail_closed(){
        let parts=[p(1,1.,1.,1.),p(2,4.,4.,2.),p(1,1.,1.,3.)];
        let (out,_)=project(parts.len(),|i|parts[i],10.,4,10.,10,0,&mut work()).unwrap();
        assert_eq!(out.len(),2);assert_eq!(out[0].parts.iter().next().unwrap().a.unwrap(),1.);assert_eq!(out[1].parts.iter().next().unwrap().a.unwrap(),4.);
        let mut w=work();w.limit=Some(1);assert!(project(parts.len(),|i|parts[i],10.,4,10.,10,0,&mut w).is_err());
    }
}

#[cfg(feature="native-cli")]
pub(super) fn moment_probe(values:&[(f64,f64)])->CoreResult<[f64;2]>{
    let (mut m,mut b)=(Acc::default(),Acc::default());
    for &(x,y) in values{m.add(x)?;b.add(y)?;}
    Ok([m.value(),b.value()])
}
