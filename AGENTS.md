# AGENTS.md

本文件写给在此仓库中工作的 AI 编码代理。请先读它，再动代码。

## 项目概况

- 一个 Python 3.12 项目，使用 **uv** 管理解释器、虚拟环境与依赖。
- 包名（导入名）：`agent_from_zero`；发行名：`agent-from-zero`。
- 布局为 **src 布局 + 构建后端 `uv_build`**，包本身以 editable 模式安装进 `.venv`。
- 版本控制：`main` 为默认分支，`origin` = `https://github.com/drop42/agent-from-zero.git`。
- 测试用 **pytest**（dev 依赖），`uv run pytest -q` 运行；linter、formatter、CI 仍未配置，不要假定它们存在。

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
uv run agent-from-zero      # 交互式对话，messages 跨轮保留；exit/quit 退出
uv run agent-from-zero "写一个 fib.py 并运行验证"   # 单次任务
uv add <pkg>                # 新增运行时依赖（同时更新 pyproject.toml 与 uv.lock）
uv add --dev <pkg>          # 新增开发依赖
uv remove <pkg>             # 移除依赖
uv lock                     # 仅重算锁文件（如改了 requires-python）
```

- 不要使用 `pip` / `python -m venv` / `requirements.txt`；本项目只用 uv。
- 不要在命令前手写 `.venv\Scripts\python`，用 `uv run` 即可。
- 若出现 `Failed to hardlink files ... falling back to full copy`：缓存与项目不在同一文件系统（Windows 常见）。可设 `UV_LINK_MODE=copy` 消除警告，无需改代码。

## Agent 运行配置

- 环境变量：`API_KEY`（必需）、`BASE_URL`（默认 `https://api.deepseek.com`）、`MODEL`（默认 `deepseek-chat`）、`NAMI_WORKSPACE`（默认启动时 cwd）。
- 工具集：`list_dir` / `read_file` / `write_file` / `run_shell` / `fetch_url`，全部在 `src/agent_from_zero/tools.py`，用 `@tool(name, description, _params(...))` 注册到 `TOOLS`，`get_schemas()` 生成给模型的说明书。
- **新增工具只写一个函数加装饰器**，并在 `permissions.py` 的 `TOOL_RISK` 登记风险等级（未登记默认 `CONFIRM`）。
- 执行链路：`agent.handle_call` → `perms.check(name, args)` → `tools.execute(name, args)`。硬规则（工作区越界、`SHELL_DENY_PATTERNS`）优先于人工确认，且不可被 `y` 放行。
- `tools.execute` 永远返回字符串，绝不抛出；输出上限 `MAX_OUTPUT = 8000`。文件工具自身也用 `resolve_in_workspace` 二次校验。
- 循环上限 `MAX_STEPS = 20`；模型给出的参数不是合法 JSON 时也必须回一条 tool 消息（"Error: 参数不是合法的 JSON"）。
- 权限逻辑改动必须配套 `tests/test_permissions.py`；该校验依赖注入的 `ask`，不要 mock `input()`。

## 代码结构

```
src/agent_from_zero/__init__.py   # 导出 main
src/agent_from_zero/agent.py      # 主循环 + handle_call 权限闸门 + REPL/单次任务
src/agent_from_zero/tools.py      # 工具注册表、五个工具、execute() 统一执行器
src/agent_from_zero/permissions.py # 硬规则 / 风险分级 / 人工确认（EP03）
tests/conftest.py                 # 把测试工作区指向临时目录
tests/test_permissions.py         # 权限用例
pyproject.toml                    # 元数据、依赖、入口点、构建后端
uv.lock                           # 锁文件
.python-version                   # 3.12.13
README.md                         # 快速开始
AGENTS.md                         # 本文件
docs/01-agent-minimal-loop.md     # 教程原文（EP01：最小 Agent 循环）
docs/02-agent-tools.md            # 教程原文（EP02：工具系统）
docs/03-agent-permissions.md      # 教程原文（EP03：权限）
```

- 可直接导入的代码放在 `src/agent_from_zero/` 下，新增模块即新增文件；`src` 不需也不应加入 `sys.path` 手工处理。
- 新增命令行子命令/关键功能时，保持 `pyproject.toml` 的 `[project.scripts]` 同步。

## 约定

- 提交信息用 Conventional Commits（`feat:` / `fix:` / `chore:` / `docs:` / `refactor:`），描述可用中文。
- 只提交源码、`pyproject.toml`、`uv.lock`、`.python-version`、文档；提交前用 `git status` 确认没有把 `.venv`、`.env`、缓存文件带进去。
- 依赖声明只写在 `pyproject.toml`，`uv.lock` 由 uv 生成——**不要手改** `uv.lock`。
- 代码注释与文档语言与所在文件保持一致；本仓库文档默认中文。
- 改动涉及环境（Python 版本、依赖、构建后端）时，同步更新本文件中对应的表格。
