//! Optional bounded ready-stock remap, only after the original tick completed
//! transfers. All merged packet targets must be already ready or identical.
//! Every group is a contiguous FIFO block with mass <= eta, entry span <= h.
use super::*;
#[derive(Clone,Copy,Debug)]
struct Info{m:f64,t:f64}
fn info(p:&Packet)->CoreResult<Option<Info>>{
    let mut m=RoadExpansion::default();let mut clock=None;
    for r in &p.parts{
        if compact_indices(r.tag,r.offset).is_none()||r.a.0!=r.b.0||!r.a.is_some(){return Ok(None)}
        let t=r.a.unwrap();if !finite_nonnegative(t)||!finite_nonnegative(r.mass)||!finite_nonnegative(r.birth){return Err(val("invalid ready rank mark"))}
        if clock.is_some_and(|a:u64|a!=r.a.0){return Ok(None)}
        clock=Some(r.a.0);m.add_finite(r.mass)?;
    }
    Ok(clock.map(|t|Info{m:m.finish(),t:f64::from_bits(t)}))
}
fn group_end(q:&[Packet],start:usize,x:f64,eta:f64,h:f64)->CoreResult<usize>{
    let Some(first)=info(&q[start])? else{return Ok(start+1)};
    if first.m>eta||first.m<=0.{return Ok(start+1)}
    let mut total=first.m;let mut end=start+1;let mut latest=first.t;
    while end<q.len(){
        if !(q[end].target<=x&&q[start].target<=x || q[end].target.to_bits()==q[start].target.to_bits()){break}
        let Some(i)=info(&q[end])? else{break};
        if i.m<=0.||i.m>eta-total||i.t<latest||i.t-first.t>h{break}
        total+=i.m;latest=i.t;end+=1;
    }
    Ok(end)
}
#[derive(Clone,Copy)]
struct Row{key:u64,ord:u32,m:f64,b:f64}
fn merge(q:&[Packet],work:&mut RoadWorkBudget,shell:usize,eta:f64)->CoreResult<Packet>{
    let n=q.iter().try_fold(0usize,|a,p|a.checked_add(p.parts.len())).ok_or_else(||budget("ready rank count overflow"))?;
    if n>u32::MAX as usize{return Err(budget("ready rank index overflow"))}
    let raw=n.saturating_mul(std::mem::size_of::<Row>());
    work.interval(shell.saturating_add(raw).saturating_add(128*1024))?;
    let mut rows=checkpoint_vec(n)?;if rows.capacity()!=n{return Err(budget("ready raw capacity differs"))}
    let mut m=RoadExpansion::default();
    let mut latest=0.0f64;
    for p in q{for r in &p.parts{
        let(k,o)=compact_indices(r.tag,r.offset).ok_or_else(||val("ready compact key"))?;
        let ord=rows.len()as u32;
        rows.push(Row{key:(k as u64)<<32|o as u64,ord,m:r.mass,b:r.birth});
        latest=latest.max(r.a.unwrap());m.add_finite(r.mass)?;
    }}
    let m=m.finish_finite()?;
    if m>eta+4.*f64::EPSILON*eta{return Err(arithmetic("ready rank mass ceiling differs"))}
    rows.sort_unstable_by_key(|r|(r.key,r.ord));
    let groups=usize::from(!rows.is_empty())+rows.windows(2).filter(|p|p[0].key!=p[1].key).count();
    work.interval(shell.saturating_add(raw).saturating_add(groups.saturating_mul(std::mem::size_of::<CorePart>())).saturating_add(128*1024+96))?;
    let mut core=checkpoint_vec(groups)?;if core.capacity()!=groups{return Err(budget("ready output capacity differs"))}
    for g in rows.chunk_by(|a,b|a.key==b.key){
        let(mut m,mut b)=(RoadExpansion::default(),RoadExpansion::default());
        for r in g{m.add_finite(r.m)?;b.add_finite(r.b)?}
        let key=g[0].key;let m=m.finish_finite()?;let b=b.finish_finite()?;
        if m<=0.{return Err(arithmetic("empty merged route mark"))}
        core.push(CorePart{tag:(key>>32)as u32,offset:key as u32,mass:m,birth:b});
    }
    drop(rows);
    let a=PackedTime::new(Some(latest))?;
    let parts=PacketParts::Uniform{a,b:a,rows:Arc::new(core)};
    work.retain_interval(parts.allocated_bytes().saturating_add(96));
    crate::v1_trace::add("ready_rank.input_rows",n as u64);
    crate::v1_trace::add("ready_rank.output_rows",groups as u64);
    crate::v1_trace::add("ready_rank.merged_packets",q.len()as u64);
    crate::v1_trace::add("ready_rank.max_prefix_bound_milliveh_ceil",(250.*m).ceil()as u64);
    Ok(Packet{target:q.last().unwrap().target,parts})
}
pub(super) fn coalesce(q:&mut Vec<Packet>,progress:f64,eta:f64,h:f64,work:&mut RoadWorkBudget)->CoreResult<()>{
    if !eta.is_finite()||eta<=0.||!h.is_finite()||h<=0.||!progress.is_finite(){return Err(val("ready rank contract"))}
    if q.len()<2{return Ok(())}
    let shell=q.len().saturating_mul(std::mem::size_of::<Packet>());
    let mut out:Option<Vec<Packet>>=None;
    let mut i=0usize;let mut removed=0usize;
    while i<q.len(){
        let j=group_end(q,i,progress,eta,h)?;
        if j>i+1{
            if out.is_none(){
                work.interval(shell.saturating_add(128*1024))?;
                let mut v=checkpoint_vec(q.len())?;if v.capacity()!=q.len(){return Err(budget("ready packet capacity differs"))}
                v.extend(q[..i].iter().cloned());out=Some(v);
            }
            out.as_mut().unwrap().push(merge(&q[i..j],work,shell,eta)?);
            removed+=j-i-1;
        }else if let Some(v)=out.as_mut(){v.push(q[i].clone())}
        i=j;
    }
    if let Some(out)=out{
        // Old owner and new descriptor vector were both charged before the
        // allocation. Do not claim any credit for old Arc payloads here.
        work.retain_interval(out.capacity().saturating_mul(std::mem::size_of::<Packet>()));
        *q=out;
        crate::v1_trace::add("ready_rank.removed_packets",removed as u64);
    }
    work.end_interval();
    Ok(())
}
#[cfg(test)]mod tests{
    use super::*;
    fn p(tag:u32,target:f64,t:f64,m:f64)->Packet{let a=PackedTime::new(Some(t)).unwrap();Packet{target,parts:PacketParts::Uniform{a,b:a,rows:Arc::new(vec![CorePart{tag,offset:0,mass:m,birth:2.*m}])}}}
    fn w()->RoadWorkBudget{RoadWorkBudget{limit:Some(10_000_000),base:0,transfer_exclusive_cell_scratch:0,events:0,event_candidate_live_bound:None,incoming:0,incoming_page_cells:0,incoming_cell_rows:None,incoming_live_pages:0,incoming_descriptor_live_bytes:None,compact_events:false,compact_incoming:false,timed_incoming_control_bytes:None,timed_referenced_rows:None,packed_ref_saved:None,interval_retained:0,interval_transient:0,service_events:None}}
    #[test]fn contiguous_ready_and_identical_future_target_only(){
        let mut q=vec![p(1,1.,1.,0.0625),p(1,2.,2.,0.0625),p(2,3.,3.,0.0625),p(3,10.,4.,0.0625),p(3,10.,5.,0.0625),p(3,11.,6.,0.0625)];
        coalesce(&mut q,3.,0.25,60.,&mut w()).unwrap();
        assert_eq!(q.len(),3);assert_eq!(q[0].target,3.);assert_eq!(q[1].target,10.);assert_eq!(q[2].target,11.);
        assert_eq!(q[0].parts.len(),2);assert_eq!(mass(&q[0]),0.1875);
        let r=q[0].parts.iter().next().unwrap();assert_eq!(r.tag,1);assert_eq!(r.mass,0.125);assert_eq!(r.birth,0.25);assert_eq!(r.a.unwrap(),3.);
        assert_eq!(q[1].parts.len(),1);assert_eq!(mass(&q[1]),0.125);
    }
    #[test]fn cap_span_and_nonpoint_are_protected(){
        let mut q=vec![p(1,1.,0.,0.125),p(1,1.,60.1,0.125),p(1,1.,60.2,0.25),p(1,1.,60.3,0.125)];
        coalesce(&mut q,2.,0.25,60.,&mut w()).unwrap();assert_eq!(q.len(),4);
        let mut q=vec![p(1,1.,0.,0.125),p(1,1.,0.,0.125)];
        let mut work=w();work.limit=Some(1);assert!(coalesce(&mut q,2.,0.25,60.,&mut work).is_err());assert_eq!(q.len(),2);
    }
}
