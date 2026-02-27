use wa_engine::{FontMetrics, RealMeasurer, TextMeasurer};

#[test]
fn font_cache_hit_rate_smoke() {
    let measurer = RealMeasurer::new();
    let metrics = FontMetrics::default();
    let text = "测试文字".repeat(200);
    let _ = measurer.measure(&text, metrics);
    let _ = measurer.measure(&text, metrics);
    if let Some(rate) = measurer.hit_rate() {
        assert!(rate > 0.95, "glyph cache hit rate too low: {}", rate);
    }
}
