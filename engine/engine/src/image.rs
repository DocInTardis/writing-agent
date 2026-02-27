use std::collections::HashMap;
use std::path::Path;

#[derive(Debug, Clone)]
pub struct ImageAsset {
    pub key: String,
    pub width: f32,
    pub height: f32,
    pub display_width: f32,
    pub display_height: f32,
}

#[derive(Debug, Default, Clone)]
pub struct ImageCache {
    entries: HashMap<String, ImageAsset>,
}

impl ImageCache {
    pub fn new() -> Self {
        Self { entries: HashMap::new() }
    }

    pub fn load(&mut self, key: &str) -> ImageAsset {
        if let Some(asset) = self.entries.get(key) {
            return asset.clone();
        }
        let asset = ImageAsset {
            key: key.to_string(),
            width: 320.0,
            height: 180.0,
            display_width: 320.0,
            display_height: 180.0,
        };
        self.entries.insert(key.to_string(), asset.clone());
        asset
    }

    pub fn load_from_path(&mut self, path: &Path) -> ImageAsset {
        let key = path.to_string_lossy().to_string();
        self.load(&key)
    }

    pub fn resize(&mut self, key: &str, width: f32, height: f32) {
        if let Some(asset) = self.entries.get_mut(key) {
            asset.display_width = width.max(1.0);
            asset.display_height = height.max(1.0);
        }
    }
}

