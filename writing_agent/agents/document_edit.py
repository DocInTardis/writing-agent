"""Document editing agent with constrained model output protocol."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from writing_agent.agents.report_policy import ReportPolicy, extract_template_headings
from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings
from writing_agent.web.html_sanitize import sanitize_html


@dataclass(frozen=True)
class EditResult:
    html: str
    assistant: str


class DocumentEditAgent:
    """Apply natural-language editing instructions to an HTML document."""

    def __init__(self) -> None:
        self._policy = ReportPolicy(min_section_paragraphs=2, min_total_chars=1200)

    @staticmethod
    def _xml_escape(raw: str) -> str:
        s = str(raw or "")
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _extract_json_dict(raw: str) -> dict | None:
        if not raw:
            return None
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text).strip()
            text = re.sub(r"\s*```$", "", text).strip()
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            payload = json.loads(m.group(0))
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    @staticmethod
    def _extract_html_from_payload(payload: dict) -> str:
        for key in ("html", "output_html", "result_html", "result"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    @staticmethod
    def _extract_assistant_from_payload(payload: dict) -> str:
        for key in ("assistant", "assistant_note", "note", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _parse_model_response(self, raw: str) -> tuple[str, str, bool]:
        payload = self._extract_json_dict(raw)
        if not isinstance(payload, dict):
            return "", "", False
        html = self._extract_html_from_payload(payload).strip()
        assistant = self._extract_assistant_from_payload(payload)
        if not html:
            return "", assistant, False
        return html, assistant, True

    def build_prompts(
        self,
        *,
        html: str,
        instruction: str,
        selection: str | None = None,
        template_html: str | None = None,
    ) -> tuple[str, str, list[str] | None]:
        required_headings = extract_template_headings(template_html or "") if (template_html or "").strip() else None
        section_rule = "Must keep a complete report structure with clear section headings."
        if required_headings:
            section_rule = f"Must preserve these section headings: {', '.join(required_headings)}."

        selection_text = str(selection or "").strip()
        selection_block = (
            f"<selection_text>\n{self._xml_escape(selection_text)}\n</selection_text>\n"
            if selection_text
            else "<selection_text>\n\n</selection_text>\n"
        )
        scope_rule = (
            "If selection_text is non-empty, prioritize local edits around the selection and avoid unrelated rewrites."
        )

        system = (
            "You are a controlled HTML document editor.\n"
            "You MUST return strict JSON only (no markdown fences).\n"
            "JSON schema:\n"
            '{"html":"<full_document_html>",'
            '"assistant":"short note about applied changes",'
            '"meta":{"scope":"selection|document","preserved_structure":true}}\n'
            "Rules:\n"
            "1) Output a complete HTML document body content, not plain text.\n"
            "2) Do not output <script> tags or on* event handlers.\n"
            f"3) {section_rule}\n"
            f"4) {scope_rule}\n"
            "5) Keep existing useful content unless instruction requires changes.\n"
        )
        user = (
            "<task>apply_instruction_to_html</task>\n"
            f"<instruction>\n{self._xml_escape(instruction)}\n</instruction>\n"
            f"{selection_block}"
            f"<document_html>\n{self._xml_escape(html)}\n</document_html>\n"
            'Return strict JSON only with key "html".'
        )
        return system, user, required_headings

    def apply_instruction(
        self,
        html: str,
        instruction: str,
        selection: str | None = None,
        template_html: str | None = None,
        title: str = "Report",
    ) -> EditResult:
        settings = get_ollama_settings()
        if not settings.enabled:
            raise OllamaError("Ollama is disabled")

        client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
        if not client.is_running():
            raise OllamaError("Ollama is not running")

        system, user, required_headings = self.build_prompts(
            html=html,
            instruction=instruction,
            selection=selection,
            template_html=template_html,
        )

        raw = client.chat(system=system, user=user, temperature=0.2)
        edited, assistant, parsed_ok = self._parse_model_response(raw)

        if not parsed_ok:
            retry_user = (
                f"{user}\n"
                "<retry_reason>\n"
                'Your previous response was invalid. Return strict JSON only: {"html":"...","assistant":"..."}.\n'
                "</retry_reason>"
            )
            retry_raw = client.chat(system=system, user=retry_user, temperature=0.1)
            retry_html, retry_assistant, retry_ok = self._parse_model_response(retry_raw)
            if retry_ok:
                edited = retry_html
                assistant = retry_assistant or assistant
                parsed_ok = True

        selection_text = str(selection or "").strip()
        if not parsed_ok and selection_text:
            # For selection-scoped edits we prefer no-op over unconstrained fallback.
            safe_original = sanitize_html(html)
            enforced = self._policy.enforce(safe_original, title=title, required_headings=required_headings)
            note = "Constrained selection edit failed; document kept unchanged."
            return EditResult(html=enforced.html, assistant=note)

        if not parsed_ok:
            # Keep backward compatibility for full-document edits: best-effort fallback.
            edited = str(raw or "")

        cleaned = sanitize_html(edited)
        enforced = self._policy.enforce(cleaned, title=title, required_headings=required_headings)
        if not enforced.html.strip():
            raise OllamaError("Model returned empty content")

        assistant_msg = assistant or "Applied requested changes to the document."
        if enforced.fixes:
            assistant_msg += " (Structure auto-repaired)"
        return EditResult(html=enforced.html, assistant=assistant_msg)

    def bootstrap(self, topic: str | None = None, template_html: str | None = None) -> str:
        title = (topic or "").strip() or "Auto-generated document"
        base = (template_html or "").strip()
        if base:
            base = base.replace("{{TITLE}}", title).replace("[TITLE]", title)
            if "<h1" not in base.lower():
                base = f"<h1>{title}</h1>" + base
            raw = base
        else:
            raw = f"<h1>{title}</h1>"

        required_headings = extract_template_headings(base) if base else None
        enforced = self._policy.enforce(raw, title=title, required_headings=required_headings)
        return sanitize_html(enforced.html)
