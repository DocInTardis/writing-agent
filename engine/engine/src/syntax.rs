use std::sync::Arc;

use syntect::easy::HighlightLines;
use syntect::highlighting::{Style, Theme, ThemeSet};
use syntect::parsing::{SyntaxReference, SyntaxSet};

#[derive(Clone)]
pub struct SyntaxHighlighter {
    syntax_set: Arc<SyntaxSet>,
    theme: Theme,
}

impl SyntaxHighlighter {
    pub fn new() -> Self {
        let syntax_set = SyntaxSet::load_defaults_newlines();
        let themes = ThemeSet::load_defaults();
        let theme = themes.themes.get("base16-ocean.dark").cloned().unwrap_or_else(|| themes.themes.values().next().cloned().unwrap());
        Self { syntax_set: Arc::new(syntax_set), theme }
    }

    pub fn highlight_lines(&self, lang: &str, code: &str) -> Vec<Vec<(Style, String)>> {
        let syntax = self.syntax(lang).unwrap_or_else(|| self.syntax_set.find_syntax_plain_text());
        let mut h = HighlightLines::new(syntax, &self.theme);
        let mut out = Vec::new();
        for line in code.lines() {
            if let Ok(ranges) = h.highlight_line(line, &self.syntax_set) {
                let spans = ranges
                    .into_iter()
                    .map(|(style, slice)| (style, slice.to_string()))
                    .collect::<Vec<_>>();
                out.push(spans);
            } else {
                out.push(vec![]);
            }
        }
        out
    }

    fn syntax(&self, lang: &str) -> Option<&SyntaxReference> {
        if lang.is_empty() {
            return None;
        }
        self.syntax_set
            .find_syntax_by_token(lang)
            .or_else(|| self.syntax_set.find_syntax_by_extension(lang))
    }
}
