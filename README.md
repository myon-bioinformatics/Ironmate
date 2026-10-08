# Ironmate

Pythonを中心に、文書・画像などの**内容や属性の変換・置換**を検証するプロジェクトです。
PPTXの文字・色・矢印属性の置換、画素／パレットに基づくドット表現を今後の対象とします。
要件は [Issue #80](https://github.com/myon-bioinformatics/Ironmate/issues/80)、
ドット表現の試作は [PR #79](https://github.com/myon-bioinformatics/Ironmate/pull/79) で追跡します。
これらの計画と、このmainに実装済みの機能は区別してください。

## 責務

- 共通GitHub操作・vendor管理は [親リポジトリ](https://github.com/myon-bioinformatics/myon-bioinformatics) と [gh_identity](https://github.com/myon-bioinformatics/gh_identity) を参照します。
- 旧GitHubカタログ、MCPサーバー、repository metadata／diagnostics、成果物provenance生成の試作は廃止しました。すべての旧APIが移管先に互換実装されているという意味ではありません。
- source／niconico実装とテストの移管先は [mcp-toolcall-lab PR #108](https://github.com/myon-bioinformatics/mcp-toolcall-lab/pull/108) です。先に移管先をマージしてから、この削除をマージします。API／MCPの差分吸収の設計は同repo #107で扱います。
- `vendor/` と `vendor.lock.json` はconsumerの固定コピーです。今回の整理では内容・pinを変更していません。
- `scripts/sync_vendor_provenance.py` は既存CIのvendor証跡をlockから投影する補助処理として残します。旧ルートの `provenance.py` とは別物です。

詳しくは [整理とvendor調査](docs/cleanup-stage-two.md)、[vendor CI](docs/vendor-automation.md) を参照してください。

## ローカルテスト

```sh
python -m pip install -r tests/requirements.txt
git clone https://github.com/myon-bioinformatics/xprobe.git build/shared
git -C build/shared checkout 7e7015b2df69ad446b968f6fa49711b5b1dbdd3f
git clone https://github.com/myon-bioinformatics/myon-bioinformatics.git .vendor-sync-tools
git -C .vendor-sync-tools checkout 974da5eb9593df652b132e4b0f1a679f67422566
python -m pytest -q -m 'not heavy'
```

xprobeと親のvendorツールはテスト用の別checkoutです。実行時依存として自動取得しません。
今後のpython-pptx等の導入は用途に応じて判断します。
