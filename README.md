# AI Revenue Recovery Agent

Built for the **Razorpay AI Buildathon — Track 03: AI Revenue Recovery**.

## The problem

Revenue loss rarely happens in one clean step. A payment fails for a
bank-side reason, a customer abandons an OTP screen, or a UPI ID is
mistyped — and without a system watching, that money is just gone.
Different failure reasons need different recovery moves; retrying a
declined card the same way it already failed wastes the attempt.

## What this agent does

Given a batch of failed/at-risk payments, the agent:

1. **Diagnoses** the root cause behind each failure (transient infra
   issue, customer fund issue, customer input error, issuer policy
   issue, incomplete customer action).
2. **Chooses a bounded recovery action** from a root-cause-specific
   playbook (auto-retry same method, auto-retry backup method, delayed
   retry, SMS nudge, WhatsApp payment link, manual escalation).
3. **Executes** the recovery workflow (simulated against Razorpay
   test-mode semantics — see "Next step" below).
4. **Stops** under three explicit rules: customer opted out of
   retries, hard cap of 3 attempts per payment, or playbook exhausted
   → payment moves to an exception queue instead of retrying forever.
5. **Logs every action** to `audit_trail.csv` — one row per attempt,
   with the action taken and its outcome, so every rupee moved can be
   traced back to a decision.
6. **Reports measured results**: total amount at risk, total amount
   recovered, recovery rate by count and by amount, and a breakdown by
   failure reason, in `summary.json`.

## Architecture

```
Failed payments (webhook/API)
        │
        ▼
Root-cause classifier  ──►  Action policy (root cause → ranked actions)
        │                          │
        ▼                          ▼
   Stopping rules  ◄──────  Bounded execution loop (max 3 attempts)
        │
        ▼
  Audit trail (CSV)  +  Recovery metrics (JSON)
```

In this build, the payment batch is synthetic (60 generated failures
across 6 realistic failure reasons) and the recovery *execution* step
is simulated with reason-specific success probabilities, so the whole
pipeline runs end to end without needing live production traffic.

## Run it

```bash
python recovery_agent.py
```

Sample output on a 60-payment batch:

```
Amount at risk        : Rs. 380,854.47
Amount recovered      : Rs. 159,396.71
Recovery rate (amount): 41.9%
Recovery rate (count) : 48.3%
Unresolved (exceptions): 31
```

## What broke, and how it got fixed

The first version checked whether a payment had been recovered with
`payment in recovered_payments`, comparing whole dicts. That's fragile
— if two synthetic payments ever land on identical values, list
membership treats them as the same payment and the recovery count
gets silently wrong. Fixed by keying everything off `payment_id`
instead of comparing full records, since that's the one field
guaranteed unique — the same assumption the real Razorpay payment
object gives you for free.

## Honest limitations / next step

- Recovery execution is simulated, not wired to the live Razorpay
  Payments API — the next step is swapping the simulated
  `recover_prob` roll for real test-mode retry/refund/notify calls.
- The action-policy success probabilities are playbook assumptions,
  not learned from historical data — with real recovery outcomes this
  becomes a place to plug in a model instead of a fixed table.
- SMS/WhatsApp notification actions are logged, not actually sent.
