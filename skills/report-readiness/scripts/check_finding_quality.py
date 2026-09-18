#!/usr/bin/env python3
"""Identify advisory-only finding-quality signals from a report and library snapshot."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import html
import json
from pathlib import Path
import re
import sys
from typing import Any


COMPARABLE_FIELDS = (
    ("title", 0.15),
    ("description", 0.20),
    ("impact", 0.15),
    ("mitigation", 0.15),
    ("replication_steps", 0.15),
    ("references", 0.10),
    ("host_detection_techniques", 0.05),
    ("network_detection_techniques", 0.05),
)
BODY_FIELDS = {field for field, _weight in COMPARABLE_FIELDS if field != "title"}
CLIENT_FACING_FIELDS = tuple(field for field, _weight in COMPARABLE_FIELDS)
INTENT_COMPARISON_FIELDS = CLIENT_FACING_FIELDS + ("finding_guidance",)
FIELD_LABELS = {
    "title": "Title",
    "description": "Description",
    "impact": "Impact",
    "mitigation": "Mitigation",
    "replication_steps": "Reproduction Steps",
    "references": "References",
    "host_detection_techniques": "Host Detection Techniques",
    "network_detection_techniques": "Network Detection Techniques",
    "affected_entities": "Affected Entities",
    "finding_guidance": "Finding Guidance",
}
PLACEHOLDER_PATTERNS = (
    re.compile(r"\bentity\s+tested\b", re.IGNORECASE),
    re.compile(r"\baffected\s+entit(?:y|ies)\b", re.IGNORECASE),
    re.compile(
        r"\[(?:client|customer|organization|hostname|host|domain|"
        r"ip(?:\s+address)?|target(?:\s+application)?)\]",
        re.IGNORECASE,
    ),
    re.compile(
        r"<(?:client|customer|organization|hostname|host|domain|"
        r"ip(?:\s+address)?|target(?:\s+application)?)>",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:replace|insert|enter)\s+(?:the\s+)?"
        r"(?:client|customer|organization|target|hostname|host|domain)",
        re.IGNORECASE,
    ),
)
HTML_TAG = re.compile(r"<[^>]+>")
TOKEN = re.compile(r"[a-z0-9][a-z0-9._:-]*", re.IGNORECASE)
STEP = re.compile(r"(?:^|\n)\s*(?:\d+[.)]|step\s+\d+\b)", re.IGNORECASE)
URL = re.compile(r"https?://\S+", re.IGNORECASE)


def source_value(finding: dict[str, Any], field: str) -> str:
    """Return a comparable finding field while tolerating GraphQL camel case."""

    aliases = {
        "replication_steps": "replicationSteps",
        "host_detection_techniques": "hostDetectionTechniques",
        "network_detection_techniques": "networkDetectionTechniques",
    }
    value = finding.get(field, finding.get(aliases.get(field, ""), ""))
    if field == "mitigation" and not value:
        value = finding.get("recommendation", "")
    return value if isinstance(value, str) else ""


def started_blank(finding: dict[str, Any]) -> bool:
    """Read the report-finding origin flag in export or GraphQL form."""

    return bool(finding.get("added_as_blank", finding.get("addedAsBlank", False)))


def normalize(value: str) -> str:
    """Normalize presentation differences while retaining target identifiers."""

    plain = html.unescape(HTML_TAG.sub(" ", value))
    return " ".join(plain.casefold().split())


def similarity(left: str, right: str) -> float:
    """Return a stable character-level similarity for normalized values."""

    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def token_jaccard(left: str, right: str) -> float:
    """Provide a cheap candidate-ranking signal for re-titled library copies."""

    left_tokens = set(TOKEN.findall(left))
    right_tokens = set(TOKEN.findall(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def combined_body(finding: dict[str, Any]) -> str:
    """Return comparable client-facing body text without internal guidance."""

    return " ".join(
        normalize(source_value(finding, field))
        for field in BODY_FIELDS
        if source_value(finding, field)
    )


def prepare_library(library: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach private normalized values used only during this process."""

    prepared = []
    for finding in library:
        if not isinstance(finding, dict):
            continue
        prepared.append(
            {
                "finding": finding,
                "title": normalize(source_value(finding, "title")),
                "body": combined_body(finding),
            }
        )
    return prepared


def candidate_pool(
    finding: dict[str, Any], library: list[dict[str, Any]], limit: int = 12
) -> list[dict[str, Any]]:
    """Return title and content candidates before the more costly field comparison."""

    title = normalize(source_value(finding, "title"))
    body = combined_body(finding)
    ranked = []
    for entry in library:
        rank = max(similarity(title, entry["title"]), token_jaccard(body, entry["body"]))
        ranked.append((rank, entry))
    return [entry for _rank, entry in sorted(ranked, key=lambda item: item[0], reverse=True)[:limit]]


def compare_fields(
    report_finding: dict[str, Any], library_finding: dict[str, Any]
) -> dict[str, Any]:
    """Score a candidate using populated library fields as the comparison baseline."""

    weighted_total = 0.0
    weight_used = 0.0
    body_total = 0.0
    body_weight = 0.0
    field_scores: dict[str, float] = {}
    for field, weight in COMPARABLE_FIELDS:
        library_value = normalize(source_value(library_finding, field))
        if not library_value:
            continue
        report_value = normalize(source_value(report_finding, field))
        score = similarity(report_value, library_value)
        field_scores[field] = round(score, 3)
        weighted_total += weight * score
        weight_used += weight
        if field in BODY_FIELDS:
            body_total += weight * score
            body_weight += weight
    return {
        "composite": weighted_total / weight_used if weight_used else 0.0,
        "body": body_total / body_weight if body_weight else 0.0,
        "body_coverage": body_weight,
        "field_scores": field_scores,
    }


def best_candidate(
    finding: dict[str, Any], library: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Find the best library candidate without asserting provenance."""

    candidates = candidate_pool(finding, library)
    if not candidates:
        return None, None
    scored = [
        (compare_fields(finding, entry["finding"]), entry["finding"])
        for entry in candidates
    ]
    comparison, candidate = max(scored, key=lambda item: item[0]["composite"])
    return candidate, comparison


def has_target_customization(finding: dict[str, Any]) -> bool:
    """Treat a non-placeholder Affected Entities value as client-specific context."""

    value = source_value(finding, "affected_entities")
    if not normalize(value):
        return False
    return not any(pattern.search(value) for pattern in PLACEHOLDER_PATTERNS)


def make_issue(
    code: str,
    finding: dict[str, Any],
    message: str,
    *,
    candidate: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    priority: str = "normal",
) -> dict[str, Any]:
    """Build a redacted, advisory-only issue record."""

    issue: dict[str, Any] = {
        "code": code,
        "severity": "warning",
        "priority": priority,
        "finding_id": finding.get("id"),
        "message": message,
    }
    if candidate is not None:
        issue["candidate"] = {
            "id": candidate.get("id"),
            "title": source_value(candidate, "title"),
        }
    if comparison is not None:
        issue["similarity"] = {
            "composite": round(comparison["composite"], 3),
            "body": round(comparison["body"], 3),
            "fields": comparison["field_scores"],
        }
    if fields:
        issue["fields"] = fields
    return issue


def check_placeholders(finding: dict[str, Any]) -> list[dict[str, Any]]:
    """Return warnings for target-substitution cues, excluding internal guidance."""

    issues = []
    for field in CLIENT_FACING_FIELDS + ("affected_entities",):
        value = source_value(finding, field)
        for pattern in PLACEHOLDER_PATTERNS:
            match = pattern.search(value)
            if match:
                issues.append(
                    make_issue(
                        "FINDING-TARGET-PLACEHOLDER",
                        finding,
                        f"{finding_label(finding)} contains a likely target-substitution "
                        f"cue in {display_field(field)}. Replace it with the actual assessed "
                        "target or confirm that the wording is intentional before delivery. "
                        "This is a client-specific wording warning, not a duplicate-finding "
                        "warning.",
                        fields=[field],
                    )
                )
                break
    return issues


def looks_like_procedure(value: str) -> bool:
    """Identify strong structural evidence of numbered reproduction instructions."""

    return len(STEP.findall(value)) >= 2


def looks_like_references(value: str) -> bool:
    """Identify a value made mostly of citations or URLs."""

    urls = URL.findall(value)
    remaining = URL.sub("", value)
    return bool(urls) and len(TOKEN.findall(remaining)) <= 5


def display_field(field: str) -> str:
    """Return the Ghostwriter-facing label for a serialized field name."""

    return FIELD_LABELS.get(field, field.replace("_", " ").title())


def finding_label(finding: dict[str, Any], source: str = "Report finding") -> str:
    """Return a concise identity suitable for a user-facing warning."""

    finding_id = finding.get("id", "unknown ID")
    title = source_value(finding, "title").strip() or "untitled"
    return f'{source} {finding_id} ("{title}")'


def percent(score: float) -> str:
    """Render a similarity score as a user-facing percentage."""

    return f"{score * 100:.1f}%"


def candidate_field_intent_mismatches(
    finding: dict[str, Any],
    candidate: dict[str, Any],
    comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detect high-confidence field swaps or misplaced candidate content."""

    issues = []
    paired_fields: set[str] = set()
    for index, left_field in enumerate(INTENT_COMPARISON_FIELDS):
        left_report = normalize(source_value(finding, left_field))
        left_library = normalize(source_value(candidate, left_field))
        if not left_report or not left_library:
            continue
        for right_field in INTENT_COMPARISON_FIELDS[index + 1 :]:
            if left_field in paired_fields or right_field in paired_fields:
                continue
            right_report = normalize(source_value(finding, right_field))
            right_library = normalize(source_value(candidate, right_field))
            if not right_report or not right_library:
                continue
            expected_left = similarity(left_report, left_library)
            expected_right = similarity(right_report, right_library)
            cross_left = similarity(left_report, right_library)
            cross_right = similarity(right_report, left_library)
            if (
                cross_left >= 0.85
                and cross_left >= expected_left + 0.20
                and cross_right >= 0.85
                and cross_right >= expected_right + 0.20
            ):
                fields = [left_field, right_field]
                issues.append(
                    make_issue(
                        "FINDING-FIELD-INTENT-MISMATCH",
                        finding,
                        f"Within {finding_label(finding, 'report finding')}, "
                        f"{display_field(left_field)} and {display_field(right_field)} "
                        "appear to be reversed when compared with "
                        f"{finding_label(candidate, 'finding-library entry')}. "
                        "This warning identifies a possible field-placement error based "
                        "on the library comparison; it does not mean the report contains "
                        "duplicate findings. Review both fields and move the content only "
                        "if the library entry reflects their intended roles.",
                        candidate=candidate,
                        comparison=comparison,
                        fields=fields,
                    )
                )
                paired_fields.update(fields)

    for field in INTENT_COMPARISON_FIELDS:
        if field in paired_fields:
            continue
        report_value = normalize(source_value(finding, field))
        expected_value = normalize(source_value(candidate, field))
        if not report_value or not expected_value:
            continue
        expected_score = similarity(report_value, expected_value)
        alternatives = [
            (similarity(report_value, normalize(source_value(candidate, other))), other)
            for other in INTENT_COMPARISON_FIELDS
            if other != field and source_value(candidate, other)
        ]
        if not alternatives:
            continue
        cross_score, source_field = max(alternatives)
        if cross_score >= 0.93 and cross_score >= expected_score + 0.30:
            issues.append(
                make_issue(
                    "FINDING-FIELD-INTENT-MISMATCH",
                    finding,
                    f"Within {finding_label(finding, 'report finding')}, "
                    f"{display_field(field)} more closely matches "
                    f"{finding_label(candidate, 'finding-library entry')}'s "
                    f"{display_field(source_field)} than its {display_field(field)}. "
                    "This warning identifies a possible field-placement error based on "
                    "the library comparison; it does not mean the report contains duplicate "
                    "findings. Confirm the content belongs in the named report field.",
                    candidate=candidate,
                    comparison=comparison,
                    fields=[field, source_field],
                )
            )
    return issues


def structural_field_intent_mismatches(finding: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect strong field-role mismatches without a useful library candidate."""

    issues = []
    title = source_value(finding, "title")
    if len(normalize(title).split()) > 24 or URL.search(title) or "\n" in title:
        issues.append(
            make_issue(
                "FINDING-FIELD-INTENT-MISMATCH",
                finding,
                "Title appears to contain body content, instructions, or a reference rather than a concise finding name.",
                fields=["title"],
            )
        )

    affected = source_value(finding, "affected_entities")
    if looks_like_procedure(affected) or looks_like_references(affected):
        issues.append(
            make_issue(
                "FINDING-FIELD-INTENT-MISMATCH",
                finding,
                "Affected Entities appears to contain instructions or references rather than target identifiers.",
                fields=["affected_entities"],
            )
        )

    references = normalize(source_value(finding, "references"))
    steps = normalize(source_value(finding, "replication_steps"))
    if looks_like_procedure(references) and looks_like_references(steps):
        issues.append(
            make_issue(
                "FINDING-FIELD-INTENT-MISMATCH",
                finding,
                "References looks procedural while Reproduction Steps appears to contain only citations or URLs.",
                fields=["references", "replication_steps"],
            )
        )
    return issues


def check_field_intent(
    finding: dict[str, Any],
    candidate: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Assess all client-facing fields using candidate and structural evidence."""

    if candidate is not None:
        candidate_issues = candidate_field_intent_mismatches(
            finding, candidate, comparison or {}
        )
        covered_fields = {
            field for issue in candidate_issues for field in issue.get("fields", [])
        }
        structural_issues = [
            issue
            for issue in structural_field_intent_mismatches(finding)
            if not set(issue.get("fields", [])) <= covered_fields
        ]
        return candidate_issues + structural_issues
    return structural_field_intent_mismatches(finding)


def review_findings(
    findings: list[dict[str, Any]], library: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return advisory-only quality issues for the supplied findings."""

    prepared_library = prepare_library(library)
    issues = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        issues.extend(check_placeholders(finding))
        candidate, comparison = best_candidate(finding, prepared_library)
        if candidate is None or comparison is None:
            issues.extend(check_field_intent(finding, None, None))
            continue

        title_score = comparison["field_scores"].get("title", 0.0)
        if not started_blank(finding):
            if comparison["composite"] >= 0.98 and not has_target_customization(finding):
                issues.append(
                    make_issue(
                        "FINDING-LIBRARY-UNCUSTOMIZED",
                        finding,
                        f"{finding_label(finding)} is "
                        f"{percent(comparison['composite'])} similar across comparable "
                        f"fields to {finding_label(candidate, 'finding-library entry')} "
                        "and does not include a non-placeholder Affected Entities value. "
                        "This report-to-library comparison suggests the library text may not "
                        "have been customized for this assessment; it does not mean the report "
                        "contains duplicate findings. Confirm the affected targets and add any "
                        "assessment-specific details before delivery.",
                        candidate=candidate,
                        comparison=comparison,
                    )
                )
        elif comparison["composite"] >= 0.80:
            issues.append(
                make_issue(
                    "FINDING-LIBRARY-CLOSE-MATCH",
                    finding,
                    f"{finding_label(finding)} is marked as having been created from blank "
                    "(added_as_blank=true), but its comparable client-facing fields are "
                    f"{percent(comparison['composite'])} similar to "
                    f"{finding_label(candidate, 'finding-library entry')}, exceeding "
                    "the 80.0% review threshold. This is a match between a report finding and "
                    "the finding library; it does not mean two findings in the report are "
                    "duplicates. Confirm whether the library wording was intentionally reused, "
                    "verify the origin flag, and peer-review the finding for target-specific "
                    "details.",
                    candidate=candidate,
                    comparison=comparison,
                )
            )
        elif (
            title_score >= 0.90
            and comparison["body_coverage"] >= 0.30
            and comparison["body"] < 0.50
        ):
            issues.append(
                make_issue(
                    "FINDING-LIBRARY-TITLE-DIVERGENCE",
                    finding,
                    f"{finding_label(finding)} has a title that is "
                    f"{percent(title_score)} similar to "
                    f"{finding_label(candidate, 'finding-library entry')}, while its "
                    f"body is only {percent(comparison['body'])} similar. This report-to-library "
                    "comparison does not indicate duplicate report findings; it indicates that "
                    "a familiar library title now describes materially different content. "
                    "Confirm that the correct finding concept and library entry were used, or "
                    "that the rewrite is intentional, and request focused peer review.",
                    candidate=candidate,
                    comparison=comparison,
                    priority="elevated",
                )
            )
        issues.extend(check_field_intent(finding, candidate, comparison))
    return issues


def load_findings(path: Path) -> list[dict[str, Any]]:
    """Load a finding list, report export, or saved GraphQL library response."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("findings"), list):
        return data["findings"]
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        findings = data["data"].get("finding")
        if isinstance(findings, list):
            return findings
    raise ValueError(
        f"{path} must be a JSON finding list, report export, or GraphQL finding response"
    )


def parse_args() -> argparse.Namespace:
    """Parse paths for an offline report-plus-library comparison."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--library-json", type=Path, required=True)
    parser.add_argument("--format", choices=("json",), default="json")
    return parser.parse_args()


def main() -> int:
    """Emit warning-level quality signals without modifying either input."""

    args = parse_args()
    try:
        findings = load_findings(args.report_json)
        library = load_findings(args.library_json)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Unable to load comparison input: {error}", file=sys.stderr)
        return 2
    issues = review_findings(findings, library)
    print(
        json.dumps(
            {
                "status": "warning" if issues else "success",
                "findings_reviewed": len(findings),
                "library_findings_compared": len(library),
                "issues": issues,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
