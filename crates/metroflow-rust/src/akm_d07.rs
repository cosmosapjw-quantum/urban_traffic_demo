//! Bounded D07 research lab, not the original city or a production candidate.
use crate::{causal::{Key,Prior,Channel,Information,Observation,Report,DecisionObservation},causal_routing::{Link,Routing,Commitment,Boundary,Preference,Decision},core_error::{CoreError,CoreResult},frozen_city::hash};
use serde::{Serialize,Deserialize};
use metroflow_headless::active_kinetic::{Moment,Rates,react_with_distance};
use std::collections::BTreeSet;
fn bad(s:&str)->CoreError{CoreError::value(s)}
const E:usize=7;const BYPASS:usize=5;
const IDS:[&str;E]=["approach","bridge","upper_exit","long","lower_exit","bypass","exit"];
const TAIL:[&str;E]=["s","x","u","x","v","x","z"];
const HEAD:[&str;E]=["x","u","z","v","z","z","d"];
const L:[f64;E]=[150.,60.,60.,130.,130.,100.,80.];
const CAP:[f64;E]=[1.,0.35,0.35,0.6,0.6,0.65,1.];
const TURNS:[(usize,usize);8]=[(0,1),(1,2),(2,6),(0,3),(3,4),(4,6),(0,5),(5,6)];
const MAX:usize=300;
fn idx(s:&str)->CoreResult<usize>{IDS.iter().position(|x|*x==s).ok_or_else(||bad("unknown lab link"))}
fn pref()->Preference{Preference{class:"car".into(),purpose:"work".into(),time_weight:1.,distance_s_per_m:0.,money_s_per_unit:0.,logit_scale_s:12.,path_size_beta:1.}}
fn route_model(installed:[bool;E],version:u32)->CoreResult<Routing>{
    let links=(0..E).filter(|&i|installed[i]).map(|i|Link{id:IDS[i].into(),tail:TAIL[i].into(),head:HEAD[i].into(),length_m:L[i],toll_units:0.}).collect();
    let turns=TURNS.iter().filter(|&&(i,j)|installed[i]&&installed[j]).map(|&(i,j)|(IDS[i].into(),IDS[j].into())).collect();
    Routing::new(links,turns,&format!("akm-d07-graph-{version}"),3,256,256,64,2)
}
fn legal(path:&[String],installed:[bool;E])->bool{
    let Ok(p)=path.iter().map(|x|idx(x)).collect::<CoreResult<Vec<_>>>() else{return false};
    if p.is_empty()||p[0]!=0||*p.last().unwrap()!=6||p.iter().any(|&i|!installed[i])||p.windows(2).any(|w|!TURNS.contains(&(w[0],w[1]))){return false}
    let mut nodes=BTreeSet::new();nodes.insert(TAIL[p[0]]);
    p.iter().all(|&i|nodes.insert(HEAD[i]))
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct Owner{
    id:usize,birth:f64,moment:Moment,route:Option<Commitment>,initial_branch:Option<String>,
    phase:u8, // 0 source pending,1 physical road,2 logical complete
    distance:f64,entry:f64,cross:f64,done:Option<f64>,last_reroute:Option<f64>
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct GraphEvent{time:f64,action:String,accepted:bool,reason:String,before:String,after:String}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct Graph{installed:[bool;E],version:u32,id:String}
impl Graph{
    fn new()->CoreResult<Self>{let mut installed=[true;E];installed[BYPASS]=false;
        Ok(Self{installed,version:0,id:route_model(installed,0)?.graph_id})}
    fn edit(&mut self,owners:&mut[Owner],t:f64,link:usize,add:bool)->CoreResult<GraphEvent>{
        if link>=E||!t.is_finite()||t<0.||self.installed[link]==add{return Err(bad("invalid graph edit"))}
        let action=format!("{}:{}",if add{"add"}else{"remove"},IDS[link]);
        let before=self.id.clone();
        let mut installed=self.installed;installed[link]=add;
        if owners.iter().filter(|o|o.phase!=2).any(|o|o.route.as_ref().is_some_and(|r|!legal(&r.links,installed))){
            return Ok(GraphEvent{time:t,action,accepted:false,reason:"live commitment prevents removal".into(),before:before.clone(),after:before})
        }
        let version=self.version.checked_add(1).ok_or_else(||bad("graph version overflow"))?;
        let id=route_model(installed,version)?.graph_id;
        for o in owners.iter_mut().filter(|o|o.phase!=2){
            if let Some(r)=&mut o.route{r.graph_id=id.clone();}
        }
        *self=Self{installed,version,id:id.clone()};
        Ok(GraphEvent{time:t,action,accepted:true,reason:"installed legal graph".into(),before,after:id})
    }
}
fn initial_owner(id:usize,t:f64)->Owner{Owner{id,birth:t,moment:Moment::point(1.,1.,0.,t),route:None,initial_branch:None,phase:0,distance:0.,entry:t,cross:0.,done:None,last_reroute:None}}
fn route(graph:&Graph,p:&[usize])->Commitment{Commitment{graph_id:graph.id.clone(),links:p.iter().map(|&i|IDS[i].into()).collect(),position:0}}
#[cfg(test)]
mod graph_tests{
    use super::*;
    #[test] fn graph_add_rebind_and_refuse_live_removal(){
        let mut g=Graph::new().unwrap();let mut owners=vec![initial_owner(0,0.)];
        owners[0].route=Some(route(&g,&[0,1,2,6]));let before=owners[0].clone();
        let a=g.edit(&mut owners,300.,BYPASS,true).unwrap();assert!(a.accepted);assert_ne!(a.before,a.after);
        assert_eq!(owners[0].route.as_ref().unwrap().links,before.route.unwrap().links);
        assert_eq!(owners[0].moment,before.moment);assert_eq!(owners[0].route.as_ref().unwrap().graph_id,g.id);
        owners[0].route=Some(route(&g,&[0,5,6]));let saved=owners.clone();let old=g.clone();
        let a=g.edit(&mut owners,540.,BYPASS,false).unwrap();assert!(!a.accepted);assert_eq!(owners,saved);assert_eq!(g,old);
        owners[0].phase=2;owners[0].done=Some(600.);
        let a=g.edit(&mut owners,600.,BYPASS,false).unwrap();assert!(a.accepted);assert!(!g.installed[BYPASS]);
    }
}
