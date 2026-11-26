fn main() {
    println!(
        "{}",
        serde_json::to_string_pretty(&_metroflow_rust::geometry_simd::benchmark()).unwrap()
    );
}
