"""MermaidCliSvgRenderer のテスト。HQ追加要件: ローカルCLI向けSVG直接出力(MVP+)。

設計判断: mermaid-cli(mmdc)が未インストールの環境で`npx`を素朴に叩くと、
Puppeteer/Chromiumを含む大きな依存をネットワーク越しに自動ダウンロードしようと
することを実測で確認した。design-diffはこれを暗黙に行わない
(`npx --no-install`で自動DLを防ぎ、無ければ明確なインストール手順を提示する)。

カバレッジ補強(実戦テストのタイミングで手薄と判明した箇所):
- `_resolve_command()`のnpxフォールバック経路(mmdc無し・npx有りの分岐、
  probeが成功/失敗する分岐)。実際にmermaid-cli/npxをインストールせずに
  `subprocess.run`をモックして検証する
- `render()`が実際のレンダリング呼び出し(2回目のsubprocess.run)に失敗した
  場合のエラーメッセージ
- コマンドが解決できた場合の正常系(モックでSVGを書き込ませて検証)
"""

import shutil
import subprocess

import pytest

from design_diff.adapters.rendering.svg_renderer import (
    MermaidCliSvgRenderer,
    SvgRenderingUnavailableError,
    _resolve_command,
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


class TestResolveCommand:
    """`_resolve_command()`の分岐(mmdc有無・npxのprobe成功/失敗)をモックで検証する。

    実環境にmermaid-cli/npxが無くても(このサンドボックスの実際の状態のまま)
    決定的に検証できるよう、`shutil.which`と`subprocess.run`をモックする。
    """

    def test_prefers_mmdc_when_available(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/local/bin/mmdc" if cmd == "mmdc" else None)

        assert _resolve_command() == ["mmdc"]

    def test_falls_back_to_npx_when_probe_succeeds(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: None if cmd == "mmdc" else "/usr/bin/npx")

        def fake_run(args, **kwargs):
            assert args == ["npx", "--no-install", "@mermaid-js/mermaid-cli", "--version"]
            return subprocess.CompletedProcess(args, returncode=0, stdout="1.0.0", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        assert _resolve_command() == ["npx", "--no-install", "@mermaid-js/mermaid-cli"]

    def test_returns_none_when_npx_probe_fails(self, monkeypatch):
        """npxコマンド自体はあるが、mermaid-cliがキャッシュされておらず
        `--no-install`のprobeが失敗する場合(実際にこのサンドボックスで
        再現するケース)。
        """
        monkeypatch.setattr(shutil, "which", lambda cmd: None if cmd == "mmdc" else "/usr/bin/npx")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda args, **kwargs: subprocess.CompletedProcess(
                args, returncode=1, stdout="", stderr="not found"
            ),
        )

        assert _resolve_command() is None

    def test_returns_none_when_neither_mmdc_nor_npx_available(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _cmd: None)

        assert _resolve_command() is None


class TestMermaidCliSvgRendererRenderFailure:
    def test_raises_actionable_error_when_render_subprocess_fails(self, monkeypatch):
        """コマンド自体は解決できても、実際のレンダリング呼び出しが失敗する場合
        (構文エラーのMermaidテキスト等)、mermaid-cliのエラー出力を含む
        分かりやすいメッセージを出す。
        """
        monkeypatch.setattr("design_diff.adapters.rendering.svg_renderer._resolve_command", lambda: ["mmdc"])
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda args, **kwargs: subprocess.CompletedProcess(
                args, returncode=1, stdout="", stderr="parse error"
            ),
        )

        with pytest.raises(SvgRenderingUnavailableError) as exc_info:
            MermaidCliSvgRenderer().render(SIMPLE_MERMAID)

        message = str(exc_info.value)
        assert "mermaid-cliの実行に失敗しました" in message
        assert "parse error" in message

    def test_returns_svg_content_when_render_subprocess_succeeds(self, monkeypatch):
        """コマンド解決・レンダリングともに成功する正常系を、実際のmermaid-cli
        インストールに依存せずモックで検証する。
        """
        monkeypatch.setattr("design_diff.adapters.rendering.svg_renderer._resolve_command", lambda: ["mmdc"])

        def fake_run(args, **kwargs):
            # renderが渡す出力先パス(-oの次の引数)にダミーのSVGを書き込む
            output_path = args[args.index("-o") + 1]
            with open(output_path, "w") as f:
                f.write("<svg>fake</svg>")
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        svg = MermaidCliSvgRenderer().render(SIMPLE_MERMAID)

        assert svg == "<svg>fake</svg>"
