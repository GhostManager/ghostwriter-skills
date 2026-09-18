#!/usr/bin/env python3
"""Create the deliberately invalid DOCX used by the first-check example."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def build_fixture(destination: Path) -> None:
    """Write a minimal DOCX with two known offline-lint failures."""
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {destination}")

    content_types = """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
      <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
    </Types>"""
    document = f"""<w:document xmlns:w="{W_NS}"><w:body>
      <w:p><w:r><w:t>{{{{ findings | made_up_filter }}}}</w:t></w:r></w:p>
    </w:body></w:document>"""
    styles = f"""<w:styles xmlns:w="{W_NS}">
      <w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
    </w:styles>"""
    relationships = f"""<Relationships xmlns="{REL_NS}">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
    </Relationships>"""

    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/_rels/document.xml.rels", relationships)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    try:
        build_fixture(arguments.destination)
    except FileExistsError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
