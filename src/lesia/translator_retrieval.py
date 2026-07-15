import asyncio
import re
from dataclasses import dataclass
from typing import Callable
import xml.etree.ElementTree as ET
from loguru import logger
from lesia.helpers import calculate_checksum, extract_translated_from_response
from pathlib import Path
from lesia.enums import ChunkType, DocumentType, Language
from lesia.translation_cache.translation_cache import TranslationCache, TranslationCacheCsv
from lesia.translator import finalize_prompt, finalize_xml_prompt, _prepare_prompt_for_language, _prepare_prompt_for_vocab_list, _prepare_prompt_for_content_type, _prepare_prompt_for_translation_example
from lesia.vocab_list import VocabList
from lesia.xml_manipulator_mod.xml import reconstruct_from_xml, verify_placeholders
from lesia.xml_manipulator_mod.mod import chunk_contains_ph_only, chunk_to_xml, chunk_to_xml_with_placeholders, code_to_xml
from lesia.xml_manipulator_mod.typst import parse_typst
from lesia.prompts import xml_translation_prompt
from lesia.translator import _ask_gemini_model
from lesia.prompts import prompt4, xml_with_previous_translation_prompt
from unified_model_caller import LLMCaller
from unified_model_caller.errors import ApiCallError
from lesia.errors import ChunkTranslationFailed, PlaceholderVerificationError
try:
    from unified_model_caller.errors import ModelOverloadedError
except ImportError:  # pragma: no cover - unified_model_caller may not expose the new error yet
    class ModelOverloadedError(ApiCallError):
        """Fallback stub when unified_model_caller doesn't expose ModelOverloadedError."""
        pass


@dataclass
class TranslationStats:
    """Aggregated statistics for a single file translation run."""
    chunks_from_cache: int = 0
    chunks_translated: int = 0
    chunks_passed_to_reasoning: int = 0
    chunks_failed: int = 0

    @property
    def total(self) -> int:
        return self.chunks_from_cache + self.chunks_translated + self.chunks_failed

    def __add__(self, other: "TranslationStats") -> "TranslationStats":
        return TranslationStats(
            chunks_from_cache=self.chunks_from_cache + other.chunks_from_cache,
            chunks_translated=self.chunks_translated + other.chunks_translated,
            chunks_passed_to_reasoning=self.chunks_passed_to_reasoning + other.chunks_passed_to_reasoning,
            chunks_failed=self.chunks_failed + other.chunks_failed,
        )


def is_whitespace(text: str) -> bool:
    return not text or text.isspace()


TYPST_INTERNAL_SUBCHUNK_MAX_CHARS = 2000


def _split_long_text_by_boundary(long_text: str, max_chars_num: int) -> list[str]:
    """Split an oversized plain-text fragment near natural boundaries.

    Preference order for split points: paragraph break, newline, sentence space,
    then generic whitespace; if none exists, perform a hard cut at max length.
    """
    if not long_text:
        return []
    if len(long_text) <= max_chars_num:
        return [long_text]

    min_split = max(1, int(max_chars_num * 0.6))
    boundary = re.compile(r"\n\s*\n+|\n|(?<=\.)\s+|\s+")

    pieces: list[str] = []
    rest = long_text
    while len(rest) > max_chars_num:
        candidate = 0
        for match in boundary.finditer(rest[: max_chars_num + 1]):
            split_idx = match.end()
            if split_idx >= min_split:
                candidate = split_idx
        if candidate == 0:
            candidate = max_chars_num
        pieces.append(rest[:candidate])
        rest = rest[candidate:]

    if rest:
        pieces.append(rest)
    return [piece for piece in pieces if piece]


def _split_typst_chunk_for_internal_translation(
    chunk: str,
    max_chars_num: int = TYPST_INTERNAL_SUBCHUNK_MAX_CHARS,
) -> list[str]:
    """Split a Typst chunk into translation subchunks while preserving syntax.

    Rules:
    - Parse the full chunk first into Typst segments (`text` vs non-text).
    - Keep non-text segments (placeholders/syntax/math-like pieces) atomic.
    - Allow splitting only inside oversized `text` segments.
    - Preserve ordering and validate lossless reconstruction.

    If reconstruction fails for any reason, return the original chunk as a
    single element to disable subchunking safely.
    """
    segments = parse_typst(chunk)
    if not segments:
        return [chunk]

    chunk_parts: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    def flush_current() -> None:
        nonlocal current_parts, current_len
        if not current_parts:
            return
        chunk_parts.append("".join(current_parts))
        current_parts = []
        current_len = 0

    for seg_type, seg_content in segments:
        if not seg_content:
            continue

        if len(seg_content) <= max_chars_num:
            if current_parts and current_len + len(seg_content) > max_chars_num:
                flush_current()
            current_parts.append(seg_content)
            current_len += len(seg_content)
            continue

        # Placeholder segments stay atomic to preserve syntax.
        if seg_type != "text":
            flush_current()
            chunk_parts.append(seg_content)
            continue

        text_pieces = _split_long_text_by_boundary(seg_content, max_chars_num)
        for piece in text_pieces:
            if current_parts and current_len + len(piece) > max_chars_num:
                flush_current()
            current_parts.append(piece)
            current_len += len(piece)
            if current_len >= max_chars_num:
                flush_current()

    flush_current()

    if not chunk_parts:
        return [chunk]

    reconstructed = "".join(chunk_parts)
    if reconstructed != chunk:
        return [chunk]

    return chunk_parts

@dataclass
class Meta:
    chunk: str
    src_lang: Language
    tgt_lang: Language
    doc_type: DocumentType
    chunk_type: ChunkType
    vocab: VocabList | None
    rel_path: str

@dataclass
class CodeMeta(Meta):
    chunk: str
    src_lang: Language
    tgt_lang: Language
    doc_type: DocumentType
    chunk_type: ChunkType
    vocab: VocabList | None
    rel_path: str
    prog_lang: str

@dataclass
class WithExampleMeta(Meta):
    chunk: str
    src_lang: Language
    tgt_lang: Language
    doc_type: DocumentType
    chunk_type: ChunkType
    vocab: VocabList | None
    rel_path: str
    ex_src: str
    ex_tgt: str

@dataclass
class PromptContext:
    is_xml: bool
    placeholders: dict[str, str] | None = None

# ====================== Prompt / Strategy layer ===================== #

class TranslateStrategy:
    """Callable bundle: build prompt  → ask LLM → post‑process."""

    def __init__(
        self,
        prompt_builder: Callable[[Meta], tuple[str, PromptContext]],
        call_model: Callable[[str], str],
        postprocess: Callable[[str, PromptContext], str],
    ) -> None:
        self._prompt_builder = prompt_builder
        self._call_model = call_model
        self._post = postprocess

    def set_call_model(self, call_mode: Callable[[str], str]) -> None:
        self._call_model = call_mode

    async def run(
        self,
        params: Meta
    ) -> str:
        prompt, context = self._prompt_builder(params)
        raw = self._call_model(prompt)
        return self._post(raw, context)


# ---- Prompt builders ---------------------------------------------- #

def _plain_prompt_builder(template: str):
    def _builder(params: Meta):
        chunk = params.chunk
        tgt = params.tgt_lang
        src = params.src_lang
        vocab = params.vocab
        p = _prepare_prompt_for_language(template, tgt, src)
        p = _prepare_prompt_for_vocab_list(p, vocab)
        p = finalize_prompt(p, chunk)
        return p, PromptContext(is_xml=False)

    return _builder


def _xml_prompt_builder(doc_type: DocumentType, chunk_type: ChunkType):
    def _builder(params: Meta):
        chunk = params.chunk
        tgt = params.tgt_lang
        src = params.src_lang
        xml_chunk = ""
        placeholders: dict[str, str] = {}
        vocab = params.vocab

        # lang = None
        if chunk_type == ChunkType.Code:
            if isinstance(params, CodeMeta):
                logger.debug("Preparing XML chunk for code translation.")
                xml_chunk, placeholders, _ = code_to_xml(chunk, params.prog_lang)
        else:
            xml_chunk, placeholders = chunk_to_xml_with_placeholders(chunk, chunk_type)

        prompt = xml_translation_prompt
        if isinstance(params, WithExampleMeta) and chunk_type != ChunkType.Code:
            prompt = xml_with_previous_translation_prompt
            ex_src = chunk_to_xml(params.ex_src, chunk_type)
            ex_tgt = chunk_to_xml(params.ex_tgt, chunk_type)
            prompt = _prepare_prompt_for_translation_example(prompt, ex_src, ex_tgt)

        prompt = _prepare_prompt_for_language(prompt, tgt, src)
        def get_content_type() -> str:
            if doc_type == DocumentType.LaTeX:
                return "LaTeX"
            if doc_type == DocumentType.Typst:
                return "Typst"
            if (doc_type == DocumentType.JupyterNotebook and chunk_type == ChunkType.Myst) or doc_type == DocumentType.Markdown:
                return "MyST"
            if doc_type == DocumentType.JupyterNotebook and chunk_type == ChunkType.Code and type(params) is CodeMeta:
                prog_lang = params.prog_lang
                return f"{prog_lang} code"
            else:
                return "any document"
        prompt = _prepare_prompt_for_content_type(prompt, get_content_type())
        prompt = _prepare_prompt_for_vocab_list(prompt, vocab)
        prompt = finalize_xml_prompt(prompt, xml_chunk)
        return prompt, PromptContext(is_xml=True, placeholders=placeholders)

    return _builder

def _identity_prompt_builder():
    def _builder(params: Meta):
        return params.chunk, PromptContext(is_xml=False)

    return _builder

def _xml_postprocess(r: str, ctx: PromptContext) -> str:
    """Extract translated XML, verify all placeholders survived, then reconstruct."""
    xml = extract_translated_from_response(r)
    if ctx.placeholders:
        # Bare whitespace PHs (e.g. lone '\n') are structural line-break markers.
        # The LLM may legitimately collapse them when rephrasing; don't retry over them.
        structural_phs = {k: v for k, v in ctx.placeholders.items() if v.strip()}
        missing, extra = verify_placeholders(xml, structural_phs)
        # Extra IDs that exist in the full placeholder map are whitespace PHs that
        # survived in the XML — that's fine. Only truly hallucinated IDs are a problem.
        real_extra = [e for e in extra if e not in ctx.placeholders]
        if missing or real_extra:
            raise PlaceholderVerificationError(missing, real_extra)
    return reconstruct_from_xml(xml, ctx.placeholders)


async def _call_model_func(text: str) -> str:
    # print("=======================")
    # print("prompt:")
    # print(text)
    return await _ask_gemini_model(text, model_name="gemini-2.0-flash")

def _dont_call_model(text: str) -> str:
    return text

# ---- Strategies map ------------------------------------------------ #
LATEX_STRATEGY   = TranslateStrategy(_xml_prompt_builder(DocumentType.LaTeX, ChunkType.LaTeX), _dont_call_model, _xml_postprocess)
MYST_STRATEGY    = TranslateStrategy(_xml_prompt_builder(DocumentType.JupyterNotebook, ChunkType.Myst), _dont_call_model, _xml_postprocess)
PLAIN_STRATEGY   = TranslateStrategy(_plain_prompt_builder(prompt4), _dont_call_model, lambda r, ctx: extract_translated_from_response(r))
CODE_STRATEGY    = TranslateStrategy(_identity_prompt_builder(), _dont_call_model, lambda r, ctx: r)
MD_STRATEGY      = TranslateStrategy(_xml_prompt_builder(DocumentType.Markdown, ChunkType.Myst), _dont_call_model, _xml_postprocess)
TYPST_STRATEGY   = TranslateStrategy(_xml_prompt_builder(DocumentType.Typst, ChunkType.Typst), _dont_call_model, _xml_postprocess)

STRATEGY_MAP: dict[tuple[DocumentType, ChunkType], TranslateStrategy] = {
    (DocumentType.LaTeX,            ChunkType.LaTeX): LATEX_STRATEGY,
    (DocumentType.JupyterNotebook,  ChunkType.Myst):  MYST_STRATEGY,
    (DocumentType.JupyterNotebook,  ChunkType.Code):  CODE_STRATEGY,
    (DocumentType.Markdown,         ChunkType.Myst):  MD_STRATEGY,
    (DocumentType.Typst,            ChunkType.Typst): TYPST_STRATEGY,
    (DocumentType.Other,            ChunkType.Other): PLAIN_STRATEGY,
}


class ChunkTranslator:
    """Facade: one method replaces legacy free‑function."""

    def __init__(
        self,
        store: TranslationCache,
        model_caller: LLMCaller | None = None,
        reasoning_caller: LLMCaller | None = None,
        *,
        overload_retry_attempts: int = 5,
        overload_retry_initial_delay: float = 1.0,
        overload_retry_max_delay: float = 16.0,
        xml_retries_before_reasoning: int = 2,
    ):
        self._store = store
        self._caller: LLMCaller | None = model_caller
        self._reasoning_caller: LLMCaller | None = reasoning_caller
        self._overload_attempts = max(1, overload_retry_attempts)
        self._overload_initial_delay = max(0.0, overload_retry_initial_delay)
        self._overload_max_delay = max(self._overload_initial_delay, overload_retry_max_delay)
        self._xml_retries_before_reasoning = max(0, xml_retries_before_reasoning)
        self._session_checksums: set[str] = set()
        self.stats = TranslationStats()
        # Provenance of the most recent model-backed translation, for chunk metadata.
        self.last_translation_service: str | None = None
        self.last_translation_model: str | None = None

    async def _translate_oversized_typst_chunk_async(
        self,
        meta: Meta,
    ) -> tuple[str, bool]:
        """Translate one oversized Typst chunk through internal subchunks.

        Subchunks are translated recursively via `translate_or_fetch`, so normal
        placeholder-only short-circuit and cache behavior still apply.

        Returns:
        - reconstructed translated full chunk,
        - `all_from_cache`: True only when every subchunk was cache-served.
        """
        subchunks = _split_typst_chunk_for_internal_translation(
            meta.chunk,
            TYPST_INTERNAL_SUBCHUNK_MAX_CHARS,
        )
        if len(subchunks) <= 1:
            return meta.chunk, True

        translated_parts: list[str] = []
        all_from_cache = True
        for subchunk in subchunks:
            sub_meta = Meta(
                subchunk,
                meta.src_lang,
                meta.tgt_lang,
                meta.doc_type,
                meta.chunk_type,
                meta.vocab,
                meta.rel_path,
            )
            translated_subchunk, from_cache = await self.translate_or_fetch(sub_meta, _skip_stats=True)
            translated_parts.append(translated_subchunk)
            all_from_cache = all_from_cache and from_cache

        return "".join(translated_parts), all_from_cache

    async def _run_with_caller(self, strategy: TranslateStrategy, meta: Meta, caller: LLMCaller | None) -> str:
        """Sets up the caller on the strategy and runs it with overload retry."""
        if caller is not None and strategy != CODE_STRATEGY:
            def f_call_model(t):
                try:
                    res = caller.call(t)
                except TypeError as exc:
                    raise TypeError(
                        f"Model '{caller.model}' failed: {exc}"
                    ) from exc
                if res is None:
                    raise TypeError(
                        f"Model '{caller.model}' returned None — "
                        "the API call may have failed or returned an empty response."
                    )
                caller.wait_cooldown()
                return res
            strategy.set_call_model(f_call_model)
            self.last_translation_service = caller.service_name
            self.last_translation_model = caller.model
        else:
            self.last_translation_service = None
            self.last_translation_model = None
        return await self._translate_with_retry(strategy, meta)

    async def translate_or_fetch(self, meta: Meta, _skip_stats: bool = False) -> tuple[str, bool]:
        """Translate one chunk or return it from cache.

        Returns `(translated_text, from_cache)`, where:
        - `from_cache=True` means no model call for that chunk request.

        Typst-specific behavior:
        - oversized Typst chunks are internally subchunked and translated piece
          by piece,
        - final persistence is still done at full original chunk granularity.
        """
        chunk = meta.chunk
        if not chunk.strip():
            return chunk, True  # whitespace → passthrough

        src_checksum = calculate_checksum(chunk)
        cached = self._store.lookup(src_checksum, meta.src_lang, meta.tgt_lang, meta.rel_path)
        if cached is not None:
            from_cache = src_checksum not in self._session_checksums
            logger.debug(f"cache hit ({meta.src_lang} -> {meta.tgt_lang}), from_cache={from_cache}")
            if not _skip_stats:
                self.stats.chunks_from_cache += 1
            return cached, from_cache

        strategy = STRATEGY_MAP[(meta.doc_type, meta.chunk_type)]
        ph_only = chunk_contains_ph_only(chunk, meta.chunk_type)
        caller = self._caller

        example = self._store.get_best_pair_example_from_cache(meta.src_lang, meta.tgt_lang, meta.chunk, meta.rel_path)
        if example is not None:
            src_ex, tgt_ex, score = example
            if score > 0.7:
                logger.debug("Found an example for a chunk")
                meta = WithExampleMeta(
                    meta.chunk,
                    meta.src_lang,
                    meta.tgt_lang,
                    meta.doc_type,
                    meta.chunk_type,
                    meta.vocab,
                    meta.rel_path,
                    src_ex,
                    tgt_ex,
                )

        if ph_only:
            logger.trace("ph only")
            logger.trace(chunk)
            logger.trace("=======")
            tgt_checksum = calculate_checksum(chunk)
            self._store.persist_pair(
                src_checksum,
                tgt_checksum,
                meta.src_lang,
                meta.tgt_lang,
                chunk,
                chunk,
                meta.rel_path,
            )
            return chunk, True  # no LLM called — passthrough, never needs review

        if (
            meta.doc_type == DocumentType.Typst
            and meta.chunk_type == ChunkType.Typst
            and len(chunk) > TYPST_INTERNAL_SUBCHUNK_MAX_CHARS
        ):
            subchunks = _split_typst_chunk_for_internal_translation(
                chunk,
                TYPST_INTERNAL_SUBCHUNK_MAX_CHARS,
            )
            if len(subchunks) > 1:
                try:
                    translated, from_cache = await self._translate_oversized_typst_chunk_async(meta)
                except ChunkTranslationFailed as exc:
                    root_exc = exc.original_exception if exc.original_exception is not None else exc
                    if not _skip_stats:
                        self.stats.chunks_failed += 1
                    raise ChunkTranslationFailed(chunk, root_exc) from exc

                tgt_checksum = calculate_checksum(translated)
                if not from_cache:
                    self._session_checksums.add(src_checksum)
                self._store.persist_pair(
                    src_checksum,
                    tgt_checksum,
                    meta.src_lang,
                    meta.tgt_lang,
                    chunk,
                    translated,
                    meta.rel_path,
                )
                if not _skip_stats:
                    if from_cache:
                        self.stats.chunks_from_cache += 1
                    else:
                        self.stats.chunks_translated += 1
                return translated, from_cache

        total_attempts = self._xml_retries_before_reasoning + 1
        reasoning_caller = self._reasoning_caller if self._reasoning_caller is not None else caller
        translated = None
        used_reasoning = False
        for attempt in range(1, total_attempts + 1):
            # verify if the current number of attemps is equal to total allowed
            # attemps
            is_final = attempt == total_attempts
            # choose the llm caller (reasoning or casual)
            active_caller = reasoning_caller if is_final else caller
            try:
                translated = await self._run_with_caller(strategy, meta, active_caller)
                if is_final and self._reasoning_caller is not None:
                    used_reasoning = True
                break
            except (ET.ParseError, PlaceholderVerificationError) as exc:
                # if there is a parse error, or placeholders are corrupted we
                # pass here

                # if we used all allowed attemps and attempt with reasoning
                # model, then we raise an error
                if is_final:
                    logger.error(
                        f"Chunk translation failed after {total_attempts} attempts due to {exc.__class__.__name__}: {exc}",
                    )
                    if not _skip_stats:
                        self.stats.chunks_failed += 1
                        if self._reasoning_caller is not None:
                            self.stats.chunks_passed_to_reasoning += 1
                    raise ChunkTranslationFailed(chunk, exc) from exc
                # if we used all attempts, but did not call the reasoner, then we call reasoner
                next_is_reasoning = attempt == self._xml_retries_before_reasoning

                if next_is_reasoning:
                    logger.warning(f"Invalid XML on attempt {attempt}, retrying with reasoning model...")
                else:
                    logger.warning(f"Invalid XML on attempt {attempt}, retrying with standard model...")
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"Chunk translation failed on attempt {attempt} due to {exc.__class__.__name__}: {exc}",
                )
                if not _skip_stats:
                    self.stats.chunks_failed += 1
                    if is_final and self._reasoning_caller is not None:
                        self.stats.chunks_passed_to_reasoning += 1
                raise ChunkTranslationFailed(chunk, exc) from exc
        assert translated is not None

        if not _skip_stats:
            self.stats.chunks_translated += 1
            if used_reasoning:
                self.stats.chunks_passed_to_reasoning += 1

        tgt_checksum = calculate_checksum(translated)
        self._session_checksums.add(src_checksum)
        self._store.persist_pair(
            src_checksum,
            tgt_checksum,
            meta.src_lang,
            meta.tgt_lang,
            chunk,
            translated,
            meta.rel_path,
        )
        return translated, False

    async def _translate_with_retry(self, strategy: TranslateStrategy, meta: Meta) -> str:
        delay = self._overload_initial_delay or 1.0
        for attempt in range(1, self._overload_attempts + 1):
            try:
                return await strategy.run(meta)
            except ModelOverloadedError as exc:
                if attempt >= self._overload_attempts:
                    logger.error(
                        f"Model overloaded after {attempt} attempts, giving up.",
                    )
                    raise exc

                wait_seconds = min(delay, self._overload_max_delay)
                logger.warning(
                    f"Model overloaded (attempt {attempt}/{self._overload_attempts}). Retrying in {wait_seconds:.2f}s...",
                )
                await asyncio.sleep(wait_seconds)
                delay = min(delay * 2, self._overload_max_delay)

def build_translator_with_model(root_path: Path, caller: LLMCaller | None = None, reasoning_caller: LLMCaller | None = None, xml_retries_before_reasoning: int = 2) -> ChunkTranslator:
    """Constructs default translation factory with a particular model"""
    return ChunkTranslator(TranslationCacheCsv(root_path), caller, reasoning_caller, xml_retries_before_reasoning=xml_retries_before_reasoning)
