# ngk2027s

NGK（名古屋合同懇親会）2027Sに関するファイルの置き場所。

このリポジトリの作り方、公開までの穴埋め、公開後の書き換えは [HOWTO.md](HOWTO.md) にまとめてある。

## ディレクトリ構成

```
├── README.md
├── HOWTO.md                                        更新手順
├── connpass_content_day_session.md                 昼の部 connpass 本文
├── connpass_content_day_session_participants.md    昼の部「参加者への情報」
├── connpass_content_evening_session.md             夜の部 connpass 本文
├── connpass_content_evening_session_participants.md 夜の部「参加者への情報」
├── docs                                            GitHub Pages で公開する
│   ├── index.md
│   ├── anti_harassment_policy.md
│   ├── lt_regulation.md
│   ├── sponsors_prospectus.md
│   ├── patron_prospectus.md
│   ├── community_prospectus.md
│   ├── img
│   │   ├── sponsor                                 企業スポンサーのロゴ
│   │   ├── community                               参加コミュニティのロゴ
│   │   └── other                                   準備中画像・グラフなど
│   └── report                                      開催結果報告書・収支報告書（開催後に置く）
└── original                                        提供いただいた原本
    ├── sponsor
    ├── community
    └── other
        └── notice.md                               広報用の告知文面
```

### connpass_content_*.md

connpassイベントページ用のmarkdown。connpass側に編集履歴が残らないため、ここでバージョン管理している。
connpassを更新したらこちらにも反映する。

### docs/

GitHub Pagesで公開しているディレクトリ。markdownファイルはhtmlファイルに変換される。

URLは https://nagoya-godo-konshinkai.github.io/ngk2027s/

connpassから画像を参照するときは、このURLから始まる絶対URLを書く。connpassはリポジトリ内の相対パスを解決できない。

#### docs/img/

connpassイベントページから参照する画像などの置き場所。

* sponsor/ : 企業スポンサー用
* community/ : コミュニティ参加用
* other/ : 準備中画像、前回参加者アンケートのグラフなど

### original/

企業スポンサーやコミュニティ参加から直接提供いただいたファイルの置き場所。
ここから適切な解像度へリサイズしたものを `docs/img/` に置く。

* sponsor/ : 企業スポンサー用
* community/ : コミュニティ参加用
* other/ : 運営が作成した告知素材
