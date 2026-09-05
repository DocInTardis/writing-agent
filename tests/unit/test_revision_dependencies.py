"""Headless revision boundary and failure-path regression tests."""
import ast
import inspect
import unittest
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from writing_agent.workflows.revision_request_workflow import RevisionDeps, RevisionRequest, run_revision_workflow


class RevisionDependencyTests(unittest.TestCase):
    def setUp(self):
        self.session = SimpleNamespace(doc_text='original', doc_ir={'text': 'original'})
        self.client = SimpleNamespace(is_running=lambda: True, chat_stream=lambda **_: iter(['revised']))
        self.persist = Mock()
        self.selected = Mock(return_value=None)
        self.deps = RevisionDeps(
            environ={}, exception_factory=lambda **kw: ValueError(kw['detail']),
            doc_ir_from_dict=lambda value: value, doc_ir_to_text=lambda value: value['text'],
            create_provider=lambda **_: self.client,
            analyze_message=lambda *_: {}, hard_constraints=lambda *_: {},
            decide_revision=lambda **_: {'should_apply': True}, try_selected_edit=self.selected,
            replace_question_headings=lambda text: text, postprocess_output=lambda session, text, *a, **kw: text,
            set_doc_text=lambda session, text: setattr(session, 'doc_text', text),
            persist_session=self.persist, sanitize_output=lambda text: text,
            looks_like_prompt_echo=lambda *_: False, safe_doc_ir_payload=lambda text: {'text': text},
            normalize_heading_text_fn=str, resolve_target_section_selection_fn=lambda **_: None,
            build_revision_fallback_prompt_fn=lambda **_: ('system', 'user'),
            extract_revision_fallback_text_fn=str,
            validate_revision_candidate_fn=lambda **_: {'passed': True},
        )

    def run_revision(self, **data):
        return run_revision_workflow(request=RevisionRequest(self.session, {'instruction': 'edit', **data}), deps=self.deps)

    def test_request_has_only_task_inputs_and_deps_are_required(self):
        self.assertEqual({f.name for f in fields(RevisionRequest)}, {'session', 'data'})
        self.assertIs(inspect.signature(run_revision_workflow).parameters['deps'].default, inspect.Parameter.empty)

    def test_workflow_cannot_reach_web_globals(self):
        path = Path(__file__).resolve().parents[2] / 'writing_agent/workflows/revision_request_workflow.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                self.assertNotEqual(node.id, 'app_v2')
            if isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or '').startswith(('writing_agent.web', 'fastapi', 'starlette')))

    def test_failed_selection_never_silently_revises_whole_document(self):
        self.client.chat_stream = Mock(side_effect=AssertionError('full document rewrite forbidden'))
        result = self.run_revision(selection={'text': 'original'})
        self.assertFalse(result['applied'])
        self.client.chat_stream.assert_not_called()
        self.persist.assert_not_called()

    def test_missing_target_rejected_before_model_probe(self):
        probe = Mock(side_effect=AssertionError('model should not be called'))
        self.deps = replace(self.deps, create_provider=probe)
        with self.assertRaisesRegex(ValueError, 'target section not found'):
            self.run_revision(target_section='missing')
        probe.assert_not_called()

    def test_hard_gate_rejection_does_not_persist(self):
        self.deps = replace(self.deps, validate_revision_candidate_fn=lambda **_: {'passed': False})
        self.assertFalse(self.run_revision()['applied'])
        self.assertEqual(self.session.doc_text, 'original')
        self.persist.assert_not_called()

    def test_model_stream_closes_on_success_and_failure(self):
        for fails in [False, True]:
            with self.subTest(fails=fails):
                closed = []

                def stream(**_):
                    try:
                        yield 'revised'
                        if fails:
                            raise RuntimeError('model failed')
                    finally:
                        closed.append(True)

                self.client.chat_stream = stream
                self.persist.reset_mock()
                if fails:
                    with self.assertRaisesRegex(RuntimeError, 'model failed'):
                        self.run_revision()
                    self.persist.assert_not_called()
                else:
                    self.assertEqual(self.run_revision()['text'], 'revised')
                    self.persist.assert_called_once()
                self.assertEqual(closed, [True])

    def test_invalid_structure_is_rejected_without_mutating_session(self):
        original = deepcopy(vars(self.session))
        for value in [{}, {'sections': 'invalid'}, [], 'bad']:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'invalid document structure'):
                self.run_revision(doc_ir=value)
            self.assertEqual(vars(self.session), original)
        self.persist.assert_not_called()

    def test_mutating_converter_failure_cannot_touch_request_or_session(self):
        incoming = {'sections': [], 'text': 'unsaved text'}
        original = deepcopy(incoming)

        def broken(value):
            value['sections'].append({'text': 'unwanted mutation'})
            raise RuntimeError('bad structure')

        self.deps = replace(self.deps, doc_ir_from_dict=broken)
        with self.assertRaisesRegex(ValueError, 'invalid document structure'):
            self.run_revision(doc_ir=incoming)
        self.assertEqual(incoming, original)
        self.assertEqual(self.session.doc_ir, {'text': 'original'})
        self.persist.assert_not_called()

    def test_model_configuration_failure_leaves_incoming_structure_uncommitted(self):
        self.deps = replace(self.deps, create_provider=Mock(side_effect=RuntimeError('missing key')))
        with self.assertRaisesRegex(ValueError, 'not configured'):
            self.run_revision(doc_ir={'sections': [], 'text': 'unsaved text'})
        self.assertEqual(self.session.doc_ir, {'text': 'original'})
        self.assertEqual(self.session.doc_text, 'original')
        self.persist.assert_not_called()

    def test_declined_selection_returns_matching_structure_without_saving(self):
        incoming = {'sections': [], 'text': 'unsaved text'}
        result = self.run_revision(doc_ir=incoming, selection='unsaved')
        self.assertEqual(result['text'], result['doc_ir']['text'])
        result['doc_ir']['sections'].append({'text': 'changed response'})
        self.assertEqual(incoming['sections'], [])
        self.assertEqual(self.session.doc_text, 'original')
        self.persist.assert_not_called()

    def test_empty_postprocessing_never_commits(self):
        self.deps = replace(self.deps, postprocess_output=lambda *a, **kw: '   ')
        for selected in [False, True]:
            self.selected.return_value = ('candidate', 'note')
            with self.subTest(selected=selected), self.assertRaisesRegex(ValueError, 'empty text'):
                self.run_revision(**({'selection': 'original'} if selected else {}))
        self.assertEqual(self.session.doc_text, 'original')
        self.persist.assert_not_called()


if __name__ == '__main__':
    unittest.main()
