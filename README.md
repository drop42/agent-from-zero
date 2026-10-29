# agent-from-zero

从零手写 Agent 的配套实现，逐课对照教程：

- [EP01｜100 行代码，写出第一个 Agent](docs/01-agent-minimal-loop.md)
- [EP02｜工具系统：加工具不再改主循环](docs/02-agent-tools.md)

当前实现对应 **EP02**：装饰器 + 注册表管理工具，统一执行器把错误变成"可被模型看到的结果"，主循环里不含任何具体工具名。

## 快速开始

```bash
uv sync
export API_KEY=你的模型密钥          # 必需
# 可选：export BASE_URL=...          # 默认 https://api.deepseek.com
# 可选：export MODEL=...             # 默认 deepseek-chat

uv run agent-from-zero                     # 交互式对话，messages 跨轮保留
uv run agent-from-zero "写一个 fib.py 并运行验证"   # 单次任务
```

交互模式输入 `exit` / `quit` 退出。

> ⚠️ EP02 的版本**没有任何权限限制**：`run_shell` 会直接执行模型给出的任意命令，`write_file` 能写任意路径。
> 请**在空目录或临时目录里运行**，不要在放着重要文件的目录里试。

```bash
mkdir /tmp/playground && cd /tmp/playground
uv run --project /path/to/agent-from-zero agent-from-zero
```

## 工具

| 工具 | 作用 |
|---|---|
| `list_dir` | 列出目录内容 |
| `read_file` | 读取文本文件 |
| `write_file` | 写入文件（覆盖，自动建父目录） |
| `run_shell` | 执行 shell 命令，30 秒超时，返回 `[exit N]` + stdout/stderr |
| `fetch_url` | 抓取网页/接口文本 |

新增工具只需写一个函数并加 `@tool(...)` 装饰器，注册表自动收录，主循环无需改动：

```python
# src/agent_from_zero/tools.py
@tool("get_time", "返回当前时间。", _params())
def get_time() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
```

## 结构

```
src/agent_from_zero/agent.py   # 主循环（run/REPL），不含具体工具名
src/agent_from_zero/tools.py   # 注册表、五个工具、统一执行器 execute()
```

- 工具输出超过 8000 字符会被截断并注明总长度（`MAX_OUTPUT`）。
- 工具异常、未知工具名、参数错误都作为 `Error: ...` 文本回传给模型，让它自行修正。
- 单次任务最多 20 步（`MAX_STEPS`）。
