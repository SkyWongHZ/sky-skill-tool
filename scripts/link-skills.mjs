#!/usr/bin/env node

import { lstat, mkdir, readdir, readlink, realpath, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "..");
const skillsRoot = path.join(repositoryRoot, "skills");

function usage() {
  return [
    "Usage: node scripts/link-skills.mjs <skill...>",
    "       node scripts/link-skills.mjs --all",
    "",
    "Environment:",
    "  AGENTS_SKILLS_DIR  Installation root (default: ~/.agents/skills)",
  ].join("\n");
}

async function pathState(target) {
  try {
    const stat = await lstat(target);
    if (!stat.isSymbolicLink()) {
      return { kind: "existing" };
    }
    const linkValue = await readlink(target);
    const resolved = path.resolve(path.dirname(target), linkValue);
    let canonical = resolved;
    try {
      canonical = await realpath(resolved);
    } catch {
      // Preserve a broken link target for a useful collision error.
    }
    return { kind: "symlink", canonical };
  } catch (error) {
    if (error?.code === "ENOENT") {
      return { kind: "missing" };
    }
    throw error;
  }
}

async function discoverAllSkills() {
  const entries = await readdir(skillsRoot, { withFileTypes: true });
  const names = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const marker = path.join(skillsRoot, entry.name, "SKILL.md");
    if ((await pathState(marker)).kind === "existing") names.push(entry.name);
  }
  return names.sort();
}

async function main() {
  const args = process.argv.slice(2);
  if (args.includes("--help") || args.includes("-h")) {
    console.log(usage());
    return;
  }

  const useAll = args.includes("--all");
  const positional = args.filter((value) => !value.startsWith("-"));
  if ((useAll && positional.length) || (!useAll && positional.length === 0)) {
    throw new Error(usage());
  }

  const requested = useAll ? await discoverAllSkills() : [...new Set(positional)];
  const installRoot = path.resolve(
    process.env.AGENTS_SKILLS_DIR || path.join(os.homedir(), ".agents", "skills"),
  );
  const plan = [];

  for (const name of requested) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name)) {
      throw new Error(`Invalid skill name: ${name}`);
    }
    const source = path.join(skillsRoot, name);
    const marker = path.join(source, "SKILL.md");
    if ((await pathState(marker)).kind !== "existing") {
      throw new Error(`Skill does not exist or lacks SKILL.md: ${name}`);
    }
    const canonicalSource = await realpath(source);
    const target = path.join(installRoot, name);
    const state = await pathState(target);
    if (state.kind === "existing") {
      throw new Error(`Refusing to replace existing non-symlink path: ${target}`);
    }
    if (state.kind === "symlink" && state.canonical !== canonicalSource) {
      throw new Error(`Refusing to replace symlink with a different target: ${target}`);
    }
    plan.push({ name, source: canonicalSource, target, state: state.kind });
  }

  await mkdir(installRoot, { recursive: true });
  for (const item of plan) {
    if (item.state === "symlink") {
      console.log(`ok  ${item.name} -> ${item.source}`);
      continue;
    }
    await symlink(item.source, item.target, process.platform === "win32" ? "junction" : "dir");
    console.log(`add ${item.name} -> ${item.source}`);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
