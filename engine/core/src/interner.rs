use crate::SharedStr;
use std::collections::HashMap;
use std::sync::Arc;

#[derive(Debug, Default)]
pub struct StringInterner {
    map: HashMap<String, SharedStr>,
}

impl StringInterner {
    pub fn new() -> Self {
        Self { map: HashMap::new() }
    }

    pub fn intern(&mut self, s: &str) -> SharedStr {
        if let Some(hit) = self.map.get(s) {
            return hit.clone();
        }
        let shared: SharedStr = Arc::from(s);
        self.map.insert(s.to_string(), shared.clone());
        shared
    }
}
