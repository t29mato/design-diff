"""中間表現(IR)。architecture.md §3。

このモジュールはドメイン層の中心であり、py2puml・git・Mermaid/JSONのいずれにも
依存しない(標準ライブラリのみ)。import-linterの domain-purity 契約がこれを強制する。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class AttributeIR:
    name: str
    type: str
    static: bool = False


@dataclass(frozen=True)
class ParameterIR:
    name: str
    type: str | None = None


@dataclass(frozen=True)
class MethodIR:
    name: str
    parameters: tuple[ParameterIR, ...] = ()
    return_type: str | None = None


@dataclass(frozen=True)
class ClassIR:
    fqn: str
    name: str
    is_abstract: bool = False
    # 属性・メソッドは「そのクラス自身が定義したもの」のみを持つ(継承分は含まない)。
    # architecture.md §3.2, §5.4(HQ指摘1)を参照。
    attributes: tuple[AttributeIR, ...] = ()
    methods: tuple[MethodIR, ...] = ()


class RelationType(Enum):
    INHERITANCE = "inheritance"
    COMPOSITION = "composition"


@dataclass(frozen=True)
class RelationIR:
    source_fqn: str
    target_fqn: str
    type: RelationType


@dataclass(frozen=True)
class SnapshotIR:
    package: str
    classes: dict[str, ClassIR]
    relations: frozenset[RelationIR]
