# sky-skill-tool

个人 Agent Skill 集合，用 monorepo 统一管理 Codex、Claude Code 等工具使用的 skill。

## Skills

| Skill | 类型 | 说明 |
|---|---|---|
| [weekly-report](./skills/weekly-report/SKILL.md) | 纯 prompt | 读取原始日报，合并同类项，生成格式化周报 md 文件 |
| [merge-and-push](./skills/merge-and-push/SKILL.md) | 工作流 + Python | 测试自动触发流水线；生产按权限直接推送或创建 GitLab MR、人工打包 |

## 安装使用

### 方式一：源码仓库 + 全局软链接（推荐）

将仓库克隆到稳定的开发目录：

```bash
git clone https://github.com/SkyWongHZ/sky-skill-tool.git
cd sky-skill-tool
```

按需链接到 Codex/Agents 的全局 Skill 目录：

```bash
npm run install:skills -- weekly-report merge-and-push
```

默认目标是 `~/.agents/skills`。如需安装到其他 Agent 的 Skill 根目录，可设置：

```bash
AGENTS_SKILLS_DIR="$HOME/.claude/skills" npm run install:skills -- weekly-report
```

安装器只创建软链接；遇到同名普通目录或指向其他位置的链接会拒绝覆盖。以后直接修改或 `git pull` 本仓库，已安装 Skill 会同步生效。

### 方式二：项目内按需复制

只把需要的 skill 目录复制到具体项目的 `skills/` 下：

```bash
cp -r path/to/sky-skill-tool/skills/weekly-report your-project/skills/
```

## 目录结构

```
sky-skill-tool/
├── skills/                   # 所有 skill
│   ├── weekly-report/        # 纯 prompt skill 示例
│   │   └── SKILL.md
│   └── merge-and-push/       # 工作流 Skill
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       └── scripts/
│           ├── inspect_repo.py
│           └── trigger_test_pipeline.py
├── packages/                 # 跨 skill 共享的工具库
├── scripts/                  # 安装、发布等仓库级自动化
├── AGENTS.md                 # Agent 项目指令
└── CLAUDE.md                 # Claude Code 项目指令
```

## 新增 Skill

### 纯 prompt 类

只需一个 `SKILL.md`：

```bash
mkdir skills/my-skill
```

然后创建 `skills/my-skill/SKILL.md`，格式：

```markdown
---
name: my-skill
description: "这个 skill 做什么。Use when user asks 'xxx'."
---

# My Skill

## 执行步骤
...
```

### 含脚本类

在 skill 目录下加 `scripts/` 子目录：

```bash
mkdir -p skills/my-skill/scripts
```

```
skills/my-skill/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── scripts/
    └── main.ts       # 或 main.py / main.go
```

## Skill 规范

- 目录名：英文小写 + 连字符，如 `weekly-report`
- 描述文件：统一命名 `SKILL.md`
- SKILL.md frontmatter 只放 `name` 和 `description`
- frontmatter 的 `name` 用英文（和目录名一致），`description` 末尾加触发词
- Codex UI 元数据放在 `agents/openai.yaml`
- SKILL.md 保持精简，内容过多时拆到 `references/` 子目录按需加载
