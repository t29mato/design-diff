"""Protocolベースのポート層 検証スピーク(2026-08-19, HQレビューv2対応)

HQ指摘2への対応として、ポートを application 層に移し
`cli|action -> application -> adapters -> domain` という import-linter の
layers契約をそのまま敷いた場合、「adapters は application を import できない」
という制約下でも adapters がポートを実装できるかを検証する。

結論: typing.Protocol による構造的部分型(structural typing)を使えば、
adapters側のクラスは application.ports を一切 import せずに
ExtractorPort 等の「形」を満たせる。呼び出し側(composition root)が
Protocol型のヒントで受け取る変数に adapters のインスタンスをそのまま渡せば型検査も通る。

実行方法:
  uv run python docs/design/spikes/protocol_layering_verification.py
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


# --- application/ports.py 相当 ---------------------------------------
@runtime_checkable
class ExtractorPort(Protocol):
    def extract(self, path: str, package: str) -> dict:
        ...


# --- adapters/extraction/py2puml_extractor.py 相当 ---------------------
# ★ ExtractorPort を import していない点に注目。
#   それでも「extract(path, package) -> dict」という形が一致していれば
#   ExtractorPort として扱える(構造的部分型)。
class Py2pumlExtractor:
    def extract(self, path: str, package: str) -> dict:
        return {"path": path, "package": package}


# --- application/use_cases/... 相当 ------------------------------------
def use_it(extractor: ExtractorPort) -> dict:
    return extractor.extract("p", "pkg")


if __name__ == "__main__":
    result = use_it(Py2pumlExtractor())
    print("戻り値:", result)
    print(
        "isinstance(Py2pumlExtractor(), ExtractorPort) =",
        isinstance(Py2pumlExtractor(), ExtractorPort),
        "(importなしでも構造的部分型として認識される)",
    )
