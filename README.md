# yaku

English | [日本語](README.ja.md)

[![PyPI](https://img.shields.io/pypi/v/yaku)](https://pypi.org/project/yaku/) [![Python](https://img.shields.io/pypi/pyversions/yaku)](https://pypi.org/project/yaku/)

Fully offline translator for command output. Only the prose gets translated; everything else is left verbatim.

Identifiers, flags, paths and quoted strings survive unchanged, because they are moved out of the way before the model sees the text and put back afterwards. No network access, no API keys, no data leaving the machine.

## Install

```console
uv tool install yaku
# or
pipx install yaku

yaku setup --lang ja
```

`yaku setup` downloads [FuguMT](https://huggingface.co/staka/fugumt-en-ja) at a pinned revision and converts it to a 62 MB int8 model. The model is not bundled because it is CC BY-SA 4.0. The converter needs torch, which yaku does not depend on, so the conversion runs in a throwaway environment created with [uv](https://docs.astral.sh/uv/).

`yaku setup` requires uv. Install it and put it on `PATH` before running the command. The conversion downloads torch and related packages (a few GB) into the uv cache; run `uv cache clean` afterwards to reclaim the space.

sentencepiece has no prebuilt wheel for Python 3.15 yet. If you install with Python 3.15, pick an older interpreter explicitly, for example `pipx install yaku --python python3.14`.

## Requirements

- Disk: 200 MB (about 6 GB temporarily during `yaku setup`)
- Memory: up to 800 MB

## Use

```console
terraform plan 2>&1 | yaku
man tar | yaku
kubectl describe pod web | yaku
pbpaste | yaku
```

Useful options:

| Option | Description |
| --- | --- |
| `--lang ja` | Target language. It also selects the model and the thresholds. Use it when you have set up a language other than the default. |
| `--fallback both\|original\|mark` | What to print for a line that fails the quality check. `both` prints the original with the translation below it (default), `original` prints only the original, and `mark` prints the translation prefixed with `*`. Use `original` when you would rather see no doubtful translation at all. |
| `--show-reason` | Append why a line failed the quality check. Use it to see whether a flagged line lost a placeholder or only has an unusual length ratio. |
| `--stats` | Write a summary to stderr. Use it to compare how many lines were translated or flagged after changing a rule or option. |
| `--show-paths` | Print where the model, cache, config and rules are, then exit. Use it to find or delete the files yaku keeps. |
| `--dry-run` | Show how each line is classified and masked, without loading the model. Use it to check a rule against your input quickly. |
| `--join` / `--no-join` | Override the automatic detection of wrapped lines. Use `--join` if sentences are cut at line breaks, or `--no-join` if separate lines are being merged. |
| `--width N` | Wrap the translated text at N columns. Use it when the output runs wider than your terminal. |
| `--mask-off NAME,...` | Disable mask rules by name. Use it when a rule hides text that you want translated. |
| `--mask-on NAME,...` | Enable mask rules that are off by default, such as `VERSION`. Use it when version numbers get changed in the translation. |
| `--rules-dir PATH` | Load extra rules from this directory. Use it to try rules for a tool that yaku does not know yet. |
| `--no-cache` | Do not read or write the translation cache. Use it when measuring speed, or to get a fresh translation after changing options. |
| `--length-penalty N` | Beam search length penalty (default 1.5). Values above 1 favour complete translations over short ones. Raise it if clauses are dropped from translations. |
| `--device NAME` | Inference device (default `cpu`). Change it only if your CTranslate2 build supports another device. |
| `--compute-type TYPE` | CTranslate2 compute type (default `int8`). Rarely needed, because the model is stored as int8. |
| `--threads N` | Number of inference threads (default 0, chosen automatically). Lower it to leave CPU for other work. |

## How it works

```
stdin
  ↓ strip ANSI escapes
  ↓ analysis pass        decides whether lines are wrapped prose
  ↓ classify             pass through / command example / translatable
  ↓ join                 reassemble wrapped sentences
  ↓ mask                 identifiers become T1, T2, ...
  ↓ split                back into sentences
  ↓ cache                keyed on the normalised masked text
  ↓ translate            CTranslate2 + SentencePiece
  ↓ check                lost placeholders, length ratio, repetition
  ↓ unmask               identifiers restored
stdout
```

Two parts carry most of the value.

**Masking** is not about withholding text. A sequence model that has never seen `aws_instance.web_server_01` in training will hallucinate around it; `T1 will be created` is ordinary English and translates cleanly. Masking also cuts the request by 5 to 10 percent in tokens, and a placeholder that fails to come back is the only reliable sign that a clause was dropped.

**The quality check** exists because dropped clauses cannot be prevented. Each line is verified afterwards, and anything suspect is shown with its original text rather than silently replaced.

## Limits

- Translation quality is bounded by a 60M parameter model. It will not match a large language model.
- Dropped clauses cannot be eliminated, only detected. Roughly 5 to 9 percent of translated lines in manual pages are flagged, of which some are real drops and some are Japanese simply being more compact than the ratio check allows.
- Whether lines are joined is decided once for the whole input. Inside record-per-line output, a paragraph is still rejoined when its lines are filled to the wrap column, but a wrap that lands just before a capitalised word is left split.
- Japanese output sometimes loses a space around a restored identifier.

## Adding a language

`--lang` switches the model and the measured constants together, so a new language needs a profile, not just a model.

1. Pick a CTranslate2-compatible model (Marian and OPUS-MT convert cleanly).
2. `uv run tools/check_placeholders.py` to choose a placeholder format.
3. `uv run tools/eval_translate.py` to measure the length ratio bounds.
4. Write `src/yaku/rules/target/<lang>.toml`.

## Development

```console
uv sync
export YAKU_MODELS_DIR=models     # use the checkout's model, not the installed one
uv run pytest
uv run ruff check src tests tools && uv run ruff format src tests tools
uv run tools/measure_wrap.py captured-output.txt
uv run tools/eval_translate.py captured-output.txt
```

Rules live in `src/yaku/rules/` as TOML. Users can add their own in `~/.config/yaku/rules/` or point `--rules-dir` at a directory; shipped rules are never edited in place.

## Licence

MIT. The default model, [FuguMT](https://huggingface.co/staka/fugumt-en-ja), is CC BY-SA 4.0 and is downloaded separately.
