from __future__ import annotations

import re

FRAMEWORK_SIGNATURES: list[tuple[str, re.Pattern[str]]] = [
    ("docusaurus", re.compile(r"(__docusaurus|docusaurus|docusaurus-version)", re.I)),
    ("mkdocs", re.compile(r"(mkdocs|md-content|material-for-mkdocs)", re.I)),
    ("vitepress", re.compile(r"(vitepress|vp-doc|vp-nav)", re.I)),
    ("sphinx", re.compile(r"(sphinx|sphinxdoc|alabaster)", re.I)),
    ("mintlify", re.compile(r"(mintlify|mint-)", re.I)),
    ("nextra", re.compile(r"(nextra|nextra-container)", re.I)),
    ("starlight", re.compile(r"(starlight|astro-starlight)", re.I)),
    ("gitbook", re.compile(r"(gitbook|gitbook-root)", re.I)),
    ("hugo", re.compile(r"(hugo|gohugo)", re.I)),
    ("jekyll", re.compile(r"(jekyll)", re.I)),
]


def detect_documentation_framework(html_text: str) -> str | None:
    for name, pattern in FRAMEWORK_SIGNATURES:
        if pattern.search(html_text):
            return name
    return None


__all__ = [
    "FRAMEWORK_SIGNATURES",
    "detect_documentation_framework",
]
