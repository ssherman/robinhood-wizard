# Kickoff note — Bucketed allocation: deploy-completeness + rationale passthrough

> Pre-brainstorm scoping note (NOT a spec yet). Next session: start with the
> `superpowers:brainstorming` skill, using this as the context. Two goals below.
> Created 2026-06-27, after Phase 5 (HumanApproval execution) landed in PR #14.

## Why we're here
While reviewing a bucketed DryRun of `legit-strategy-1`, two issues surfaced:

1. **Per-trade Rationale renders as `-` for bucketed strategies.** (cosmetic/audit)
2. **A bucketed run deploys less than its target** because rejected/floored
   dollars are silently left as cash, not redistributed. (real allocator change)

These are cohesive (both touch the bucketed allocator + render), so do them as
ONE design→plan→build cycle.

## Goal 1 — Surface the per-position thesis as the trade rationale (trivial)
The bucket recommender LLM already produces a one-line `thesis` per position
(prompt asks for it: `allocation/web_llm.py:64`; stored in
`RecommendedPosition.thesis`, `models/allocation.py:24`). But the deterministic
allocator drops it: `_buy_intent` (`allocation/engine.py:66-78`) and
`_trim_sells` (`engine.py:117-146`) build each `TradeIntent` WITHOUT setting
`.rationale` (defaults to `""`). Render shows `i.rationale or "-"`
(`cli/render.py:209`) → `-`.

Fix: thread `pos.thesis` into the buy intent's rationale in `_split_buys`
(`engine.py:108-113`); give sells a fixed rationale like `"trim to bucket target"`.
This is purely passthrough — it does NOT affect sizing. ~2 lines + a test.
(Flat LLM-planned strategies already populate rationale via `planning/llm.py`,
which is why this only shows up in bucketed mode.)

## Goal 2 — Redistribute rejected/floored dollars within a bucket (real change)
### Current behavior (the gap)
- Sizing IS conviction-weighted: within a bucket, the dollar budget
  (`target_pct/100 × investable`) is split proportionally to the LLM's numeric
  `weight` per position (`engine.py:100-113`, `dollars = shortfall × w / Σw`);
  equal-weight only as a fallback when no positive weights. Dollars → qty:
  fractionable → notional `amount`; else whole shares ROUND_DOWN (`engine.py:72-78`).
- BUT `allocate()` is a single deterministic pass. Rejections happen later in
  risk `vet()` (`risk/engine.py`), AFTER the plan is built. A name that gets
  rejected (e.g. POWL: liquidity floor) or floored to 0 whole shares has its
  slice simply dropped — the freed dollars are NOT reassigned to surviving
  names in the same bucket. Whole-share flooring remainder is likewise dropped
  ("remainder→cash").

### Evidence from the run (investable ≈ $3,000, cash_reserve via a 5% bucket)
- AI Infrastructure bucket (35% = $1,050): MU/MRVL/CLS/DELL/AMAT summed to
  EXACTLY $1,050 in ratio 30:24:20:16:10 → proves weight-proportional, not even.
- Power & Electrification (25% = $750): approved names summed to only $630 —
  the missing ~$120 is POWL, allocated then rejected (liquidity), not reassigned.
- Cannabis (10%): GTBIF/IIPR/TRLV/MJ ALL rejected "exceeds max trades per cycle
  (20)" → bucket deployed ~$0. Redistribution within the bucket CANNOT fix this
  (the cap is global, not name-specific). See open question 4.

### The core design problem
To redistribute, you must know WHICH intents get rejected — and that only
happens in `vet()`. So this is an **allocate ↔ vet loop**, not a pure-allocator
tweak. The allocator (`allocation/engine.py`) is purity-guarded
(`tests/unit/test_allocator_purity.py`) and `vet()` is the sole, un-bypassable
cap authority (`VettedPlan`) — keep both true.

### Open design questions for brainstorming
1. **Loop shape:** bounded iterative (allocate → vet → redistribute survivors →
   re-vet, capped at N rounds for determinism) vs single redistribution pass?
   (Lean: bounded iterative, small cap e.g. 3, deterministic.)
2. **Where does the loop live?** Likely in `core/cycle.py` `_run_bucketed`
   (it already calls allocate then vet), keeping `allocate()` itself pure —
   pass the survivor budget back in as a re-allocation. Don't move cap logic
   into the allocator (would duplicate risk authority).
3. **Flooring remainder:** also sweep within-bucket whole-share flooring leftover
   into the redistribution, or only rejections?
4. **Rejections redistribution can't fix** (global "max trades per cycle (20)"
   cap; single-name > max_position; a bucket with zero eligible survivors): leave
   as cash + report clearly. Also: does the max-trades-per-cycle cap itself need
   rethinking for multi-bucket strategies? (Cannabis lost its whole budget to it.)
   Decide if that's in scope here or a separate follow-up.
5. **Stay within the bucket** (preserve `target_pct` meaning) — confirm yes;
   never bleed one bucket's budget into another.
6. **Reporting:** `AllocationReport` should show deployed-vs-target per bucket and
   name what was left as cash and why, so under-deploy is visible not silent.

## Constraints that still bind (carry into the spec)
- `allocate()` stays pure (purity test). `vet()` stays the sole cap authority and
  re-prices/re-caps EVERY intent incl. notional buys.
- Cycle stays brain-agnostic (no openai/strands in `core/cycle.py`).
- Flat (non-bucketed) path must stay byte-for-byte unchanged.
- DryRun default; the Phase 5 execution path (typed-yes, review→place→journal)
  must keep working unchanged after these allocator changes.

## Recommended workflow (the project's usual)
brainstorming (resolve Qs 1–6) → writing-plans → subagent-driven-development →
finishing-a-development-branch (push + PR for Shane to merge).

## Suggested resume prompt for the new session
"Let's brainstorm the bucketed-allocation deploy-completeness + rationale
passthrough work. See docs/superpowers/notes/2026-06-27-bucket-deploy-completeness-kickoff.md."
