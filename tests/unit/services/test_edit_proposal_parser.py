"""Unit tests for document modify proposal JSON parsing."""

import json

from app.services.edit_proposal_parser import parse_document_edit_proposal


def test_parse_valid_json():
    raw = json.dumps(
        {
            "kind": "document_edit_proposal",
            "summary_markdown": "Add intro",
            "html_fragment": "<p>Hello</p>",
            "warnings": ["a"],
        }
    )
    out = parse_document_edit_proposal(raw)
    assert out is not None
    summary, frag, warnings = out
    assert summary == "Add intro"
    assert frag == "<p>Hello</p>"
    assert warnings == ["a"]


def test_parse_markdown_fence():
    inner = json.dumps(
        {
            "kind": "document_edit_proposal",
            "summary_markdown": "x",
            "html_fragment": "<div/>",
            "warnings": [],
        }
    )
    raw = f"```json\n{inner}\n```"
    out = parse_document_edit_proposal(raw)
    assert out is not None
    assert out[1] == "<div/>"


def test_reject_wrong_kind():
    raw = json.dumps(
        {
            "kind": "other",
            "summary_markdown": "x",
            "html_fragment": "<p></p>",
        }
    )
    assert parse_document_edit_proposal(raw) is None


def test_reject_empty_fragment():
    raw = json.dumps(
        {
            "kind": "document_edit_proposal",
            "summary_markdown": "x",
            "html_fragment": "   ",
        }
    )
    assert parse_document_edit_proposal(raw) is None
