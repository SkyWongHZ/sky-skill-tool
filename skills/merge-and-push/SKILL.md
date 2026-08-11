---
name: merge-and-push
description: Commit the current feature or hotfix changes, merge the exact commit with --no-ff into a configured test or production branch, push only that target branch, automatically trigger a safe webhook:dev after verified test pushes, keep production pipeline execution manual, enforce test-before-production, and clean up the source branch after production. Use when the user asks to commit/merge/push, submit for testing, rebuild or redeploy the same test version, release or go live, push to production, finish a feature branch, says "提交合并推送", "帮我提测", "发测试", "重新打包", "重新触发测试流水线", "上线", "发生产", "收尾分支", or explicitly invokes $merge-and-push.
---

# Merge and Push

Carry one feature or hotfix branch through either the test or production integration boundary. Treat an explicit environment choice as authorization to commit, merge, and push that target. A test release also authorizes the configured safe test-pipeline trigger; production pipeline execution stays manual. Ask only when the environment, branch mapping, pipeline directory, or commit scope is ambiguous.

## Hard rules

- Operate only from a named feature or hotfix branch. Stop on detached HEAD or when the source is the configured test or production branch.
- Push only the selected target branch. Do not push the source branch.
- Never force-push, rebase, reset, auto-stash, amend, skip hooks, use `git add .`/`git add -A`, or auto-resolve/abort a merge conflict.
- Never include unrelated changes. Stage explicit task paths only; ask once when scope is mixed or uncertain.
- Use `git merge --no-ff` and merge the recorded source SHA, not a ref that could move during the workflow.
- Preserve every conflict or failed push for inspection. Report the exact worktree and state; do not clean it up.
- Run lint, build, or test commands only when an applicable `AGENTS.md` explicitly requires them.
- Automatically trigger only the tracked `webhook:dev` test pipeline. Never invoke `webhook:prod` in the default workflow, never retry a webhook automatically, and never print its URL.
- Before production, require the exact source SHA to be an ancestor of the fetched remote test branch.
- Delete a source branch only after the production push is verified and both local and remote source tips are contained in remote production. Never use forced deletion.
- Validate branch names with `git check-ref-format --branch` and quote every dynamic shell argument.

## Resolve intent and configuration

1. Resolve the environment from explicit wording:
   - Test: test, testing, development, dev, staging, UAT, 提测, 测试, 开发环境, 验收.
   - Production: production, prod, release, go live, 上线, 生产, 正式发布.
2. If the environment is still ambiguous, ask exactly one question: test or production? Include the configured branch names when known.
3. Resolve `test branch`, `production branch`, and `remote` in this order:
   1. Values explicitly supplied for this request.
   2. The closest applicable `AGENTS.md` section named `Merge and Push`. Accept `Test branch` or `Development branch` for the test boundary, plus `Production branch` and `Remote`.
   3. Local Git config keys `merge-and-push.testBranch`, `merge-and-push.productionBranch`, and `merge-and-push.remote`.
   4. Ask the user to map existing branches. Persist the confirmed values with `git config --local`; these values stay in `.git/config` and are not committed.
4. Default the remote to `origin` only when that remote exists. Never invent a target branch.
5. Resolve the optional test pipeline directory in this order:
   1. A directory explicitly supplied for this request.
   2. `Test pipeline directory` in the closest applicable `AGENTS.md` section named `Merge and Push`.
   3. Local Git config key `merge-and-push.testPipelineCwd`.
   4. Automatic discovery when exactly one tracked `package.json` defines `webhook:dev`.
   5. If multiple candidates remain, ask once and persist the repository-relative directory with `git config --local merge-and-push.testPipelineCwd <directory>`.

Canonical project configuration:

```markdown
## Merge and Push

- Test branch: develop
- Production branch: main
- Remote: origin
- Test pipeline directory: .
```

## Inspect repository state

Set `SKILL_DIR` to the directory containing this file. Fetch the selected remote, then use the bundled read-only inspector:

```bash
git fetch "$remote"
python3 "$SKILL_DIR/scripts/inspect_repo.py" \
  --repo "$PWD" \
  --environment "$environment" \
  --test-branch "$test_branch" \
  --production-branch "$production_branch" \
  --remote "$remote" \
  --pretty
```

Exit code `2` means the JSON contains safety blockers. Stop and report them. Remote-tracking refs are snapshots, so always fetch immediately before relying on ancestry or ahead/behind data.

Before changing state, announce the resolved source branch, environment, target branch, remote, dirty paths, and whether a target worktree already exists.

## Commit the source

1. Inspect `git status`, the complete diff, and untracked files. Match them to the current task and conversation.
2. If all dirty paths clearly belong to the task, stage only those explicit paths with `git add -- <paths>`. If any path may be unrelated, show the paths and ask the user to choose; do not continue until scope is clear.
3. Review `git diff --cached` before committing. Stop on secrets, generated noise, or unrelated edits.
4. Run only checks explicitly required by applicable `AGENTS.md`. Stop on failure.
5. If the index is non-empty, create a concise commit that follows repository instructions and recent history. Never bypass hooks. If there is nothing to commit, continue with the existing tip.
6. Record `source_branch` and `source_sha=$(git rev-parse HEAD)`. Re-run the inspector after the commit.

## Prepare the target worktree

1. Require the remote target branch to exist.
2. If the target branch is checked out in an existing worktree, require that worktree to be clean and fast-forward it to the fetched remote target with `git merge --ff-only`.
3. Otherwise, require the committed source worktree to be clean and any local target ref to be equal to or behind the remote target. Stop when the target is ahead or diverged.
4. Reuse the clean source worktree for integration: check out the existing local target and fast-forward it to the remote target, or create it from the remote target with `git checkout -b "$target_branch" --track "$remote/$target_branch"`. Record that this worktree must return to the source branch after a successful test push.
5. Use `git checkout`, not `git switch`, for compatibility with older Git versions. Never switch a dirty worktree.

For production, run the gate immediately before merging:

```bash
git merge-base --is-ancestor "$source_sha" "refs/remotes/$remote/$test_branch"
```

Stop and require another test integration when the gate fails. Do not offer a production override.

## Merge and push

1. Record the target SHA before merging.
2. Merge the recorded source SHA in the clean target worktree:

   ```bash
   git merge --no-ff "$source_sha" -m "Merge branch '$source_branch' into '$target_branch'"
   ```

3. If Git reports conflicts, leave the merge and worktree intact. Report the worktree path and conflict files. Do not push or run `git merge --abort`.
4. Run only post-merge checks explicitly required by applicable `AGENTS.md`. On failure, leave the merge commit and worktree intact; do not push.
5. Push the exact target ref without force:

   ```bash
   git push "$remote" "HEAD:refs/heads/$target_branch"
   ```

6. Fetch the remote target and require its SHA to equal the merged target `HEAD`. A rejected or unverifiable push is a failure; preserve the target worktree and never trigger a pipeline.
7. For test, run the pipeline stage below while the target worktree is still on the verified target SHA, then check out the recorded source branch again when the source worktree was reused. Return to the source branch even when the pipeline stage fails because the Git push is already complete.
8. After a verified production push, keep that worktree on production so the source branch can be deleted safely. Never remove a user-owned target worktree.

If the source SHA was already contained in the target, treat the merge and push as an idempotent no-op and do not create an empty commit.

## Trigger the test pipeline

Set `SKILL_DIR` to the directory containing this file. Trigger only after fetching the test target and proving its SHA equals the merged target SHA.

For a new test merge, pass the target SHA recorded before the merge as `trusted_sha` and the verified remote test SHA as `target_sha`. If a pipeline directory was resolved explicitly or from `AGENTS.md`, pass it with `--package-dir`; otherwise let the helper use local Git config or unique discovery:

```bash
python3 "$SKILL_DIR/scripts/trigger_test_pipeline.py" \
  --repo "$PWD" \
  --trusted-sha "$trusted_sha" \
  --target-sha "$target_sha" \
  --remote "$remote" \
  --test-branch "$test_branch" \
  --pretty
```

- Before sending, the helper fetches the named remote test branch itself and requires its fetched SHA to equal `target_sha`. It then reads tracked `package.json` content from the two commits, requires the `webhook:dev` command to be unchanged, accepts only one HTTPS `curl POST`, preserves its header/data arguments, and accepts only an HTTP 2xx response. It upgrades legacy `http://flow-openapi.aliyun.com` endpoints to HTTPS before sending and rejects every other plain-HTTP endpoint.
- Exit `0` means the trigger request was accepted, not that the build or deployment completed. Exit `2` is unavailable or unsafe configuration, exit `3` is a request failure, and exit `1` is an internal failure.
- If exit `2` reports multiple candidates, ask once, persist the selected directory locally, and retry once. For missing, placeholder, modified, or unsafe scripts, do not trigger and do not ask for a production webhook fallback.
- Never display the command or webhook URL. Never retry an HTTP, network, or timeout failure because the endpoint may have accepted the first request.
- A pipeline failure never rolls back or hides the successful Git push. Return to the feature branch, keep it, and report `Git push succeeded; test pipeline was not confirmed` with the helper's redacted reason.
- When the source SHA was already in the remote test branch, do not trigger again during an ordinary repeated test request. If the user explicitly asks to rebuild or retrigger the same test version, first verify the source SHA is still contained in the fetched remote test branch, then call the helper with that remote test SHA as both `trusted_sha` and `target_sha`.

## Finish by environment

### Test

- Keep the source branch and source worktree intact for acceptance fixes.
- Report the source commit, target branch, merge commit or no-op status, remote target SHA, pipeline status (`trigger accepted`, `not triggered`, or `trigger failed`), and any explicitly required checks.

### Production

1. Fetch production and verify `source_sha` is an ancestor of remote production.
2. If a same-named remote source branch exists, fetch its tip and require that tip to be an ancestor of remote production before deleting it.
3. Delete the remote source branch with `git push "$remote" --delete "$source_branch"` only when the containment check passes.
4. When the source worktree was reused for production, it is already on the production branch; delete the local source branch with `git branch -d`.
5. When production ran in another existing worktree, remove a clean linked source worktree without force only if the installed Git supports `git worktree remove`, then delete the local source branch with `git branch -d`. If the source worktree cannot be removed safely, preserve it and report partial cleanup.
6. If a safe cleanup step is blocked, keep the remaining branch/worktree and report partial cleanup. Never undo a successful production push.
7. Never run `webhook:prod`. Report source and target SHAs, production verification, deleted or preserved refs, any cleanup blocker, and the explicit handoff: `Production code was pushed; run the production pipeline manually in Aliyun Flow.`
