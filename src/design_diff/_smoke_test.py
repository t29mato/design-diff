"""Action実機検証用の一時ファイル。

Issue #2「PRコメント自動投稿の実証」を、実際のGitHub Actions経由で確認するために
一時的に追加するダミークラス。検証が終わり次第このファイルとPRは削除する
(mainにはマージしない)。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SmokeTestMarker:
    """design-diffのGitHub Action実証用の一時クラス(mainにはマージしない)。"""

    label: str

    def describe(self) -> str:
        return f"smoke-test:{self.label}"
