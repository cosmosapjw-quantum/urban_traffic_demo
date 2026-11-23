//! Regression contract for immutable retained event history.
//! This fixture initially targets the baseline two-argument read_state API.
//! When the decoder gains byte/domain arguments, change decode_fixture only;
//! the raw wire, expected rows and cost assertions are the fixed contract.
use super::*;

fn empty_service() -> NativeServiceCore {
    NativeServiceCore {
        buses: vec![],
        people: vec![],
        freight: vec![],
        cars: vec![],
        people_by_run: vec![],
        last_events: Arc::default(),
        state: (vec![], vec![], vec![], vec![], vec![]),
        pending: None,
    }
}

fn original_row(i: usize) -> EventRow {
    (
        i % 257,
        i % 7,
        if i % 3 == 0 { None } else { Some((i + 1) % 11) },
        f64::from_bits(0x3ff0_0000_0000_0000 + (i % 257) as u64),
        -0.0,
        12.5,
        if i % 2 == 0 {
            -0.0
        } else {
            f64::from_bits(0x3fe8_0000_0000_0000 + (i % 17) as u64)
        },
    )
}

// Independent legacy service wire fixture: five empty physical vectors,
// followed by event length and the original MFWHOLE1 event row fields.
fn original_service_wire(rows: usize) -> Vec<u8> {
    let mut bytes = Vec::new();
    for _ in 0..5 {
        bytes.extend_from_slice(&0u64.to_le_bytes());
    }
    bytes.extend_from_slice(&(rows as u64).to_le_bytes());
    for i in 0..rows {
        let e = original_row(i);
        bytes.extend_from_slice(&(e.0 as u64).to_le_bytes());
        bytes.extend_from_slice(&(e.1 as u64).to_le_bytes());
        bytes.extend_from_slice(&u64::from(e.2.is_some()).to_le_bytes());
        if let Some(dest) = e.2 {
            bytes.extend_from_slice(&(dest as u64).to_le_bytes());
        }
        for value in [e.3, e.4, e.5, e.6] {
            bytes.extend_from_slice(&value.to_bits().to_le_bytes());
        }
    }
    bytes
}

fn decode_fixture(core: &NativeServiceCore, bytes: &[u8], rows: usize) -> ServiceCheckpoint {
    let mut input = std::io::Cursor::new(bytes);
    let checkpoint = core.read_state(&mut input, rows).unwrap();
    assert_eq!(input.position(), bytes.len() as u64);
    checkpoint
}

fn roundtrip(rows: usize) -> NativeServiceCore {
    let bytes = original_service_wire(rows);
    let mut core = empty_service();
    let checkpoint = decode_fixture(&core, &bytes, rows);
    core.install_state(checkpoint);
    assert_eq!(core.last_events.len(), rows);
    for (i, e) in core.last_events.iter().enumerate() {
        let expected = original_row(i);
        assert_eq!((e.0, e.1, e.2), (expected.0, expected.1, expected.2));
        for (actual, wanted) in [e.3, e.4, e.5, e.6]
            .into_iter()
            .zip([expected.3, expected.4, expected.5, expected.6])
        {
            assert_eq!(actual.to_bits(), wanted.to_bits());
        }
    }
    let mut encoded = Vec::new();
    core.write_state(&mut encoded).unwrap();
    assert_eq!(encoded, bytes, "legacy event wire/order/IEEE bits changed");
    core
}

#[test]
fn legacy_event_wire_roundtrip_is_ieee_exact_across_pages() {
    for rows in [0, 1, 4095, 4096, 4097, 8193] {
        let _ = roundtrip(rows);
    }
}

#[test]
fn repeated_time_checkpoint_history_uses_less_than_48_bytes_per_event() {
    let rows = 65_536usize;
    let core = roundtrip(rows);
    let checkpoint = core.checkpoint();
    assert!(Arc::ptr_eq(&checkpoint.1, &core.last_events));
    let retained = service_event_storage_bytes(&checkpoint);
    let ceiling = 48 * rows;
    assert!(
        retained < ceiling,
        "repeated-time immutable history retained_bytes={retained} must be below {ceiling}; \
         raw logical rows, order and bits have already roundtripped exactly"
    );
}
