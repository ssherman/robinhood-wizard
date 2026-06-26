# Phase 4f — Prose→Buckets Compiler (Design)

- **Date:** 2026-06-26
- **Status:** Approved design (pre-plan)
- **Depends on:** Phase 4c (NL strategy compiler + the `WebSearchLlm` seam), merged; Phase 4e
  (bucketed `Strategy` + `Bucket` model + the deterministic allocator/cycle), merged (PR #12).
- **Scope:** DryRun-only. Extends `wizard compile` so it can emit a **bucketed**
  thematic-allocation strategy (target % per theme) when the prose specifies one. It places no
  orders and is broker-free; the deterministic risk engine remains the un-bypassable runtime gate.

## 1. Goal

Today `wizard compile` always flattens prose into a single-universe strategy — a thesis like
*"10% rare-earth small-caps, 70% large-cap value under $100, 20% cannabis"* loses its
percentages (they land in `intent`) and merges every theme into one flat `universe`. This phase
teaches the compiler to recognize a thematic allocation and emit a **bucketed** `Strategy`
(the Phase 4e structure), so the type-a-thesis → reviewable-strategy → `wizard run` loop works
end-to-end for allocations without hand-authoring bucket YAML.

This realizes the last user-facing piece of the thematic-strategy vision: the compiler produces
the allocation buckets that 4e's allocator already knows how to size.

**In scope:** LLM auto-detection of allocation language; an optional bucket structure on the
compile output model; assembling a bucketed `Strategy` (per-bucket frozen universe + intent +
target %); writer + review-header support; clear over-allocation errors. **Out of scope (later):**
per-bucket dial inference; any change to the allocator/cycle (4e already runs bucketed
strategies); order execution.

## 2. Key reuse finding

The compiler already targets a single structured-output model (`CompiledStrategy`) via the
**unchanged** `WebSearchLlm` seam (OpenAI Responses + hosted `web_search`). Adding an optional
`buckets` list to that model keeps **one** LLM target and reuses the entire `llm/` layer with
**zero changes**. `SuggestedTicker` (`models/compile.py`), `Source` (`models/research.py`),
`Bucket` (`models/bucket.py`), and the `Strategy` validator (Σ`target_pct` ≤ 100, etc.) are all
reused as-is.

## 3. Decisions (this phase)

| Decision | Choice |
|----------|--------|
| Flat vs bucketed | **LLM auto-detects.** If the prose specifies target percentages per theme, the LLM returns `buckets`; otherwise it returns the flat `tickers` list (today's behavior). |
| Output model | **One model, optional `buckets`.** Extend `CompiledStrategy` with `buckets: list[CompiledBucket] = []`; non-empty ⇒ bucketed, empty ⇒ flat. The LLM fills one or the other, never both. |
| Per-bucket universe | **Freeze the web-searched suggestions as each bucket's explicit `universe`, `discover=False`** — exactly like flat 4c. The compiled file is a concrete, reviewable allocation; `run` uses it deterministically. The user flips a bucket to `discover: true` if they want it dynamic. |
| Allocation dials | The compiler does **not** infer `allow_fractional` / `rebalance_mode` / `rebalance_band_pct` — they stay at model defaults (`true` / `full` / `5`) for the user to edit. |
| Bucket id | A deterministic slug of the bucket `name` (lowercased, non-alphanumeric → `-`, collapsed/trimmed), deduped with a numeric suffix on collision. |
| signals_needed | For bucketed output the compiler includes `fractionable` (the allocator needs it) alongside the LLM-inferred signals. |
| Over-allocation | If Σ`target_pct` > 100, the assembled `Strategy` fails validation → the CLI surfaces a **clear compile error** (no silent normalizing/clamping). Σ < 100 is allowed (remainder = cash). |
| Risk | Unchanged 4c invariant: **prose can never set `risk_overrides`** — `CompiledStrategy`/`CompiledBucket` have no risk field, and the assembled `Strategy` hardcodes `risk_overrides={}`. |
| Provider / mode | OpenAI only (seam allows others). Broker-free, orderless, DryRun-only. |

## 4. Architecture & components

### 4.1 Models: `models/compile.py` (modify)

- New `CompiledBucket(pydantic.BaseModel)`: `name: str`, `target_pct: LlmDecimal`,
  `intent: str = ""`, `tickers: list[SuggestedTicker] = []`. `target_pct` uses `LlmDecimal`
  (schema-safe Decimal — no JSON-schema lookaround) since `CompiledStrategy` is an LLM target.
- `CompiledStrategy` gains `buckets: list[CompiledBucket] = []`. Existing fields unchanged.
- `CompileResult` is unchanged (it already carries the assembled `Strategy` + the flat
  `tickers` + `sources`); per-bucket tickers are read off `result.strategy.buckets` /
  `compiled.buckets` for the review header (see §4.3).

### 4.2 Compiler: `strategies/compiler.py` (modify)

- `COMPILE_SYSTEM` + `_compile_prompt` updated: *if the thesis assigns target percentages to
  themes, return `buckets` — each with a short name, its target % (of investable capital), a
  one-line intent, and web-searched US-listed tickers that fit that theme (with citations);
  otherwise return a single flat `tickers` list as today. Do not size positions or set risk.*
- `compile()` branches on `compiled.buckets`:
  - **Bucketed:** build `Strategy(id, name=compiled.name, intent=compiled.intent, buckets=[
    Bucket(id=_slug(b.name, seen), name=b.name, target_pct=b.target_pct, intent=b.intent,
    universe=[t.symbol for t in b.tickers], discover=False, max_candidates=20) for b in
    compiled.buckets], signals_needed=set(compiled.signals_needed) | {Signal.FRACTIONABLE},
    cadence=compiled.cadence, risk_overrides={}, web_research=True)`.
  - **Flat:** exactly today's assembly.
  - Return `CompileResult(strategy=…, tickers=compiled.tickers, sources=sources)` (the flat
    `tickers` list stays the flat-path field; the bucketed header reads from the buckets).
- A small `_slug(name, seen)` helper produces the deterministic, deduped bucket id.
- The dependency wall holds: the compiler imports models + `WebSearchLlm` only; no
  openai/strands import (those stay lazy in `cli/compile.py`).

### 4.3 Writer: `strategies/writer.py` (modify)

- `_strategy_to_dict` emits `buckets` (each: id/name/target_pct/intent/universe/discover/
  max_candidates) and the three allocation dials (`allow_fractional`/`rebalance_mode`/
  `rebalance_band_pct`) at their values when `strategy.buckets` is non-empty; for a flat
  strategy the output is **byte-for-byte unchanged** (no buckets/dials keys, keeping the flat
  `universe` form). `target_pct` and `rebalance_band_pct` serialize as plain numbers/strings
  (Decimal → `str`/number) that re-load cleanly.
- `_comment_header` groups the suggested tickers **per bucket** (with their citations) when
  buckets are present; the flat header is unchanged. The header is comment-only and dropped by
  `yaml.safe_load` on the next load, so the file still round-trips through `StrategyRegistry`.

### 4.4 CLI: `cli/compile.py` (modify)

- No new flags. `_render_summary` prints a per-bucket summary (bucket name, target %, its
  tickers) when buckets are present; otherwise the flat summary. The over-allocation /
  validation failure (a `pydantic.ValidationError` raised while assembling the `Strategy`) is
  caught and reported as a clear non-zero-exit compile error, alongside the existing `LlmError`
  handling. `_build_compiler` (lazy OpenAI import) is unchanged.

## 5. Error handling

| Condition | Behavior |
|-----------|----------|
| Prose has no target %s | LLM returns flat `tickers`; today's flat strategy is written. |
| Prose specifies an allocation | LLM returns `buckets`; a bucketed strategy is written. |
| Σ`target_pct` > 100 (contradictory prose) | `Strategy` validation fails → clear CLI compile error, non-zero exit, nothing written. |
| Σ`target_pct` < 100 | Allowed; the remainder is extra cash (documented in the summary/header). |
| A bucket has `target_pct ≤ 0` | `Strategy`/`Bucket` validation fails → clear compile error. |
| LLM returns both `tickers` and `buckets` | Bucketed wins (buckets non-empty ⇒ bucketed path); the stray flat `tickers` are ignored for assembly. |
| Empty/garbled prose, file-not-found, bad id, existing file without `--force` | Today's existing CLI errors (unchanged). |
| LLM error after retries | `LlmError` → today's non-zero-exit handling (unchanged). |

## 6. Safety

- **Prose cannot inject risk:** neither `CompiledStrategy` nor `CompiledBucket` has a risk
  field, and the assembled `Strategy` always sets `risk_overrides={}` (by construction).
- **Broker-free / orderless:** compile talks only to the LLM (web search). The risk `vet()`
  remains the un-bypassable gate at *run* time; a suggested/overweight bucket cannot place an
  unsafe order (4e's allocator sizes, `vet()` re-checks).
- **Human gate preserved:** compile → review the file → `wizard run` (suggestions are
  web-search picks, not vetted; flagged in the header and summary).
- **Dependency wall:** compiler imports models + `WebSearchLlm` only; the openai import stays
  lazy in `cli/compile.py`. `OPENAI_API_KEY` is read inside the unchanged `OpenAiWebSearchLlm`
  and never logged/rendered.
- **Schema safety:** `CompiledStrategy` (now with `CompiledBucket`) must still emit a JSON
  schema with no regex lookaround — `target_pct` uses `LlmDecimal`.

## 7. Testing

- **Offline unit (no network)** via a `FakeWebSearchLlm` returning a canned `CompiledStrategy`:
  - Bucketed: a "10/70/20" canned output assembles a valid bucketed `Strategy` — slugged,
    deduped bucket ids; per-bucket `universe` from the suggested tickers; `discover=False`;
    Σtargets ≤ 100; `signals_needed` includes `fractionable`; `risk_overrides={}`.
  - Flat: a canned flat output still compiles a flat `Strategy` (regression — no buckets, no
    dials in the YAML).
  - Over-allocation (canned 60/60) raises a clear error and writes nothing.
  - `_slug` collisions dedupe deterministically.
- **Schema safety:** assert the extended `CompiledStrategy` has no lookaround patterns.
- **Writer:** bucketed YAML round-trips through `StrategyRegistry.load` (comment header dropped,
  `Strategy` re-validates); flat YAML byte-for-byte unchanged.
- **CLI:** `wizard compile` with a monkeypatched `_build_compiler` writes a bucketed file and
  prints the per-bucket summary; the over-allocation error exits non-zero.
- **Live opt-in (double-gated `RH_WIZARD_LIVE=1` + `OPENAI_API_KEY`):** compile a real
  "10/70/20" prose; assert a bucketed `Strategy` with Σtargets ≤ 100 and ≥1 ticker per bucket.
  No broker, no orders.

## 8. Out of scope (later phases)

- Per-bucket dial inference (e.g. prose "whole shares only" → `allow_fractional: false`).
- Any change to the allocator, recommender, or cycle (Phase 4e already runs bucketed
  strategies).
- Order execution (Human-Approval / Autonomous) + kill-switch enforcement.

## 9. Risks to pin during planning

- Re-confirm `responses.parse` + `web_search` returns a valid `CompiledStrategy` carrying
  `buckets` with `settings.model_id` (proven for the flat `CompiledStrategy`; differs only in
  the added optional field). Keep `target_pct` as `LlmDecimal`.
- `_slug` must be deterministic, collision-safe, and produce ids that satisfy the bucketed
  `Strategy` (non-empty ids; the cycle/journal use them).
- Writer must serialize `Decimal` target_pct/band as values that re-load to `Decimal` cleanly
  (no float drift) and keep the flat path byte-for-byte unchanged.
- Keep the dependency wall: no openai/strands import creeping into `compiler.py`/`writer.py`;
  the openai import stays lazy in `cli/compile.py`.
