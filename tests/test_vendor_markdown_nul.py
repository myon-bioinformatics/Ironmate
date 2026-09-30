"""Upstream markdown#62 regressions through Ironmate's vendored emitter."""

import pytest

from scripts.build_web_ui_consumer_examples import markdown


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("keep \x00PH0\x00 here and `code`", "<p>keep \ufffdPH0\ufffd here and <code>code</code></p>\n"),
        ("only \x00PH0\x00 text", "<p>only \ufffdPH0\ufffd text</p>\n"),
        ("```\n\x00\n```", "<pre><code>\ufffd\n</code></pre>\n"),
    ],
)
def test_vendored_markdown_and_web_ui_replace_input_nul(source, expected):
    html = markdown.markdown_to_html(source)
    assert html == expected
    assert "\x00" not in html

    document = markdown.markdown_to_web_ui_v1(source)
    assert expected in document
    assert "\x00" not in document
