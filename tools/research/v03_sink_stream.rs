use std::alloc::{GlobalAlloc, Layout, System};
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Read, Seek, SeekFrom};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
use std::time::Instant;

struct Meter;
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
fn add(n: usize) {
    let v = LIVE.fetch_add(n, Relaxed) + n;
    PEAK.fetch_max(v, Relaxed);
}
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = System.alloc(l);
        if !p.is_null() {
            add(l.size());
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        System.dealloc(p, l);
        LIVE.fetch_sub(l.size(), Relaxed);
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = System.realloc(p, l, n);
        if !q.is_null() {
            if n >= l.size() {
                add(n - l.size())
            } else {
                LIVE.fetch_sub(l.size() - n, Relaxed);
            }
        }
        q
    }
}
#[global_allocator]
static METER: Meter = Meter;
type Input = BufReader<File>;
fn word(r: &mut Input) -> io::Result<u64> {
    let mut b = [0; 8];
    r.read_exact(&mut b)?;
    Ok(u64::from_le_bytes(b))
}
fn skip(r: &mut Input, mut bytes: u64) -> io::Result<()> {
    while bytes != 0 {
        let avail = r.fill_buf()?.len();
        if avail == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "checkpoint truncation",
            ));
        }
        let n = bytes.min(avail as u64) as usize;
        r.consume(n);
        bytes -= n as u64;
    }
    Ok(())
}
fn opt(r: &mut Input) -> io::Result<()> {
    match word(r)? {
        0 => Ok(()),
        1 => skip(r, 8),
        _ => Err(io::Error::new(io::ErrorKind::InvalidData, "option")),
    }
}
fn packets(r: &mut Input) -> io::Result<()> {
    for _ in 0..word(r)? {
        skip(r, 8)?;
        for _ in 0..word(r)? {
            skip(r, 32)?;
            opt(r)?;
            opt(r)?;
        }
    }
    Ok(())
}
fn locate(r: &mut Input) -> io::Result<(f64, u64, u64)> {
    let mut magic = [0; 8];
    r.read_exact(&mut magic)?;
    assert_eq!(&magic, b"MFWHOLE1");
    for _ in 0..2 {
        let n = word(r)?;
        skip(r, n)?;
    }
    let t = f64::from_bits(word(r)?);
    for _ in 0..word(r)? {
        skip(r, 64)?;
        packets(r)?;
        let n = word(r)?;
        skip(r, 16 * n)?;
    }
    for _ in 0..word(r)? {
        packets(r)?;
    }
    skip(r, 56)?;
    let n = word(r)?;
    skip(r, 40 * n)?;
    for width in [40, 40, 8, 8, 8] {
        let n = word(r)?;
        skip(r, width * n)?;
    }
    let count = word(r)?;
    Ok((t, count, r.stream_position()?))
}
#[derive(Clone, Copy, PartialEq, Eq)]
struct Sink(u64, u64, u64);
fn sinks(r: &mut Input, count: u64, mut f: impl FnMut(Sink)) -> io::Result<()> {
    for _ in 0..count {
        let tag = word(r)?;
        skip(r, 8)?;
        match word(r)? {
            0 => {
                let mass = word(r)?;
                skip(r, 8)?;
                let end = word(r)?;
                skip(r, 8)?;
                f(Sink(tag, mass, end));
            }
            1 => skip(r, 40)?,
            _ => panic!("invalid optional destination"),
        }
    }
    Ok(())
}
// Same nonoverlapping expansion recurrence and final half-even tie adjustment as v1_journey::fsum.
#[derive(Default)]
struct Expansion(Vec<f64>);
impl Expansion {
    fn add(&mut self, mut x: f64) {
        let p = &mut self.0;
        let mut i = 0;
        for j in 0..p.len() {
            let mut y = p[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            assert!(hi.is_finite());
            let lo = y - (hi - x);
            if lo != 0.0 {
                p[i] = lo;
                i += 1;
            }
            x = hi;
        }
        p.truncate(i);
        if x != 0.0 {
            p.push(x);
        }
    }
    fn finish(mut self) -> f64 {
        let p = &mut self.0;
        let Some(mut hi) = p.pop() else {
            return 0.0;
        };
        let mut lo = 0.0;
        while let Some(y) = p.pop() {
            let x = hi;
            hi = x + y;
            lo = y - (hi - x);
            if lo != 0.0 {
                break;
            }
        }
        if let Some(&last) = p.last() {
            if (lo < 0.0 && last < 0.0) || (lo > 0.0 && last > 0.0) {
                let y = lo * 2.0;
                let x = hi + y;
                if y == x - hi {
                    hi = x;
                }
            }
        }
        hi
    }
}
fn hash(h: &mut u64, v: u64) {
    for b in v.to_le_bytes() {
        *h = (*h ^ b as u64).wrapping_mul(0x100000001b3);
    }
}
fn observe(h: &mut u64, e: Sink) {
    for v in [e.0, e.1, e.2] {
        hash(h, v);
    }
}
fn main() -> io::Result<()> {
    let args: Vec<_> = std::env::args().collect();
    let mode = args[1].as_str();
    assert!(["ref", "stream", "verify"].contains(&mode));
    let mut r = BufReader::with_capacity(1 << 20, File::open(&args[2])?);
    let (time, num, offset) = if args.len() == 6 {
        let t: f64 = args[3].parse().unwrap();
        let count: u64 = args[4].parse().unwrap();
        let offset: u64 = args[5].parse().unwrap();
        assert!(
            offset.checked_add(count.checked_mul(56).unwrap()).unwrap()
                <= r.get_ref().metadata()?.len()
        );
        r.seek(SeekFrom::Start(offset))?;
        (t, count, offset)
    } else {
        locate(&mut r)?
    };
    let resident = LIVE.load(Relaxed);
    PEAK.store(resident, Relaxed);
    let t = Instant::now();
    let mut ref_rows = Vec::new();
    let mut expected = BTreeMap::new();
    let mut totals = BTreeMap::new();
    let mut digest = 0xcbf29ce484222325;
    let mut n = 0usize;
    let mut max_partials = 0;
    if mode != "stream" {
        sinks(&mut r, num, |e| ref_rows.push(e))?;
        let copied = ref_rows.clone();
        let mut groups = BTreeMap::<u64, Vec<f64>>::new();
        for e in &copied {
            groups.entry(e.0).or_default().push(f64::from_bits(e.1));
        }
        for (tag, rows) in groups {
            expected.insert(tag, reference_fsum(rows).to_bits());
        }
        drop(copied);
        if mode == "ref" {
            for &e in &ref_rows {
                observe(&mut digest, e);
            }
            n = ref_rows.len();
            totals = std::mem::take(&mut expected);
        }
    }
    if mode != "ref" {
        r.seek(SeekFrom::Start(offset))?;
        let mut by_tag = BTreeMap::<u64, Expansion>::new();
        sinks(&mut r, num, |e| {
            let sum = by_tag.entry(e.0).or_default();
            sum.add(f64::from_bits(e.1));
            max_partials = max_partials.max(sum.0.len());
        })?;
        for (tag, expansion) in by_tag {
            totals.insert(tag, expansion.finish().to_bits());
        }
        r.seek(SeekFrom::Start(offset))?;
        sinks(&mut r, num, |e| {
            if mode == "verify" {
                assert!(
                    ref_rows.get(n) == Some(&e),
                    "journey sink tuple mismatch at {n}"
                );
            }
            observe(&mut digest, e);
            n += 1;
        })?;
        if mode == "verify" {
            assert_eq!(n, ref_rows.len());
            assert_eq!(totals, expected);
        }
    }
    let mut sums = 0xcbf29ce484222325;
    for (&tag, &v) in &totals {
        hash(&mut sums, tag);
        hash(&mut sums, v);
    }
    let peak = PEAK.load(Relaxed) - resident;
    println!("{{\"mode\":\"{mode}\",\"checkpoint_s\":{time},\"events\":{num},\"event_offset\":{offset},\"exits\":{n},\"routes\":{},\"ordered_sink_fnv64\":\"{digest:016x}\",\"route_fsum_fnv64\":\"{sums:016x}\",\"max_route_partials\":{max_partials},\"additional_peak_requested_heap_bytes\":{peak},\"consumer_s\":{:.6}}}",totals.len(),t.elapsed().as_secs_f64());
    Ok(())
}

// Verbatim canonical reference for the batched route sum.
fn reference_fsum(values: impl IntoIterator<Item = f64>) -> f64 {
    let mut partials: Vec<f64> = Vec::new();
    for mut x in values {
        let mut i = 0;
        for j in 0..partials.len() {
            let mut y = partials[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            if !hi.is_finite() {
                return hi;
            }
            let lo = y - (hi - x);
            if lo != 0.0 {
                partials[i] = lo;
                i += 1;
            }
            x = hi;
        }
        partials.truncate(i);
        if x != 0.0 {
            partials.push(x);
        }
    }
    let Some(mut hi) = partials.pop() else {
        return 0.0;
    };
    let mut lo = 0.0;
    while let Some(y) = partials.pop() {
        let x = hi;
        hi = x + y;
        lo = y - (hi - x);
        if lo != 0.0 {
            break;
        }
    }
    if let Some(last) = partials.last() {
        if (lo < 0.0 && *last < 0.0) || (lo > 0.0 && *last > 0.0) {
            let y = lo * 2.0;
            let x = hi + y;
            if y == x - hi {
                hi = x;
            }
        }
    }
    hi
}
