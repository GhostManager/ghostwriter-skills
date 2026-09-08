#!/usr/bin/env python3
"""Offline Ghostwriter template lint and compatibility checks.

The Ghostwriter-parity checks mirror the inexpensive, deterministic checks in
Ghostwriter's DOCX and PPTX linters.  Additional package and authoring checks
are reported separately so callers can distinguish product parity from broader
compatibility advice.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import posixpath
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

W = f"{{{W_NS}}}"
R = f"{{{R_NS}}}"
P = f"{{{P_NS}}}"
A = f"{{{A_NS}}}"
PKG_REL = f"{{{PKG_REL_NS}}}"

DOCX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
PPTX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
)

EXPECTED_DOCX_STYLES = {
    "Bullet List": "paragraph",
    "Number List": "paragraph",
    "CodeBlock": "paragraph",
    "CodeInline": "character",
    "Caption": "paragraph",
    "List Paragraph": "paragraph",
    "Blockquote": "paragraph",
    "footnote text": "paragraph",
    "footnote reference": "character",
    **{f"Heading {level}": "paragraph" for level in range(1, 7)},
}

DEFAULT_REPORT_CONTEXT = {
    "report_date",
    "tags",
    "project",
    "client",
    "team",
    "objectives",
    "targets",
    "scope",
    "deconflictions",
    "whitecards",
    "infrastructure",
    "severities",
    "findings",
    "observations",
    "docx_template",
    "pptx_template",
    "logs",
    "company",
    "title",
    "complete",
    "archived",
    "delivered",
    "totals",
    "tools",
    "evidence",
    "contacts",
    "recipient",
    "extra_fields",
    "bloodhound",
}

DEFAULT_PROJECT_CONTEXT = {
    "project",
    "client",
    "contacts",
    "team",
    "objectives",
    "targets",
    "scope",
    "deconflictions",
    "whitecards",
    "infrastructure",
    "logs",
    "company",
    "report_date",
    "tools",
    "recipient",
    "extra_fields",
}

DEFAULT_GHOSTWRITER_FILTERS = {
    "filter_severity",
    "filter_type",
    "strip_html",
    "compromised",
    "add_days",
    "format_datetime",
    "to_datetime",
    "business_days",
    "get_item",
    "regex_search",
    "filter_tags",
    "replace_blanks",
    "filter_bhe_findings_by_domain",
    "translate_domain_sid",
}

DEFAULT_JINJA_FILTERS = {
    "abs", "attr", "batch", "capitalize", "center", "d", "default",
    "dictsort", "e", "escape", "filesizeformat", "first", "float",
    "forceescape", "format", "groupby", "indent", "int", "items", "join",
    "last", "length", "list", "lower", "map", "max", "min", "pprint",
    "random", "reject", "rejectattr", "replace", "reverse", "round", "safe",
    "select", "selectattr", "slice", "sort", "string", "striptags", "sum",
    "title", "tojson", "trim", "truncate", "unique", "upper", "urlencode",
    "urlize", "wordcount", "wordwrap", "xmlattr",
}

JINJA_GLOBALS = {"range", "dict", "lipsum", "cycler", "joiner", "namespace"}
JINJA_KEYWORDS = {
    "and", "as", "break", "by", "call", "continue", "else", "false",
    "filter", "for", "from", "if", "import", "in", "is", "macro", "none",
    "not", "or", "recursive", "scoped", "true", "with", "without",
}

EXTERNAL_FIELD_TYPES = {
    "DDE",
    "DDEAUTO",
    "DATABASE",
    "INCLUDEPICTURE",
    "INCLUDETEXT",
    "LINK",
    "RD",
}

RICH_TEXT_FIELDS = {
    "affected_entities",
    "description",
    "impact",
    "mitigation",
    "recommendation",
    "replication_steps",
    "host_detection_techniques",
    "network_detection_techniques",
    "references",
    "result",
    "collab_note",
    "address",
}

EXTRA_FIELD_REFERENCE_RE = re.compile(
    r"(?<![\w.])(?:(project)\.)?extra_fields\.([A-Za-z_][A-Za-z0-9_]*)"
)
EXTRA_FIELD_SPEC_QUERY = """
query ReviewTemplateExtraFieldSpec($model: String!) {
  getExtraFieldSpec(model: $model) {
    extraFieldSpec
  }
}
"""


class NoRedirect(HTTPRedirectHandler):
    """Avoid forwarding an API token when an endpoint redirects elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class Issue:
    severity: str
    category: str
    code: str
    message: str
    location: str | None = None
    suggestion: str | None = None


class Review:
    def __init__(self, template: Path, document_type: str):
        self.template = template
        self.document_type = document_type
        self.issues: list[Issue] = []
        self.inventory: dict[str, object] = {}
        self.analysis: dict[str, object] = {}

    def add(
        self,
        severity: str,
        category: str,
        code: str,
        message: str,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        issue = Issue(severity, category, code, message, location, suggestion)
        if issue not in self.issues:
            self.issues.append(issue)

    def status(self, category: str | None = None) -> str:
        relevant = [
            issue
            for issue in self.issues
            if category is None or issue.category == category
        ]
        if any(issue.severity == "error" for issue in relevant):
            return "failed"
        if any(issue.severity == "warning" for issue in relevant):
            return "warning"
        return "success"

    def result(self) -> dict[str, object]:
        parity_issues = [
            asdict(issue)
            for issue in self.issues
            if issue.category == "ghostwriter-parity"
        ]
        compatibility_issues = [
            asdict(issue)
            for issue in self.issues
            if issue.category != "ghostwriter-parity"
        ]
        return {
            "schema_version": 1,
            "template": {
                "path": str(self.template.resolve()),
                "document_type": self.document_type,
                "size_bytes": self.template.stat().st_size
                if self.template.is_file()
                else None,
                "sha256": sha256(self.template) if self.template.is_file() else None,
            },
            "overall_status": self.status(),
            "ghostwriter_parity": {
                "status": self.status("ghostwriter-parity"),
                "issues": parity_issues,
            },
            "compatibility": {
                "status": status_for_issues(compatibility_issues),
                "issues": compatibility_issues,
            },
            "inventory": self.inventory,
            "analysis": self.analysis,
        }


def status_for_issues(issues: list[dict[str, object]]) -> str:
    if any(issue["severity"] == "error" for issue in issues):
        return "failed"
    if any(issue["severity"] == "warning" for issue in issues):
        return "warning"
    return "success"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xml(review: Review, archive: ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(archive.read(name))
    except (KeyError, ET.ParseError) as exc:
        review.add(
            "error",
            "package",
            "PKG-XML-INVALID",
            f"Required OOXML part could not be parsed: {exc}",
            name,
            "Recreate or repair this package part in the Office application.",
        )
        return None


def content_type_for(archive: ZipFile, part_name: str) -> str | None:
    try:
        root = ET.fromstring(archive.read("[Content_Types].xml"))
    except (KeyError, ET.ParseError):
        return None
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for child in root:
        if local_name(child.tag) == "Default":
            defaults[child.attrib.get("Extension", "").lower()] = child.attrib.get(
                "ContentType", ""
            )
        elif local_name(child.tag) == "Override":
            overrides[child.attrib.get("PartName", "").lstrip("/")] = child.attrib.get(
                "ContentType", ""
            )
    return overrides.get(part_name) or defaults.get(part_name.rsplit(".", 1)[-1].lower())


def source_part_for_rels(rels_name: str) -> str:
    if rels_name == "_rels/.rels":
        return ""
    directory, filename = posixpath.split(rels_name)
    if not directory.endswith("/_rels") or not filename.endswith(".rels"):
        return ""
    source_directory = directory[: -len("/_rels")]
    source_filename = filename[: -len(".rels")]
    return posixpath.join(source_directory, source_filename)


def resolve_relationship_target(rels_name: str, target: str) -> str:
    source_part = source_part_for_rels(rels_name)
    base = posixpath.dirname(source_part)
    return posixpath.normpath(posixpath.join(base, target)).lstrip("/")


def audit_relationships(review: Review, archive: ZipFile) -> None:
    names = set(archive.namelist())
    external: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for rels_name in sorted(name for name in names if name.endswith(".rels")):
        try:
            root = ET.fromstring(archive.read(rels_name))
        except ET.ParseError as exc:
            review.add(
                "error",
                "package",
                "PKG-RELS-INVALID",
                f"Relationship part is invalid XML: {exc}",
                rels_name,
            )
            continue
        for relationship in root:
            target = relationship.attrib.get("Target", "")
            relation_type = relationship.attrib.get("Type", "")
            relation_id = relationship.attrib.get("Id", "")
            mode = relationship.attrib.get("TargetMode", "")
            if mode.lower() == "external":
                record = {
                    "part": rels_name,
                    "id": relation_id,
                    "type": relation_type,
                    "target": target,
                }
                external.append(record)
                if relation_type.endswith("/hyperlink"):
                    review.add(
                        "info",
                        "compatibility",
                        "PKG-EXTERNAL-HYPERLINK",
                        "Document contains an external hyperlink.",
                        rels_name,
                    )
                else:
                    review.add(
                        "warning",
                        "compatibility",
                        "PKG-EXTERNAL-DEPENDENCY",
                        f"External package relationship may require another file or network resource: {target}",
                        rels_name,
                        "Embed the resource unless the dependency is intentional and documented.",
                    )
                continue
            if not target or target.startswith("#"):
                continue
            resolved = resolve_relationship_target(rels_name, target)
            if resolved not in names:
                missing.append(
                    {
                        "part": rels_name,
                        "id": relation_id,
                        "target": target,
                        "resolved": resolved,
                    }
                )
                review.add(
                    "error",
                    "package",
                    "PKG-REL-TARGET-MISSING",
                    f"Internal relationship target is missing: {resolved}",
                    rels_name,
                    "Repair the relationship or restore the missing package part.",
                )
    review.inventory["external_relationships"] = external
    review.inventory["missing_relationship_targets"] = missing


def discover_ghostwriter_context(
    root: Path | None, document_type: str
) -> tuple[set[str], str, dict[str, object] | None]:
    fallback = (
        set(DEFAULT_PROJECT_CONTEXT)
        if document_type == "project_docx"
        else set(DEFAULT_REPORT_CONTEXT)
    )
    if root is None:
        return fallback, "bundled defaults", None
    lint_path = root / "ghostwriter" / "modules" / "linting_utils.py"
    try:
        module = ast.parse(lint_path.read_text(encoding="utf-8"))
        for node in module.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if not any(isinstance(target, ast.Name) and target.id == "LINTER_CONTEXT" for target in targets):
                continue
            value = ast.literal_eval(node.value)
            if isinstance(value, dict):
                if document_type == "project_docx":
                    value = {
                        key: value[key]
                        for key in DEFAULT_PROJECT_CONTEXT
                        if key in value
                    }
                return set(value), str(lint_path), value
    except (OSError, SyntaxError, ValueError):
        pass
    return fallback, "bundled defaults (Ghostwriter context discovery failed)", None


def discover_ghostwriter_filters(root: Path | None) -> tuple[set[str], str]:
    filters = set(DEFAULT_GHOSTWRITER_FILTERS)
    if root is None:
        return filters, "bundled defaults"
    env_path = root / "ghostwriter" / "modules" / "reportwriter" / "__init__.py"
    try:
        module = ast.parse(env_path.read_text(encoding="utf-8"))
        discovered: set[str] = set()
        for node in ast.walk(module):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Subscript):
                    continue
                owner = target.value
                if not (
                    isinstance(owner, ast.Attribute)
                    and owner.attr == "filters"
                    and isinstance(owner.value, ast.Name)
                    and owner.value.id == "env"
                ):
                    continue
                key = target.slice
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    discovered.add(key.value)
        if discovered:
            return discovered, str(env_path)
    except (OSError, SyntaxError):
        pass
    return filters, "bundled defaults (Ghostwriter filter discovery failed)"


def load_context_json(
    path: Path | None,
) -> tuple[set[str] | None, str | None, dict[str, object] | None]:
    if path is None:
        return None, None, None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("context JSON must contain an object at the top level")
    return set(value), str(path), value


def default_extra_field_models(document_type: str) -> list[str]:
    """Return the Ghostwriter models that can supply extra fields to a template."""
    if document_type == "project_docx":
        return ["project"]
    if document_type in {"docx", "pptx"}:
        # Report templates can also render project.extra_fields references.
        return ["report", "project"]
    return []


def normalize_extra_field_spec(payload: object) -> dict[str, str] | None:
    """Extract only field names/types from GraphQL or proxied action output.

    Defaults and display names are intentionally discarded: a review needs the
    schema, not potentially sensitive instance configuration values.
    """
    if not isinstance(payload, dict):
        return None
    node = payload.get("data", payload)
    if not isinstance(node, dict):
        return None
    node = node.get("getExtraFieldSpec", node)
    if not isinstance(node, dict):
        return None
    raw_spec = node.get("extraFieldSpec")
    if isinstance(raw_spec, str):
        try:
            raw_spec = json.loads(raw_spec)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw_spec, dict):
        return None
    fields: dict[str, str] = {}
    for key, value in raw_spec.items():
        if not isinstance(value, dict):
            continue
        name = value.get("internalName", key)
        field_type = value.get("type")
        if isinstance(name, str) and isinstance(field_type, str):
            fields[name] = field_type
    return fields


def fetch_remote_extra_field_spec(
    endpoint: str, token: str, model: str, timeout: float
) -> tuple[dict[str, str] | None, str | None]:
    """Fetch one model's public extra-field metadata without exposing the token."""
    body = json.dumps(
        {
            "operationName": "ReviewTemplateExtraFieldSpec",
            "query": EXTRA_FIELD_SPEC_QUERY,
            "variables": {"model": model},
        }
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Ghostwriter-review-template/1.0",
        },
        method="POST",
    )
    try:
        # Do not silently follow a redirect and risk sending credentials to a
        # different endpoint. Limit the response to metadata-sized payloads.
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw_response = response.read(1024 * 1024 + 1)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None, "request failed or was rejected"
    if len(raw_response) > 1024 * 1024:
        return None, "response exceeded the 1 MiB metadata limit"
    try:
        payload = json.loads(raw_response)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "response was not valid JSON"
    if isinstance(payload, dict) and payload.get("errors"):
        return None, "endpoint returned GraphQL errors"
    spec = normalize_extra_field_spec(payload)
    if spec is None:
        return None, "response did not contain an extraFieldSpec object"
    return spec, None


def load_remote_extra_field_specs(
    review: Review,
    endpoint: str | None,
    token_env: str,
    models: list[str],
    timeout: float,
) -> dict[str, dict[str, str]]:
    """Optionally obtain remote schema metadata, keeping all secrets out of output."""
    if not endpoint:
        review.analysis["extra_field_specs"] = {
            "source": "not supplied; references remain unverified",
            "models": {},
        }
        return {}

    token = os.environ.get(token_env)
    if not token:
        review.add(
            "info",
            "compatibility",
            "GW-EXTRA-FIELD-SPEC-REMOTE-UNAVAILABLE",
            "A remote extra-field-spec endpoint was supplied, but its token environment variable is unset; extra fields remain unverified.",
            suggestion="Set the token in the named environment variable and rerun the read-only review.",
        )
        review.analysis["extra_field_specs"] = {
            "source": "remote endpoint unavailable (token not present)",
            "models": {},
        }
        return {}

    specs: dict[str, dict[str, str]] = {}
    failures: dict[str, str] = {}
    for model in models:
        spec, failure = fetch_remote_extra_field_spec(endpoint, token, model, timeout)
        if spec is None:
            failures[model] = failure or "unknown failure"
        else:
            specs[model] = spec
    if failures:
        review.add(
            "info",
            "compatibility",
            "GW-EXTRA-FIELD-SPEC-REMOTE-UNAVAILABLE",
            "Could not retrieve extra-field metadata for "
            + ", ".join(sorted(failures))
            + "; affected extra fields remain unverified.",
            suggestion="Confirm the GraphQL endpoint, token permissions, and selected model, then rerun the review.",
        )
    review.analysis["extra_field_specs"] = {
        "source": "remote endpoint" if specs else "remote endpoint unavailable",
        "models": {
            model: {"field_count": len(spec), "field_types": dict(sorted(spec.items()))}
            for model, spec in sorted(specs.items())
        },
        "unavailable_models": sorted(failures),
    }
    return specs


def element_text(element: ET.Element, text_tags: set[str]) -> str:
    return "".join(
        child.text or "" for child in element.iter() if child.tag in text_tags
    )


def parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def has_ancestor(
    element: ET.Element, parents: dict[ET.Element, ET.Element], expected_tag: str
) -> bool:
    current = element
    while current in parents:
        current = parents[current]
        if current.tag == expected_tag:
            return True
    return False


STRUCTURAL_TAG_RE = re.compile(r"\{%\s*(p|tr|tc|r)\b.*?%\}", re.DOTALL)


def check_docxtpl_structural_tags(
    review: Review, part_name: str, root: ET.Element
) -> None:
    parents = parent_map(root)
    text_tags = {W + "t"}
    all_text = element_text(root, text_tags)
    all_tags = STRUCTURAL_TAG_RE.findall(all_text)
    located = 0

    container_for = {
        "p": W + "p",
        "tr": W + "tr",
        "tc": W + "tc",
        "r": W + "r",
    }
    for prefix, container_tag in container_for.items():
        for index, container in enumerate(root.iter(container_tag), start=1):
            text = element_text(container, text_tags)
            matches = [
                match
                for match in STRUCTURAL_TAG_RE.finditer(text)
                if match.group(1) == prefix
            ]
            if matches:
                located += len(matches)
            if len(matches) > 1:
                review.add(
                    "error",
                    "compatibility",
                    "DOCX-STRUCTURAL-TAG-DUPLICATE",
                    f"The docxtpl prefix '{{%{prefix}' appears more than once in one {prefix} container.",
                    f"{part_name}#{local_name(container_tag)}-{index}",
                    "Place the opening and closing structural tags in separate containers.",
                )

    for index, paragraph in enumerate(root.iter(W + "p"), start=1):
        text = element_text(paragraph, text_tags)
        for match in STRUCTURAL_TAG_RE.finditer(text):
            prefix = match.group(1)
            if prefix == "p":
                continue
            if prefix == "tr" and not has_ancestor(paragraph, parents, W + "tr"):
                expected = "table row"
            elif prefix == "tc" and not has_ancestor(paragraph, parents, W + "tc"):
                expected = "table cell"
            elif prefix == "r" and not any(
                match.group(0) in element_text(run, text_tags)
                for run in paragraph.iter(W + "r")
            ):
                expected = "single Word run"
            else:
                continue
            review.add(
                "error",
                "compatibility",
                "DOCX-STRUCTURAL-TAG-LOCATION",
                f"The '{{%{prefix}' tag is not wholly contained in the required {expected}.",
                f"{part_name}#paragraph-{index}",
                "Re-enter the complete tag in the matching Word structure.",
            )

    if all_tags and located < len(all_tags):
        review.add(
            "warning",
            "compatibility",
            "DOCX-STRUCTURAL-TAG-SPLIT",
            "At least one docxtpl structural tag appears split across a boundary the offline checker could not localize.",
            part_name,
            "Inspect the tag in Word and ensure it is contained in one paragraph, row, cell, or run as required.",
        )


def normalize_docxtpl_for_jinja(source: str) -> str:
    # docxtpl accepts control tags wrapped as ``{{%p ... %}}`` in addition to
    # the documented ``{%p ... %}`` form. Normalize the wrapped form before
    # removing the structural prefix for Jinja's parser.
    source = re.sub(
        r"\{\{%\s*(p|tr|tc|r)\s+(.+?)%\}\}",
        lambda match: "{%" + match.group(1) + " " + match.group(2).strip() + "%}",
        source,
        flags=re.DOTALL,
    )
    source = re.sub(r"\{%\s*(?:p|tr|tc|r)\s+", "{% ", source)
    source = re.sub(r"\{\{\s*(?:p|r)\s+", "{{ ", source)
    source = re.sub(
        r"\{%\s*(?:cellbg|colspan)\s+(.+?)%\}",
        lambda match: "{{ " + match.group(1).strip() + " }}",
        source,
        flags=re.DOTALL,
    )
    source = re.sub(r"\{%\s*(?:vm|hm)\s*%\}", "", source)
    return source


def extract_docx_template_sources(
    review: Review, archive: ZipFile
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    sources: dict[str, str] = {}
    paragraphs: list[tuple[str, str]] = []
    candidates = [
        name
        for name in archive.namelist()
        if (
            name == "word/document.xml"
            or re.fullmatch(r"word/(?:header|footer)\d+\.xml", name)
            or name
            in {
                "word/footnotes.xml",
                "word/endnotes.xml",
                "word/comments.xml",
                "docProps/core.xml",
            }
        )
    ]
    for name in sorted(candidates):
        try:
            root = ET.fromstring(archive.read(name))
        except ET.ParseError as exc:
            review.add(
                "error",
                "package",
                "PKG-XML-INVALID",
                f"Template-bearing part contains invalid XML: {exc}",
                name,
            )
            continue
        if name.startswith("word/"):
            check_docxtpl_structural_tags(review, name, root)
            chunks = []
            for index, paragraph in enumerate(root.iter(W + "p"), start=1):
                text = element_text(paragraph, {W + "t"})
                if text:
                    chunks.append(text)
                    paragraphs.append((f"{name}#paragraph-{index}", text))
            sources[name] = "\n".join(chunks)
        else:
            sources[name] = "\n".join(
                text.strip() for text in root.itertext() if text and text.strip()
            )
    return sources, paragraphs


def check_jinja(
    review: Review,
    sources: dict[str, str],
    known_context: set[str],
    known_filters: set[str],
) -> None:
    try:
        import jinja2
        from jinja2 import meta
    except ImportError:
        check_jinja_fallback(review, sources, known_context, known_filters)
        review.add(
            "info",
            "compatibility",
            "JINJA-DEEP-PARSER-UNAVAILABLE",
            "Jinja2 is unavailable; the built-in structural fallback ran, but full parser parity was not available.",
            suggestion="Run in an environment with Jinja2 for authoritative grammar and meta analysis.",
        )
        return

    environment = jinja2.Environment(autoescape=True)
    for filter_name in known_filters:
        environment.filters[filter_name] = lambda value, *args, **kwargs: value

    undeclared: set[str] = set()
    parsed_parts = 0
    for part_name, raw_source in sources.items():
        if not any(delimiter in raw_source for delimiter in ("{{", "{%", "{#")):
            continue
        source = normalize_docxtpl_for_jinja(raw_source)
        if re.search(r"(?:\.\s*__|\[\s*['\"]__)", source):
            review.add(
                "error",
                "ghostwriter-parity",
                "GW-JINJA-UNSAFE-ATTRIBUTE",
                "Template attempts to access a private or dunder attribute blocked by Ghostwriter's sandbox.",
                part_name,
                "Use only documented report data, filters, tests, and safe built-in operations.",
            )
        try:
            parsed = environment.parse(source)
        except jinja2.TemplateError as exc:
            review.add(
                "error",
                "ghostwriter-parity",
                "GW-JINJA-SYNTAX",
                f"Template syntax or filter recognition failed: {exc}",
                part_name,
                "Correct the expression using filters and tags supported by the target Ghostwriter version.",
            )
            continue
        parsed_parts += 1
        undeclared.update(meta.find_undeclared_variables(parsed))

    potential = sorted(undeclared - known_context)
    for variable in potential:
        review.add(
            "warning",
            "ghostwriter-parity",
            "GW-JINJA-UNDEFINED",
            f"Potential undefined variable: {variable!r}",
            suggestion="Confirm the variable exists in the target report context or extra-field configuration.",
        )
    review.analysis["jinja"] = {
        "parts_with_jinja_parsed": parsed_parts,
        "undeclared_top_level_variables": sorted(undeclared),
        "potential_undefined_variables": potential,
        "known_filter_count": len(known_filters),
    }


def remove_quoted_strings(source: str) -> str:
    return re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "''", source)


def check_jinja_fallback(
    review: Review,
    sources: dict[str, str],
    known_context: set[str],
    known_filters: set[str],
) -> None:
    """Perform conservative grammar/filter/context checks without Jinja2."""
    opener_to_closer = {
        "for": "endfor",
        "if": "endif",
        "block": "endblock",
        "macro": "endmacro",
        "call": "endcall",
        "filter": "endfilter",
        "with": "endwith",
        "autoescape": "endautoescape",
    }
    closers = set(opener_to_closer.values())
    valid_statements = set(opener_to_closer) | closers | {
        "else", "elif", "set", "include", "import", "from", "extends",
    }
    declared: set[str] = set()
    candidates: set[str] = set()
    used_filters: set[str] = set()
    parsed_parts = 0

    for part_name, raw_source in sources.items():
        if not any(delimiter in raw_source for delimiter in ("{{", "{%", "{#")):
            continue
        parsed_parts += 1
        source = normalize_docxtpl_for_jinja(raw_source)
        if re.search(r"(?:\.\s*__|\[\s*['\"]__)", source):
            review.add(
                "error",
                "ghostwriter-parity",
                "GW-JINJA-UNSAFE-ATTRIBUTE",
                "Template attempts to access a private or dunder attribute blocked by Ghostwriter's sandbox.",
                part_name,
            )
        for opening, closing in (("{{", "}}"), ("{%", "%}"), ("{#", "#}")):
            if source.count(opening) != source.count(closing):
                review.add(
                    "error",
                    "ghostwriter-parity",
                    "GW-JINJA-DELIMITER",
                    f"Unbalanced Jinja delimiter {opening} ... {closing}.",
                    part_name,
                )

        scan_source = re.sub(
            r"{%\s*raw\s*%}.*?{%\s*endraw\s*%}", "", source, flags=re.DOTALL
        )
        stack: list[tuple[str, str]] = []
        for match in re.finditer(r"{%[-+]?\s*(.*?)\s*[-+]?%}", scan_source, re.DOTALL):
            body = match.group(1).strip()
            if not body:
                continue
            statement = body.split(None, 1)[0]
            if statement not in valid_statements:
                review.add(
                    "error",
                    "ghostwriter-parity",
                    "GW-JINJA-STATEMENT-UNKNOWN",
                    f"Unsupported or unknown Jinja statement: {statement}",
                    part_name,
                )
                continue
            if statement in opener_to_closer:
                stack.append((statement, opener_to_closer[statement]))
            elif statement in closers:
                if not stack or stack[-1][1] != statement:
                    review.add(
                        "error",
                        "ghostwriter-parity",
                        "GW-JINJA-BLOCK-MISMATCH",
                        f"Unexpected {statement} tag.",
                        part_name,
                    )
                else:
                    stack.pop()
            if statement == "for":
                declaration = re.match(r"for\s+(.+?)\s+in\s+", body, re.DOTALL)
                if declaration:
                    declared.update(re.findall(r"\b[A-Za-z_]\w*\b", declaration.group(1)))
            elif statement == "set":
                declaration = re.match(r"set\s+([A-Za-z_]\w*)", body)
                if declaration:
                    declared.add(declaration.group(1))
        for statement, closer in stack:
            review.add(
                "error",
                "ghostwriter-parity",
                "GW-JINJA-BLOCK-UNCLOSED",
                f"Jinja {statement} block is missing {closer}.",
                part_name,
            )

        expressions = re.findall(r"{{[-+]?\s*(.*?)\s*[-+]?}}", scan_source, re.DOTALL)
        expressions.extend(
            match.group(1)
            for match in re.finditer(
                r"{%[-+]?\s*(?:if|elif)\s+(.+?)\s*[-+]?%}",
                scan_source,
                re.DOTALL,
            )
        )
        expressions.extend(
            match.group(1)
            for match in re.finditer(
                r"{%[-+]?\s*for\s+.+?\s+in\s+(.+?)\s*[-+]?%}",
                scan_source,
                re.DOTALL,
            )
        )
        template_code = expressions + [
            match.group(1)
            for match in re.finditer(
                r"{%[-+]?\s*(.*?)\s*[-+]?%}", scan_source, re.DOTALL
            )
        ]
        for code in template_code:
            used_filters.update(
                re.findall(r"\|\s*([A-Za-z_]\w*)", remove_quoted_strings(code))
            )
        for expression in expressions:
            unquoted = remove_quoted_strings(expression)
            for match in re.finditer(r"(?<![.\w])([A-Za-z_]\w*)", unquoted):
                token = match.group(1)
                remainder = unquoted[match.end() :]
                if re.match(r"\s*=", remainder):
                    continue
                candidates.add(token)

    allowed_filters = known_filters | DEFAULT_JINJA_FILTERS
    for filter_name in sorted(used_filters - allowed_filters):
        review.add(
            "error",
            "ghostwriter-parity",
            "GW-JINJA-FILTER-UNKNOWN",
            f"Unknown filter for the target Ghostwriter environment: {filter_name}",
        )

    excluded = (
        declared
        | JINJA_GLOBALS
        | JINJA_KEYWORDS
        | allowed_filters
        | {"loop"}
    )
    potential = sorted(candidates - known_context - excluded)
    for variable in potential:
        review.add(
            "warning",
            "ghostwriter-parity",
            "GW-JINJA-UNDEFINED",
            f"Potential undefined variable: {variable!r}",
            suggestion="Confirm the variable exists in the target report context or extra-field configuration.",
        )
    review.analysis["jinja"] = {
        "mode": "built-in fallback",
        "parts_with_jinja_parsed": parsed_parts,
        "potential_undefined_variables": potential,
        "used_filters": sorted(used_filters),
        "known_filter_count": len(known_filters),
    }


def check_docxtpl_render(
    review: Review,
    context: dict[str, object] | None,
    known_filters: set[str],
) -> None:
    if context is None:
        review.analysis["ghostwriter_render"] = {
            "performed": False,
            "reason": "No representative context was available; provide --ghostwriter-root or --context-json.",
        }
        return
    try:
        import jinja2
        from docxtpl import DocxTemplate
    except ImportError:
        review.analysis["ghostwriter_render"] = {
            "performed": False,
            "reason": "docxtpl and Jinja2 are required for the offline structural render.",
        }
        return

    environment = jinja2.Environment(
        autoescape=True,
        undefined=jinja2.DebugUndefined,
    )
    for filter_name in known_filters:
        environment.filters[filter_name] = lambda value, *args, **kwargs: value
    try:
        template = DocxTemplate(review.template)
        template.render(context, environment, autoescape=True)
        rendered = io.BytesIO()
        template.save(rendered)
        rendered.seek(0)
        with ZipFile(rendered) as archive:
            bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"rendered package failed CRC check at {bad_member}")
    except Exception as exc:  # The dependency raises several library-specific types.
        review.add(
            "error",
            "ghostwriter-parity",
            "GW-DOCX-REPRESENTATIVE-RENDER",
            f"Offline representative docxtpl render failed: {type(exc).__name__}: {exc}",
            suggestion="Correct the structural/Jinja issue, then confirm with the target Ghostwriter renderer.",
        )
        review.analysis["ghostwriter_render"] = {
            "performed": True,
            "mode": "offline docxtpl structural render",
            "success": False,
        }
        return
    review.analysis["ghostwriter_render"] = {
        "performed": True,
        "mode": "offline docxtpl structural render",
        "success": True,
        "limitation": "This does not reproduce Ghostwriter's rich-text, evidence, database, or instance-specific extra-field processing.",
    }


def check_rich_text_usage(review: Review, paragraphs: list[tuple[str, str]]) -> None:
    expression_re = re.compile(r"\{\{(?!\s*[pr]\s)(.*?)\}\}", re.DOTALL)
    raw_hits: list[dict[str, str]] = []
    for location, text in paragraphs:
        for match in expression_re.finditer(text):
            expression = match.group(1)
            field_match = re.search(
                r"\b(?:finding|observation|objective|project|client)\.([a-zA-Z_][a-zA-Z0-9_]*)\b",
                expression,
            )
            if not field_match:
                continue
            field = field_match.group(1)
            if field not in RICH_TEXT_FIELDS or "strip_html" in expression:
                continue
            raw_hits.append({"location": location, "expression": match.group(0)})
            review.add(
                "warning",
                "authoring",
                "DOCX-RICH-TEXT-RAW-HTML",
                f"Expression may emit stored HTML as plain text: {match.group(0)}",
                location,
                f"Use the matching `_rt` field with `{{{{p ...}}}}` when formatted rich text is intended.",
            )
    review.analysis["raw_rich_text_expressions"] = raw_hits


def check_extra_field_references(
    review: Review,
    sources: dict[str, str],
    document_type: str,
    specs: dict[str, dict[str, str]],
) -> None:
    """Validate field names and rich-text use when read-only schema metadata exists."""
    primary_model = "project" if document_type == "project_docx" else "report"
    references: dict[tuple[str, str], set[str]] = {}
    for part_name, source in sources.items():
        for match in EXTRA_FIELD_REFERENCE_RE.finditer(source):
            model = "project" if match.group(1) else primary_model
            references.setdefault((model, match.group(2)), set()).add(part_name)

    unverified: list[dict[str, object]] = []
    for (model, field), parts in sorted(references.items()):
        spec = specs.get(model)
        locations = ", ".join(sorted(parts))
        if spec is None:
            unverified.append({"model": model, "field": field, "parts": sorted(parts)})
            continue
        if field not in spec:
            review.add(
                "warning",
                "ghostwriter-parity",
                "GW-EXTRA-FIELD-UNDEFINED",
                f"Extra field '{field}' is not defined for the remote {model} schema.",
                locations,
                "Create the field in Ghostwriter, correct the reference, or select the matching extra-field model.",
            )
            continue
        rich_text_pattern = re.compile(
            r"\{\{\s*[pr]\s+"
            + (r"project\." if model == "project" else "")
            + r"extra_fields\."
            + re.escape(field)
            + r"\b"
        )
        if rich_text_pattern.search("\n".join(sources[part] for part in parts)) and spec[field] != "rich_text":
            review.add(
                "warning",
                "compatibility",
                "DOCX-EXTRA-FIELD-RICH-TEXT-TYPE",
                f"Extra field '{field}' is type '{spec[field]}', but it is rendered with a rich-text {{{{p ...}}}} or {{{{r ...}}}} tag.",
                locations,
                "Use a normal expression for a plain-text field, or change the Ghostwriter field type to rich_text.",
            )

    details = review.analysis.setdefault("extra_field_specs", {})
    if isinstance(details, dict):
        details["unverified_references"] = unverified


def collect_field_records(root: ET.Element) -> list[dict[str, str]]:
    """Return Word field instructions together with their cached display value."""
    fields: list[dict[str, str]] = []
    stack: list[dict[str, object]] = []
    for element in root.iter():
        if element.tag == W + "fldSimple":
            instruction = element.attrib.get(W + "instr", "")
            if instruction.strip():
                fields.append(
                    {
                        "instruction": instruction.strip(),
                        "cached_result": element_text(element, {W + "t"}).strip(),
                    }
                )
        elif element.tag == W + "fldChar":
            kind = element.attrib.get(W + "fldCharType")
            if kind == "begin":
                stack.append({"instruction": [], "result": [], "in_result": False})
            elif kind == "separate" and stack:
                stack[-1]["in_result"] = True
            elif kind == "end" and stack:
                current = stack.pop()
                instruction = "".join(current["instruction"]).strip()
                if instruction:
                    fields.append(
                        {
                            "instruction": instruction,
                            "cached_result": "".join(current["result"]).strip(),
                        }
                    )
        elif element.tag == W + "instrText":
            text = element.text or ""
            if stack:
                stack[-1]["instruction"].append(text)
            elif text.strip():
                fields.append({"instruction": text.strip(), "cached_result": ""})
        elif element.tag == W + "t" and stack and stack[-1]["in_result"]:
            stack[-1]["result"].append(element.text or "")
    return fields


def collect_field_instructions(root: ET.Element) -> list[str]:
    return [field["instruction"] for field in collect_field_records(root)]


def toc_entry_label(paragraph_text: str, cached_result: str) -> str:
    """Return the visible TOC label without its cached page number."""
    label = paragraph_text.strip()
    if cached_result and label.endswith(cached_result):
        label = label[: -len(cached_result)].rstrip()
    return label or "(TOC entry text unavailable)"


def analyze_docx(
    review: Review,
    archive: ZipFile,
    default_paragraph_style: str | None,
    known_context: set[str],
    known_filters: set[str],
    context_data: dict[str, object] | None,
    extra_field_specs: dict[str, dict[str, str]],
) -> None:
    names = set(archive.namelist())
    main_type = content_type_for(archive, "word/document.xml")
    if "word/document.xml" not in names or main_type != DOCX_MAIN_CONTENT_TYPE:
        review.add(
            "error",
            "ghostwriter-parity",
            "GW-DOC-TYPE-MISMATCH",
            "File does not contain a standard DOCX main document matching the selected document type.",
            "[Content_Types].xml",
        )
        return

    document_root = parse_xml(review, archive, "word/document.xml")
    styles_root = parse_xml(review, archive, "word/styles.xml")
    if document_root is None or styles_root is None:
        review.add(
            "error",
            "ghostwriter-parity",
            "GW-DOCX-OPEN",
            "Ghostwriter would not be able to open this file as a Word template.",
        )
        return

    styles: dict[str, dict[str, str]] = {}
    for style in styles_root.iter(W + "style"):
        name = style.find(W + "name")
        style_name = name.attrib.get(W + "val") if name is not None else None
        if not style_name:
            style_name = style.attrib.get(W + "styleId")
        if not style_name:
            continue
        styles[style_name.casefold()] = {
            "name": style_name,
            "type": style.attrib.get(W + "type", ""),
            "style_id": style.attrib.get(W + "styleId", ""),
        }

    for expected_name, expected_type in EXPECTED_DOCX_STYLES.items():
        style = styles.get(expected_name.casefold())
        if style is None:
            review.add(
                "warning",
                "ghostwriter-parity",
                "GW-STYLE-RECOMMENDED-MISSING",
                f"Template is missing a recommended style: {expected_name}",
                "word/styles.xml",
            )
        elif style["type"] != expected_type:
            review.add(
                "warning",
                "ghostwriter-parity",
                "GW-STYLE-TYPE",
                f"{expected_name} is a {style['type'] or 'typeless'} style; Ghostwriter expects {expected_type}.",
                "word/styles.xml",
            )

    if "table grid" not in styles:
        review.add(
            "error",
            "ghostwriter-parity",
            "GW-STYLE-TABLE-GRID-MISSING",
            "Template is missing the required Table Grid style.",
            "word/styles.xml",
            "Apply or create Table Grid in Word and save the template.",
        )
    if default_paragraph_style and default_paragraph_style.casefold() not in styles:
        review.add(
            "warning",
            "ghostwriter-parity",
            "GW-STYLE-DEFAULT-MISSING",
            f"Template is missing the configured default paragraph style: {default_paragraph_style}",
            "word/styles.xml",
        )

    sources, paragraphs = extract_docx_template_sources(review, archive)
    check_jinja(review, sources, known_context, known_filters)
    check_extra_field_references(
        review, sources, review.document_type, extra_field_specs
    )
    check_rich_text_usage(review, paragraphs)
    check_docxtpl_render(review, context_data, known_filters)

    bookmarks: set[str] = set()
    field_instructions: list[dict[str, str]] = []
    external_fields: list[dict[str, str]] = []
    references: list[dict[str, str]] = []
    for name in sorted(
        candidate
        for candidate in names
        if candidate.startswith("word/") and candidate.endswith(".xml")
    ):
        try:
            root = ET.fromstring(archive.read(name))
        except ET.ParseError:
            continue
        bookmarks.update(
            element.attrib.get(W + "name", "")
            for element in root.iter(W + "bookmarkStart")
            if element.attrib.get(W + "name")
        )
        for paragraph_index, paragraph in enumerate(root.iter(W + "p"), start=1):
            paragraph_text = element_text(paragraph, {W + "t"}).strip()
            location = f"{name}#paragraph-{paragraph_index}"
            for field in collect_field_records(paragraph):
                instruction = field["instruction"]
                cached_result = field["cached_result"]
                field_instructions.append(
                    {
                        "part": name,
                        "location": location,
                        "instruction": instruction,
                        "cached_result": cached_result,
                    }
                )
                field_type_match = re.match(r"\s*([A-Za-z]+)", instruction)
                field_type = field_type_match.group(1).upper() if field_type_match else ""
                if field_type in EXTERNAL_FIELD_TYPES:
                    external_fields.append(
                        {
                            "part": name,
                            "location": location,
                            "type": field_type,
                            "instruction": instruction,
                        }
                    )
                    review.add(
                        "warning",
                        "compatibility",
                        "DOCX-EXTERNAL-FIELD",
                        f"Word field may depend on an external file or data source: {field_type}",
                        location,
                        "Remove or replace the field unless the dependency is intentional.",
                    )
                ref_match = re.match(
                    r"\s*(?:REF|PAGEREF)\s+(?:\"([^\"]+)\"|([^\s\\]+))",
                    instruction,
                    re.IGNORECASE,
                )
                if ref_match:
                    target = ref_match.group(1) or ref_match.group(2)
                    references.append(
                        {
                            "part": name,
                            "location": location,
                            "target": target,
                            "cached_result": cached_result,
                            "paragraph_text": paragraph_text,
                        }
                    )

    missing_references = [
        reference for reference in references if reference["target"] not in bookmarks
    ]
    missing_toc = [
        reference
        for reference in missing_references
        if reference["target"].startswith("_Toc")
    ]
    missing_other = [
        reference
        for reference in missing_references
        if not reference["target"].startswith("_Toc")
    ]
    if missing_toc:
        labels = [
            f"{toc_entry_label(reference['paragraph_text'], reference['cached_result'])} (cached page {reference['cached_result'] or 'unknown'})"
            for reference in missing_toc
        ]
        review.add(
            "info",
            "authoring",
            "DOCX-TOC-SOURCE-TARGETS-UNRESOLVED",
            f"Source-template TOC entries have no source bookmarks: {'; '.join(labels)}.",
            "word/document.xml",
            "This is common when headings are inserted dynamically. Verify these entries and their links after a populated Ghostwriter render; recreate bookmarks only if they should resolve in the source template itself.",
        )
    if missing_other:
        examples = "; ".join(
            f"{reference['target']} (cached result: {reference['cached_result'] or 'none'})"
            for reference in missing_other[:3]
        )
        suffix = "..." if len(missing_other) > 3 else ""
        review.add(
            "warning",
            "compatibility",
            "DOCX-BOOKMARK-TARGET-MISSING",
            f"Word cross-reference target(s) are missing: {examples}{suffix}",
            "word/document.xml",
            "Verify the reference in Word and a non-Word renderer. Recreate the bookmark/cross-reference or replace it with static text if it must be portable.",
        )

    update_fields = False
    if "word/settings.xml" in names:
        try:
            settings = ET.fromstring(archive.read("word/settings.xml"))
            for element in settings.iter(W + "updateFields"):
                value = element.attrib.get(W + "val", "true").lower()
                update_fields = value not in {"0", "false", "off", "no"}
        except ET.ParseError:
            pass
    if update_fields:
        review.add(
            "warning",
            "compatibility",
            "DOCX-UPDATE-FIELDS-ON-OPEN",
            "Word is instructed to update fields when the document opens; this can trigger a generic external-file warning even without external dependencies.",
            "word/settings.xml",
            "Disable automatic field updates unless the open-time prompt is acceptable.",
        )

    tracked_changes = 0
    for name in names:
        if not (name.startswith("word/") and name.endswith(".xml")):
            continue
        try:
            root = ET.fromstring(archive.read(name))
        except ET.ParseError:
            continue
        tracked_changes += sum(
            1 for element in root.iter() if element.tag in {W + "ins", W + "del"}
        )
    if tracked_changes:
        review.add(
            "warning",
            "authoring",
            "DOCX-TRACKED-CHANGES",
            f"Template contains tracked-change markup ({tracked_changes} marker(s)).",
            suggestion="Accept or reject changes before release unless revision markup is intentional.",
        )

    review.inventory.update(
        {
            "styles": sorted(style["name"] for style in styles.values()),
            "style_count": len(styles),
            "template_parts": sorted(sources),
            "field_instructions": field_instructions,
            "external_fields": external_fields,
            "bookmark_count": len(bookmarks),
            "missing_bookmark_targets": missing_references,
            "update_fields_on_open": update_fields,
            "tracked_change_markers": tracked_changes,
            "has_toc_field": any(
                re.match(r"\s*TOC\b", field["instruction"], re.IGNORECASE)
                for field in field_instructions
            ),
        }
    )


def ordered_pptx_layouts(archive: ZipFile) -> list[str]:
    master_name = "ppt/slideMasters/slideMaster1.xml"
    rels_name = "ppt/slideMasters/_rels/slideMaster1.xml.rels"
    if master_name not in archive.namelist() or rels_name not in archive.namelist():
        return []
    master = ET.fromstring(archive.read(master_name))
    rels = ET.fromstring(archive.read(rels_name))
    targets = {
        rel.attrib.get("Id", ""): resolve_relationship_target(
            rels_name, rel.attrib.get("Target", "")
        )
        for rel in rels
    }
    return [
        targets.get(layout.attrib.get(R + "id", ""), "")
        for layout in master.iter(P + "sldLayoutId")
        if targets.get(layout.attrib.get(R + "id", ""), "")
    ]


def pptx_placeholder_types(archive: ZipFile, name: str) -> set[str]:
    try:
        root = ET.fromstring(archive.read(name))
    except (KeyError, ET.ParseError):
        return set()
    return {
        placeholder.attrib.get("type", "obj")
        for placeholder in root.iter(P + "ph")
    }


def analyze_pptx(review: Review, archive: ZipFile) -> None:
    names = set(archive.namelist())
    main_type = content_type_for(archive, "ppt/presentation.xml")
    if "ppt/presentation.xml" not in names or main_type != PPTX_MAIN_CONTENT_TYPE:
        review.add(
            "error",
            "ghostwriter-parity",
            "GW-DOC-TYPE-MISMATCH",
            "File does not contain a standard PPTX presentation matching the selected document type.",
            "[Content_Types].xml",
        )
        return

    presentation = parse_xml(review, archive, "ppt/presentation.xml")
    if presentation is None:
        review.add(
            "error",
            "ghostwriter-parity",
            "GW-PPTX-OPEN",
            "Ghostwriter would not be able to open this file as a PowerPoint template.",
        )
        return

    slides = sorted(
        name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
    )
    if slides:
        review.add(
            "warning",
            "ghostwriter-parity",
            "GW-PPTX-NOT-EMPTY",
            f"PowerPoint template contains {len(slides)} slide(s); Ghostwriter expects zero.",
            suggestion="Move design content to Slide Master layouts and remove ordinary slides.",
        )

    layouts = ordered_pptx_layouts(archive)
    if not layouts:
        layouts = sorted(
            name
            for name in names
            if re.fullmatch(r"ppt/slideLayouts/slideLayout\d+\.xml", name)
        )
    if len(layouts) < 3:
        review.add(
            "warning",
            "compatibility",
            "PPTX-LAYOUT-COUNT",
            f"Template has {len(layouts)} slide layout(s); Ghostwriter documentation recommends at least three.",
            suggestion="Provide title, content, and final/conclusion layouts.",
        )

    layout_placeholders = {
        layout: sorted(pptx_placeholder_types(archive, layout)) for layout in layouts
    }
    if layouts:
        first_types = set(layout_placeholders[layouts[0]])
        if not ({"title", "ctrTitle"} & first_types):
            review.add(
                "warning",
                "compatibility",
                "PPTX-TITLE-LAYOUT-PLACEHOLDER",
                "First slide layout lacks a title placeholder.",
                layouts[0],
            )
    if len(layouts) >= 2:
        second_types = set(layout_placeholders[layouts[1]])
        if not ({"obj", "body"} & second_types):
            review.add(
                "warning",
                "compatibility",
                "PPTX-CONTENT-LAYOUT-PLACEHOLDER",
                "Second slide layout lacks a content/body placeholder.",
                layouts[1],
            )

    review.inventory.update(
        {
            "slide_count": len(slides),
            "slide_layout_count": len(layouts),
            "slide_layout_order": layouts,
            "layout_placeholder_types": layout_placeholders,
        }
    )
    review.analysis["ghostwriter_render"] = {
        "performed": False,
        "reason": "Ghostwriter's current PPTX linter does not perform a representative render.",
    }


def render_markdown(result: dict[str, object]) -> str:
    template = result["template"]
    lines = [
        "# Ghostwriter Template Review",
        "",
        f"- Template: `{template['path']}`",
        f"- Document type: `{template['document_type']}`",
        f"- SHA-256: `{template['sha256']}`",
        f"- Overall status: **{str(result['overall_status']).upper()}**",
        f"- Ghostwriter-parity status: **{str(result['ghostwriter_parity']['status']).upper()}**",
        f"- Compatibility status: **{str(result['compatibility']['status']).upper()}**",
        "",
    ]
    for title, section in (
        ("Ghostwriter-parity findings", result["ghostwriter_parity"]),
        ("Additional compatibility and authoring findings", result["compatibility"]),
    ):
        lines.extend([f"## {title}", ""])
        issues = section["issues"]
        if not issues:
            lines.extend(["No issues found.", ""])
            continue
        for issue in issues:
            location = f" — `{issue['location']}`" if issue.get("location") else ""
            lines.append(
                f"- **{issue['severity'].upper()} · {issue['code']}**: {issue['message']}{location}"
            )
            if issue.get("suggestion"):
                lines.append(f"  - Suggested action: {issue['suggestion']}")
        lines.append("")
    lines.extend(
        [
            "## Offline limitation",
            "",
            "This pass may perform a local docxtpl structural render, but it does not reproduce Ghostwriter's full rich-text/evidence pipeline or validate instance-specific extra fields. Use the target Ghostwriter version as final authority when exact linting is available.",
            "",
        ]
    )
    return "\n".join(lines)


def infer_document_type(path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return "docx"
    if suffix == ".pptx":
        return "pptx"
    return "unknown"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline Ghostwriter DOCX/PPTX template lint and compatibility review."
    )
    parser.add_argument("template", type=Path)
    parser.add_argument(
        "--document-type",
        choices=("auto", "docx", "project_docx", "pptx"),
        default="auto",
    )
    parser.add_argument("--default-paragraph-style")
    parser.add_argument(
        "--ghostwriter-root",
        type=Path,
        help="Optional Ghostwriter checkout used to discover current context keys and filters.",
    )
    parser.add_argument(
        "--context-json",
        type=Path,
        help="Optional exported Ghostwriter JSON whose top-level keys define known variables.",
    )
    parser.add_argument(
        "--extra-field-spec-endpoint",
        help=(
            "Optional Ghostwriter GraphQL endpoint used for a read-only "
            "getExtraFieldSpec query."
        ),
    )
    parser.add_argument(
        "--extra-field-spec-token-env",
        default="GHOSTWRITER_EXTRA_FIELD_SPEC_TOKEN",
        help=(
            "Environment-variable name containing the bearer token for the "
            "extra-field endpoint (default: GHOSTWRITER_EXTRA_FIELD_SPEC_TOKEN)."
        ),
    )
    parser.add_argument(
        "--extra-field-spec-model",
        action="append",
        dest="extra_field_spec_models",
        metavar="MODEL",
        help=(
            "Ghostwriter model to query for extra fields; repeat as needed. "
            "Defaults to the applicable report/project models."
        ),
    )
    parser.add_argument(
        "--extra-field-spec-timeout",
        type=float,
        default=15.0,
        metavar="SECONDS",
        help="Remote extra-field metadata request timeout (default: 15).",
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning", "never"),
        default="error",
        help="Exit nonzero for the selected threshold (default: error).",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    document_type = infer_document_type(args.template, args.document_type)
    review = Review(args.template, document_type)

    if args.extra_field_spec_timeout <= 0:
        print("--extra-field-spec-timeout must be greater than zero", file=sys.stderr)
        return 2

    if not args.template.is_file():
        review.add(
            "error",
            "ghostwriter-parity",
            "GW-FILE-MISSING",
            "Template file does not exist.",
            str(args.template),
        )
    elif document_type == "unknown":
        review.add(
            "error",
            "ghostwriter-parity",
            "GW-DOC-TYPE-UNKNOWN",
            "Document type could not be inferred; select docx, project_docx, or pptx.",
        )
    else:
        context, context_source, context_data = discover_ghostwriter_context(
            args.ghostwriter_root, document_type
        )
        explicit_context, explicit_source, explicit_data = load_context_json(
            args.context_json
        )
        if explicit_context is not None:
            context = explicit_context
            context_source = explicit_source or context_source
            context_data = explicit_data
        filters, filter_source = discover_ghostwriter_filters(args.ghostwriter_root)
        review.analysis["target_discovery"] = {
            "context_source": context_source,
            "filter_source": filter_source,
            "known_top_level_context": sorted(context),
            "known_ghostwriter_filters": sorted(filters),
        }
        extra_field_specs = load_remote_extra_field_specs(
            review,
            args.extra_field_spec_endpoint,
            args.extra_field_spec_token_env,
            args.extra_field_spec_models or default_extra_field_models(document_type),
            args.extra_field_spec_timeout,
        )
        try:
            with ZipFile(args.template) as archive:
                bad_member = archive.testzip()
                if bad_member:
                    review.add(
                        "error",
                        "package",
                        "PKG-CRC-FAILED",
                        f"ZIP integrity check failed for package member: {bad_member}",
                    )
                audit_relationships(review, archive)
                if document_type in {"docx", "project_docx"}:
                    analyze_docx(
                        review,
                        archive,
                        args.default_paragraph_style,
                        context,
                        filters,
                        context_data,
                        extra_field_specs,
                    )
                else:
                    analyze_pptx(review, archive)
        except BadZipFile:
            review.add(
                "error",
                "ghostwriter-parity",
                "GW-PACKAGE-INVALID",
                "File is not a readable Office Open XML package.",
            )

    result = review.result()
    if args.format == "markdown":
        print(render_markdown(result))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))

    severities = {issue["severity"] for issue in result["ghostwriter_parity"]["issues"]}
    severities.update(issue["severity"] for issue in result["compatibility"]["issues"])
    if args.fail_on == "error" and "error" in severities:
        return 1
    if args.fail_on == "warning" and ({"error", "warning"} & severities):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
