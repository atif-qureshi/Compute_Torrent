# 09 — Incentives and Credits (BOINC-style, off-chain)

## Purpose
Reward honest contribution with credits, discourage cheating, and use credits to prioritize requesters. No real money, no crypto.

## Responsibilities
1. Compute credit per verified chunk using a BOINC-inspired formula: credit grows with the amount of verified work (for example tokens processed times a hardware-normalized factor), not with claimed time.
2. Append-only ledger of credit and penalty entries.
3. Requester spending: submitting tasks costs credits (estimated at submit, settled at completion).
4. Priority management: higher balance or higher contribution gives higher queue priority; workers with high trust get preferred assignment.
5. Trust score for workers: rises with canary passes and agreements, falls with failures and flags.
6. Penalties: failed verification, abandoned chunks, repeated timeouts.
7. Initial grant for new users so the demo works.

## Credit rules (conceptual)
| Event | Effect |
|---|---|
| chunk verified | + credit proportional to verified work |
| replica verified (agreement) | + smaller credit |
| canary pass | + small trust, no credit (not real work) |
| canary or L3 fail | - penalty and trust drop |
| timeout/abandon | - small penalty |
| task completed (requester) | - credits equal to work cost |

Anti-gaming: credit only after verification; cap per period; new workers start with low trust and limited high-value tasks.

## Privacy levels and priority (proposal feature; not the hardware capability tier)
| Level | Meaning | Credit/priority effect |
|---|---|---|
| 1 | Public data, any worker | base cost |
| 2 | Sliced so no worker sees the whole task | higher cost |
| 3 | Only trusted workers | highest cost, fastest priority |
MVP: privacy levels are stored, priced and used for seeder eligibility filtering; stronger protection is documented as future work. Credits earned are sent to the seeder app in `verdict_notice` so the dashboard can show them (APP-3).

## Inputs / Outputs
| In | Out |
|---|---|
| verdicts from 06, completed chunks, timeouts | ledger entries, trust scores |
| task submit and complete events | balance checks, priority values for 05 |

## Dependencies
- Needs: 03, 06. Feeds: 05, 01.
- Tech: Python, PostgreSQL ledger.

## Rules
1. Never edit past entries; correct with new entries.
2. Balance shown to users is computed from the ledger.
3. Formula constants are configuration, tuned in module 11.

## Build steps
1. Ledger table and balance query.
2. Credit on verified chunk.
3. Requester cost and balance checks.
4. Trust score and penalty rules.
5. Priority and tier handling.

## Acceptance checks
- Honest worker's balance grows in proportion to verified work.
- Cheater's trust and eligibility drop after caught results.
- Requester with zero balance cannot submit (clear message).
- Ledger sums reconcile with task records.

## Out of scope
Real payments, cryptocurrency, marketplace pricing.
