# Playwright Persona Matrix

## Reliability Personas
- Persona A: Fast-paced operator who submits multiple instructions during active generation.
  - Test: `test_reliability_queue_instruction_while_busy`
  - Status: Covered
- Persona B: User editing while output is still being produced.
  - Test: `test_reliability_edit_attempt_during_generation_no_crash`
  - Status: Covered
- Persona C: Interrupted generation user expecting partial cache persistence after refresh.
  - Test: `test_reliability_partial_stream_abort_autosave_and_reload`
  - Status: Covered
- Persona C2: Interrupted generation user expecting one-click resume from cached instruction.
  - Test: `test_reliability_resume_button_replays_interrupted_instruction`
  - Status: Covered
- Persona D: User retries failed section generation from failure panel.
  - Test: `test_reliability_section_retry_resume_after_failure`
  - Status: Covered
- Persona E: User uploads mixed assets (txt/md/csv/json + image) from assistant dock.
  - Test: `test_upload_text_and_image_files_are_accepted`
  - Status: Covered
- Persona F: User intent routing (continue vs overwrite) and modify intent safety.
  - Tests: `test_intent_inference_for_continue_and_overwrite_without_dialog`, `test_modify_intent_prefers_continue_not_overwrite`
  - Status: Covered

## Component Personas
- Persona G: Multi-select editor selecting heading + paragraphs, opening inline panel by shortcut.
  - Test: `test_component_multi_select_and_ctrl_enter_opens_inline_panel`
  - Status: Covered
- Persona H: Inline style operator changing font and size from the style panel.
  - Test: `test_component_inline_style_panel_changes_font_and_size`
  - Status: Covered
- Persona I: Slash-command user expecting `/` command insertion menu and command execution (e.g. TOC insertion).
  - Test: `test_component_slash_menu_should_appear_after_slash`
  - Status: Covered
- Persona J: Keyboard-heavy user expecting plain Enter newline and Ctrl+Enter new block.
  - Test: `test_component_ctrl_enter_should_create_new_block_plain_enter_newline`
  - Status: Covered

## Document Quality Personas
- Persona K: Format-sensitive reviewer checking heading alignment and font-size contrast.
  - Test: `test_document_quality_heading_alignment_and_font_contrast`
  - Status: Covered
- Persona L: Citation-trust reviewer checking factual truthfulness of references.
  - Test: `test_document_quality_citation_verify_pipeline`
  - Status: Covered (mocked verify response + UI wiring + payload assertions).
- Persona M: Export user blocked by unverified citations expecting immediate guidance and citation modal jump.
  - Test: `test_document_quality_export_block_opens_citation_modal`
  - Status: Covered
