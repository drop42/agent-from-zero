# agent-from-zero

从零手写 Agent 的配套实现，逐课对照教程：

- [EP01｜100 行代码，写出第一个 Agent](docs/01-agent-minimal-loop.md)
- [EP02｜工具系统：加工具不再改主循环](docs/02-agent-tools.md)
- [EP03｜权限：给 Agent 装上刹车](docs/03-agent-permissions.md)

当前实现对应 **EP03**：装饰器注册表管理工具 + 三道权限闸门（硬规则 / 风险分级 / 人工确认），拒绝原因会回传给模型。

## 快速开始

```bash
uv sync
export API_KEY=你的模型密钥                       # 必需
export NAMI_WORKSPACE=~/agent-workspace            # 可选，Agent 只能碰这个目录
# 可选：export BASE_URL=...   # 默认 https://api.deepseek.com
# 可选：export MODEL=...      # 默认 deepseek-chat

uv run agent-from-zero                            # 交互式对话，messages 跨轮保留
uv run agent-from-zero "写一个 fib.py 并运行验证"   # 单次任务
uv run pytest -q                                  # 权限逻辑测试
```

交互模式输入 `exit` / `quit` 退出。未设置 `NAMI_WORKSPACE` 时，工作区 = 启动时的当前目录。

## 权限

每个工具调用在真正执行前都会过 `perms.check(name, args)`：

1. **硬规则**：路径落在工作区之外、命中灾难性命令黑名单（`sudo`、`mkfs`、`curl … | sh` 等）→ 直接拒绝，人也不能放行。
2. **风险分级**：`list_dir` / `read_file` 为 SAFE，自动放行；`write_file` / `run_shell` / `fetch_url` 为 CONFIRM；未登记的工具一律 CONFIRM。
3. **人工确认**：终端展示真实参数（命令原文、写入路径与内容摘要），`y` 放行 / `n` 拒绝（可附原因）；`write_file` 支持 `a` 本次会话一直允许，`run_shell` 每条都要过目。

拒绝不会中断流程：`[权限拒绝] 原因` 会作为 tool 结果回传，模型可换条路。非交互环境（管道/脚本）默认视为拒绝。

## 工具

| 工具 | 作用 |
|---|---|
| `list_dir` | 列出目录内容（限工作区） |
| `read_file` | 读取文本文件（限工作区） |
| `write_file` | 写入文件（限工作区，自动建父目录） |
| `run_shell` | 在工作区执行 shell 命令，30 秒超时，返回 `[exit N]` + stdout/stderr |
| `fetch_url` | 抓取网页/接口文本 |

新增工具只需写一个函数并加 `@tool(...)` 装饰器，注册表自动收录，主循环无需改动；记得在 `permissions.py` 的 `TOOL_RISK` 里登记风险等级（未登记默认 CONFIRM）。

```python
# src/agent_from_zero/tools.py
@tool("get_time", "返回当前时间。", _params())
def get_time() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
```

## 结构

```
src/agent_from_zero/agent.py        # 主循环（run/REPL）、handle_call 权限闸门
src/agent_from_zero/tools.py        # 注册表、五个工具、execute() 统一执行器
src/agent_from_zero/permissions.py  # 硬规则、风险分级、人工确认
tests/test_permissions.py           # 6 个权限用例
```

- 工具输出超过 8000 字符会被截断并注明总长度（`MAX_OUTPUT`）。
- 工具异常、未知工具名、参数错误都作为 `Error: ...` 文本回传给模型，让它自行修正。
- 单次任务最多 20 步（`MAX_STEPS`）。
