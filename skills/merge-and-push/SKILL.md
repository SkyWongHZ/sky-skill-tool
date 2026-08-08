---
name: merge-and-push
description: Commit the current feature or hotfix changes, merge the exact commit with --no-ff into a configured test or production branch, push only that target branch, enforce test-before-production, and clean up the source branch after production. Use when the user asks to commit/merge/push, submit for testing, merge into a test or development environment, release or go live, push to production, finish or close out a feature branch, says "提交合并推送", "帮我提测", "发测试", "上线", "发生产", "收尾分支", or explicitly invokes $merge-and-push.
---

# Merge and Push

Carry one feature or hotfix branch through either the test or production integration boundary. Treat an explicit environment choice as authorization to commit, merge, and push that target. Ask only when the environment, branch mapping, or commit scope is ambiguous.

## Hard rules

- Operate only from a named feature or hotfix branch. Stop on detached HEAD or when the source is the configured test or production branch.
- Push only the selected target branch. Do not push the source branch.
- Never force-push, rebase, reset, auto-stash, amend, skip hooks, use `git add .`/`git add -A`, or auto-resolve/abort a merge conflict.
- Never include unrelated changes. Stage explicit task paths only; ask once when scope is mixed or uncertain.
- Use `git merge --no-ff` and merge the recorded source SHA, not a ref that could move during the workflow.
- Preserve every conflict or failed push for inspection. Report the exact worktree and state; do not clean it up.
- Run lint, build, or test commands only when an applicable `AGENTS.md` explicitly requires them.
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

Canonical project configuration:

```markdown
## Merge and Push

- Test branch: develop
- Production branch: main
- Remote: origin
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

6. Fetch the remote target and require its SHA to equal the merged target `HEAD`. A rejected or unverifiable push is a failure; preserve the target worktree.
7. After a verified test push, check out the recorded source branch again when the source worktree was reused. After a verified production push, keep that worktree on production so the source branch can be deleted safely. Never remove a user-owned target worktree.

If the source SHA was already contained in the target, treat the merge and push as an idempotent no-op and do not create an empty commit.

## Finish by environment

### Test

- Keep the source branch and source worktree intact for acceptance fixes.
- Report the source commit, target branch, merge commit or no-op status, remote target SHA, and any explicitly required checks.

### Production

1. Fetch production and verify `source_sha` is an ancestor of remote production.
2. If a same-named remote source branch exists, fetch its tip and require that tip to be an ancestor of remote production before deleting it.
3. Delete the remote source branch with `git push "$remote" --delete "$source_branch"` only when the containment check passes.
4. When the source worktree was reused for production, it is already on the production branch; delete the local source branch with `git branch -d`.
5. When production ran in another existing worktree, remove a clean linked source worktree without force only if the installed Git supports `git worktree remove`, then delete the local source branch with `git branch -d`. If the source worktree cannot be removed safely, preserve it and report partial cleanup.
6. If a safe cleanup step is blocked, keep the remaining branch/worktree and report partial cleanup. Never undo a successful production push.
7. Report source and target SHAs, production verification, deleted or preserved refs, and any cleanup blocker.
