use metroflow_headless::{
    input::Input,
    queue::{self, Config},
    receipt,
};
use serde_json::json;
use std::{path::Path, time::Instant};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = std::env::args().collect();
    if a.len() != 8 {
        return Err(
            "usage: metroflow-headless NETWORK PASSAGES MESH HORIZON SEED THREADS OUT_JSON".into(),
        );
    }
    let cfg = Config {
        mesh_s: a[3].parse()?,
        horizon_s: a[4].parse()?,
        seed: a[5].parse()?,
        shock_link: None,
        shock_factor: 1.,
    };
    let threads: usize = a[6].parse()?;
    if !(1..=256).contains(&threads) {
        return Err("threads outside 1..256".into());
    }
    let start = Instant::now();
    let n = Path::new(&a[1]);
    let p = Path::new(&a[2]);
    let network_sha = receipt::sha256(n)?;
    let passages_sha = receipt::sha256(p)?;
    let input = Input::load(n, p)?;
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let prep_s = start.elapsed().as_secs_f64();
    let clock = Instant::now();
    let run = pool.install(|| queue::run(&input, cfg))?;
    let run_s = clock.elapsed().as_secs_f64();
    if network_sha != receipt::sha256(n)? || passages_sha != receipt::sha256(p)? {
        return Err("input changed".into());
    }
    let exe = std::env::current_exe()?;
    let value = json!({"schema":"metroflow_standalone_projection_v1","scope":"historical prepared input, not original V03 native acceptance","config":cfg,"threads":threads,"network_sha256":network_sha,"passages_sha256":passages_sha,"executable_sha256":receipt::sha256(&exe)?,"prep_s":prep_s,"run_s":run_s,"wall_s":start.elapsed().as_secs_f64(),"peak_rss_bytes":receipt::peak_rss_bytes(),"result":run});
    let out = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&a[7])?;
    serde_json::to_writer_pretty(out, &value)?;
    println!("{}", serde_json::to_string(&value)?);
    Ok(())
}
