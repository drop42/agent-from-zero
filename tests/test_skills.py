"""EP05：技能的测试 —— 解析、发现、按需加载、只读保护、清理豁免。"""

from agent_from_zero import context, skills
from agent_from_zero.permissions import WORKSPACE, PermissionManager


def write_skill(name, text):
    d = WORKSPACE / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    return d


def test_parse_skill():
    meta, body = skills.parse_skill("---\nname: a\ndescription: 做 A: 带冒号\n---\n正文")
    assert meta == {"name": "a", "description": "做 A: 带冒号"} and body == "正文"
    assert skills.parse_skill("---\nname: a\n没闭合")[0] == {}


def test_discover_and_load():
    write_skill("git-commit", "---\nname: git-commit\ndescription: 写提交信息\n---\n规则正文")
    write_skill("broken", "---\nname: broken\n---\n没有描述")
    assert "broken" not in skills.discover()
    assert skills.load_skill("git-commit").startswith("[skill] git-commit")
    assert skills.load_skill("nope").startswith("Error")


def test_load_lists_extra_files():
    d = write_skill("report", "---\nname: report\ndescription: 出周报\n---\n步骤")
    (d / "template.md").write_text("模板", encoding="utf-8")
    assert "template.md" in skills.load_skill("report")


def test_skill_dir_readonly_even_if_user_says_yes():
    pm = PermissionManager(ask=lambda n, a: ("y", ""))
    assert not pm.check("write_file", {"path": "skills/x/SKILL.md", "content": ""}).allowed
    assert pm.check("write_file", {"path": "notes.txt", "content": ""}).allowed


def test_clear_keeps_skill():
    msgs = [
        {"role": "system", "content": ""},
        {"role": "tool", "tool_call_id": "s", "content": "[skill] x\n正文"},
    ]
    msgs += [
        {"role": "tool", "tool_call_id": str(i), "content": f"r{i}"} for i in range(5)
    ]
    context.clear_old_tool_results(msgs, keep=1)
    assert msgs[1]["content"].startswith("[skill]")
    assert msgs[-1]["content"] == "r4"


def test_build_system_lists_skills_and_notes():
    from agent_from_zero.agent import build_system

    write_skill("deploy", "---\nname: deploy\ndescription: 部署前检查\n---\n步骤")
    prompt = build_system()
    assert "- deploy：部署前检查" in prompt
    assert "先调用 load_skill" in prompt
