# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

* Added the initial portable Ghostwriter Agent Skills collection
  * `create-template` converts sample Word reports into Ghostwriter Jinja2 DOCX templates
  * `draft-executive-summary` drafts a traceable executive summary from one Ghostwriter report
  * `report-readiness` grades a report or linked finding for final-reporting readiness
  * `review-template` checks DOCX and PPTX templates for Ghostwriter compatibility and broader authoring risks
* Added offline analysis paths for template review, template conversion, report readiness, and report-summary drafting from complete local exports
* Added connected GraphQL workflows using the public `/v1/graphql` endpoint and scoped project-read service tokens
