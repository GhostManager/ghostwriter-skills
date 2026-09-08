#!/usr/bin/env python3
"""Report external OOXML relationships and external-capable Word fields."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Optional
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
EXTERNAL_FIELD_TYPES = {
    "DATABASE",
    "DDE",
    "DDEAUTO",
    "INCLUDEPICTURE",
    "INCLUDETEXT",
    "LINK",
    "RD",
}


def source_part_for_relationships(relationship_part: str) -> Optional[str]:
    """Return the package source part associated with a .rels part."""
    path = PurePosixPath(relationship_part)
    if path == PurePosixPath("_rels/.rels"):
        return "/"
    if path.parent.name != "_rels" or not path.name.endswith(".rels"):
        return None
    return str(path.parent.parent / path.name[: -len(".rels")])


def relationship_kind(type_uri: str) -> str:
    """Return the readable final component of an OOXML relationship URI."""
    return type_uri.rstrip("/").rsplit("/", 1)[-1]


def field_instruction_groups(root: ElementTree.Element) -> list[str]:
    """Collect field instructions, joining split instrText nodes per paragraph."""
    namespace = {"w": WORD_NS}
    instructions = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:instrText", namespace))
        if text.strip():
            instructions.append(" ".join(text.split()))
        for field in paragraph.findall(".//w:fldSimple", namespace):
            instruction = field.get(f"{{{WORD_NS}}}instr", "")
            if instruction.strip():
                instructions.append(" ".join(instruction.split()))
    return instructions


def audit_docx(path: Path) -> dict:
    """Return external relationship and field evidence from a DOCX package."""
    result = {
        "path": str(path.resolve()),
        "external_relationships": [],
        "external_fields": [],
        "update_fields_on_open": False,
    }
    with ZipFile(path) as archive:
        for part_name in archive.namelist():
            payload = archive.read(part_name)
            if part_name.endswith(".rels"):
                root = ElementTree.fromstring(payload)
                for relationship in root.findall(f"{{{PACKAGE_REL_NS}}}Relationship"):
                    if relationship.get("TargetMode") != "External":
                        continue
                    type_uri = relationship.get("Type", "")
                    result["external_relationships"].append(
                        {
                            "relationship_part": part_name,
                            "source_part": source_part_for_relationships(part_name),
                            "id": relationship.get("Id"),
                            "kind": relationship_kind(type_uri),
                            "type": type_uri,
                            "target": relationship.get("Target"),
                        }
                    )
            if not part_name.endswith(".xml"):
                continue
            try:
                root = ElementTree.fromstring(payload)
            except ElementTree.ParseError:
                continue
            if part_name == "word/settings.xml":
                update_fields = root.find(f".//{{{WORD_NS}}}updateFields")
                if update_fields is not None:
                    value = update_fields.get(f"{{{WORD_NS}}}val", "true").lower()
                    result["update_fields_on_open"] = value not in {"0", "false", "off", "no"}
            for instruction in field_instruction_groups(root):
                matches = sorted(
                    {
                        match.group(1).upper()
                        for match in re.finditer(
                            r"(?:^|\s)(DATABASE|DDEAUTO|DDE|INCLUDEPICTURE|INCLUDETEXT|LINK|RD)(?=\s|$)",
                            instruction,
                            flags=re.IGNORECASE,
                        )
                    }
                )
                for field_type in matches:
                    result["external_fields"].append(
                        {
                            "part": part_name,
                            "type": field_type,
                            "instruction": instruction,
                        }
                    )
    result["has_external_references"] = bool(
        result["external_relationships"] or result["external_fields"]
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path, help="DOCX package to inspect")
    parser.add_argument(
        "--fail-on-external",
        action="store_true",
        help="exit with status 1 when external relationships or fields are found",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.docx.is_file():
        raise SystemExit(f"DOCX not found: {args.docx}")
    try:
        result = audit_docx(args.docx)
    except BadZipFile as error:
        raise SystemExit(f"Invalid DOCX package: {args.docx}: {error}") from error
    print(json.dumps(result, indent=2))
    return int(args.fail_on_external and result["has_external_references"])


if __name__ == "__main__":
    raise SystemExit(main())
