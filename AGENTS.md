# AGENTS.md

本文件写给在此仓库中工作的 AI 编码代理。请先读它，再动代码。

## 项目概况

- 一个 Python 3.12 项目，使用 **uv** 管理解释器、虚拟环境与依赖。
- 包名（导入名）：`agent_from_zero`；发行名：`agent-from-zero`。
- 布局为 **src 布局 + 构建后端 `uv_build`**，包本身以 editable 模式安装进 `.venv`。
- 版本控制：`main` 为默认分支，`origin` = `https://github.com/drop42/agent-from-zero.git`。
- 当前**尚未**配置测试框架、linter、formatter、CI。不要假定它们存在；若需要，先征询再添加。

## 环境与版本约束

| 项 | 值 | 说明 |
|---|---|---|
| `.python-version` | `3.12.13` | 精确补丁版，`uv sync` / `uv run` 均按此解析 |
| `pyproject.toml` → `requires-python` | `>=3.12,<3.13` | 本地 pin 到补丁版，包兼容范围锁在 3.12 线 |
| `uv.lock` | 必须提交 | 随依赖变更一并提交；不要手改 |

不要手动创建/修改 `.venv`，也不要把 `.venv` 加入版本控制（`.gitignore` 已排除）。

## 常用命令

```bash
uv sync                     # 按 uv.lock 精确还原环境
uv run python -V            # 确认解释器为 3.12.13
uv run python -c "import agent_from_zero"   # 在项目环境中执行代码
uv run agent-from-zero      # 通过 [project.scripts] 入口运行（无参数时打印用法）
uv run agent-from-zero "在当前目录创建 hello.py 并运行"   # 执行一句话任务
uv add <pkg>                # 新增运行时依赖（同时更新 pyproject.toml 与 uv.lock）
uv add --dev <pkg>          # 新增开发依赖
uv remove <pkg>             # 移除依赖
uv lock                     # 仅重算锁文件（如改了 requires-python）
```

- 不要使用 `pip` / `python -m venv` / `requirements.txt`；本项目只用 uv。
- 不要在命令前手写 `.venv\Scripts\python`，用 `uv run` 即可。
- 若出现 `Failed to hardlink files ... falling back to full copy`：缓存与项目不在同一文件系统（Windows 常见）。可设 `UV_LINK_MODE=copy` 消除警告，无需改代码。

## Agent 运行配置

- 环境变量：`API_KEY`（必需）、`BASE_URL`（默认 `https://api.deepseek.com`）、`MODEL`（默认 `deepseek-chat`）。
- 工具集：`read_file` / `write_file` / `run_shell`，三者都在 `src/agent_from_zero/agent.py`；`run_shell` 每次执行需人工输入 `y` 确认，非交互环境下直接拒绝。
- 循环上限 `MAX_STEPS = 20`；工具异常会被捕获成字符串结果回传给模型，而不是中断进程。
- `TOOLS`（给模型的说明）与 `TOOL_FUNCS`（实际执行）必须同名对应；新增工具时两处同步。

## 代码结构

```
src/agent_from_zero/__init__.py   # 导出 main
src/agent_from_zero/agent.py      # 工具 + 工具说明 + Agent 循环（EP01）
pyproject.toml                    # 元数据、依赖、入口点、构建后端
uv.lock                           # 锁文件
.python-version                   # 3.12.13
README.md                         # 快速开始
AGENTS.md                         # 本文件
docs/01-agent-minimal-loop.md     # 教程原文（EP01：最小 Agent 循环）
```

- 可直接导入的代码放在 `src/agent_from_zero/` 下，新增模块即新增文件；`src` 不需也不应加入 `sys.path` 手工处理。
- 新增命令行子命令/关键功能时，保持 `pyproject.toml` 的 `[project.scripts]` 同步。

## 约定

- 提交信息用 Conventional Commits（`feat:` / `fix:` / `chore:` / `docs:` / `refactor:`），描述可用中文。
- 只提交源码、`pyproject.toml`、`uv.lock`、`.python-version`、文档；提交前用 `git status` 确认没有把 `.venv`、`.env`、缓存文件带进去。
- 依赖声明只写在 `pyproject.toml`，`uv.lock` 由 uv 生成——**不要手改** `uv.lock`。
- 代码注释与文档语言与所在文件保持一致；本仓库文档默认中文。
- 改动涉及环境（Python 版本、依赖、构建后端）时，同步更新本文件中对应的表格。
