# GitHub markdownでの生SVGタグ検証(後で削除)

インラインSVGがサニタイズされず描画されるか確認する。

<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg">
  <rect x="10" y="10" width="150" height="60" fill="#22863a" stroke="#000" stroke-width="2" />
  <text x="20" y="45" fill="white" font-size="16">SVG OK?</text>
</svg>

## imgタグ+data URI での検証

<img src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjEwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8cmVjdCB4PSIxMCIgeT0iMTAiIHdpZHRoPSIxNTAiIGhlaWdodD0iNjAiIGZpbGw9IiMyMjg2M2EiIHN0cm9rZT0iIzAwMCIgc3Ryb2tlLXdpZHRoPSIyIiAvPgogIDx0ZXh0IHg9IjIwIiB5PSI0NSIgZmlsbD0id2hpdGUiIGZvbnQtc2l6ZT0iMTYiPkRhdGFVUkkgT0s/PC90ZXh0Pgo8L3N2Zz4=" alt="test" />
