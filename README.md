# repo1
这是我的第一个仓库，尝试用git连接本地

## Codex Agent Manager Marketplace

本仓库现在提供可共享的 Codex marketplace，包含 `codex-agent-manager` 插件。

插件工作流：

1. 根据需求复杂度决定是否使用 `grilling` 逐项澄清。
2. 提示用户是否进入 `to-spec`。
3. 每次选择发布 issue 并保存本地副本，或只生成本地 Markdown。
4. 选择当前 Codex、Kiro、Cursor 或 Claude 执行。
5. 保存执行日志并由 Codex 独立验证结果。

### 安装

```bash
codex plugin marketplace add guber6666/repo1 --ref main
codex plugin add codex-agent-manager@guber6666-repo1
```

安装后重启 Codex，并新建任务使 Skill 生效。

### 更新

```bash
codex plugin marketplace upgrade guber6666-repo1
codex plugin add codex-agent-manager@guber6666-repo1
```

### 依赖

- Python 3.10+
- 完整需求分析流程需要已安装的 `grilling` 和 `to-spec` Skills
- 外部执行器按需安装：Kiro CLI、Cursor Agent CLI、Claude Code CLI
- 选择当前 Codex Agent 时不需要外部 CLI

插件源码及详细说明见 [`plugins/codex-agent-manager`](plugins/codex-agent-manager/README.md)。
阿三你上课满是，马上111
