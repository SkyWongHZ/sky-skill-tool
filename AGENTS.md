# Repository instructions

- Treat this repository as the source of truth for personal skills. Put each skill in `skills/<skill-name>/` and install it with `scripts/link-skills.mjs`; do not maintain copied runtime versions.
- Preserve unrelated or untracked skills. Do not edit an existing skill unless the user places it in scope.
- Use the `skill-creator` workflow for new or substantially revised skills. Keep `SKILL.md` frontmatter limited to `name` and `description`, keep the body concise, and generate `agents/openai.yaml` for UI metadata.
- Put deterministic per-skill helpers in that skill's `scripts/` directory. Keep repository-wide installation or validation utilities in the root `scripts/` directory.
- Validate changed skills with `quick_validate.py` and test scripts against disposable fixtures before reporting completion.
- Never commit or push repository changes unless the user explicitly authorizes that publication step.
