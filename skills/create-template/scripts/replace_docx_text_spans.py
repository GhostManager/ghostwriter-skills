#!/usr/bin/env python3
"""Safely replace a confirmed UTF-8 text token in DOCX paragraph text nodes.

This helper deliberately operates only on <w:t> text-node contents in DOCX XML
parts. It replaces tokens contained in one text node or split across adjacent
text nodes in one paragraph. For a split token, the replacement is placed in
the first matched text node so it inherits that run's formatting; consumed text
in later nodes is cleared. The rest of the ZIP package, including relationships,
formatting, fields, images, and Word run boundaries, is preserved. It is
intentionally not a semantic document converter: determine mappings before
invoking it.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile
from xml.etree import ElementTree
from xml.sax.saxutils import escape


TEXT_NODE = re.compile(rb"(<w:t(?:\s+[^>]*)?>)(.*?)(</w:t>)", re.DOTALL)
PARAGRAPH = re.compile(rb"(<w:p(?:\s+[^>]*)?>)(.*?)(</w:p>)", re.DOTALL)
WORD_XML_PREFIX = "word/"


def replace_in_text_nodes(xml: bytes, old: bytes, new: bytes) -> tuple[bytes, int]:
    """Replace an exact token only inside individual Word text nodes."""

    replacements = 0

    def replace_node(match: re.Match[bytes]) -> bytes:
        nonlocal replacements
        text = match.group(2)
        count = text.count(old)
        if not count:
            return match.group(0)
        replacements += count
        return match.group(1) + text.replace(old, new) + match.group(3)

    return TEXT_NODE.sub(replace_node, xml), replacements


def replace_cross_node_paragraph_tokens(xml: bytes, old: bytes, new: bytes) -> tuple[bytes, int]:
    """Replace remaining tokens split across two or more text nodes in one paragraph."""

    replacements = 0

    def replace_paragraph(match: re.Match[bytes]) -> bytes:
        nonlocal replacements
        content = match.group(2)
        nodes = list(TEXT_NODE.finditer(content))
        if len(nodes) < 2:
            return match.group(0)

        values = [node.group(2) for node in nodes]
        joined = b"".join(values)
        offsets: list[tuple[int, int]] = []
        cursor = 0
        for value in values:
            offsets.append((cursor, cursor + len(value)))
            cursor += len(value)

        occurrences: list[tuple[int, int]] = []
        search_from = 0
        while True:
            start = joined.find(old, search_from)
            if start < 0:
                break
            end = start + len(old)
            first_node = next(i for i, (_, node_end) in enumerate(offsets) if start < node_end)
            last_node = next(i for i, (node_start, node_end) in enumerate(offsets) if node_start < end <= node_end)
            if first_node != last_node:
                occurrences.append((start, end))
            search_from = end

        if not occurrences:
            return match.group(0)

        new_values: list[bytes] = []
        for node_start, node_end in offsets:
            output = bytearray()
            position = node_start
            for occurrence_start, occurrence_end in occurrences:
                if occurrence_end <= node_start or occurrence_start >= node_end:
                    continue
                keep_until = min(occurrence_start, node_end)
                if keep_until > position:
                    output.extend(joined[position:keep_until])
                if node_start <= occurrence_start < node_end:
                    output.extend(new)
                position = max(position, min(occurrence_end, node_end))
            if position < node_end:
                output.extend(joined[position:node_end])
            new_values.append(bytes(output))

        rebuilt = bytearray()
        previous_end = 0
        for node, value in zip(nodes, new_values):
            rebuilt.extend(content[previous_end : node.start()])
            rebuilt.extend(node.group(1))
            rebuilt.extend(value)
            rebuilt.extend(node.group(3))
            previous_end = node.end()
        rebuilt.extend(content[previous_end:])
        replacements += len(occurrences)
        return match.group(1) + bytes(rebuilt) + match.group(3)

    return PARAGRAPH.sub(replace_paragraph, xml), replacements


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source DOCX file to leave unchanged.")
    parser.add_argument("output", type=Path, help="New DOCX file to create.")
    parser.add_argument("--old", required=True, help="Exact text token to replace.")
    parser.add_argument("--new", required=True, help="Replacement text token.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.source.resolve() == args.output.resolve():
        print("Refusing to overwrite the source DOCX.", file=sys.stderr)
        return 2
    if args.output.exists():
        print("Refusing to overwrite an existing output path.", file=sys.stderr)
        return 2
    if not args.source.is_file() or args.source.suffix.lower() != ".docx":
        print("Source must be an existing .docx file.", file=sys.stderr)
        return 2
    if not args.output.parent.is_dir():
        print("Output directory does not exist.", file=sys.stderr)
        return 2

    old = escape(args.old).encode("utf-8")
    new = escape(args.new).encode("utf-8")
    if not old:
        print("--old must not be empty.", file=sys.stderr)
        return 2

    replacement_count = 0
    modified_parts: list[str] = []
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{args.output.name}.",
            suffix=".tmp",
            dir=args.output.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        with zipfile.ZipFile(args.source, "r") as source_zip:
            with zipfile.ZipFile(temporary_path, "w") as output_zip:
                for info in source_zip.infolist():
                    content = source_zip.read(info.filename)
                    if info.filename.startswith(WORD_XML_PREFIX) and info.filename.endswith(".xml"):
                        content, count = replace_in_text_nodes(content, old, new)
                        content, cross_node_count = replace_cross_node_paragraph_tokens(content, old, new)
                        count += cross_node_count
                        if count:
                            ElementTree.fromstring(content)
                            replacement_count += count
                            modified_parts.append(info.filename)
                    output_zip.writestr(info, content)
        with zipfile.ZipFile(temporary_path, "r") as completed_zip:
            corrupt_member = completed_zip.testzip()
            if corrupt_member is not None:
                raise zipfile.BadZipFile(f"CRC check failed for {corrupt_member}")
    except (ElementTree.ParseError, OSError, zipfile.BadZipFile) as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        print(f"Could not process DOCX: {error}", file=sys.stderr)
        return 1

    if not replacement_count:
        temporary_path.unlink(missing_ok=True)
        print(
            "No replacement was made. The token was not found within one Word paragraph.",
            file=sys.stderr,
        )
        return 3

    try:
        # Linking within the output directory publishes the completed file without
        # replacing a path that appeared after the initial existence check.
        os.link(temporary_path, args.output)
    except FileExistsError:
        temporary_path.unlink(missing_ok=True)
        print("Refusing to overwrite an existing output path.", file=sys.stderr)
        return 2
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        print(f"Could not publish output DOCX: {error}", file=sys.stderr)
        return 1
    temporary_path.unlink(missing_ok=True)

    print(f"Replaced {replacement_count} occurrence(s) in: {', '.join(modified_parts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
