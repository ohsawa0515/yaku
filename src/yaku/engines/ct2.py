"""CTranslate2 backend with SentencePiece tokenisation.

The transformers tokeniser is deliberately not used: it pulls in torch, and
its slow tokenisers were removed in version 5, which is what Marian models
need. SentencePiece reads the same .spm files directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import ctranslate2
import sentencepiece as spm

EOS = "</s>"


class EngineError(Exception):
    """The model directory is missing or incomplete."""


@dataclass
class CT2Engine:
    """Translates batches of plain text.

    Decoding options are bound here rather than passed per call, so callers
    never depend on parameters that only this backend has.
    """

    translator: ctranslate2.Translator
    source_sp: spm.SentencePieceProcessor
    target_sp: spm.SentencePieceProcessor
    beam: int = 5
    # Above 1.0 the beam search stops favouring short hypotheses. A decoder
    # that drops a clause produces exactly such a hypothesis: at 1.5, 19 of
    # 45 hand-labelled drops in held-out manual pages came back complete,
    # with no new drop among the segments that were already complete.
    length_penalty: float = 1.5
    max_batch_tokens: int = 2048
    max_decoding_length: int = 512

    @classmethod
    def load(
        cls,
        model_dir: Path,
        beam: int = 5,
        length_penalty: float = 1.5,
        device: str = "cpu",
        compute_type: str = "int8",
        threads: int = 0,
    ) -> CT2Engine:
        if not (model_dir / "model.bin").is_file():
            raise EngineError(f"no model in {model_dir}")

        source_path = model_dir / "source.spm"
        if not source_path.is_file():
            candidates = sorted(model_dir.glob("*.spm"))
            if not candidates:
                raise EngineError(f"no .spm tokeniser in {model_dir}")
            source_path = candidates[0]

        target_path = model_dir / "target.spm"
        if not target_path.is_file():
            target_path = source_path

        return cls(
            translator=ctranslate2.Translator(
                str(model_dir),
                device=device,
                compute_type=compute_type,
                inter_threads=1,
                intra_threads=threads,
            ),
            source_sp=spm.SentencePieceProcessor(str(source_path)),
            target_sp=spm.SentencePieceProcessor(str(target_path)),
            beam=beam,
            length_penalty=length_penalty,
        )

    def translate(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        batch = [[*self.source_sp.encode(t, out_type=str), EOS] for t in texts]
        results = self.translator.translate_batch(
            batch,
            beam_size=self.beam,
            length_penalty=self.length_penalty,
            batch_type="tokens",
            max_batch_size=self.max_batch_tokens,
            max_decoding_length=self.max_decoding_length,
            replace_unknowns=True,
        )
        return [self.target_sp.decode([t for t in r.hypotheses[0] if t != EOS]) for r in results]
