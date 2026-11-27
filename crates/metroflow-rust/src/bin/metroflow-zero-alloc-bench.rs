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
    }
}
#[cfg(not(feature="budget_trace"))] fn main(){probe::run()}
#[cfg(feature="budget_trace")] fn main(){panic!("run this isolated allocation diagnostic without budget_trace")}
