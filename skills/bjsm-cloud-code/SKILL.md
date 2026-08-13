---
name: bjsm-cloud-code
description: Guide requirement analysis, backend development, code fixes, and feature-branch review for the bjsm-cloud Spring Boot monorepo. Use automatically only when a task targets bjsm-cloud and asks to discuss or implement a backend requirement, inspect affected modules, review Git changes or commits, or address adopted review findings; also use when the user explicitly invokes $bjsm-cloud-code. Do not apply it to unrelated Java repositories or frontend-only work.
---

# BJSM Cloud Code

Guide `bjsm-cloud` backend work from scope discovery through implementation or review. Keep discussion, development, review, and delivery as separate states so that analysis does not silently become code modification.

## Establish context

1. Confirm that the target repository is `bjsm-cloud`. If the request spans repositories, apply this workflow only to its backend portion.
2. Read the repository's applicable `AGENTS.md`, requirement source, and relevant existing documentation completely. Treat `AGENTS.md` as authoritative for project rules not restated here.
3. Inspect the current branch, worktree, production baseline, and user-owned changes before taking action. Preserve unrelated or untracked work.
4. Classify the request:
   - Discussion or analysis: inspect and explain only; do not modify code.
   - Development or fix: require explicit authorization to implement, modify, or fix code.
   - Review: remain read-only until the user explicitly adopts findings or requests fixes.
   - Delivery: hand off commit, merge, push, pipeline, and branch cleanup work to `$merge-and-push`.

## Develop a feature

### Research before coding

1. Inspect analogous implementations in the same business module, their callers, and the established package structure before proposing changes.
2. Prefer CodeGraph for Java symbols and call chains when the repository provides it; use `rg` for configuration, XML, SQL, and literal text.
3. State the expected modification scope before coding. Include only actually affected backend modules and any verified impact on the management frontend, H5, database, or configuration.
4. Wait for scope confirmation unless the user already confirmed the same scope in the current conversation. Do not treat requirement discussion or document writing as implementation authorization.

### Keep the implementation local and consistent

- Search for an existing method or component before adding one. When reusing it, verify normal behavior, exception behavior, side effects, and existing callers; add a new implementation only when the existing contract is insufficient.
- Before changing a shared utility, common module, global `application-*.properties`, database structure, or cross-module interface, explain why a business-local solution is insufficient and identify affected consumers.
- Do not add feature-specific hospital IDs as standalone custom entries in `application-*.properties`. Keep institution-specific behavior inside the corresponding business module unless an authoritative requirement establishes a different shared configuration model.
- Follow the target module's existing FORM, Controller, Service, DAO, and Mapper structure:
  - Keep HTTP request boundaries in FORM and Controller.
  - Keep business rules in Service.
  - Keep data access in DAO and Mapper.
  - Do not turn a one-off helper such as a Matcher into a standard architecture layer.
- Add an auxiliary component only when it has a single clear responsibility, justified reuse across real callers, and a package location consistent with neighboring code.
- Avoid unrelated refactors, generalized abstractions, and speculative cross-project changes.

### Verify the result

Run the smallest sufficient verification for the actual change, following `AGENTS.md`. Reinspect the complete diff and report checks not run, environmental failures, and remaining risks honestly.

## Review a feature branch

### Establish the review diff

1. Review without modifying files unless the user explicitly asks to fix adopted findings.
2. Use the merge base with `origin/master` as the default production baseline. Inspect the final diff first, then the commit overview:

   ```bash
   base=$(git merge-base origin/master HEAD)
   git log --oneline "$base"..HEAD
   git diff --stat "$base"...HEAD
   git diff --name-status "$base"...HEAD
   git diff "$base"...HEAD
   git diff --check "$base"...HEAD
   git diff -w --name-only "$base"...HEAD
   ```

3. Inspect individual commits only when the overview shows scope drift, suspicious intermediate changes, or the user asks for commit-by-commit review.
4. If the production branch or remote is different in repository instructions, use that authoritative baseline instead of `origin/master`.

### Check the change

- Check business correctness and requirement boundaries before style preferences.
- For every added file, identify its responsibility, existing alternative, package placement, and real callers. Do not optimize for fewer files; require a defensible purpose.
- Inspect shared utilities, common modules, global properties, database changes, and cross-module interfaces as high-impact changes. Verify necessity and affected consumers.
- Detect unrelated files, generated noise, broad formatting, and whitespace-only changes; require them to be removed from the feature diff.
- Apply the security, permission, encryption, amount, MyBatis, SQL, and verification rules from `AGENTS.md` without duplicating them here.
- When requirement or acceptance documents exist, compare their declared files, class names, configuration, test evidence, and behavior with the final code. Skip this check when no such documents exist.

### Report findings

List actionable findings first, ordered by severity. Give each finding a precise code location, evidence, impact, and recommended direction. Classify it as one of:

- **Current feature issue**: introduced or expanded by the feature branch; address in this feature.
- **Historical issue**: already present in the production baseline and not expanded; report it but do not modify it by default.
- **Historical issue touched by this feature**: pre-existing, but directly depended on or worsened by the feature; explain whether it blocks delivery.
- **Optional improvement**: does not affect current correctness; do not block delivery on it.

When no actionable findings remain, say so explicitly and state residual verification gaps. Do not silently change code after reporting findings; wait for the user to adopt them.

## Evolve this skill

At the end of relevant work, propose reusable rule candidates only when evidence suggests the issue can recur. For each candidate, state the evidence, intended scope, and possible conflict with existing rules. Do not edit this skill automatically; update it only after the user explicitly adopts the candidate.

Do not store requirement-specific IDs, class names, or one-off implementation details in this skill.
