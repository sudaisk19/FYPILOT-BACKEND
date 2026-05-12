"""LLM modify-mode system prompt must stay small enough for inference APIs."""

from app.services.llm import _build_system_message


def test_modify_mode_omits_long_doc_type_block() -> None:
    system_extra = (
        "\n## MODIFY MODE (document edit proposal)\n"
        "The user chose **Modify**: you must output **only** a single JSON object.\n"
        "### Current document HTML\n```html\n<p>hi</p>\n```\n"
    )
    text = _build_system_message(
        document_content=None,
        doc_type="proposal",
        system_extra=system_extra,
        leading_document_context=None,
    )
    assert "Document-type guidance" not in text
    assert "MODIFY MODE" in text
    assert "<p>hi</p>" in text


def test_non_modify_keeps_doc_type_guidance() -> None:
    text = _build_system_message(
        document_content=None,
        doc_type="proposal",
        system_extra=None,
        leading_document_context=None,
    )
    assert "Document-type guidance" in text
