use metroflow_headless::{input::Input, preflight, receipt};
use serde_json::json;
use std::{hint::black_box, path::Path, time::Instant};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 3 {
        return Err("usage: metroflow-preflight-bench NETWORK PASSAGES".into());
    }
    let input = Input::load(Path::new(&a[1]), Path::new(&a[2]))?;
    let mut results = vec![];
    for threads in [1, 8] {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()?;
        let reference = pool.install(|| preflight::ranks(&input, 600., false))?;
        let mut scalar = vec![];
        let mut vector = vec![];
        for rep in 0..9 {
            for simd in if rep % 2 == 0 {
                [false, true]
            } else {
                [true, false]
            } {
                let t = Instant::now();
                let x = pool.install(|| preflight::ranks(black_box(&input), 600., simd))?;
                let elapsed = t.elapsed().as_secs_f64();
                assert_eq!(x, reference);
                if simd {
                    vector.push(elapsed)
                } else {
                    scalar.push(elapsed)
                }
            }
        }
        scalar.sort_by(f64::total_cmp);
        vector.sort_by(f64::total_cmp);
        results.push(json!({"threads":threads,"scalar_s":scalar,"vector_s":vector,"scalar_median_s":scalar[4],"vector_median_s":vector[4],"speedup":scalar[4]/vector[4]}));
    }
    println!(
        "{}",
        serde_json::to_string_pretty(
            &json!({"groups":input.groups.len(),"avx":preflight::available(),"network_sha256":receipt::sha256(Path::new(&a[1]))?,"passages_sha256":receipt::sha256(Path::new(&a[2]))?,"results":results})
        )?
    );
    Ok(())
}
