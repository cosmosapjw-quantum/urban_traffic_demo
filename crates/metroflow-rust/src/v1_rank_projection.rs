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
// Bounded dynamic programming over contiguous blocks of the fine grid.
// Each block has a local causal transport-delay budget. No heap allocation.
fn adaptive_partition(g:Grid,mass:[Acc;MAX_BINS],delay:[Acc;MAX_BINS],dt:f64,milli:u64)->CoreResult<Grid>{
    let tol=dt*(milli as f64/1000.);
    if !tol.is_finite()||tol<=0.||milli>1000{return Err(val("adaptive rank tolerance outside domain"))}
    let mut best=[usize::MAX;MAX_BINS+1];let mut cost=[f64::INFINITY;MAX_BINS+1];let mut prev=[0usize;MAX_BINS+1];
    best[0]=0;cost[0]=0.;
    for j in 1..=g.n{
        for i in 0..j{
            if best[i]==usize::MAX{continue}
            let(mut m,mut d)=(Acc::default(),Acc::default());
            for k in i..j{
                m.add(mass[k].value())?;
                d.add(delay[k].value())?;
                d.add(mass[k].value()*(g.ends[j-1]-g.ends[k]))?;
            }
            let budget=tol*m.value();
            if !budget.is_finite(){return Err(arithmetic("adaptive rank budget overflow"))}
            if d.value()>budget+1e-12*budget.max(1e-300){continue}
            let count=best[i]+1;let score=cost[i]+d.value();
            if !score.is_finite(){return Err(arithmetic("adaptive rank total delay overflow"))}
            if count<best[j]||(count==best[j]&&score<cost[j]){best[j]=count;cost[j]=score;prev[j]=i;}
        }
    }
    if best[g.n]==usize::MAX{return Err(arithmetic("adaptive rank no admissible fine-grid partition"))}
    let mut ends=[0.;MAX_BINS];let mut j=g.n;let n=best[j];
    for k in (0..n).rev(){ends[k]=g.ends[j-1];j=prev[j];}
    Ok(Grid{lo:g.lo,ends,n,sparse:false})
}
fn adapt_grid(g:Grid,len:usize,get:&impl Fn(usize)->Part,dt:f64,milli:u64)->CoreResult<Grid>{
    if g.sparse||g.n<=1{return Ok(g)}
    let(mut mass,mut delay)=([Acc::default();MAX_BINS],[Acc::default();MAX_BINS]);
    for i in 0..len{
        let p=get(i);
        for k in 0..g.n{let f=g.fraction(p,k);if f>0.{
            let m=p.mass*f;mass[k].add(m)?;delay[k].add(m*g.delay(p,k))?;
        }}
    }
    adaptive_partition(g,mass,delay,dt,milli)
}

// A receiving cell normally has one route offset per tag. When this is
// checked, stable tag scatter is exactly the original (tag,offset,ordinal)
// order, without comparison sort. Repeated-cell paths use the old fallback.
#[derive(Clone,Copy,Default)]
struct TagSlot{offset:u32,count:u32,cursor:u32}
pub(super) struct RankScatter{slots:Vec<TagSlot>}
impl RankScatter{
    pub(super) fn bytes(tags:usize)->usize{tags.saturating_mul(std::mem::size_of::<TagSlot>())}
    pub(super) fn new(tags:usize)->CoreResult<Self>{
        let mut slots=checkpoint_vec(tags)?;
        if slots.capacity()!=tags{return Err(budget("rank scatter exact allocation differs"))}
        slots.resize(tags,TagSlot::default());Ok(Self{slots})
    }
    fn reorder(&mut self,len:usize,get:&impl Fn(usize)->Part,order:&mut Vec<(u64,u32)>)->CoreResult<bool>{
        if len<self.slots.len().saturating_mul(2)||len>u32::MAX as usize||order.capacity()<len{return Ok(false)}
        self.slots.fill(TagSlot::default());
        for i in 0..len{
            let p=get(i);let (tag,offset)=compact_indices(p.tag,p.offset).ok_or_else(||val("rank scatter wide source"))?;
            let slot=self.slots.get_mut(tag as usize).ok_or_else(||val("rank scatter tag outside registry"))?;
            if slot.count!=0&&slot.offset!=offset{return Ok(false)}
            slot.offset=offset;slot.count=slot.count.checked_add(1).ok_or_else(||budget("rank scatter count overflow"))?;
        }
        let mut total=0u32;
        for s in &mut self.slots{s.cursor=total;total=total.checked_add(s.count).ok_or_else(||budget("rank scatter prefix overflow"))?;}
        if total as usize!=len{return Err(arithmetic("rank scatter census differs"))}
        order.clear();order.resize(len,(0,0));
        for i in 0..len{
            let p=get(i);let (tag,offset)=compact_indices(p.tag,p.offset).ok_or_else(||val("rank scatter wide source"))?;
            let slot=&mut self.slots[tag as usize];
            order[slot.cursor as usize]=(((tag as u64)<<32)|offset as u64,i as u32);
            slot.cursor+=1;
        }
        Ok(true)
    }
}
fn sorted_ordinals(len:usize,get:&impl Fn(usize)->Part,order:&mut Vec<(u64,u32)>,scatter:Option<&mut RankScatter>)->CoreResult<bool>{
    if let Some(scatter)=scatter{if scatter.reorder(len,get,order)?{return Ok(true)}}
    order.clear();
    for i in 0..len{let p=get(i);let (tag,offset)=compact_indices(p.tag,p.offset).ok_or_else(||val("rank sort wide source"))?;order.push((((tag as u64)<<32)|offset as u64,i as u32));}
    order.sort_unstable();Ok(false)
}

// Explicit two-pass count and emit. Cached integer keys avoid repeated packed
// payload decoding in the sort comparator; source ordinal resolves ties.
// All output vectors reserved once with actual cardinality. No per-row maps.
#[cfg(test)]
pub(super) fn project(len:usize,get:impl Fn(usize)->Part,target:f64,bins:usize,dt:f64,record_budget:usize,scratch:usize,work:&mut RoadWorkBudget)->CoreResult<(Vec<Packet>,f64)>{
    let bytes=len.saturating_mul(std::mem::size_of::<(u64,u32)>());
    work.interval(scratch.saturating_add(bytes))?;
    let mut workspace=checkpoint_vec(len)?;
    project_with(len,get,target,bins,None,dt,record_budget,scratch.saturating_add(bytes),work,&mut workspace,None)
}
pub(super) fn project_with(len:usize,get:impl Fn(usize)->Part,target:f64,bins:usize,adaptive:Option<u64>,dt:f64,record_budget:usize,scratch:usize,work:&mut RoadWorkBudget,order:&mut Vec<(u64,u32)>,scatter:Option<&mut RankScatter>)->CoreResult<(Vec<Packet>,f64)>{
    let grid=grid(len,&get,bins,dt)?;
    let grid=if let Some(milli)=adaptive{adapt_grid(grid,len,&get,dt,milli)?}else{grid};
    if len==0{return Ok((vec![],0.))}
    if len>u32::MAX as usize{return Err(budget("rank source ordinal overflow"))}
    if order.capacity()<len{return Err(budget("rank workspace capacity too small"))}
    let shell=grid.n*std::mem::size_of::<Packet>()+grid.n*96;
    let base=scratch.saturating_add(shell).saturating_add(128*1024);
    work.interval(base)?;
    if sorted_ordinals(len,&get,order,scatter)?{
        crate::v1_trace::add("rank.stable_scatter_rows",len as u64);
        crate::v1_trace::add("rank.stable_scatter_cells",1);
    }else{crate::v1_trace::add("rank.comparator_sort_rows",len as u64);}
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
    if let Some(milli)=adaptive{
        let limit=all.value()*dt*(milli as f64/1000.);
        if !limit.is_finite()||delay.value()>limit+1e-10*limit.max(1e-300){return Err(arithmetic("adaptive rank actual transport delay exceeds budget"))}
        crate::v1_trace::add("rank.adaptive_cells",1);
        crate::v1_trace::add("rank.adaptive_bins",grid.n as u64);
        crate::v1_trace::add("rank.adaptive_fine_bins_limit",bins as u64);
        crate::v1_trace::add("rank.adaptive_delay_budget_milliveh_s_ceil",(1000.*limit).ceil()as u64);
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
    crate::v1_trace::add("rank.local_causal_prefix_upper_milliveh_ceil",(1000.*bin_totals.iter().map(|a|a.value()).fold(0.,f64::max)).ceil()as u64);
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
    #[test] fn adaptive_uses_minimal_feasible_causal_partition(){
        let parts=[p(0,0.,4.,1.),p(1,3.,4.,9.)];
        let fine=grid(parts.len(),&|i|parts[i],4,4.).unwrap();
        let chosen=adapt_grid(fine,parts.len(),&|i|parts[i],4.,500).unwrap();
        assert_eq!(chosen.n,1);assert_eq!(chosen.ends[0],4.);
        let early=[p(0,0.,0.5,9.),p(1,3.,4.,1.)];
        let fine=grid(early.len(),&|i|early[i],4,4.).unwrap();
        let chosen=adapt_grid(fine,early.len(),&|i|early[i],4.,500).unwrap();
        assert_eq!(chosen.n,2);assert_eq!(chosen.ends[1],4.);
        let mut ws=Vec::with_capacity(early.len());let mut w=work();
        let (out,m)=project_with(early.len(),|i|early[i],10.,4,Some(500),4.,100,0,&mut w,&mut ws,None).unwrap();
        assert_eq!(m,10.);assert_eq!(out.len(),2);assert!(out.iter().flat_map(|p|p.parts.iter()).all(|p|p.a.0==p.b.0));
    }
    #[test] fn stable_scatter_matches_sort_and_repeated_offsets_fall_back(){
        let rows:Vec<_>=(0..1024).map(|i|p((i*13)%17,0.,2.,(i+1)as f64)).collect();
        let mut scatter=RankScatter::new(17).unwrap();let mut a=Vec::with_capacity(rows.len());let mut b=Vec::with_capacity(rows.len());
        assert!(sorted_ordinals(rows.len(),&|i|rows[i],&mut a,Some(&mut scatter)).unwrap());
        assert!(!sorted_ordinals(rows.len(),&|i|rows[i],&mut b,None).unwrap());
        assert_eq!(a,b);
        let mut rows=rows;rows[17].offset=2;
        assert!(!sorted_ordinals(rows.len(),&|i|rows[i],&mut a,Some(&mut scatter)).unwrap());
        sorted_ordinals(rows.len(),&|i|rows[i],&mut b,None).unwrap();assert_eq!(a,b);
    }
    #[test] fn adaptive_partition_matches_exhaustive_fine_grid_partitions(){
        let mut ends=[0.;MAX_BINS];ends[..4].copy_from_slice(&[1.,2.,3.,4.]);
        let g=Grid{lo:0.,ends,n:4,sparse:false};
        for encoded in 0..256usize{
            let mut mass=[Acc::default();MAX_BINS];let mut delay=[Acc::default();MAX_BINS];
            let m:[u64;4]=std::array::from_fn(|k|((encoded>>(2*k))&3)as u64);
            for mask in 0..16usize{
                let d:[u64;4]=std::array::from_fn(|k|m[k]*((mask>>k)&1)as u64);
                for k in 0..4{mass[k]=Acc::default();mass[k].add(m[k] as f64).unwrap();delay[k]=Acc::default();delay[k].add(d[k] as f64*0.5).unwrap();}
                let mut best=(usize::MAX,u64::MAX);
                for bits in 0..8usize{
                    let(mut lo,mut count,mut sum_d,mut ok)=(0usize,0usize,0u64,true);
                    for hi in 0..4{if hi==3||bits&(1<<hi)!=0{
                        let mm=m[lo..=hi].iter().sum::<u64>();
                        let dd=(lo..=hi).map(|k|d[k]+2*m[k]*(hi-k)as u64).sum::<u64>();
                        ok&=dd<=4*mm;count+=1;sum_d+=dd;lo=hi+1;
                    }}
                    if ok{best=best.min((count,sum_d));}
                }
                let q=adaptive_partition(g,mass,delay,4.,500).unwrap();
                let(mut lo,mut sum_d)=(0usize,0u64);
                for &r in &q.ends[..q.n]{let hi=r as usize-1;sum_d+=(lo..=hi).map(|k|d[k]+2*m[k]*(hi-k)as u64).sum::<u64>();lo=hi+1;}
                assert_eq!((q.n,sum_d),best);
            }
        }
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


#[cfg(feature="native-cli")]
pub(super) fn adaptive_probe()->CoreResult<[usize;2]>{
    let make=|tag,a,b,m|Ok(Part{tag,offset:0,mass:m,birth:m,a:PackedTime::new(Some(a))?,b:PackedTime::new(Some(b))?});
    let early=[make(0,0.,0.5,9.)?,make(1,3.,4.,1.)?];
    let late=[make(0,0.,4.,1.)?,make(1,3.,4.,9.)?];
    let early=std::hint::black_box(early);let late=std::hint::black_box(late);
    let e=adapt_grid(grid(2,&|i|early[i],4,4.)?,2,&|i|early[i],4.,500)?;
    let l=adapt_grid(grid(2,&|i|late[i],4,4.)?,2,&|i|late[i],4.,500)?;
    Ok([e.n,l.n])
}

#[cfg(feature="native-cli")]
pub struct RankScatterProbe{scatter:RankScatter,order:Vec<(u64,u32)>,rows:Vec<Part>}
#[cfg(feature="native-cli")]
impl RankScatterProbe{
    pub fn new()->CoreResult<Self>{
        let mut rows=checkpoint_vec(1024)?;
        let a=PackedTime::new(Some(0.))?;let b=PackedTime::new(Some(1.))?;
        for i in 0..1024{rows.push(Part{tag:(i*13)%17,offset:1,mass:(i+1)as f64,birth:0.,a,b})}
        Ok(Self{scatter:RankScatter::new(17)?,order:checkpoint_vec(1024)?,rows})
    }
    pub fn run(&mut self)->CoreResult<[u64;2]>{
        let rows=&self.rows;
        if !sorted_ordinals(rows.len(),&|i|rows[i],&mut self.order,Some(&mut self.scatter))?{return Err(val("rank scatter probe fallback"))}
        Ok([self.order.len() as u64,self.order.iter().map(|x|x.1 as u64).sum()])
    }
}
