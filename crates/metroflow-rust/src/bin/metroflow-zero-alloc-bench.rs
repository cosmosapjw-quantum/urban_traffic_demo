//! Isolated diagnostic: initialization and JSON allocations excluded.
#[cfg(not(feature="budget_trace"))]
mod probe {
    use std::{alloc::{GlobalAlloc,Layout,System},sync::atomic::{AtomicBool,AtomicU64,Ordering::Relaxed},hint::black_box,time::Instant};
    use _metroflow_rust::{causal_bottleneck::{LinkQueue,Supply},allocation_probe_fsum};
    use serde_json::json;
    struct Counter;
    static ON:AtomicBool=AtomicBool::new(false);
    static ALLOC:AtomicU64=AtomicU64::new(0);
    static REALLOC:AtomicU64=AtomicU64::new(0);
    unsafe impl GlobalAlloc for Counter{
        unsafe fn alloc(&self,l:Layout)->*mut u8{if ON.load(Relaxed){ALLOC.fetch_add(1,Relaxed);} unsafe{System.alloc(l)}}
        unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{if ON.load(Relaxed){ALLOC.fetch_add(1,Relaxed);} unsafe{System.alloc_zeroed(l)}}
        unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{if ON.load(Relaxed){REALLOC.fetch_add(1,Relaxed);} unsafe{System.realloc(p,l,n)}}
        unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
    }
    #[global_allocator]static GA:Counter=Counter;
    fn start()->Instant{ALLOC.store(0,Relaxed);REALLOC.store(0,Relaxed);let t=Instant::now();ON.store(true,Relaxed);t}
    fn finish(t:Instant)->(u64,u64,f64){ON.store(false,Relaxed);(ALLOC.load(Relaxed),REALLOC.load(Relaxed),t.elapsed().as_secs_f64())}
    pub fn run(){
        let n=1_000_000usize;
        let mut q=LinkQueue::new(1.,3).unwrap();
        let s=Supply{storage_veh:64.,receiving_veh:2.,sending_veh:2.};
        let t=start();
        for k in 1..=n{black_box(q.step(black_box(k as f64),s).unwrap());}
        let (a,r,w)=finish(t);
        let vals=[1e16,1.,-1e16,2.,0.125,0.375];let expected=3.5;
        let t=start();let mut total=0.;
        for _ in 0..n{total=black_box(allocation_probe_fsum(black_box(&vals)));}
        let (a2,r2,w2)=finish(t);
        assert_eq!(total,expected);
        println!("{}",json!({"iterations_per_kernel":n,"link_step":{"allocation_calls":a,"reallocation_calls":r,"wall_s":w,"final_counts":q.counts()},"journey_fsum":{"allocation_calls":a2,"reallocation_calls":r2,"wall_s":w2,"last_value":total},"scope":"single process, initialized ring, tested six-term finite cancellation input; other inputs may spill; no full-engine zero heap claim"}));
        assert_eq!((a,r,a2,r2),(0,0,0,0));
        use _metroflow_rust::marked_fifo::{Diverge,Link};
        let count=100_000usize;
        let l=Link{storage_m:64.,lag:2,send_veh:2.,receive_veh:2.};
        let mut net=Diverge::new(1.,count,[l;3],[5.,10.]).unwrap();
        let t=start();
        for k in 0..count{let f=if k%7==0{0.}else{1.};black_box(net.step(black_box([0.6,0.2]),[1.,f,1.],[1.;3]).unwrap());}
        let (a3,r3,w3)=finish(t);
        let m=net.metrics().unwrap();
        println!("{}",json!({"kernel":"marked_fifo_diverge_step","iterations":count,"allocation_calls":a3,"reallocation_calls":r3,"wall_s":w3,"metrics":m,"scope":"preallocated marked network; 2 classes, unequal footprints, intermittent receiving restriction; no full V03 zero heap claim"}));
        assert_eq!((a3,r3),(0,0));
        let probe=_metroflow_rust::PackedRankProbe::new(65536).unwrap();
        let t=start();
        let mut check=0u64;
        for i in 0..n{let x=black_box(probe.get(black_box(i.wrapping_mul(7919))));check=check.wrapping_add(x[0]^x[1]^x[2]^x[3]^x[4]);}
        let(a4,r4,w4)=finish(t);
        println!("{}",json!({"kernel":"packed_reference_and_event_random_access","iterations":n,"allocation_calls":a4,"reallocation_calls":r4,"wall_s":w4,"checksum":check,"sealed_saved_bytes":probe.saved_bytes(),"scope":"initialized exact packed ranks and event pages; encoding allocates per sealed page"}));
        assert_eq!((a4,r4),(0,0));
        let values=[(0.125,0.375),(0.25,0.75),(0.5,1.5),(0.125,0.375)];
        let t=start();let mut answer=[0.;2];
        for _ in 0..n{answer=black_box(_metroflow_rust::allocation_probe_rank_moments(black_box(&values)).unwrap());}
        let(a5,r5,w5)=finish(t);assert_eq!(answer,[1.,3.]);assert_eq!((a5,r5),(0,0));
        println!("{}",json!({"kernel":"rank_positive_mass_birth_accumulation","iterations":n,"allocation_calls":a5,"reallocation_calls":r5,"wall_s":w5,"answer":answer,"scope":"actual compensated per-mark accumulator; excludes sort and packet output allocations"}));
        let mut bucket=_metroflow_rust::ReceiptBucketProbe::new().unwrap();
        let t=start();let mut bucket_result=[0.;4];
        for _ in 0..n{bucket_result=black_box(bucket.run().unwrap());}
        let(ba,br,bw)=finish(t);assert_eq!(bucket_result,[0.5,4.75,0.5,10.375]);assert_eq!((ba,br),(0,0));
        println!("{}",json!({"kernel":"warmed_receipt_grid_bucket","iterations":n,"allocation_calls":ba,"reallocation_calls":br,"wall_s":bw,"answer":bucket_result,"scope":"actual warmed bucket insertion and inline positive mass/moment sums; output history and source visitor excluded"}));
        let t=start();let mut streaming=[0.;2];
        for _ in 0..n{streaming=black_box(_metroflow_rust::allocation_probe_streaming_receipt().unwrap());}
        let(sa,sr,sw)=finish(t);assert_eq!(streaming,[13.875,1.]);assert_eq!((sa,sr),(0,0));
        println!("{}",json!({"kernel":"transactional_receipt_accumulator","iterations":n,"allocation_calls":sa,"reallocation_calls":sr,"wall_s":sw,"answer":streaming,"scope":"actual fixed inline positive completion measure; excludes transaction scratch initialization, Arc history replacement and output"}));
        let mut egress=_metroflow_rust::EgressBucketProbe::new().unwrap();
        let t=start();let mut egress_result=[0.;2];
        for _ in 0..n{egress_result=black_box(egress.run().unwrap());}
        let(ea,er,ew)=finish(t);assert_eq!(egress_result,[2.,1.]);assert_eq!((ea,er),(0,0));
        println!("{}",json!({"kernel":"warmed_egress_retirement_buckets","iterations":n,"allocation_calls":ea,"reallocation_calls":er,"wall_s":ew,"answer":egress_result,"scope":"actual warmed per-leg outlet law product projection from four products into two retirement buckets; stage output append excluded"}));
        let mut entry=_metroflow_rust::EntryBucketProbe::new().unwrap();
        let t=start();let mut entry_result=[0.;3];
        for _ in 0..n{entry_result=black_box(entry.run().unwrap());}
        let(ia,ir,iw)=finish(t);assert_eq!(entry_result,[2.,2.,2.]);assert_eq!((ia,ir),(0,0));
        println!("{}",json!({"kernel":"warmed_entry_access_projection","iterations":n,"allocation_calls":ia,"reallocation_calls":ir,"wall_s":iw,"answer":entry_result,"scope":"actual preallocated per-proposal access projection, four law products to two consumption ticks; excludes initialization, queue output and periodic sweep"}));
        let t=start();let mut delay=[0.;3];
        for _ in 0..n{delay=black_box(_metroflow_rust::allocation_probe_delay_cell().unwrap());}
        let(da,dr,dw)=finish(t);assert_eq!(delay,[1.5,5.,15.5]);assert_eq!((da,dr),(0,0));
        println!("{}",json!({"kernel":"protected_delay_calendar_cell","iterations":n,"allocation_calls":da,"reallocation_calls":dr,"wall_s":dw,"answer":delay,"scope":"actual inline positive mass/birth/ready moment reduction and observer checks; partition output and tail sort excluded"}));
        let t=start();let mut dictionary=[0usize;2];
        let nd=n/10;
        for _ in 0..nd{dictionary=black_box(_metroflow_rust::allocation_probe_moment_dictionary().unwrap());}
        let(da,dr,dw)=finish(t);assert_eq!(dictionary,[224,6]);assert_eq!((da,dr),(0,0));
        println!("{}",json!({"kernel":"bit_pair_dictionary_plan_lookup","iterations":nd,"allocation_calls":da,"reallocation_calls":dr,"wall_s":dw,"answer":dictionary,"scope":"actual fixed stack plan of 32 input rows and 4 bit-distinct pairs; output dictionary Vecs excluded"}));
        let t=start();let mut x=[0;2];for _ in 0..n{x=black_box(_metroflow_rust::allocation_probe_outlet_and_wire().unwrap());}let(a6,r6,w6)=finish(t);assert_eq!(x[0],3);assert_eq!((a6,r6),(0,0));println!("{}",json!({"kernel":"outlet_group_and_stack_wire","iterations":n,"allocation_calls":a6,"reallocation_calls":r6,"wall_s":w6,"checksum":x,"scope":"actual fixed-slice grouped outlet and stack word writer; no allocation for tested small fsum; full histories may spill"}));

    }
}
#[cfg(not(feature="budget_trace"))] fn main(){probe::run()}
#[cfg(feature="budget_trace")] fn main(){panic!("run this isolated allocation diagnostic without budget_trace")}
