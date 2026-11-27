use std::{fs::File, io::BufReader};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if ![4, 5].contains(&a.len()) {
        return Err(
            "usage: metroflow-causal-bottleneck MANIFEST DT_S RECEIPT [CAPACITY_SCALE]".into(),
        );
    }
    #[cfg(target_os = "linux")]
    unsafe {
        let mut lim = libc::rlimit {
            rlim_cur: 0,
            rlim_max: 0,
        };
        if libc::getrlimit(libc::RLIMIT_AS, &mut lim) != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        lim.rlim_cur = lim.rlim_cur.min(lim.rlim_max).min(8 * 1024u64.pow(3));
        if libc::setrlimit(libc::RLIMIT_AS, &lim) != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
    }
    let m = serde_json::from_reader(BufReader::new(File::open(&a[1])?))?;
    let r = _metroflow_rust::causal_bottleneck::project_manifest(
        m,
        a[2].parse()?,
        a.get(4)
            .map(|x| x.parse::<f64>())
            .transpose()?
            .unwrap_or(1.),
    )
    .map_err(|e| e.to_string())?;
    serde_json::to_writer_pretty(
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&a[3])?,
        &r,
    )?;
    println!("{}", serde_json::to_string(&r)?);
    Ok(())
}
