# Bucketed allocation — deploy-completeness + rationale passthrough (Design)

- **Date:** 2026-06-28
- **Status:** Approved design (pre-plan)
- **Depends on:** Phases 0–5, all merged to main — in particular Phase 4e (allocation buckets +
  the pure deterministic allocator), 4f (prose→buckets compiler), and Phase 5 (HumanApproval
  execution). This change sits entirely on the **bucketed** path.
- **Origin:** `docs/superpowers/notes/2026-06-27-bucket-deploy-completeness-kickoff.md` (scoping
  note). Two issues surfaced reviewing a bucketed DryRun of `legit-strategy-1`.
- **Scope:** (1) Surface each position's `thesis` as its trade rationale on the bucketed path.
  (2) Deploy a bucketed strategy *closer to its target* by redistributing dollars freed by
  rejected/floored names to surviving names **within the same bucket**, and by fixing the
  ordering artifact that starves late buckets under a binding trade cap.
- **Out of scope:** Sweeping whole-share *flooring* remainders (fractionable survivors already
  absorb redistributed dollars exactly; whole-share rounding leftovers are a noted follow-up).
  Shrinking a cap-violating intent *to fit* (that is `vet`'s `adjusted` forward-seam, still empty).
  Autonomous mode and the drawdown kill-switch (separate follow-on).

## 1. Why we're here

Reviewing a bucketed DryRun of `legit-strategy-1` (6 buckets: AI 35 / Power 25 / Industrial 15 /
Water 10 / Cannabis 10 / Cash 5; ~5 candidates each; investable ≈ $3,000):

1. **Per-trade Rationale renders as `-`.** The recommender LLM already emits a one-line `thesis`
   per position (`RecommendedPosition.thesis`, `models/allocation.py:24`), but the deterministic
   allocator never copies it onto the `TradeIntent`, so render's `i.rationale or "-"`
   (`cli/render.py:209`) prints `-`. Flat (LLM-planned) strategies populate rationale via
   `planning/llm.py`, which is why this only shows on the bucketed path. Cosmetic/audit.

2. **A bucketed run deploys less than its target, silently.** Two distinct causes:
   - **Rejected/floored dollars are dropped, not reassigned.** Sizing *is* conviction-weighted
     (a bucket's `target_pct/100 × investable` budget is split across its positions proportional
     to the LLM's relative `weight`; `engine.py:100-113`). But `allocate()` is a single pass, and
     rejections happen *later* in risk `vet()` (`risk/engine.py`). A name `vet` rejects
     (e.g. POWL: liquidity floor) or that the allocator floored to 0 whole shares has its slice
     simply dropped — the freed dollars stay as cash instead of flowing to surviving names in the
     same bucket. *Evidence:* the Power bucket (25% = $750) deployed only ~$630; the ~$120
     difference is POWL, allocated then rejected.
   - **Bucket-sequential ordering starves late buckets under the global trade cap.** `allocate()`
     emits buy intents bucket-by-bucket (`engine.py:166` loops `strategy.buckets` in order,
     `buy_intents.extend(buys)`), and `vet()` approves the first N in that flat order until
     `max_trades_per_cycle` is hit. With ~5 name-buckets × ~5 names ≈ 25 intents and a cap of 20,
     the *last* buckets get nothing. *Evidence:* the Cannabis bucket (10% = $300) had **all** its
     names rejected "exceeds max trades per cycle (20)" → deployed ≈ $0. This is an **ordering
     artifact**, not a cap-value problem — `max_trades_per_cycle` is already per-strategy
     configurable via `risk_overrides` (clamped by `RiskCeiling`).

These are cohesive — both touch the bucketed allocator + render — so they ship as one
design → plan → build cycle.

## 2. Invariants that bind (carried from the kickoff, must stay true)

- **`allocate()` stays pure.** No I/O-layer imports (`broker`/`auth`/`memory`/`cli`/`llm`);
  guarded by `tests/unit/test_allocator_purity.py`. Deterministic.
- **`vet()` stays the sole, un-bypassable cap authority.** All rejection/cap logic lives only in
  `risk/engine.py`. Nothing in this change replicates or relocates a cap. `vet` re-prices and
  re-caps *every* intent (including notional buys) on every call.
- **The flat (non-bucketed) path is byte-for-byte unchanged.**
- **The cycle stays brain-agnostic** — no `openai`/`strands`/`llm` imports reach `core/`.
- **DryRun stays the default**; the Phase 5 execution path (typed-yes → review → place → journal,
  halt-on-fail) must keep working unchanged after these allocator changes — it consumes only the
  *final* `VettedPlan`.

## 3. Resolved design decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Redistribution mechanism | **Re-allocate with a growing exclusion set** (allocate ↔ vet loop), keeping `vet` as sole authority and `allocate` pure. |
| 2 | Loop shape | **Bounded iterative** (round 0 + up to `MAX_ROUNDS = 3`), **return the best-deploying round** (not the last). |
| 3 | Whole-share flooring remainder | **Out of v1.** Redistribute only dollars freed by *rejected/excluded* names. Note as follow-up. |
| 4 | `max_trades_per_cycle` redesign | **In scope, via fair interleaving** in the allocator (ordering change only); `vet` untouched; cap value stays per-strategy configurable. |
| 5 | Stay within bucket | **Yes** — a bucket's freed dollars never bleed into another bucket. |
| 6 | Reporting | **Full visibility** — per-bucket deployed $/cash-left + a notes line naming each under-deployed bucket and its dominant reason. |
| — | Loop placement | **Extracted pure module** `core/deploy.py` (`complete_allocation`), unit-testable with plain data; `_run_bucketed` calls it. |

## 4. Component design

### 4.1 Rationale passthrough (Goal 1)

Pure passthrough — **no sizing impact.**

- `allocation/engine.py`:
  - `_buy_intent(symbol, dollars, data, allow_fractional, rationale="")` — add the `rationale`
    param, pass it straight to `TradeIntent(...)`.
  - `_split_buys(...)` — call `_buy_intent(sym, dollars, market[sym], allow_fractional,
    rationale=pos.thesis)` (it already holds `pos` in the loop).
  - `_trim_sells(...)` — set `rationale="trim to bucket target"` on the sell `TradeIntent`.
- Effect: render's Rationale column shows the thesis for bucketed approved trades, matching flat.

### 4.2 Fair interleaving (Goal 2 — the cap "redesign")

Make the binding cap *fair* by reordering, not by touching `vet`.

- In `allocate()`, replace the bucket-sequential `buy_intents.extend(buys)` with: collect one
  **rank-ordered buy list per bucket**, then **interleave by rank** across buckets — every
  bucket's rank-1 buy, then every bucket's rank-2, and so on — before composing
  `sell_intents + interleaved_buys`.
- **Per-bucket rank** = normalized `weight` descending, tie-break by symbol ascending
  (deterministic; equal-weight fallback already produces weight 1 → rank by symbol). Bucket order
  for the round-robin = `strategy.buckets` order.
- **`vet` is unchanged** — it still walks the plan in order under the global cap; it just now sees
  a fair order, so every bucket gets its top names before any bucket gets its tail. **Sizes are
  unchanged — only order changes.** The dollar `max_deploy_pct_per_cycle` cap likewise now
  consumes fairly across buckets, which is *more* aligned with `target_pct` than today.
- Single-bucket behavior is unaffected (one list, nothing to interleave); existing single-bucket
  allocator tests stay green. Multi-bucket tests that assert intent order will be updated to the
  interleaved order.

### 4.3 Redistribution loop (Goal 2 — deploy-completeness)

A bounded **allocate ↔ vet** loop that feeds `vet`'s own rejections back to the allocator as
exclusions, so freed dollars flow to surviving names in the same bucket.

- **`allocate()` signature gains `exclude: frozenset[str] = frozenset()`.** `_split_buys` skips
  any position whose `_norm(symbol) in exclude`. **Empty default ⇒ byte-for-byte identical** to
  today — the flat path never sets it and existing allocator tests are unaffected. (`frozenset`
  default is immutable — no mutable-default footgun.) Exclusion is buy-side only; sells (trims)
  are untouched.
- **`core/deploy.py` — `complete_allocation(strategy, recommendation, policy, portfolio, market,
  max_rounds=3) -> tuple[TradePlan, AllocationReport, VettedPlan]`:**
  1. Round 0: `plan, report = allocate(..., exclude=frozenset())`;
     `vetted = vet(plan, policy, portfolio, market.to_symbol_risk())`.
     Seed `best = (plan, report, vetted)`; `excluded: set[str] = set()`.
  2. For up to `max_rounds` rounds:
     - `newly = {rejected buy symbols in vetted} − excluded`. If empty → **break** (converged).
     - `excluded |= newly`; re-`allocate(..., exclude=frozenset(excluded))` → re-`vet`. Freed
       dollars flow to that bucket's survivors automatically via the same weight-split.
     - If this round's **total approved-buy dollars** exceeds best's → replace `best`.
  3. Return `best`, then enrich its report (§4.4).
- **Keep-best, not last — the correctness guard.** Re-allocating grows survivors, and a grown
  survivor can itself breach a cap (deploy/position) and flip approved → rejected, deploying
  *less*. Returning the round with max total approved-buy dollars (round 0 always a candidate;
  ties → earliest round) **guarantees the result is never worse than today**, and makes
  exclusion-reason classification unnecessary — we exclude *all* rejected buys and simply discard
  any regressive round. The loop **terminates** because `excluded` grows monotonically (a symbol,
  once excluded, is never re-added) and is hard-capped by `max_rounds`.
- **Within-bucket only.** A bucket's freed dollars never cross into another bucket (membership is
  first-match per symbol; redistribution re-splits a single bucket's budget over its survivors),
  preserving `target_pct` meaning. A bucket left with **zero survivors** (Cannabis-style total
  loss to the global cap, which redistribution *cannot* fix) keeps its budget as cash — surfaced
  in the report (§4.4), not silent.
- **Brain-agnostic.** `core/deploy.py` imports only `allocate` (allocation), `vet` (risk), and
  models — no `llm`/`broker`. It is pure and deterministic, takes the `MarketContext` and adapts
  (`market.symbols` for `allocate`, `market.to_symbol_risk()` for `vet`).

### 4.4 Reporting (Goal 2 — visibility)

Make under-deploy visible, never silent.

- **`BucketAllocation` gains** (all dollar `Decimal`): `budget` (= `target_pct/100 × investable`),
  `deployed` (Σ approved-buy `_order_value` mapped to the bucket), `cash_left`
  (= `max(budget − deployed, 0)`).
- **`AllocationReport.notes`** (field already exists) gains one line per under-deployed bucket
  naming the **dominant rejection reason** (the most frequent reason among that bucket's rejected
  intents, ties broken deterministically), grouping `vetted.rejected` by bucket — e.g.
  *"Cannabis Policy Optionality: $300 left as cash — 5 names rejected (exceeds max trades per
  cycle)."*
- Enrichment is a **pure** helper in `core/deploy.py`,
  `deployment_summary(report, strategy, recommendation, vetted) -> AllocationReport` (budget is
  recomputed from `report.investable` × `target_pct`), returning a new report (`model_copy`) with
  the per-bucket fields filled and notes appended. It
  maps approved/rejected buy symbols → buckets via a newly-exposed public pure helper
  `bucket_membership(strategy, recommendation) -> dict[str, str]` (today's private `_membership`
  in `allocation/engine.py`).
- **`cli/render.py`:** add a **Deployed** column to the allocation table (showing `deployed` and
  its % of the bucket `budget`, with a `($X left)` suffix when `cash_left > 0`), and render
  `allocation.notes` (currently unrendered).
- **Journaling is unchanged.** `memory/journal.py::record_allocation` keeps its current explicit
  column set (there is no schema-migration framework — tables are `CREATE TABLE IF NOT EXISTS`),
  so the new `BucketAllocation` fields are simply ignored on write (safe, no breakage).
  `deployed`/`cash_left` are render-time values and remain reconstructable from the already-
  journaled approved `plan_intents` + membership, so no durable audit is lost. (Persisting them
  is a noted follow-up if/when a migration mechanism lands.)

### 4.5 Wiring

`core/cycle.py::_run_bucketed` replaces its inline `allocate(...)` + `vet(...)` pair with a single
`complete_allocation(...)` call; everything downstream — `journal.record_plan/record_allocation`,
`_execute`, render — consumes the final `plan` / `vetted` / `allocation` exactly as before.

## 5. Files touched (anticipated)

| File | Change |
|------|--------|
| `src/rh_wizard/allocation/engine.py` | `exclude` param + rank-interleave in `allocate`; `rationale` passthrough in `_buy_intent`/`_split_buys`/`_trim_sells`; expose public `bucket_membership`. |
| `src/rh_wizard/core/deploy.py` | **New.** `complete_allocation` loop + `deployment_summary` enricher + a deployed-value helper. Pure. |
| `src/rh_wizard/core/cycle.py` | `_run_bucketed` calls `complete_allocation` instead of allocate+vet. |
| `src/rh_wizard/models/allocation.py` | `BucketAllocation` gains `budget` / `deployed` / `cash_left`. |
| `src/rh_wizard/cli/render.py` | Deployed column + render `allocation.notes`. |
| `src/rh_wizard/risk/engine.py` | **No change.** (Listed to make the invariant explicit.) |

## 6. Test plan

1. **Rationale:** bucketed `allocate` buys carry `pos.thesis`; sells carry `"trim to bucket
   target"`; `render` shows the thesis (not `-`).
2. **Interleaving:** multi-bucket `allocate` returns buys ordered round-robin by rank; under a
   small `max_trades_per_cycle` in `vet`, *every* bucket is represented (no late-bucket
   starvation).
3. **Redistribution:** a name rejected for a name-specific reason (e.g. liquidity floor) has its
   dollars redistributed to bucket survivors → total deployed rises; no cross-bucket bleed
   (each bucket's deployed ≤ its budget).
4. **Never-worse-than-round-0:** a constructed case where naive redistribution would regress →
   assert final total deployed ≥ round-0 total deployed.
5. **Zero-survivor bucket:** all of a bucket's names rejected → budget left as cash; report
   `cash_left == budget` and a notes line with the dominant reason.
6. **Reporting:** `budget` / `deployed` / `cash_left` correct; notes present; render shows the
   Deployed column and notes.
7. **Determinism:** identical inputs → identical converged plan (run twice).
8. **Regressions:** `test_allocator_purity` still green; flat cycle unchanged
   (`test_flat_cycle_unchanged_has_no_allocation`); bucketed execute path still places
   (`test_human_approval_places_orders_from_bucketed_path`).

## 7. Follow-ups (explicitly deferred)

- **Whole-share flooring-remainder sweep** — redistribute per-name whole-share rounding leftovers
  to fractionable survivors (needs the allocator to report per-name remainders + a second
  injection path; marginal gain on a fractionable-heavy broker).
- **Per-bucket trade cap** as a hard ceiling (distinct from the fairness fix here).
- **Persisting `deployed`/`cash_left` to the journal** (needs a schema-migration mechanism the
  journal doesn't have yet; today these are render-time and derivable from journaled intents).
- Autonomous mode + drawdown kill-switch.

## 8. Workflow

brainstorming (done) → writing-plans → subagent-driven-development →
finishing-a-development-branch (push + PR for Shane to merge).
