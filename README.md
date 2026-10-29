# agent-from-zero

从零手写 Agent 的配套实现，对照教程 [从零手写 Agent · EP01｜100 行代码，写出第一个 Agent](https://namiai.tech/articles/agent-minimal-loop/)。

核心只有三块：**工具**（`read_file` / `write_file` / `run_shell`）、**工具说明**（发给模型的 JSON schema）、**循环**（模型请求工具 → 代码执行 → 结果回传 → 直到模型不再请求）。

## 快速开始

```bash
uv sync
export API_KEY=你的模型密钥          # 必需
# 可选：export BASE_URL=...          # 默认 https://api.deepseek.com
# 可选：export MODEL=...             # 默认 deepseek-chat

uv run agent-from-zero "在当前目录创建 hello.py，打印 hello，并运行它"
```

> 这个版本的 Agent 能写任意文件，请**在空目录里运行它**，或用 `--project` 指向本项目、在临时目录中作为工作目录：

```bash
mkdir /tmp/playground && cd /tmp/playground
uv run --project /path/to/agent-from-zero agent-from-zero "创建 hello.py 并运行"
```

`run_shell` 每执行一条命令都会要求输入 `y` 确认；非交互环境一律拒绝。

## 结构

```
src/agent_from_zero/agent.py   # 工具、工具说明、循环、CLI 入口
```

默认最多 20 步（`MAX_STEPS`），工具异常会作为文本结果回传给模型，让它自行修正。
