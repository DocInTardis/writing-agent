use std::sync::{Arc, Mutex};
use std::num::NonZeroUsize;
use fontdue::{Font, FontSettings};
use lru::LruCache;

#[derive(Debug, Clone, Copy)]
pub struct FontMetrics {
    pub font_size: f32,
    pub line_height: f32,
}

impl Default for FontMetrics {
    fn default() -> Self {
        Self {
            font_size: 14.0,
            line_height: 1.6,
        }
    }
}

pub trait TextMeasurer: Send + Sync {
    fn measure(&self, text: &str, metrics: FontMetrics) -> f32;
}

#[derive(Debug, Default, Clone)]
pub struct SimpleMeasurer;

impl TextMeasurer for SimpleMeasurer {
    fn measure(&self, text: &str, metrics: FontMetrics) -> f32 {
        if text.is_ascii() && text.len() < 128 {
            return text.len() as f32 * metrics.font_size * 0.6;
        }
        if text.is_ascii() {
            return measure_ascii_fast(text.as_bytes(), metrics.font_size);
        }
        let mut width = 0.0;
        for ch in text.chars() {
            if is_cjk(ch) {
                width += metrics.font_size;
            } else if ch.is_ascii() {
                width += metrics.font_size * 0.6;
            } else {
                width += metrics.font_size * 0.7;
            }
        }
        width
    }
}

fn measure_ascii_fast(bytes: &[u8], font_size: f32) -> f32 {
    #[cfg(target_arch = "x86_64")]
    {
        if std::is_x86_feature_detected!("sse2") {
            // Safety: SSE2 supported and we only read within bounds.
            unsafe {
                use std::arch::x86_64::*;
                let mut i = 0usize;
                let mut count = 0usize;
                let zero = _mm_setzero_si128();
                while i + 16 <= bytes.len() {
                    let ptr = bytes.as_ptr().add(i) as *const __m128i;
                    let chunk = _mm_loadu_si128(ptr);
                    let msb = _mm_cmpgt_epi8(zero, chunk);
                    let mask = _mm_movemask_epi8(msb) as u32;
                    count += 16 - mask.count_ones() as usize;
                    i += 16;
                }
                if i < bytes.len() {
                    for &b in &bytes[i..] {
                        if b.is_ascii() {
                            count += 1;
                        }
                    }
                }
                return count as f32 * font_size * 0.6;
            }
        }
    }
    let mut ascii_count = 0usize;
    for &b in bytes {
        if b.is_ascii() {
            ascii_count += 1;
        }
    }
    ascii_count as f32 * font_size * 0.6
}

fn is_cjk(ch: char) -> bool {
    matches!(
        ch as u32,
        0x4E00..=0x9FFF
            | 0x3400..=0x4DBF
            | 0x20000..=0x2A6DF
            | 0x2A700..=0x2B73F
            | 0x2B740..=0x2B81F
            | 0x2B820..=0x2CEAF
            | 0xF900..=0xFAFF
    )
}

#[derive(Clone)]
pub struct SharedMeasurer(pub Arc<dyn TextMeasurer>);

#[derive(Clone)]
pub enum RealMeasurer {
    Fontdue(FontdueMeasurer),
    Simple(SimpleMeasurer),
}

impl RealMeasurer {
    pub fn new() -> Self {
        let cap = if std::env::var("WA_LOW_SPEC").ok().as_deref() == Some("1") {
            2048
        } else {
            8192
        };
        if let Some(font) = load_default_font() {
            RealMeasurer::Fontdue(FontdueMeasurer::new(font, cap))
        } else {
            RealMeasurer::Simple(SimpleMeasurer)
        }
    }

    pub fn hit_rate(&self) -> Option<f64> {
        match self {
            RealMeasurer::Fontdue(m) => Some(m.hit_rate()),
            _ => None,
        }
    }

    pub fn prewarm_chars(&self, chars: &[char], metrics: FontMetrics) {
        if let RealMeasurer::Fontdue(m) = self {
            m.prewarm_chars(chars, metrics);
        }
    }
}

impl TextMeasurer for RealMeasurer {
    fn measure(&self, text: &str, metrics: FontMetrics) -> f32 {
        match self {
            RealMeasurer::Fontdue(m) => m.measure(text, metrics),
            RealMeasurer::Simple(m) => m.measure(text, metrics),
        }
    }
}

fn load_default_font() -> Option<Font> {
    if let Ok(path) = std::env::var("WA_FONT_PATH") {
        if let Ok(bytes) = std::fs::read(&path) {
            if let Ok(font) = Font::from_bytes(bytes, FontSettings::default()) {
                return Some(font);
            }
        }
    }
    let candidates = [
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\msyh.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ];
    for path in candidates {
        if let Ok(bytes) = std::fs::read(path) {
            if let Ok(font) = Font::from_bytes(bytes, FontSettings::default()) {
                return Some(font);
            }
        }
    }
    None
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct GlyphKey {
    ch: char,
    size: u16,
}

#[derive(Debug)]
struct GlyphCache {
    hot: LruCache<GlyphKey, fontdue::Metrics>,
    cold: LruCache<GlyphKey, fontdue::Metrics>,
    hits: u64,
    misses: u64,
}

impl GlyphCache {
    fn new(capacity: usize) -> Self {
        let total = capacity.max(1);
        let hot_cap = (total / 4).max(64);
        let cold_cap = (total - hot_cap).max(64);
        let hot = LruCache::new(NonZeroUsize::new(hot_cap).unwrap());
        let cold = LruCache::new(NonZeroUsize::new(cold_cap).unwrap());
        Self { hot, cold, hits: 0, misses: 0 }
    }

    fn get_or_insert(&mut self, key: GlyphKey, font: &Font) -> fontdue::Metrics {
        if let Some(hit) = self.hot.get(&key) {
            self.hits += 1;
            return *hit;
        }
        if let Some(hit) = self.cold.get(&key) {
            self.hits += 1;
            let val = *hit;
            self.hot.put(key, val);
            return val;
        }
        let metrics = font.metrics(key.ch, key.size as f32);
        self.cold.put(key, metrics);
        self.misses += 1;
        metrics
    }

    fn hit_rate(&self) -> f64 {
        let total = self.hits + self.misses;
        if total == 0 {
            0.0
        } else {
            self.hits as f64 / total as f64
        }
    }
}

#[derive(Clone)]
pub struct FontdueMeasurer {
    font: Arc<Font>,
    cache: Arc<Mutex<GlyphCache>>,
}

impl FontdueMeasurer {
    pub fn new(font: Font, cache_capacity: usize) -> Self {
        Self {
            font: Arc::new(font),
            cache: Arc::new(Mutex::new(GlyphCache::new(cache_capacity))),
        }
    }

    pub fn hit_rate(&self) -> f64 {
        self.cache.lock().map(|c| c.hit_rate()).unwrap_or(0.0)
    }

    pub fn prewarm_chars(&self, chars: &[char], metrics: FontMetrics) {
        let mut cache = self.cache.lock().unwrap();
        let size = metrics.font_size.round().max(1.0) as u16;
        for &ch in chars {
            let key = GlyphKey { ch, size };
            let _ = cache.get_or_insert(key, &self.font);
        }
    }
}

impl TextMeasurer for FontdueMeasurer {
    fn measure(&self, text: &str, metrics: FontMetrics) -> f32 {
        if text.is_ascii() && text.len() < 128 {
            return text.len() as f32 * metrics.font_size * 0.6;
        }
        let mut width = 0.0;
        let mut cache = self.cache.lock().unwrap();
        for ch in text.chars() {
            let key = GlyphKey { ch, size: metrics.font_size.round().max(1.0) as u16 };
            let m = cache.get_or_insert(key, &self.font);
            width += m.advance_width.max(0.0);
        }
        width
    }
}
