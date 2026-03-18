# sky-skill-tool

个人工具与 Claude Code Skill 集合。

## 仓库结构

```
sky-skill-tool/
├── skills/          # 所有 skill，按功能命名（英文）
│   └── weekly-report/
│       └── SKILL.md
├── packages/        # 跨 skill 共享的工具库（npm workspace）
├── scripts/         # 发布、同步等自动化脚本
└── docs/            # 文档
```

## Skill 规范

每个 skill 放在 `skills/<skill-name>/` 目录下：

- 纯 prompt 类：只需 `SKILL.md`
- 含脚本类：`SKILL.md` + `scripts/main.ts`（或 `.py` / `.go`）

```
skills/my-skill/
├── SKILL.md          # skill 描述与 prompt
└── scripts/
    └── main.ts       # 可选，有脚本时添加
```

## 命名规范

- skill 目录名：英文小写 + 连字符，如 `weekly-report`
- skill 文件：统一命名为 `SKILL.md`
- 共享包：放 `packages/` 下，独立 `package.json`
