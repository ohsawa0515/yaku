# yaku

English | [日本語](README.ja.md)

[![PyPI](https://img.shields.io/pypi/v/yaku)](https://pypi.org/project/yaku/) [![Python](https://img.shields.io/pypi/pyversions/yaku)](https://pypi.org/project/yaku/)

Fully offline translator for command output. Only the prose gets translated; everything else is left verbatim.

Identifiers, flags, paths and quoted strings survive unchanged, because they are moved out of the way before the model sees the text and put back afterwards. No network access, no API keys, no data leaving the machine.

## Install

```console
uv tool install yaku    # or: pipx install yaku
yaku setup --lang ja
```

`yaku setup` downloads [FuguMT](https://huggingface.co/staka/fugumt-en-ja) at a pinned revision and converts it to a 62 MB int8 model. The model is not bundled because it is CC BY-SA 4.0. The converter needs torch, which yaku does not depend on, so the conversion runs in a throwaway environment created with [uv](https://docs.astral.sh/uv/).

`yaku setup` requires uv. Install it and put it on `PATH` before running the command.

## Use

```console
terraform plan 2>&1 | yaku
man tar | col -bx | yaku
kubectl describe pod web | yaku
pbpaste | yaku
```

Useful options:

| Option | Effect |
| --- | --- |
| `--lang ja` | target language, which also selects the model and thresholds |
| `--fallback both\|original\|mark` | what to emit for a line that fails the quality check |
| `--show-reason` | append why a line failed |
| `--stats` | write a summary to stderr |
| `--dry-run` | show classification and masking without loading a model |
| `--join` / `--no-join` | override the automatic wrapped-line detection |
| `--width N` | wrap the translated text |
| `--mask-off NAME,...` | disable mask rules |

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
