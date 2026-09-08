#!/usr/bin/env python3
"""Run a configured Ghostwriter checkout's actual linter without an upload.

This script must run in the target Ghostwriter Python/Django environment.  It
uses a small in-memory report-template adapter and rejects database write SQL.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace


WRITE_PREFIXES = (
    "ALTER ",
    "CREATE ",
    "DELETE ",
    "DROP ",
    "INSERT ",
    "REPLACE ",
    "TRUNCATE ",
    "UPDATE ",
)


class RejectDatabaseWrites:
    """Django execute wrapper that permits reads and rejects mutations."""

    def __call__(self, execute, sql, params, many, context):
        normalized = sql.lstrip().upper()
        if normalized.startswith(WRITE_PREFIXES):
            raise RuntimeError(
                "The exact template review blocked a database write attempted by the target environment."
            )
        return execute(sql, params, many, context)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Ghostwriter's actual DOCX/PPTX linter against a local file without uploading it."
    )
    parser.add_argument("template", type=Path)
    parser.add_argument(
        "--ghostwriter-root",
        type=Path,
        default=Path.cwd(),
        help="Target Ghostwriter checkout (default: current directory).",
    )
    parser.add_argument(
        "--document-type",
        choices=("docx", "project_docx", "pptx"),
        required=True,
    )
    parser.add_argument("--default-paragraph-style", default="")
    parser.add_argument("--bloodhound-heading-offset", type=int, default=0)
    parser.add_argument("--evidence-image-width", type=float)
    parser.add_argument(
        "--evidence-image-alignment",
        choices=("USE_GLOBAL", "LEFT", "CENTER", "RIGHT"),
        default="USE_GLOBAL",
    )
    parser.add_argument(
        "--settings",
        default=os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.local"),
        help="Django settings module (default: environment or config.settings.local).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    template = args.template.resolve()
    root = args.ghostwriter_root.resolve()

    if not template.is_file():
        print(json.dumps({"result": "failed", "warnings": [], "errors": ["Template file does not exist"]}))
        return 1
    if not (root / "manage.py").is_file() or not (root / "ghostwriter").is_dir():
        print(
            json.dumps(
                {
                    "result": "failed",
                    "warnings": [],
                    "errors": ["Ghostwriter root does not look like a checkout"],
                }
            )
        )
        return 1

    sys.path.insert(0, str(root))
    os.environ["DJANGO_SETTINGS_MODULE"] = args.settings

    try:
        import django

        django.setup()

        from django.db import connection
        from ghostwriter.commandcenter.models import CompanyInformation, ReportConfiguration
        from ghostwriter.reporting.models import (
            EvidenceImageAlignment,
            EvidenceImageAlignmentOverride,
            _text_choice_from_stored_value,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "result": "failed",
                    "warnings": [],
                    "errors": [
                        f"Could not initialize the target Ghostwriter environment: {type(exc).__name__}: {exc}"
                    ],
                }
            )
        )
        return 1

    if not CompanyInformation.objects.exists() or not ReportConfiguration.objects.exists():
        print(
            json.dumps(
                {
                    "result": "failed",
                    "warnings": [],
                    "errors": [
                        "Target database lacks initialized company/report configuration; exact lint was not run to avoid creating records"
                    ],
                }
            )
        )
        return 1

    class LocalTemplateAdapter:
        document = SimpleNamespace(path=str(template))
        p_style = args.default_paragraph_style
        bloodhound_heading_offset = args.bloodhound_heading_offset
        evidence_image_width = args.evidence_image_width
        evidence_image_alignment = args.evidence_image_alignment

        def get_effective_evidence_image_alignment(self, report_config):
            selected = _text_choice_from_stored_value(
                EvidenceImageAlignmentOverride, self.evidence_image_alignment
            )
            if selected == EvidenceImageAlignmentOverride.USE_GLOBAL:
                return _text_choice_from_stored_value(
                    EvidenceImageAlignment, report_config.evidence_image_alignment
                )
            return _text_choice_from_stored_value(
                EvidenceImageAlignment, selected.value
            )

        def get_effective_evidence_image_width(self, report_config):
            if self.evidence_image_width is not None:
                return self.evidence_image_width
            if report_config.evidence_image_width is not None:
                return report_config.evidence_image_width
            return 6.5

    try:
        with connection.execute_wrapper(RejectDatabaseWrites()):
            if args.document_type == "docx":
                from ghostwriter.modules.reportwriter.report.docx import ExportReportDocx

                warnings, errors = ExportReportDocx.lint(LocalTemplateAdapter())
            elif args.document_type == "project_docx":
                from ghostwriter.modules.reportwriter.project.docx import ExportProjectDocx

                warnings, errors = ExportProjectDocx.lint(LocalTemplateAdapter())
            else:
                from ghostwriter.modules.reportwriter.report.pptx import ExportReportPptx

                warnings, errors = ExportReportPptx.lint(template_loc=str(template))
    except Exception as exc:
        warnings = []
        errors = [f"Exact target lint failed unexpectedly: {type(exc).__name__}: {exc}"]

    result = "failed" if errors else "warning" if warnings else "success"
    print(
        json.dumps(
            {
                "result": result,
                "warnings": warnings,
                "errors": errors,
                "exact_target_lint": True,
                "database_writes_blocked": True,
                "template": str(template),
                "document_type": args.document_type,
                "settings": args.settings,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
