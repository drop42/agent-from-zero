"""EP05：技能（按需加载的能力说明书）。

AGENTS.md 常驻 system prompt；技能只放一行目录，模型按需调用 load_skill 读全文。
"""

from __future__ import annotations

from .permissions import SKILLS_DIR, WORKSPACE
from .tools import _params, tool

SKILL_MARK = "[skill]"
MAX_NOTES_CHARS = 3000


def parse_skill(text: str) -> tuple[dict, str]:
    """拆出 frontmatter（--- 之间的 key: value）和正文。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text.strip()
    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1 :]).strip()
        key, sep, value = line.partition(":")  # 只切第一个冒号，描述里可以带冒号
        if sep:
            meta[key.strip()] = value.strip()
    return {}, text.strip()  # 没有闭合的 ---，当作没有 frontmatter


def discover(skills_dir=None) -> dict[str, dict]:
    skills_dir = skills_dir or SKILLS_DIR
    found: dict[str, dict] = {}
    if not skills_dir.is_dir():
        return found
    for f in sorted(skills_dir.glob("*/SKILL.md")):
        meta, _ = parse_skill(f.read_text(encoding="utf-8"))
        name = meta.get("name") or f.parent.name
        if not meta.get("description"):
            print(f"[skills] 跳过 {f}：缺少 description")
            continue
        found[name] = {"description": meta["description"], "path": f}
    return found


def skills_section(found: dict | None = None) -> str:
    """system prompt 里的技能目录：只有名字和一句话用途。"""
    found = discover() if found is None else found
    if not found:
        return ""
    lines = [
        "",
        "## 可用技能",
        "下面只列出技能的名字和用途。当任务和某个技能的用途匹配时，"
        "先调用 load_skill 读取完整说明，再按说明执行。",
    ]
    lines += [f"- {n}：{s['description']}" for n, s in found.items()]
    return "\n".join(lines)


def project_notes() -> str:
    """AGENTS.md：项目级说明，每次都放进 system prompt。"""
    p = WORKSPACE / "AGENTS.md"
    if not p.is_file():
        return ""
    text = p.read_text(encoding="utf-8")[:MAX_NOTES_CHARS]
    return f"\n\n## 项目说明（来自 AGENTS.md）\n{text}"


@tool(
    "load_skill",
    "读取一个技能的完整说明。任务和「可用技能」列表里某个技能的用途匹配时调用。",
    _params(name="技能名"),
)
def load_skill(name: str) -> str:
    found = discover()
    if name not in found:
        return f"Error: 没有名为 {name!r} 的技能，可用：{', '.join(found) or '无'}"
    path = found[name]["path"]
    _, body = parse_skill(path.read_text(encoding="utf-8"))
    extras = sorted(p.name for p in path.parent.iterdir() if p.name != "SKILL.md")
    rel = path.parent.relative_to(WORKSPACE)
    note = f"\n\n（技能目录 {rel}/ 下还有：{', '.join(extras)}）" if extras else ""
    return f"{SKILL_MARK} {name}\n{body}{note}"
