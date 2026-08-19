"""MermaidCliSvgRenderer のテスト。HQ追加要件: ローカルCLI向けSVG直接出力(MVP+)。

設計判断: mermaid-cli(mmdc)が未インストールの環境で`npx`を素朴に叩くと、
Puppeteer/Chromiumを含む大きな依存をネットワーク越しに自動ダウンロードしようと
することを実測で確認した。design-diffはこれを暗黙に行わない
(`npx --no-install`で自動DLを防ぎ、無ければ明確なインストール手順を提示する)。
"""

import shutil

import pytest

from design_diff.adapters.rendering.svg_renderer import (
    MermaidCliSvgRenderer,
    SvgRenderingUnavailableError,
)

SIMPLE_MERMAID = "classDiagram\n    class Foo\n"


class TestMermaidCliSvgRendererUnavailable:
    def test_raises_actionable_error_when_mermaid_cli_is_not_available(self, monkeypatch):
        # このサンドボックスにmermaid-cliはインストールされていないことを実測済み。
        # 確実性のため shutil.which を強制的に「何も見つからない」状態にする。
        monkeypatch.setattr(shutil, "which", lambda _cmd: None)

        with pytest.raises(SvgRenderingUnavailableError) as exc_info:
            MermaidCliSvgRenderer().render(SIMPLE_MERMAID)

        message = str(exc_info.value)
        assert "npm install -g @mermaid-js/mermaid-cli" in message
        assert "mermaid.live" in message  # インストールなしの代替手段も案内する


class TestMermaidCliSvgRendererAvailable:
    """実際にmermaid-cliが使える環境でのみ実行する統合テスト。"""

    @pytest.mark.skipif(shutil.which("mmdc") is None, reason="mermaid-cli (mmdc) is not installed")
    def test_renders_valid_svg_when_mmdc_is_installed(self):
        svg = MermaidCliSvgRenderer().render(SIMPLE_MERMAID)
        assert "<svg" in svg
