"""测试前把工作区与会话状态目录都指向临时目录，避免碰到真实文件。"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="agent-ep04-"))
os.environ["NAMI_WORKSPACE"] = str(_TMP / "workspace")
os.environ["NAMI_STATE_DIR"] = str(_TMP / "state")
Path(os.environ["NAMI_WORKSPACE"]).mkdir(parents=True, exist_ok=True)
