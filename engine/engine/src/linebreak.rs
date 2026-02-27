use unicode_linebreak::linebreaks;

#[derive(Debug, Clone)]
pub struct LineBreaker;

impl LineBreaker {
    pub fn break_positions(&self, text: &str) -> Vec<usize> {
        linebreaks(text).map(|(idx, _)| idx).collect()
    }

    pub fn break_positions_into(&self, text: &str, out: &mut Vec<usize>) {
        out.clear();
        out.extend(linebreaks(text).map(|(idx, _)| idx));
    }
}
