# Jev vs Microsoft-Decision-1 Benchmark

判断特化型AI（System 1モデル）である **TypeSafe Jev** と **Microsoft-Decision-1** の日本語処理能力および「確信度（Confidence）のキャリブレーション」を比較検証するためのベンチマークスイートです。

AI Nexus事業の技術ブランディング記事企画の一環として、同一の日本語問い合わせ分類タスクを用いて両モデルの分類精度、確信度（Probability）、レイテンシ（処理時間）を計測します。

---

## 📁 ディレクトリ構成

```text
jev-vs-decision1-benchmark/
├── .env.example            # 環境変数のテンプレート設定ファイル
├── .gitignore              # 機密情報・中間成果物の除外設定
├── requirements.txt        # 必要なPythonライブラリ一覧
├── evaluate_models.py      # 比較検証・評価実行スクリプト
├── README.md               # 本ドキュメント（実行手順書）
└── data/
    └── test_data.json      # 日本語問い合わせテストケース（計12件）
```

---

## 🎯 検証タスク定義

両モデルに対して以下の共通フォーマットでリクエストを送信します。

- **問い（Question）**: 「このユーザー問い合わせの主目的を分類してください」
- **判定タイプ**: `choice`（多肢選択）
- **選択肢（Options）**:
  - `billing`: 料金・請求・見積もり
  - `contract`: 契約更新・プラン変更・解約手続き
  - `technical`: 操作方法・不具合・エラー報告
  - `other`: どれにも該当しない、または判断が困難

---

## 📊 テストデータセット構成（全80件 / 各20問）

[`data/test_data.json`](data/test_data.json) に定義されている4カテゴリ・計80ケースの構成です。
企業の経営陣、プロダクトマネージャー、CS（カスタマーサポート）責任者が日々の業務で直面する「リアルな問い合わせ実務」を想定して設計されています。

| カテゴリ | 件数 / ID | 期待ラベル | 主な実務シチュエーション例 | 評価の着眼点 |
|---|---|---|---|---|
| **Category A: 典型的な明瞭ケース** | 20件<br>(A-01〜A-20) | `billing`<br>`technical`<br>`contract` | 領収書再発行・インボイス対応・クレカ更新・SAML認証設定・2FA不着・CSV文字化け・年間契約移行・名義変更 など | **期待確信度 0.90 以上**<br>主目的が明瞭な日常的問い合わせに対して、迷いなく高確信度で正しいカテゴリにルーティングできるか。 |
| **Category B: 複数意図の重複・境界線ケース** | 20件<br>(B-01〜B-20) | `technical or billing`<br>`contract or billing`<br>`contract or technical` など | 「障害時間の返金とSLA減額」「アカウント数拡大の試算とプラン変更」「退会前のデータ一括エクスポート」「プラン移行時の権限引継ぎ」「未払い停止時の即時復旧」など | **確信度 0.50〜0.65 分散**<br>複数部門（経理・技術・営業）に跨る複合課題に対し、無理に1点に偏らず過剰確信（Overconfidence）が抑制されているか。 |
| **Category C: 日本語特有の表現（皮肉・婉曲・感情）** | 20件<br>(C-01〜C-20) | `technical`<br>`billing`<br>`contract` | 「画面真っ白で仕事にならない（皮肉）」「対応は丁寧だが請求金額が1桁違う」「誰も使っておらず付き合い方を悩んでいる」「他社への乗り換え提案を受けている」「SOC2認証レポートがないと稟議が通らない」など | **文脈解釈力と真の意図抽出**<br>丁寧なクッション言葉や皮肉、感情的な前置きに惑わされず、ユーザーが真に求めているアクション（不具合調査、減額、解約等）を見抜けるか。 |
| **Category D: 範囲外・敵対的入力（インジェクション対策）** | 20件<br>(D-01〜D-20) | `other`<br>（すべて該当なし） | 営業売り込み・時候の挨拶・誤送信メール・Prompt Injection（システム命令上書き、ロールプレイ誘導、プロンプト開示要求）・文字化け・法律税務相談 など | **ガードレール耐性とノイズ排除**<br>SaaSサポート業務外の問い合わせや悪意ある攻撃プロンプトを確実に `other` として弾き、誤分類しないか。 |

---

## 🚀 セットアップ手順

### 1. 仮想環境の準備とパッケージインストール

プロジェクト直下に Python 仮想環境を作成し、必要なライブラリをインストールします。

```bash
# 仮想環境の作成
python3 -m venv .venv

# 仮想環境のアクティベート
source .venv/bin/activate

# 依存ライブラリのインストール
pip install -r requirements.txt
```

### 2. 環境変数の設定 (`.env`)

`.env.example` をコピーして `.env` を作成し、各モデルの API エンドポイントおよび API キーを設定します。

```bash
cp .env.example .env
```

`.env` の内容を編集します：

```env
# TypeSafe Jev API 設定
# ※ 'https://api.typesafe.ai' または 'https://api.typesafe.ai/v1/systemone' のどちらでも自動正規化されます
JEV_API_URL=https://api.typesafe.ai/v1/systemone
JEV_API_KEY=your_actual_jev_api_key

# Microsoft-Decision-1 API 設定 (Microsoft Foundry)
# ※ 「詳細」タブの完全URL (末尾 /v1/systemone) でも、
#   「モデルを呼び出す」コード例の base_url (末尾 /providers/microsoft) でも、
#   どちらを貼り付けてもスクリプト側で自動的に正規化されます。
DECISION1_API_URL=https://<your-resource-name>.services.ai.azure.com/providers/microsoft/v1/systemone
DECISION1_API_KEY=your_actual_decision1_api_key

# タイムアウト時間（秒）
REQUEST_TIMEOUT_SECONDS=15
```

> **注意**: `.env` や実行結果 `results.csv` は `.gitignore` に指定されており、Git の公開リポジトリにはコミットされません。機密情報がコミットされないようご注意ください。

---

## 🧪 実行方法

### 1. 接続確認テスト（事前診断）

本番評価（80件）を回す前に、両モデルのAPI疎通・認証キーが正常に通るかを1問のテストリクエストで事前確認できます。

```bash
# 両モデルの接続テストを一括実行
python3 test_connection.py

# 片方のみテストしたい場合
python3 test_connection.py --model jev
python3 test_connection.py --model decision1
```

### 2. 通常実行（実APIによる本番評価）

接続確認が完了したら、以下のコマンドで80件のベンチマークを実行します。

```bash
python3 evaluate_models.py
```

### ドライラン実行（モック動作確認）

実APIにリクエストを送らず、テストデータの読み込みやCSV出力形式の整合性を確認したい場合に利用します。

```bash
python3 evaluate_models.py --dry-run
```

### コマンドライン引数オプション

```bash
python3 evaluate_models.py \
  --data-file data/test_data.json \
  --output custom_results.csv \
  --dry-run
```

- `--data-file`: テストデータJSONのパス（デフォルト: `data/test_data.json`）
- `--output`: 出力先CSVファイルのパス（デフォルト: `results.csv`）
- `--dry-run`: モックデータを用いた検証モード
- `--summary [CSV_PATH]`: 実行結果CSVから正解率・速度・激論ケースのMarkdownサマリー表を集計出力

### 集計サマリーレポートの生成

実行完了時に自動でサマリーレポートが表示されますが、過去の出力CSVや公式検証データを再集計したい場合は以下でいつでも確認できます。

```bash
python3 evaluate_models.py --summary data/benchmark_results.csv
```

---

## 📈 出力フォーマット (`results.csv`)

実行完了後、指定したパス（デフォルト: `results.csv`）に以下の全20カラム構成で出力されます。ExcelやGoogleスプレッドシートでの文字化けを防ぐため、UTF-8 (BOM付き) で保存されます。

| カラム名 | 説明 | 例 | 分析・記事での活用法 |
|---|---|---|---|
| `ID` | テストケースID | `B-01` | 個別問題の参照キー |
| `Category` | テストカテゴリ | `Category B` | カテゴリごとの集計グループ |
| `Input_Text` | ユーザーの問い合わせ入力文 | `システム障害で半日使えなかった…` | 定性分析用の入力原文 |
| `Input_Length` | 入力文字数 | `37` | 文字数とレイテンシの相関分析 |
| `Expected` | 期待される分類ラベル（複合含む） | `technical or billing` | 正解判定の基準 |
| `Models_Agree` | 2モデルの判断が一致したか | `TRUE` / `FALSE` | **意見が割れた注目ケースの抽出** |
| `Jev_Result` | Jev の1位分類結果 | `technical` | 主分類ラベル |
| `Jev_Is_Expected` | Jev が期待値通りに判定したか | `TRUE` / `FALSE` | **Jev の正解率（Accuracy）集計** |
| `Jev_Confidence` | Jev の確信度（1位の確率） | `0.528` | キャリブレーション・確信度分析 |
| `Jev_Margin` | 1位と2位の確率差（迷い度） | `0.116` | **接戦度（小さいほど境界線と認識）** |
| `Jev_Second_Result` | Jev の2位候補ラベル | `billing` | 対抗馬として捉えた第2の意図 |
| `Jev_Probabilities` | 全選択肢の確率分布 | `technical:0.528 \| billing:0.412...` | **確率配分・過剰確信の可視化グラフ** |
| `Jev_Latency_ms` | Jev の処理時間（ミリ秒） | `138.20` | 推論速度・応答性の評価 |
| `Decision1_Result` | Decision-1 の1位分類結果 | `technical` | 主分類ラベル |
| `Decision1_Is_Expected` | Decision-1 が期待値通りか | `TRUE` / `FALSE` | **Decision-1 の正解率集計** |
| `Decision1_Confidence` | Decision-1 の確信度（1位の確率） | `0.575` | キャリブレーション・確信度分析 |
| `Decision1_Margin` | 1位と2位の確率差（迷い度） | `0.210` | 接戦度（Jevとの迷い方の比較） |
| `Decision1_Second_Result` | Decision-1 の2位候補ラベル | `billing` | 対抗馬として捉えた第2の意図 |
| `Decision1_Probabilities` | 全選択肢の確率分布 | `technical:0.575 \| billing:0.365...` | 確率配分の可視化グラフ |
| `Decision1_Latency_ms` | Decision-1 の処理時間（ミリ秒） | `155.60` | 推論速度・応答性の評価 |

### エラーハンドリング仕様
- **APIキー未設定時**: プログラムは強制終了せず、結果欄に `SKIPPED: Missing <KEY>` と記録して次のケースへ進みます。
- **タイムアウト・通信エラー時**: `ERROR: TIMEOUT` や `ERROR: HTTP_500` などのエラー概要が結果欄に記録され、全体の処理を最後まで継続します。

