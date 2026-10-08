# cleanup-stage-one.md

# 第一段階：旧アシスタント構成の整理

対象: [Ironmate #77](https://github.com/myon-bioinformatics/Ironmate/issues/77)。
移管先PR: [mcp-toolcall-lab #104](https://github.com/myon-bioinformatics/mcp-toolcall-lab/pull/104)。先に取り込む。

棚卸し基準: Ironmate `1281553`、mcp-toolcall-lab `e403593` のmain。
この段階では新製品・新しい試作ディレクトリ構成は導入しない。

| 対象 | 処置 | 理由・移管先 |
| --- | --- | --- |
| `gradio_galleria.py` | mcp-toolcall-labへ移管 | 既存vendored ASCII/Markdownとloaderを再利用。任意のGradio extraで起動。古いimportを修正し、callbackと実UI構築を検証 |
| `file_finder.py` | 独立ファイルを削除 | 利用者は旧画面のみ。移管先の小さなviewerに走査を集約し、JSON拡張子・隠しディレクトリ・symlinkを整理 |
| `i_am_ironmate.py`, `llm_launchpad.py`, `llm_loader.py` | 削除 | 旧モデルロード・量子化・キャラクターREPL。試作検証に必須でなく、lab側の既存モデル実験へ重複移植しない |
| `template_store.py`, `templates_ascii/`, `templates_prompt/` | 削除 | 旧キャラクター資産と専用loader。汎用ASCIIテンプレートは独立済みライブラリに残る |
| `requirements.txt` | 必須依存なし | torch / transformers / accelerate / bitsandbytes / Gradio / PyYAMLをコアから除去。テストのPyYAMLと任意MCPのFastMCPは専用requirementsに維持 |
| `repository_metadata*.py`, `python_artifact_provenance.py`, `provenance.py` | 維持 | 他repoが利用する既存の共有契約・producer |
| GitHub/ニコニコadapter・catalog・MCP・PR/comment consumer | 維持 | フィクスチャ付きの試作と実利用経路。親のgh_ops / gh_identityを利用 |
| `vendor/`, `vendor.lock.json`, provenance | 維持 | 提供元のソース・LICENSE・固定identity。親のvendor_sync / vendor_stageを継続使用 |
| `scripts/`, `tests/`, CI / Pages | 維持 | JUnit・共通証跡・診断ページ・consumer表示の回帰経路 |
| README / Pages入口 / CONTRIBUTING | 更新 | 廃止した起動例と旧目的を除去 |

## 横断確認と順序

1. ascii_artistの汎用形状・組み込みテンプレート、markdownの保存・読込・見出し抽出は独立済み。コアの再移植は不要。
2. markdownには既存Gradio分析demoもあるが、複数ライブラリを組み合わせるgalleriaは既存の両vendorを持つmcp-toolcall-labへ置く。同repoのMCPやモデル実験には依存させない。
3. 移管先でcallback・実Gradio構築を確認し、そのPRを取り込んでからIronmateの削除PRを取り込む。新規利用者に削除済みコマンドを案内しない。
4. Ironmateのpytest/JUnitと既存CIを確認する。metadata、Pagesのcatalog URL、vendor契約は変更しない。

旧ソースは [整理前commit](https://github.com/myon-bioinformatics/Ironmate/tree/1281553) から確認できる。削除ファイルのアーカイブコピーは現行ツリーに残さない。

## この後に決めること

候補の新しい配置・自動化は利用者の次段階の構想に合わせる。
現段階では既存テストで再現条件・対象SHA・実行結果を記録し、提供元の
不具合はそのrepoへ還元する。共有需要と責務が明確になるまでは候補を
保持してよく、独立repo化を完了条件にはしない。
