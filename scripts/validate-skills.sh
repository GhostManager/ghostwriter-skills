#!/usr/bin/env bash

set -euo pipefail

found=0
skill_files=()
while IFS= read -r -d '' skill_file; do
    skill_files+=("${skill_file}")
done < <(find skills -mindepth 2 -maxdepth 2 -type f -name SKILL.md -print0 | sort -z)

if [[ "${#skill_files[@]}" -eq 0 ]]; then
    echo "No skills found; scaffold validation complete."
    exit 0
fi

if ! command -v skills-ref >/dev/null 2>&1; then
    echo "skills-ref is required. Install it from https://github.com/agentskills/agentskills/tree/main/skills-ref" >&2
    exit 1
fi

for skill_file in "${skill_files[@]}"; do
    skill_dir="${skill_file%/SKILL.md}"
    echo "Validating ${skill_dir}"
    skills-ref validate "${skill_dir}"
done
