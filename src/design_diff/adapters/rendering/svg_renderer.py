"""MermaidCliSvgRenderer。HQ追加要件: ローカルCLI向けSVG直接出力(MVP+)。

**2026-08-25時点の位置づけ(HQ #36/#38対応後)**: `--format svg`の既定は
`GitHubStyleSvgRenderer`(mermaid非依存のネイティブSVGレンダラー)に切り替わって
おり、このモジュールが対象とするのは`--format svg-mermaid`(旧実装、要
mermaid-cli)のみになった。以下のコメントは元々`--format svg`が本レンダラー
だった時点のもので、経緯として残している。

GitHubのPRコメントはMermaidをネイティブ描画するが、ローカルでCLIを使う開発者は
そのままではプレビューできない。ローカルでも「絵」で確認できるよう、既に
Mermaidテキストとしてレンダリング済みの出力(MermaidRendererの結果)を
SVGに変換するアダプタを用意する。

設計判断(重要): design-diff自身の依存としてNode.js/Puppeteer/Chromiumを
追加するのではなく、**開発者の環境に既にmermaid-cli(mmdc)が入っていれば
それを使う、という薄いラッパーに留める**。
実測により、mermaid-cli未インストールの環境で素朴に`npx @mermaid-js/mermaid-cli`
を叩くと、Puppeteer/Chromiumを含む大きな依存をネットワーク越しに自動ダウンロード
しようとすることを確認した。design-diffがこれを暗黙に(ユーザーの同意なく)
行うのは望ましくないため、`npx --no-install`で自動ダウンロードを防ぎ、
mermaid-cliが見つからない場合は明確なインストール手順(またはインストール
無しで試せるhttps://mermaid.live)を提示するだけに留める。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

_INSTALL_HELP = (
    "--format svg-mermaid にはmermaid-cli (mmdc) が必要です"
    "(GitHub diff風のネイティブSVGが欲しいだけなら、mermaid-cli不要の"
    "--format svg(既定)を使ってください)。次のいずれかをお試しください:\n"
    "  npm install -g @mermaid-js/mermaid-cli\n"
    "  npx @mermaid-js/mermaid-cli -i input.mmd -o output.svg  (一度だけ試す場合)\n"
    "インストールせずに確認したい場合は、Mermaidテキストを"
    "https://mermaid.live に貼り付けてSVG/PNGとしてエクスポートすることもできます。"
)


class SvgRenderingUnavailableError(RuntimeError):
    """mermaid-cli (mmdc) がローカルに見つからない、または実行に失敗した場合。"""


def _resolve_command() -> list[str] | None:
    if shutil.which("mmdc"):
        return ["mmdc"]
    if shutil.which("npx"):
        # --no-install: 未キャッシュ時にPuppeteer/Chromiumを自動ダウンロードしない
        probe = subprocess.run(
            ["npx", "--no-install", "@mermaid-js/mermaid-cli", "--version"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return ["npx", "--no-install", "@mermaid-js/mermaid-cli"]
    return None


class MermaidCliSvgRenderer:
    """既にレンダリング済みのMermaidテキストをSVGへ変換する(SnapshotDiffは扱わない)。"""

    def render(self, mermaid_text: str) -> str:
        command = _resolve_command()
        if command is None:
            raise SvgRenderingUnavailableError(_INSTALL_HELP)

        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "diagram.mmd"
            output_path = Path(tmp) / "diagram.svg"
            input_path.write_text(mermaid_text)

            result = subprocess.run(
                [*command, "-i", str(input_path), "-o", str(output_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise SvgRenderingUnavailableError(
                    f"mermaid-cliの実行に失敗しました: {result.stderr.strip()}\n{_INSTALL_HELP}"
                )
            return output_path.read_text()
