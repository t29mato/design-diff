# 調査: mermaid-cli(Chromium)を介さずMermaidをSVG化できるか

**依頼元**: HQ情報共有(2026-08-20)。plantuml-web プロジェクト(PlantUML用のVS Code Web
Extension)で、`@plantuml/core`(Graphviz WASMコンパイル版を同梱)を使い、Java・
Graphvizバイナリ・サーバーいずれも無しでクラス図をSVGレンダリングできることが
実証された。design-diffの`--format svg`も内部でmermaid-cli(`mmdc`)= Node.js +
Puppeteer(Chromium)を要求しており、同じ「図を見るために重い依存が要る」問題を
抱えているため、Mermaid側に同種の軽量な代替経路がないか調査した。

**結論(先に): ある。`mermaidx`というPython製パッケージが、Node/npm/Java/ブラウザ
いずれも要求せずMermaidをSVG/PNG/PDF化できることを実機で確認した。**
ただし現時点ではdesign-diffの実装変更はしない(投資判断は別途)。

## 1. Mermaid本体の構造的な制約

Web検索と実機検証で確認した限り、Mermaidの`classDiagram`(design-diffが使っている
図種)は、ノードラベルを`<foreignObject>`(SVG内にHTMLを埋め込む要素)でレンダリング
する。レイアウト計算にはブラウザの`getBBox()`/`getComputedTextLength()`という、
実際にDOMツリーにマウントされた要素でなければ正しい値を返さないAPIに依存している。

これは「design-diffやmermaid-cliの実装が悪い」という話ではなく、**Mermaid本体の
アーキテクチャ上の制約**([mermaid-js/mermaid#3886](https://github.com/mermaid-js/mermaid/issues/3886)、
[#6634](https://github.com/mermaid-js/mermaid/issues/6634)、
[#4180](https://github.com/mermaid-js/mermaid/issues/4180)で継続的に議論されている)。
そのため公式の`mermaid-cli`は今も唯一の「公式にサポートされた」経路としてPuppeteer
(Chromium)を使い続けている。

`jsdom`/`svgdom`でDOMを模倣する`isomorphic-mermaid`のような試みもあるが、
`foreignObject`内のコンテンツはvisibility:hiddenなSVG内でブラウザがレイアウトを
スキップするため、`classDiagram`/`erDiagram`/`requirementDiagram`(=`foreignObject`
を使う図種)ではラベルのサイズが0扱いになり、レイアウトが壊れやすい。

## 2. 実機で見つかった有望な経路: `mermaidx`

[MohammadRaziei/mermaidx](https://github.com/MohammadRaziei/mermaidx)
(PyPI: `mermaidx`, v0.9.4, MIT License)は、上記の制約を「ブラウザを避ける」のではなく
「本物のMermaid.jsコードを、本物のブラウザ以外の場所で動かし、フォントメトリクスだけ
Python側から正確に供給する」ことで解決している:

- 埋め込みJSエンジン(`quickjs-ng`、軽量な組み込み用JavaScriptエンジンで**ブラウザでは
  ない**)上で、本物のmermaid.js(確認時点でv11.16.0。design-diffがGitHubで実機検証
  した際と同じメジャーバージョン系統)をそのまま実行する
- `getBBox`/`getComputedTextLength`が必要とする文字幅を、同梱フォントを読んで
  Python側で計算し、QuickJS側に正確な値として供給する(＝「DOMを騙す」のではなく
  「本物の値を渡す」ため、foreignObjectを使うclassDiagramでも正しくレイアウトできる)
- 最終的なラスタライズ(SVG→PNG等)は`resvg`(Rust製、ブラウザではない)を使い、
  「mermaidがレイアウト計算時に使ったのと同じフォント」で描画するため、測定結果と
  実際の見た目がズレない

### 実機検証結果

design-diffが実際に出力したMermaidソース(`namespace`記法・`style`文・
メンバー単位ASCIIタグ・`note`を全て含む、`shop-discount-codes`例そのもの)を
`mermaidx`にそのまま入力し、問題なくSVG/PNGへの変換に成功した。`style`文による
色分け(緑/赤/黄の背景・枠線・文字色)もGitHub実機で確認した見た目と一致して
正しく反映されており、`namespace`グループ化・リレーション線・`note`吹き出しも
崩れずにレイアウトされた。

```bash
pip install mermaidx
mermaidx -i shop.mmd -o shop.png -w 1400
```

依存関係は`quickjs-ng` / `resvg-py` / `termaid`のみで、いずれもPythonのpipで
完結する(Node.js・npm・Java・ブラウザ・OS別バイナリのダウンロードは不要)。

## 3. design-diffへの示唆(投資判断はまだしていない)

現状の`--format svg`は「mermaid-cliが無ければインストール手順を案内して終了する」
という設計(重い依存を自動導入しない、という判断自体は妥当で変更不要)。
`mermaidx`に乗り換えれば、この「重い依存」自体をNode.js/Puppeteer(Chromium)から
軽量なPython pipパッケージに置き換えられる可能性がある。ただし本調査の時点では
以下が未検証・未判断:

- `mermaidx`はv0.9.4とまだ1.0未満で、design-diffが使う全構文(特に`style`文・
  `namespace`・大規模図)を長期的に安定してサポートし続けるかは不明
- ライセンス(MIT)・保守体制(個人開発者)のリスク評価は未実施
- design-diffの依存に追加するかどうかは、この調査結果を踏まえてオーナーが
  改めて判断すること(本調査はあくまで「調査だけ」の依頼に対する回答)

## まとめ

| 問い | 答え |
|---|---|
| Mermaidをmermaid-cli(Chromium)無しでSVG化する現実的な経路はあるか | **ある**(`mermaidx`、実機検証済み) |
| Mermaid本体に制約があるのか、アプローチの問題なのか | **Mermaid本体の構造的制約**(classDiagram等がforeignObjectに依存し、正確なDOM無しでは
レイアウトできない)。ただし「フォントメトリクスを正確に供給する」という
アプローチでその制約を回避できることを`mermaidx`が示している |
