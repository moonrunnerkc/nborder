from __future__ import annotations

import re
from dataclasses import dataclass

from nborder.parser.models import Magic

_SHELL_ASSIGNMENT_PATTERN = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*!.+")
_HELP_PATTERN = re.compile(r"^\s*[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\?\??\s*$")
_AUTO_CALL_PREFIXES = (",", ";", "/")


@dataclass(frozen=True, slots=True)
class MagicStrip:
    """Python source and IPython syntax separated from a code cell."""

    stripped_source: str
    magics: tuple[Magic, ...]



def strip_magics(source: str) -> MagicStrip:
    """Strip IPython-only syntax from source before LibCST parsing.

    Args:
        source: Original code-cell source.

    Returns:
        Source safe for Python parsing plus typed records for stripped IPython syntax.
    """
    source_lines = source.splitlines()
    if source_lines and source_lines[0].startswith("%%"):
        return _strip_cell_magic(source_lines)

    stripped_lines: list[str] = []
    magics: list[Magic] = []
    for line_offset, source_line in enumerate(source_lines, start=1):
        shell_assignment_match = _SHELL_ASSIGNMENT_PATTERN.match(source_line)
        if shell_assignment_match:
            magics.append(
                Magic(
                    kind="shell_assignment",
                    name="!",
                    source=source_line,
                    line_number=line_offset,
                    binding=shell_assignment_match.group(1),
                )
            )
            stripped_lines.append("")
            continue

        stripped_line = source_line.lstrip()
        if stripped_line.startswith("%"):
            magic_name = stripped_line[1:].split(maxsplit=1)[0]
            magics.append(
                Magic(kind="line", name=magic_name, source=source_line, line_number=line_offset)
            )
            stripped_lines.append("")
            continue

        if stripped_line.startswith("!"):
            magics.append(
                Magic(kind="shell", name="!", source=source_line, line_number=line_offset)
            )
            stripped_lines.append("")
            continue

        if _HELP_PATTERN.match(source_line):
            help_target = source_line.strip().rstrip("?")
            magics.append(
                Magic(kind="help", name=help_target, source=source_line, line_number=line_offset)
            )
            stripped_lines.append("")
            continue

        if stripped_line.startswith(_AUTO_CALL_PREFIXES):
            magics.append(
                Magic(
                    kind="auto_call",
                    name=stripped_line[0],
                    source=source_line,
                    line_number=line_offset,
                )
            )
            stripped_lines.append("")
            continue

        stripped_lines.append(source_line)

    return MagicStrip(stripped_source="\n".join(stripped_lines), magics=tuple(magics))



def _strip_cell_magic(source_lines: list[str]) -> MagicStrip:
    header = source_lines[0]
    header_body = header[2:].strip()
    magic_name = header_body.split(maxsplit=1)[0] if header_body else ""
    binding = _cell_magic_binding(magic_name, header_body)
    magic = Magic(
        kind="cell",
        name=magic_name,
        source="\n".join(source_lines),
        line_number=1,
        binding=binding,
    )
    return MagicStrip(stripped_source="", magics=(magic,))



def _cell_magic_binding(magic_name: str, header_body: str) -> str | None:
    if magic_name != "capture":
        return None
    capture_parts = header_body.split()
    if len(capture_parts) < 2:
        return None
    capture_target = capture_parts[1]
    return capture_target if capture_target.isidentifier() else None
