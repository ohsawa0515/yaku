# yaku

[English](README.md) | 日本語

[![PyPI](https://img.shields.io/pypi/v/yaku)](https://pypi.org/project/yaku/) [![Python](https://img.shields.io/pypi/pyversions/yaku)](https://pypi.org/project/yaku/)

コマンド出力を翻訳する、完全オフラインのフィルタです。翻訳するのは文章の部分だけで、それ以外は原文のまま残します。

識別子、フラグ、パス、引用符で囲まれた文字列は変わりません。モデルに渡す前に退避し、翻訳後に元へ戻すためです。ネットワーク通信も API キーも不要で、データがマシンの外に出ることはありません。

## インストール

```console
uv tool install yaku
# または
pipx install yaku

yaku setup --lang ja
```

`yaku setup` は [FuguMT](https://huggingface.co/staka/fugumt-en-ja) を固定したリビジョンで取得し、62 MB の int8 モデルに変換します。モデルは CC BY-SA 4.0 のため、同梱していません。変換には torch が必要ですが、yaku の依存には含めていません。そのため変換は使い捨ての環境で行い、その作成に [uv](https://docs.astral.sh/uv/) を使います。

`yaku setup` の実行には uv が必要です。uv を `PATH` 上に入れてから実行してください。変換では torch などのパッケージ (数 GB) を uv のキャッシュに取得します。完了後に `uv cache clean` を実行すると容量を回収できます。

Python 3.15 では、sentencepiece のビルド済み wheel がまだ公開されていません。3.15 で入れる場合は、 `pipx install yaku --python python3.14` のように古いバージョンを明示してください。

## 動作環境

- ディスク 200 MB (`yaku setup` 中は一時的に約 6 GB)
- メモリ 最大 800 MB

## 使い方

```console
terraform plan 2>&1 | yaku
man tar | yaku
kubectl describe pod web | yaku
pbpaste | yaku
```

主なオプションは次のとおりです。

| オプション | 説明 |
| --- | --- |
| `--lang ja` | 翻訳先の言語です。モデルと閾値も、これに合わせて切り替わります。標準以外の言語をセットアップしたときに使います。 |
| `--fallback both\|original\|mark` | 品質検査に通らなかった行の出力方法です。`both` は原文の下に訳を付け (標準)、`original` は原文だけ、`mark` は訳の先頭に `*` を付けて出力します。疑わしい訳を表示したくないときは `original` を使います。 |
| `--show-reason` | 検査に通らなかった理由を付けます。プレースホルダの消失なのか、長さ比が想定外なだけなのかを確認したいときに使います。 |
| `--stats` | 集計を stderr に出力します。規則やオプションを変えた前後で、翻訳された行と検査に通らなかった行の数を比べるときに使います。 |
| `--show-paths` | モデル、キャッシュ、設定、規則の場所を表示して終了します。yaku が保持するファイルを探したり、削除したりするときに使います。 |
| `--dry-run` | モデルを読み込まず、行の分類とマスクの結果を表示します。入力に対して規則がどう働くかを、すばやく確認するときに使います。 |
| `--join` / `--no-join` | 折り返し行の自動判定を上書きします。文が行末で途切れるなら `--join`、別々の行が結合されてしまうなら `--no-join` を使います。 |
| `--width N` | 翻訳結果を N 桁で折り返します。出力がターミナルの幅を超えるときに使います。 |
| `--mask-off NAME,...` | 名前を指定してマスク規則を無効にします。規則が、翻訳したい部分まで退避してしまうときに使います。 |
| `--mask-on NAME,...` | `VERSION` など、標準では無効のマスク規則を有効にします。バージョン番号が訳で変わってしまうときに使います。 |
| `--rules-dir PATH` | 追加の規則を、このディレクトリから読み込みます。yaku がまだ対応していないツールの規則を試すときに使います。 |
| `--no-cache` | 翻訳キャッシュを読み書きしません。速度を計測するときや、オプションを変えて訳し直したいときに使います。 |
| `--length-penalty N` | ビームサーチの長さペナルティです (標準は 1.5)。1 より大きいと、短い訳より完全な訳を優先します。訳から節が抜けるときに上げます。 |
| `--device NAME` | 推論に使うデバイスです (標準は `cpu`)。ご利用の CTranslate2 が別のデバイスに対応しているときだけ変更します。 |
| `--compute-type TYPE` | CTranslate2 の計算型です (標準は `int8`)。モデルが int8 で保存されているため、変更が必要になることはまれです。 |
| `--threads N` | 推論のスレッド数です (標準は 0 で、自動で決まります)。他の処理に CPU を残したいときに下げます。 |

## 仕組み

```
stdin
  ↓ ANSI エスケープの除去
  ↓ 解析パス             折り返された文章かどうかを判定
  ↓ 分類                 そのまま出力 / コマンド例 / 翻訳対象
  ↓ 結合                 折り返された文を再構成
  ↓ マスク               識別子を T1, T2, ... に置き換え
  ↓ 分割                 文単位に戻す
  ↓ キャッシュ           正規化したマスク後の文をキーにする
  ↓ 翻訳                 CTranslate2 + SentencePiece
  ↓ 検査                 プレースホルダの消失、長さ比、反復
  ↓ 復元                 識別子を元に戻す
stdout
```

価値の大部分は次の 2 つにあります。

マスクは、テキストをモデルに見せないためのものではありません。`aws_instance.web_server_01` のような文字列は、系列変換モデルが学習時に見ていない形なので、その周辺で誤った出力を生みます。`T1 will be created` は通常の英文なので、きれいに訳せます。マスクによってモデルへの入力はトークン数で 5 から 10 パーセント減り、プレースホルダが戻ってこないことが、節が訳抜けしたことを確実に示す唯一の手がかりになります。

品質検査があるのは、訳抜けを防げないからです。各行を翻訳後に検査し、疑わしいものは通知なく置き換えず、原文を併記して表示します。

## 制約

- 訳質は 60M パラメータのモデルの範囲にとどまり、大規模言語モデルには及びません。
- 訳抜けはなくせず、検出できるだけです。man ページでは翻訳した行の 5 から 9 パーセントほどが検査に引っかかります。その中には、本当に訳が抜けたものと、日本語が長さ比の想定より短くなっただけのものがあります。
- 行を結合するかどうかは、入力全体に対して 1 回だけ判定します。1 行 1 記録の出力の中でも、折り返し幅まで埋まった行からなる段落は再結合しますが、折り返し位置の直後が大文字で始まる語の場合は分かれたままになります。
- 日本語の出力で、復元した識別子の前後の空白が欠けることがあります。

## 言語の追加

`--lang` はモデルと、計測した定数をまとめて切り替えます。新しい言語には、モデルだけでなくプロファイルが必要です。

1. CTranslate2 に変換できるモデルを選びます（Marian と OPUS-MT は問題なく変換できます）。
2. `uv run tools/check_placeholders.py` でプレースホルダの形式を選びます。
3. `uv run tools/eval_translate.py` で長さ比の範囲を計測します。
4. `src/yaku/rules/target/<lang>.toml` を書きます。

## 開発

```console
uv sync
export YAKU_MODELS_DIR=models     # インストール済みではなく、チェックアウト内のモデルを使う
uv run pytest
uv run ruff check src tests tools && uv run ruff format src tests tools
uv run tools/measure_wrap.py captured-output.txt
uv run tools/eval_translate.py captured-output.txt
```

規則は `src/yaku/rules/` に TOML で置いています。独自の規則は `~/.config/yaku/rules/` に追加するか、`--rules-dir` でディレクトリを指定します。同梱の規則を直接編集することはありません。

## ライセンス

MIT です。標準のモデルである [FuguMT](https://huggingface.co/staka/fugumt-en-ja) は CC BY-SA 4.0 で、別途ダウンロードします。
