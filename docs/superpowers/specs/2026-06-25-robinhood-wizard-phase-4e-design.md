# Phase 4e — Allocation Buckets + Allocation-Aware Planning (Design)

- **Date:** 2026-06-25
- **Status:** Approved design (pre-plan)
- **Depends on:** Phase 4d (per-cycle universe discovery + the reusable `WebSearchLlm` seam),
  merged (PR #10); Phase 2 risk engine (`risk/engine.py`); Phase 4b-1/4b-2 LLM research seams.
- **Scope:** DryRun-only. Adds bucketed (thematic-allocation) strategies and a new **pure,
  deterministic Allocator** that sizes positions to hit per-bucket target percentages, plus
  bucket-aware discovery + research. It places no orders and runs no executor. The
  deterministic risk engine remains the un-bypassable gate.

## 1. Goal

Let a strategy express a **thematic allocation** — *buckets*, each a theme with a target
percentage ("40% AI, 20% energy, 20% rare-earth-metal funds, …") — and have the agent
discover/research each bucket and **size positions to hit those targets**. This is the last
major piece of the thematic-strategy vision: universe discovery (4d) produced a flat candidate
list; this phase adds the allocation *structure* and the planning that respects it.

Division of labor (the project's ethos — *deterministic where it matters*; LLMs drift on
multi-step dollar math, code never does):

- **LLM = judgment.** Per bucket: which tickers fit, a thesis, and a **relative weight** per
  position (e.g. 50/30/20). It never computes dollars or share counts.
- **Deterministic Allocator = arithmetic.** target % → per-bucket budget → split by weight →
  dollars → shares (under the fractional/whole-share rules) → sized `TradeIntent`s. Pure,
  unit-tested, auditable — a sibling to the risk engine.
- **Risk `vet()` = the gate.** Unchanged; re-checks every sized intent against the resolved
  price and all guardrails. The Allocator cannot bypass it.

**In scope:** bucket model; per-bucket discovery + research; the LLM relative-weight
recommendation; the deterministic Allocator (buy + sell-to-trim, drift-band gated,
fractional/whole sizing); a `fractionable` data signal; journal + render.

**Out of scope (later phases):** the prose→buckets compiler (`wizard compile` extracting
"40% AI" from prose); order execution + kill-switch enforcement (the next phase);
redistributing an unfilled bucket's leftover into other buckets; per-bucket fractional/band
overrides; tax-lot optimization.

## 2. Key reuse finding

- **Discovery + research reuse the unchanged `WebSearchLlm` seam** (`llm/web_search.py`,
  `research(output_model, prompt, system) -> tuple[T, list[Source]]`), already proven generic
  over the output model across 4b-2/4c/4d. New structured-output models slot in with **zero
  `llm/` changes**. `SuggestedTicker` / `Source` are reused.
- **The risk engine is unchanged.** The Allocator produces a normal `TradePlan`; `vet()` vets
  it exactly as today. No change to `risk/engine.py` or `risk/policy.py`.
- **The cycle stays brain-agnostic.** New stages are reached through Protocols
  (`UniverseDiscoverer`, `Researcher`/recommender, and a new pure `allocate()` function); the
  cycle imports no `cli`/`openai`/`strands`.

## 3. Decisions (this phase)

| Decision | Choice |
|----------|--------|
| Strategy shape | **Additive + opt-in.** A strategy is *either* flat (today) *or* bucketed. Non-empty `buckets` ⇒ bucketed mode. Existing flat strategies run byte-for-byte unchanged. |
| Buckets vs flat fields | **Mutually exclusive.** The loader rejects a strategy that sets both `buckets` and a top-level `universe`/`discover`, so there is no ambiguity about which path runs. |
| Sizing engine | **LLM recommends, code computes.** The LLM emits per-bucket selected positions + relative weights (no dollars/shares). A new **pure deterministic Allocator** does all dollar/share math. |
| Intra-bucket split | **LLM relative weights.** Code normalizes the weights within a bucket and multiplies by the bucket budget. |
| Target base | Bucket `target_pct` is a share of **investable capital** (= portfolio value minus the cash-reserve floor), decoupled from the reserve dial. "40% AI" = 40% of the money being invested. Load-time: each `target_pct > 0` and **Σ `target_pct` ≤ 100**. |
| Rebalance mode | Per-strategy `rebalance_mode: "full" \| "buy_only"`, **default `full`** (buy + sell-to-trim). `buy_only` never sells. |
| Drift band | Per-strategy `rebalance_band_pct: Decimal`, **default `5`**. A bucket is acted on only when \|drift\| > band — this decouples *how often you run* from *how often it trades*. |
| Fractional shares | Per-strategy `allow_fractional: bool`, **default `True`**, AND auto-respecting per-stock fractionability: a position is sized fractionally only if the strategy allows it AND Robinhood reports the symbol fractionable; otherwise it floors to whole shares. |
| Orphan holdings | A held symbol in **no** bucket is **left untouched and reported** — we never auto-sell a name the strategy does not recognize. |
| Single-name bucket vs `max_position_pct` | The Allocator stays allocation-only; `vet()` remains the sole authority on caps. If a bucket target exceeds the position cap, the Allocator sizes to target and `vet()` rejects the overage; the drift report shows the shortfall. (No pre-clamp in the Allocator — one source of truth for caps.) |
| Config home | **Per-strategy only** (`allow_fractional`, `rebalance_mode`, `rebalance_band_pct`, plus the `buckets` list), with model defaults. Allocation is inherently a per-strategy concern. |
| Provider / mode | OpenAI only (seams allow others). DryRun-only; no executor. |

## 4. Architecture & components

### 4.1 Strategy & Bucket model: `models/strategy.py` (modify) + `models/bucket.py` (new)

`Bucket` (new, `extra="forbid"`):

- `id: str`
- `name: str = ""`
- `target_pct: Decimal` — share of investable capital (whole-number percent, like the risk dials)
- `intent: str = ""` — theme text driving this bucket's discovery + research
- `universe: list[str] = []` — explicit tickers for this bucket (optional)
- `discover: bool = False` — per-bucket discovery toggle
- `max_candidates: int = 20`

`Strategy` gains:

- `buckets: list[Bucket] = []` — non-empty ⇒ bucketed mode
- `allow_fractional: bool = True`
- `rebalance_mode: str = "full"` — `"full"` | `"buy_only"` (validated)
- `rebalance_band_pct: Decimal = 5`

`signals_needed` stays strategy-level (applies to every bucket; per-bucket signals are YAGNI).
Loader validation (`strategies/registry.py`): reject mixing `buckets` with a non-empty
top-level `universe`/`discover`; reject `Σ target_pct > 100` or any `target_pct ≤ 0`; reject an
unknown `rebalance_mode`.

### 4.2 The Allocator: `allocation/engine.py` (new — pure, deterministic, no I/O)

A sibling to `risk/engine.py`: pure, purity-test-guarded, the new crown jewel beside risk.

Signature (indicative):

```
allocate(
    recommendation: AllocationRecommendation,  # LLM output: per-bucket positions + weights
    buckets: list[Bucket],
    policy: RiskPolicy,                         # for cash_reserve_pct
    portfolio: PortfolioState,
    market: dict[str, SymbolRisk],             # resolved price + fractionable
    allow_fractional: bool,
    rebalance_mode: str,
    rebalance_band_pct: Decimal,
) -> tuple[TradePlan, AllocationReport]
```

It produces a normal `TradePlan` (the sized `TradeIntent`s) plus an `AllocationReport`
(per-bucket target%/current%/drift/within-band?/action) for render + journal. `vet()` then runs
on the `TradePlan` unchanged.

The algorithm is specified in §5.

### 4.3 Cycle: `core/cycle.py` (modify)

Bucketed strategies route through bucket-aware stages; flat strategies use today's exact path.
The cycle stays brain-agnostic (Protocols + the pure `allocate()` only).

```
flat:     reconcile → discover → resolve → research → plan(LLM) → vet → journal   (unchanged)
bucketed: reconcile → discover(per-bucket) → resolve(+fractionable)
                    → research(bucket-tagged) → recommend(LLM: relative weights)
                    → allocate(deterministic) → vet → journal
```

`CycleDeps` gains the bucket-aware recommender + (reused) discoverer seams; `CycleResult` gains
`allocation: AllocationReport | None` and the recommendation. Routing is chosen by
`strategy.buckets` being non-empty. Failure handling per §6.

### 4.4 Discovery & research, bucket-aware

- **Discovery** (`discovery/`): runs **per bucket** — each bucket's `intent` → its candidate
  tickers, hard-capped at the bucket's `max_candidates`, tagged with the bucket `id`. Reuses
  the unchanged `WebSearchLlm` seam. Per-bucket degrade-and-report (one bucket failing does not
  abort the cycle). The per-cycle resolve universe = (each bucket's explicit `universe` ∪ its
  discovered tickers) ∪ current holdings, normalized + deduped.
- **Research / recommend** (`research/` + a recommender): candidates are tagged per bucket; the
  LLM emits, per bucket, the selected positions each with a **relative weight** + thesis, plus
  web-search `sources`. This is the `AllocationRecommendation` (LLM structured output) — *no
  dollars or shares*. Decimal weights use `LlmDecimal` (avoid the JSON-schema lookaround issue;
  see §10).

### 4.5 Data layer — fractionability: `data/` (modify)

New per-symbol **`fractionable: bool | None`** signal, sourced from Robinhood
(`get_equity_tradability` / instrument `fractional_tradability`). Resolved into `MarketContext`
(and surfaced on the `SymbolRisk` the Allocator reads) like the other signals;
`None` ⇒ treat as **non-fractionable** (safe default → whole shares). `SignalResolver` keeps
its degrade-and-report contract. The exact MCP field name/shape is **live-verified during
planning** (same discipline that pinned earlier payload shapes in the main spec §18).

### 4.6 Wiring: `cli/run.py` (modify)

Lazy builders (mirroring `_build_discoverer` / `_build_web_researcher`) construct the
bucket-aware discoverer + recommender only when `strategy.buckets` is non-empty; the OpenAI
import stays lazy and behind the key guard. The Allocator is pure code (no builder). Flat
strategies are wired exactly as today.

### 4.7 Models, journal, render

- **Models:** `Bucket` (§4.1); `AllocationRecommendation` (LLM output: per-bucket positions
  with relative weights + thesis + sources); `AllocationReport` (per-bucket
  target%/current%/drift/within-band?/buys+sells, for render + journal). New structured-output
  models avoid `Decimal` JSON-schema lookaround (reuse `LlmDecimal` where a Decimal is needed).
- **Journal** (`memory/journal.py`): additive, idempotent (`CREATE TABLE IF NOT EXISTS`) tables
  for the strategy's buckets/targets, the recommendation, and the allocation/drift report,
  written alongside `record_plan`/`record_research`.
- **Render** (`cli/render.py`): an **"Allocation"** block — per bucket: target%, current%,
  drift, within-band?, and the resulting buys/sells; orphan holdings listed separately.

## 5. The allocation algorithm (deterministic)

All math is `Decimal`. `portfolio_value`, `cash`, and per-position `market_value` come from the
Phase 1 reconcile; `price` + `fractionable` come from the Phase 3 resolve.

1. **Reserve first.** `investable = portfolio_value × (1 − cash_reserve_pct/100)`.
2. **Per-bucket budget.** `budget(b) = b.target_pct/100 × investable`. Σtargets < 100 ⇒ the
   remainder simply stays as extra cash.
3. **Map holdings → buckets.** A held symbol belongs to the bucket whose `universe` or current
   recommendation contains it. Held symbols in no bucket are **orphans** (reported, untouched).
4. **Per-bucket drift + band gate.** `current_value(b)` = Σ market_value of in-bucket holdings;
   `drift(b) = current_value(b)/investable×100 − b.target_pct` (percentage points). **If
   \|drift(b)\| ≤ rebalance_band_pct, skip the bucket** (no trades).
5. **Buys (underweight beyond band).** Shortfall `= budget(b) − current_value(b)`. Split the
   shortfall across the bucket's recommended positions by their **normalized relative weights**.
6. **Sells (overweight beyond band).** If `rebalance_mode == "full"`: excess
   `= current_value(b) − budget(b)`, trimmed **proportionally across the bucket's held
   positions** to reach `budget(b)`. If `rebalance_mode == "buy_only"`: no sells (drift is
   reported only). (Precise proportional-trim formula pinned during planning.)
7. **Sequence:** compute all sells first (trim proceeds raise cash), then buys, so buys can use
   the freed cash while honoring the reserve.
8. **dollars → shares.** For each sized position at the resolved `price`:
   - fractional path (`allow_fractional` AND `market[sym].fractionable`): a **buy** emits a
     notional `amount` (exact dollars); a **sell** emits a fractional `quantity`.
   - whole-share path (otherwise): `quantity = floor(dollars / price)`; the sub-one-share
     remainder stays cash. A sell floors to whole shares too.
   - `limit_price = price` (the resolved market price) so the risk slippage band passes.
9. **Gate.** The resulting `TradePlan` goes through `vet()` unchanged. Anything that violates a
   guardrail (e.g. a single-name bucket exceeding `max_position_pct`) is rejected there; the
   `AllocationReport` reflects the post-vet shortfall.

## 6. Error handling

| Condition | Behavior |
|-----------|----------|
| Flat strategy (no buckets) | Today's path exactly; no Allocator, no bucket stages. |
| Per-bucket discovery fails | Degrade-and-report for that bucket; other buckets + the cycle proceed (note recorded). |
| Recommender (LLM) fails | Agentic-stage failure → abort the cycle cleanly (journaled, no crash), like research/plan today. |
| Bucket has zero priced/recommended candidates | Budget cannot be deployed; recorded as drift; cycle completes cleanly. |
| Σtargets < 100 / whole-share rounding / `vet()` rejection | Leftover stays cash; no redistribution (v1). Surfaced in the report. |
| Orphan holding (in no bucket) | Untouched; reported. |
| Hallucinated / unknown symbol | Resolve drops it to `None` fields; Allocator can't price it → no intent; `vet()` never sees a tradeable intent. |
| `portfolio_value ≤ 0` | No buys sized (matches the risk engine's positive-value requirement); reported. |

## 7. Safety

- The Allocator **cannot place orders** and **cannot weaken guardrails** — it only sizes. The
  un-bypassable `vet()` re-checks every intent against the **resolved** price + all caps
  (position, cash reserve, per-cycle deploy, liquidity, slippage), so a manipulated or
  hallucinated recommendation cannot bypass the gate (same argument as 4b-2/4c/4d).
- Targets are % of investable, which is itself net of the cash reserve — buys structurally
  respect the reserve before `vet()` even runs.
- Web content (discovery/research) is framed as information, not instructions.
- `OPENAI_API_KEY` is read from the environment inside the unchanged `OpenAiWebSearchLlm` and is
  never logged, journaled, or rendered.
- DryRun-only: no executor exists yet (next phase).

## 8. Testing

- **Pure Allocator unit tests (the new crown jewel, no I/O):** per-bucket budgets; weight
  normalization; drift computation + band gating (skip within band, act beyond); `full` vs
  `buy_only`; fractional (notional `amount`) vs whole-share (`floor`) sizing per the
  `fractionable` flag; leftover → cash; orphan holdings untouched; sells-sequenced-before-buys;
  single-name-bucket vs `max_position_pct` (Allocator sizes, `vet()` rejects); zero/empty/`≤0`
  edges. A purity guard (no I/O imports), mirroring the risk engine's.
- **Offline cycle tests (no network):** with `buckets`, the resolve universe = per-bucket
  (explicit ∪ discovered) ∪ holdings; routing picks the Allocator path; a per-bucket discovery
  failure degrades; the recommendation, `TradePlan`, and `AllocationReport` are journaled +
  visible on `CycleResult`; flat strategies are unchanged. Fakes: `FakeWebSearchLlm`.
- **Schema-safety:** assert each new LLM structured-output model has no JSON-schema lookaround
  (no bare `Decimal`).
- **Models / loader:** bucket validation (Σtargets ≤ 100, mutually-exclusive flat fields,
  `rebalance_mode` allow-list); round-trips via `StrategyRegistry`.
- **Persistence + render:** the new journal tables and the "Allocation" render block.
- **Live opt-in (double-gated `RH_WIZARD_LIVE=1` + `OPENAI_API_KEY`):** a small bucketed
  strategy runs a real DryRun cycle; asserts the run is `completed`/`aborted` (never crashes),
  the discovered + recommended buckets are populated, and the sized plan is vetted.
  No orders.

## 9. Out of scope (later phases)

- The prose→buckets compiler (`wizard compile` extracting buckets + target % from free text).
- Order execution (Human-Approval / Autonomous) + kill-switch enforcement (the next phase).
- Redistributing an unfilled bucket's leftover budget into other buckets.
- Per-bucket fractional / band / mode overrides.
- Tax-lot / tax-aware rebalancing.

## 10. Risks to pin during planning

- **Live-verify the `fractionable` field:** the exact `get_equity_tradability` /
  `fractional_tradability` shape (and how a non-fractionable / unknown symbol presents) — record
  it in the main spec §18 like prior phases.
- **Re-confirm `responses.parse` + `web_search`** returns a valid `AllocationRecommendation`
  with `settings.model_id` (proven for `ResearchReport`/`CompiledStrategy`/`DiscoveredUniverse`;
  differs only in fields). Keep weights as `LlmDecimal` to avoid the lookaround issue.
- **Precise proportional-trim formula** for overweight buckets (full mode), and the exact
  per-position buy split (normalized weights, handling a held name absent from this cycle's
  recommendation).
- **Symbol normalization** on the bucket union: uppercase + strip, dedupe against explicit
  bucket universes + holdings, so resolve gets a clean set; preserve bucket membership.
- **Decimal discipline:** all Allocator math in `Decimal`; `floor` for whole shares; notional
  `amount` for fractional buys — keep the money rule intact (no float).
- **Journal migrations** additive + idempotent (`CREATE TABLE IF NOT EXISTS`).
- **Cycle stays brain-agnostic:** new stages via Protocols + the pure `allocate()`; the
  OpenAI-importing builders stay lazy in `cli/run.py`.
