"""测试前把工作区指向临时目录，避免碰到真实文件。"""

import os
import tempfile
from pathlib import Path

_TMP_WORKSPACE = Path(tempfile.mkdtemp(prefix="agent-workspace-"))
os.environ["NAMI_WORKSPACE"] = str(_TMP_WORKSPACE)
