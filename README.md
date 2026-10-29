# agent-from-zero

从零手写 Agent 的配套实现，逐课对照教程：

- [EP01｜100 行代码，写出第一个 Agent](docs/01-agent-minimal-loop.md)
- [EP02｜工具系统：加工具不再改主循环](docs/02-agent-tools.md)
- [EP03｜权限：给 Agent 装上刹车](docs/03-agent-permissions.md)
- [EP04｜上下文管理：别让 Agent 被自己的历史撑爆](docs/04-agent-context.md)
- [EP05｜Skills：让 Agent 按需加载能力](docs/05-agent-skills.md)

当前实现对应 **EP05**：注册表工具系统 + 三道权限闸门 + 三层上下文管理 + 按需加载的技能（AGENTS.md 常驻、`skills/*/SKILL.md` 按需读取且对 Agent 只读）。

## 快速开始

```bash
uv sync
export API_KEY=你的模型密钥                       # 必需
export NAMI_WORKSPACE=~/agent-workspace            # 可选，Agent 只能碰这个目录
export NAMI_STATE_DIR=~/.nami-agent                # 可选，会话与状态文件位置
# 可选：export BASE_URL=... / MODEL=... / NAMI_SOFT_LIMIT=16000 / NAMI_HARD_LIMIT=24000

uv run agent-from-zero                            # 交互式对话，messages 跨轮保留并落盘
uv run agent-from-zero "写一个 fib.py 并运行验证"   # 单次任务
uv run pytest -q                                  # 测试
```

交互模式输入 `exit` / `quit` 退出。未设置 `NAMI_WORKSPACE` 时，工作区 = 启动时的当前目录。

## 上下文管理

每轮请求前按**上一次 API 返回的 `prompt_tokens`** 决定动作（不自己估算 token）：

| 层 | 触发 | 行为 |
|---|---|---|
| 1 | 工具结果进 messages 时 | 超过 4000 字符截断，保留头尾并注明省略长度 |
| 2 | `prompt_tokens > SOFT_LIMIT`（默认 16000） | 旧的 tool 消息内容替换为占位符，**不删消息** |
| 3 | `prompt_tokens > HARD_LIMIT`（默认 24000） | 早期对话摘要压缩，只在 user 消息处切，保留最近 2 轮原文 |

会话以纯 dict 存成 `$NAMI_STATE_DIR/sessions/default.json`；该目录默认在 `~/.nami-agent`，位于工作区之外，Agent 的文件工具碰不到。

## 权限

每个工具调用在真正执行前都会过 `perms.check(name, args)`：

1. **硬规则**：路径落在工作区之外、命中灾难性命令黑名单（`sudo`、`mkfs`、`curl … | sh` 等）→ 直接拒绝，人也不能放行。
2. **风险分级**：`list_dir` / `read_file` 为 SAFE；`write_file` / `run_shell` / `fetch_url` 为 CONFIRM；未登记工具一律 CONFIRM。
3. **人工确认**：展示真实参数，`y` / `n`（可附原因）；`write_file` 支持 `a` 本次会话一直允许，`run_shell` 每条都要过目。

拒绝不会中断流程：`[权限拒绝] 原因` 作为 tool 结果回传，模型可换条路。非交互环境默认视为拒绝。

## 工具

| 工具 | 作用 |
|---|---|
| `list_dir` | 列出目录内容（限工作区） |
| `read_file` | 读取文本文件（限工作区） |
| `write_file` | 写入文件（限工作区，自动建父目录） |
| `run_shell` | 在工作区执行 shell 命令，30 秒超时，返回 `[exit N]` + stdout/stderr |
| `fetch_url` | 抓取网页/接口文本 |

新增工具只需写一个函数并加 `@tool(...)` 装饰器，注册表自动收录；记得在 `permissions.py` 的 `TOOL_RISK` 里登记风险等级（未登记默认 CONFIRM）。

```python
# src/agent_from_zero/tools.py
@tool("get_time", "返回当前时间。", _params())
def get_time() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
```

## 技能

工作区根目录的 `AGENTS.md` 常驻 system prompt（截断到 3000 字）；`skills/<name>/SKILL.md` 只在 system prompt 里出现一行「名字：用途」，模型判断相关时调用 `load_skill` 读取全文：

```markdown
---
name: git-commit
description: 按团队规范写 git 提交信息。用户要求提交代码或写 commit message 时使用。
---

# 提交信息规范
...
```

- 技能目录对 Agent **只读**：`write_file` 命中 `skills/` 会被硬规则拒绝（`run_shell` 仍可用，但每条命令要确认）。
- 技能内容以 `[skill]` 开头，不参与上下文第 2 层清理，避免任务中途"忘记规矩"。
- 缺 `description` 的 `SKILL.md` 会被跳过并打印提示。
- 技能目录下的其他文件（如 `template.md`）会在加载时列出，模型可用 `read_file` 按需读取。

## 结构

```
src/agent_from_zero/agent.py        # 主循环、handle_call、上下文阈值、build_system、会话读写
src/agent_from_zero/tools.py        # 注册表、五个工具、execute() 统一执行器
src/agent_from_zero/permissions.py  # 硬规则、风险分级、人工确认
src/agent_from_zero/context.py      # 截断、清理、摘要压缩、会话持久化
src/agent_from_zero/skills.py       # SKILL.md 解析、发现、load_skill 工具
tests/                              # 权限、上下文、技能用例
```
- 工具输出超过 8000 字符在 `execute` 截断，进入 messages 时再按 4000 字符截断（`MAX_OUTPUT` / `MAX_TOOL_CHARS`）。
- 工具异常、未知工具名、参数错误都作为 `Error: ...` 文本回传给模型，让它自行修正。
- 单次任务最多 20 步（`MAX_STEPS`）。
