"""Packaged rule documentation access."""

from __future__ import annotations

from importlib import resources

_RULE_DOCS_PACKAGE = "nborder._rule_docs"


def read_rule_doc(rule_code: str) -> str | None:
    """Return packaged Markdown documentation for a rule code.

    Args:
        rule_code: Rule code such as NB101.

    Returns:
        Markdown text when packaged documentation exists, otherwise None.
    """
    rule_resource = resources.files(_RULE_DOCS_PACKAGE).joinpath(f"{rule_code.upper()}.md")
    if not rule_resource.is_file():
        return None
    return rule_resource.read_text(encoding="utf-8")
