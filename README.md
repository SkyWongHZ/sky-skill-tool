# sky-skill-tool

个人 Claude Code Skill 集合，用 monorepo 统一管理各类工具 skill。

## Skills

| Skill | 类型 | 说明 |
|---|---|---|
| [weekly-report](./skills/weekly-report/SKILL.md) | 纯 prompt | 读取原始日报，合并同类项，生成格式化周报 md 文件 |

## 安装使用

### 方式一：全局安装（推荐）

将仓库克隆到 Claude Code 的 skill 目录，所有项目都能直接调用：

```bash
git clone git@github.com:SkyWongHZ/sky-skill-tool.git ~/.claude/skills
```

之后在任意项目里对 Claude 说 "帮我整理周报" 就会自动触发对应 skill。

### 方式二：按需复制

只把需要的 skill 目录复制到具体项目的 `skills/` 下：

```bash
cp -r path/to/sky-skill-tool/skills/weekly-report your-project/skills/
```

## 目录结构

```
sky-skill-tool/
├── skills/                   # 所有 skill
│   └── weekly-report/        # 纯 prompt skill 示例
│       └── SKILL.md
├── packages/                 # 跨 skill 共享的工具库
├── scripts/                  # 仓库级自动化脚本
├── docs/                     # 文档
│   └── skill-repo-guide.md   # 仓库搭建指南
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
version: "1.0.0"
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
└── scripts/
    └── main.ts       # 或 main.py / main.go
```

## Skill 规范

- 目录名：英文小写 + 连字符，如 `weekly-report`
- 描述文件：统一命名 `SKILL.md`
- frontmatter 的 `name` 用英文（和目录名一致），`description` 末尾加触发词
- SKILL.md 保持精简，内容过多时拆到 `references/` 子目录按需加载

详细规范见 [docs/skill-repo-guide.md](./docs/skill-repo-guide.md)。
