//! Native ownership bridge. A new wire and identity deliberately prevent an
//! AKM state from being interpreted as the original exact packet engine.
use super::*;
use crate::v1_akm::{State,MODEL,HYBRID_MODEL,INTERFACE_MODEL,ROAD_ROW_LIMIT};
use crate::v1_journey::{Service,advance_akm_tick};
use crate::v1_road::{read_len,write_len};
use serde_json::{json,Value};

const PILOT_MODEL:&str="akm-native-reserved-interface-clock-v1";

struct Binding<'a>{
    owners:&'a[Option<usize>],classes:&'a[String],freight:&'a[f64],
    legs:&'a[SharedJourneyLeg],
}
impl Binding<'_>{
    fn check(&self,s:&State,j:&Journey,service:&Service)->CoreResult<()>{
        if s.t!=j.0{return Err(bad("AKM owner clocks differ"))}
        let stages=stage_sums(j,self.legs.len())?;
        let mut active=HashMap::<usize,f64>::new();
        for (tag,m) in s.active_by_tag(){
            if let Some(i)=*self.owners.get(tag).ok_or_else(||bad("AKM owner registry differs"))?{*active.entry(i).or_default()+=m;}
        }
        for (i,l) in self.legs.iter().enumerate(){
            if l.5==1||l.5==2{
                let mass=stages[i]+active.get(&i).copied().unwrap_or(0.);
                if (j.4[i]-j.5[i]-mass).abs()>1e-9*l.1.max(1.){
                    return Err(bad(format!("AKM journey/road owner mass differs at leg {i}")));
                }
            }
        }
        let check=|name:&str,a:f64,b:f64|->CoreResult<()>{
            let k=self.classes.iter().position(|c|c==name).ok_or_else(||bad("AKM class absent"))?;
            let row=s.class[k];
            if (a-row[0]).abs()>1e-9*row[0].max(1.)||(b-row[1]).abs()>1e-9*row[1].max(1.){
                return Err(bad(format!("AKM {name} physical class differs: {a} {b} vs {row:?}")))
            }Ok(())
        };
        check("car",fsum(self.legs.iter().enumerate().filter(|(_,l)|l.5==1).map(|(i,_)|j.4[i]))-fsum(j.1.iter().map(|a|a.1)),
            fsum(self.legs.iter().enumerate().filter(|(_,l)|l.5==1).map(|(i,_)|j.5[i]))+fsum(j.2.iter().filter(|a|self.legs[a.0].5==1).map(|a|a.1)))?;
        check("freight",fsum(self.freight.iter().zip(&service.2).filter(|(_,r)|**r).map(|(m,_)|*m)),fsum(service.3.iter().copied()))?;
        check("scheduled_bus",fsum(service.0.iter().map(|r|r.0 as f64+if r.1==1{1.}else{0.})),
            fsum(service.0.iter().map(|r|r.0 as f64+if r.1==1{r.3}else{0.})))?;
        Ok(())
    }
}
fn check(e:&NativeWholeEngine,s:&State,j:&Journey,service:&ServiceCheckpoint)->CoreResult<()>{
    s.check(&e.road)?;
    e.journey.check_service_binding(j,&service.0)?;
    for x in service.1.iter(){
        if x.0>=e.tags.len()||x.1>=e.group_count||x.2.is_some_and(|i|i>=e.group_count)||!x.3.is_finite()||x.3<=0.||!x.4.is_finite()||!x.5.is_finite()||x.4>x.5||x.5>s.t+1e-8||!x.6.is_finite()||x.6<0.{
            return Err(bad("AKM event binding differs"))
        }
    }
    Binding{owners:&e.car_tag_legs,classes:&e.class_names,freight:&e.freight_vehicles,legs:e.journey.legs()}.check(s,j,&service.0)
}
fn ledger(e:&NativeWholeEngine,j:&Journey)->Value{
    let profiles:Vec<_>=e.profiles.iter().map(|p|fraction(p,j.0)).collect();
    let mut v=[[0.;4];3];
    for (i,a) in e.amounts.iter().enumerate(){
        let carrier=e.journey.legs()[i].1;
        for k in 0..3{let ratio=if carrier!=0.{a[k]/carrier}else{0.};
            v[k][0]+=a[k]*profiles[e.profile_ids[i]];
            v[k][1]+=ratio*j.4[i];v[k][2]+=ratio*j.5[i];v[k][3]+=ratio*j.7[i];
        }
    }
    let row=|k:usize|json!({"requested":v[k][0],"released":v[k][1],"completed":v[k][2],"active":v[k][1]-v[k][2],"pending":v[k][0]-v[k][1],"released_intent_first_moment":v[k][3]});
    json!({"persons":row(0),"vehicles":row(1),"cargo_kg":row(2)})
}
fn save(e:&NativeWholeEngine,s:&State,id:&str,path:&str)->CoreResult<()>{
    check(e,s,e.journey.state(),&e.service.checkpoint())?;
    let tmp=format!("{path}.stage-{}",std::process::id());
    let mut f=BufWriter::with_capacity(1024*1024,std::fs::OpenOptions::new().create_new(true).write(true).open(&tmp).map_err(io)?);
    f.write_all(if s.interface{b"AKMFULL3"}else if s.whole_bus_class.is_some(){b"AKMFULL2"}else{b"AKMFULL1"}).map_err(io)?;write_len(&mut f,id.len())?;f.write_all(id.as_bytes()).map_err(io)?;
    s.write(&mut f)?;e.service.write_state(&mut f)?;e.journey.write_state(&mut f)?;
    f.flush().map_err(io)?;f.get_ref().sync_all().map_err(io)?;drop(f);
    if std::path::Path::new(path).exists(){return Err(bad("AKM output already exists"))}
    std::fs::rename(tmp,path).map_err(io)?;sync_parent_native(path)
}
fn read(e:&mut NativeWholeEngine,id:&str,path:&str,whole_bus_class:Option<usize>,interface:bool)->CoreResult<State>{
    let mut f=BufReader::with_capacity(1024*1024,File::open(path).map_err(io)?);
    let mut magic=[0;8];f.read_exact(&mut magic).map_err(io)?;
    if &magic!=(if interface{b"AKMFULL3"}else if whole_bus_class.is_some(){b"AKMFULL2"}else{b"AKMFULL1"})||read_len(&mut f,id.len())?!=id.len(){return Err(bad("AKM checkpoint schema/identity differs"))}
    let mut raw=vec![0;id.len()];f.read_exact(&mut raw).map_err(io)?;
    if raw!=id.as_bytes(){return Err(bad("AKM checkpoint manifest binding differs"))}
    let s=State::read(&mut f,&e.road,whole_bus_class,interface)?;
    let pool=e.road_storage_bytes.ok_or_else(||bad("AKM dynamic pool absent"))?;
    let remaining=pool.checked_sub(s.work_reserve()).filter(|x|*x>0).ok_or_else(||CoreError::resource("AKM read reserve"))?;
    let service=e.service.read_state_codec(&mut f,e.event_limit,Some(remaining/3),false,false)?;
    let remaining=remaining.checked_sub(service_event_storage_bytes(&service)).filter(|x|*x>0).ok_or_else(||CoreError::resource("AKM owner read reserve"))?;
    e.journey.set_phase_storage_budget(remaining)?;
    let j=e.journey.read_state(&mut f)?;
    let mut tail=[0;1];if f.read(&mut tail).map_err(io)?!=0{return Err(bad("AKM checkpoint trailing bytes"))}
    check(e,&s,&j,&service)?;
    e.journey.install_state(j);e.service.install_state(service);Ok(s)
}
pub fn run_akm_native(manifest:Value,manifest_sha:&str,mode:&str,source:&str,target:f64,threads:usize,output:&str)->CoreResult<Value>{
    if manifest_sha.len()!=64||!manifest_sha.bytes().all(|b|b.is_ascii_hexdigit())||!target.is_finite()||target<0.{return Err(bad("AKM manifest hash or target"))}
    if manifest.as_object().is_some_and(|m|m.keys().any(|k|k.starts_with("research_"))){return Err(bad("AKM accepts original native declarations only"))}
    let start=Instant::now();
    let(mut e,calendar_legs,calendar_totals)=build_native_input(manifest,threads)?;
    let build_s=start.elapsed().as_secs_f64();
    let (pilot,hybrid,interface,mode)=if let Some(m)=mode.strip_prefix("pilot-"){(true,true,true,m)}else if let Some(m)=mode.strip_prefix("interface-"){(false,true,true,m)}else if let Some(m)=mode.strip_prefix("hybrid-"){(false,true,false,m)}else{(false,false,false,mode)};
    let model=if pilot{PILOT_MODEL}else if interface{INTERFACE_MODEL}else if hybrid{HYBRID_MODEL}else{MODEL};
    let wall_slice=if pilot{
        let v=std::env::var("METROFLOW_AKM_PILOT_SLICE_S").ok().map(|x|x.parse::<f64>()).transpose().map_err(|_|bad("invalid pilot wall slice"))?.unwrap_or(180.);
        if !v.is_finite()||!(1. ..=7200.).contains(&v){return Err(bad("pilot wall slice domain"))}Some(v)
    }else{None};
    // Earlier observer-guarded quotient; not a relaxation of resource limits.
    if pilot{
        e.journey.set_research_receipt_period(60)?;
        e.journey.enable_research_group_outlets()?;
        e.journey.enable_research_receipt_grid(e.step)?;
        e.journey.enable_research_schedule_receipts()?;
        e.journey.enable_research_stream_receipts()?;
        e.journey.enable_research_egress_buckets()?;
        e.journey.enable_research_entry_buckets()?;
        e.journey.enable_research_delay_calendar()?;
    }
    let whole_bus_class=if hybrid{Some(e.class_names.iter().position(|x|x=="scheduled_bus").ok_or_else(||bad("scheduled bus class absent"))?)}else{None};
    let id=format!("{model}:{}:{manifest_sha}",e.identity);
    let init=Instant::now();let mut migration=Value::Null;
    let mut s=match mode{
        "fresh"|"migrate"=>{
            let old=if mode=="fresh"{e.initial()}else{e.load(source.to_owned())?};
            let (mut projected,n)=e.road.akm_project(&old.value.road)?;
            if let Some(k)=whole_bus_class{projected.enable_whole_bus(k,&e.road)?;}
            projected.interface=interface;
            check(&e,&projected,&old.value.journey,&old.value.service)?;
            migration=json!({"source_time_s":old.time_s(),"source_native_identity":e.identity,"source_rows":n,"projected_rows":projected.rows(),"projected_active_mass":projected.active_mass(),
                "projected_active_birth":projected.total_birth(),"source_owner_ledger":ledger(&e,&old.value.journey),
                "scope":"mass/birth/route position and bulk speed/latent point reconstruction; ordered rank and remaining in-link distance not retained"});
            e.journey.install_state(old.value.journey.clone());e.service.install_state(old.value.service.clone());
            // Old exact road owner is no longer used after projection.
            e.road.install_state(e.initial_state.road.clone());drop(old);projected
        },
        "resume"|"recover"=>read(&mut e,&id,source,whole_bus_class,interface)?,
        _=>return Err(bad("AKM mode must be fresh/migrate/resume/recover"))
    };
    let source_time=s.t;
    // An empty initial state has no physical or owner transition before all
    // profiles and first scheduled offers. Land on a grid boundary no later
    // than the earliest offer, preserving the tick which admits that offer.
    let mut idle_skipped=0.;
    if pilot&&mode=="fresh"&&s.t==0.&&s.rows()==0{
        let first=e.profiles.iter().flat_map(|p|p.iter().map(|x|x.0))
            .fold(e.service.akm_first_offer_time(),f64::min);
        let jump=((first.min(target)/e.step).floor()*e.step).max(0.);
        if jump>0.{
            let mut j=e.journey.state().clone();
            if j.1.len()!=0||j.2.len()!=0||j.3.len()!=0||j.4.iter().any(|x|*x!=0.)||j.5.iter().any(|x|*x!=0.)||j.7.iter().any(|x|*x!=0.)||e.service.checkpoint().1.len()!=0{return Err(bad("pilot initial idle not empty"))}
            j.0=jump;s.t=jump;e.journey.install_state(j);check(&e,&s,e.journey.state(),&e.service.checkpoint())?;
            idle_skipped=jump;
        }
    }
    let init_s=init.elapsed().as_secs_f64();
    let count=(target-s.t)/e.step;
    if count<0.||(count-count.round()).abs()>1e-8||count>10000.||mode=="recover"&&count!=0.{return Err(bad("AKM horizon not aligned or recovery advances"))}
    let pool=e.road_storage_bytes.ok_or_else(||bad("AKM dynamic pool absent"))?;
    let indices:HashMap<&str,usize>=e.tags.iter().enumerate().map(|(i,t)|(t.as_str(),i)).collect();
    if indices.len()!=e.tags.len(){return Err(bad("duplicate AKM route tags"))}
    let initial_ledger=ledger(&e,e.journey.state());let initial_rows=s.rows();
    let mut peak_rows=s.rows();let mut peak_storage=s.check(&e.road)?;let mut steps=0usize;let mut failure=None;let mut exited=0.;let mut transferred=0.;let mut offered=0.;let mut substeps=0;let mut bus_exited=0.;let mut bus_moves=0usize;let mut bus_quota_blocks=0usize;let mut boundary=[0.;3];let mut peak_crossings=s.crossings.len();
    let advance=Instant::now();let mut step_times=Vec::new();
    let sample=|e:&NativeWholeEngine,s:&State|json!({"time_s":s.t,"ledger":ledger(e,e.journey.state()),"road_rows":s.rows(),"road_mass":s.active_mass(),"road_birth":s.total_birth(),"journey_records":e.journey.record_counts(),"bus_tracks":s.bus_tracks.len(),"crossings":s.crossings.len()});
    let mut samples=if pilot{vec![sample(&e,&s)]}else{vec![]};let mut failure_kind=None;
    for _ in 0..count.round() as usize{
        if wall_slice.is_some_and(|w|advance.elapsed().as_secs_f64()>=w){failure=Some("D09 session slice reached; last committed state retained".into());failure_kind=Some("SESSION_SLICE".to_owned());break}
        let tick=Instant::now();
        let owners=&e.car_tag_legs;let classes=&e.class_names;let freight=&e.freight_vehicles;
        let result=e.parallel.run(||advance_akm_tick(&e.road,&mut s,&mut e.service,&mut e.journey,&e.tags,&indices,e.step,pool,e.event_limit,
            |next,j,service,legs|Binding{owners,classes,freight,legs}.check(next,j,service)));
        match result{Ok(st)=>{steps+=1;peak_rows=peak_rows.max(st.peak_rows);peak_storage=peak_storage.max(st.peak_storage_ratio);exited+=st.exited;transferred+=st.transferred;offered+=st.offered;substeps+=st.substeps;bus_exited+=st.bus_exited;bus_moves+=st.bus_moves;bus_quota_blocks+=st.bus_quota_blocks;boundary[0]+=st.bus_boundary_in;boundary[1]+=st.bus_boundary_internal;boundary[2]+=st.bus_boundary_sink;peak_crossings=peak_crossings.max(s.crossings.len());step_times.push(tick.elapsed().as_secs_f64())},Err(err)=>{failure_kind=Some(format!("{:?}",err.kind));failure=Some(err.message);break}}
        if pilot&&s.t%600.==0.{samples.push(sample(&e,&s));}
    }
    let advance_s=advance.elapsed().as_secs_f64();
    let save_start=Instant::now();save(&e,&s,&id,output)?;let save_s=save_start.elapsed().as_secs_f64();
    let support=e.road.akm_support();
    let mut receipt=json!({"schema":"metroflow_akm_native_owners_v1","scope":"research sparse kinetic transport; original native calendar/journey/service owners; not V03 acceptance","transport_policy":model,
        "status":if failure.is_none(){"EXECUTED_FOR_REVIEW"}else{"BLOCKED"},"failure":failure,"model_identity":id,"original_identity":e.identity,
        "mode":mode,"city_identity":e.city,"schedule_identity":e.schedule,"manifest_sha256":manifest_sha,"threads":threads,"start_s":source_time,"requested_end_s":target,"time_s":s.t,
        "calendar_legs":calendar_legs,"calendar_totals":[calendar_totals.0,calendar_totals.1,calendar_totals.2],"unsupported_legs":e.unsupported,"unassigned":e.unassigned,"supported":e.supported,
        "initial_ledger":initial_ledger,"ledger":ledger(&e,e.journey.state()),"class_names":e.class_names,"class_road_ledger":s.class});
    let measurements=json!({
        "road_rows":s.rows(),"road_initial_rows":initial_rows,"peak_road_rows":peak_rows,"road_rows_guard":ROAD_ROW_LIMIT,"declared_route_tags":support.0,"declared_route_positions":support.1,
        "active_road_mass":s.active_mass(),"active_road_birth":s.total_birth(),"initial_road_birth":s.initial_birth,"new_offered_birth":s.offered_birth,"outlet_birth":s.outlet_birth,
        "peak_storage_ratio":peak_storage,"road_offered":offered,"road_exited":exited,"road_transferred":transferred,"committed_steps":steps,"road_substeps":substeps,
        "journey_records":e.journey.record_counts(),"service_events_last_tick":e.service.checkpoint().1.len(),"migration":migration,
        "build_s":build_s,"init_s":init_s,"advance_s":advance_s,"save_s":save_s,"wall_s":start.elapsed().as_secs_f64(),"tick_times_s":step_times,
        "dynamic_pool_bytes":pool,"byte_budget":e.byte_budget,"user_checkpoint":output});
    receipt.as_object_mut().unwrap().extend(measurements.as_object().unwrap().clone());
    receipt["whole_bus"]=json!({"enabled":hybrid,"active_tracks":s.bus_tracks.len(),"exited_veh":bus_exited,"moves":bus_moves,"quota_blocks":bus_quota_blocks});
    receipt["interface"]=json!({"enabled":interface,"partial_crossings":s.crossings.len(),"peak_crossings_at_owner_tick":peak_crossings,"sum_fraction":s.crossings.values().sum::<f64>(),"physical_boundary_in_veh":boundary[0],"physical_boundary_internal_veh":boundary[1],"physical_boundary_sink_veh":boundary[2],"logical_sink_completed_veh":bus_exited});
    if pilot{
        if samples.last().is_none_or(|x|x["time_s"]!=json!(s.t)){samples.push(sample(&e,&s));}
        receipt["pilot"]=json!({"clock_cell_closure":true,"session_slice_s":wall_slice,"idle_skipped_s":idle_skipped,"failure_kind":failure_kind,
            "samples":samples,"original_external_wall_s":7200,"scope":"fixed original owner/calendar; same road/interface; guarded temporal quotient, no new support or calibration"});
    }
    Ok(receipt)
}

fn support_ceiling(profile:f64,direct:f64,parent:f64)->CoreResult<f64>{
    if [profile,direct,parent].iter().any(|x|!x.is_finite()||*x<0.||*x>1.+1e-9){return Err(bad("D09 support fraction domain"))}
    Ok(profile.min(direct).min(parent).min(1.))
}
#[cfg(test)]
mod d09_support_tests{
    use super::*;
    #[test]
    fn parent_and_declared_service_limit_are_both_binding(){
        assert_eq!(support_ceiling(0.8,0.7,0.4).unwrap(),0.4);
        assert_eq!(support_ceiling(1.,0.,1.).unwrap(),0.);
        assert_eq!(support_ceiling(0.2,1.,1.).unwrap(),0.2);
    }
}

/// Rebuild the actual calendar and native static owner admission; no tick.
pub fn akm_support_audit(manifest:Value,threads:usize)->CoreResult<Value>{
    if manifest.as_object().is_some_and(|m|m.keys().any(|k|k.starts_with("research_"))){return Err(bad("original input required"))}
    let budget=manifest["byte_budget"].as_u64().ok_or_else(||bad("budget"))? as usize;
    let declaration:crate::v1_calendar::FactorizedDeclaration=serde_json::from_value(manifest["calendar"].clone()).map_err(|e|bad(e.to_string()))?;
    let(e,n,totals)=build_native_input(manifest,threads)?;
    let cal=declaration.compile(budget)?;
    let direct=e.journey.akm_direct_support()?;
    let legs=e.journey.legs();
    if n!=legs.len()||n!=direct.len()||cal.owned_legs().len()!=n{return Err(bad("D09 calendar binding"))}
    let mut groups=std::collections::BTreeMap::<(String,String),[f64;8]>::new();
    for (i,l) in cal.owned_legs().iter().enumerate(){
        if cal.text(l.id).as_ref()!=Some(&legs[i].0){return Err(bad("D09 ordered leg identity"))}
        let key=(cal.owned_labels()[l.metadata[3]as usize].clone(),cal.owned_labels()[l.metadata[7]as usize].clone());
        let g=groups.entry(key).or_default();
        g[0]+=1.;
        if direct[i]==0.{g[1]+=1.;}
        for k in 0..3{g[2+k]+=e.amounts[i][k];g[5+k]+=e.amounts[i][k]*(1.-direct[i]);}
    }
    let mut windows=vec![];
    for t in [21600.,25320.,28800.,43200.,61200.,64800.,86400.]{
        let mut u=vec![0.;n];let mut totals:[[Sum;3];3]=std::array::from_fn(|_|std::array::from_fn(|_|Sum::default()));
        for (i,l) in legs.iter().enumerate(){
            let f=fraction(&l.4,t).clamp(0.,1.);
            let p=if let Some(p)=l.2{if p>=i{return Err(bad("D09 parent order unsupported"))}u[p]}else{1.};
            u[i]=support_ceiling(f,direct[i],p)?;
            for k in 0..3{let a=e.amounts[i][k];totals[0][k].add(a*f);totals[1][k].add(a*u[i]);totals[2][k].add(a*(f-u[i]));}
        }
        let rows:Vec<Vec<f64>>=totals.into_iter().map(|r|r.into_iter().map(|s|s.finish()).collect()).collect();
        windows.push(json!({"time_s":t,"requested":rows[0],"optimistic_completion_ceiling":rows[1],"uncompleted_lower_bound":rows[2]}));
    }
    Ok(json!({"schema":"akm_d09_support_v1","scope":"optimistic structural support, not simulated completion","status":"EXECUTED_FOR_REVIEW","calendar_legs":n,
        "calendar_totals":[totals.0,totals.1,totals.2],"original_identity":e.identity,"unsupported_legs":e.unsupported,"original_unassigned":e.unassigned,
        "groups":groups.into_iter().map(|((mode,endpoint),r)|json!({"mode":mode,"endpoint":endpoint,"legs":r[0],"zero_direct_support_legs":r[1],"amounts":&r[2..5],"direct_uncompleted_lower_bound":&r[5..8]})).collect::<Vec<_>>(),
        "windows":windows}))
}
