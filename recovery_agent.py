"""
AI Revenue Recovery Agent
--------------------------
Detects at-risk / failed payments, diagnoses the root cause, chooses a
bounded recovery action, executes a simulated recovery workflow, and
reports measured results with a full audit trail.

Built for the Razorpay AI Buildathon — Track 03: AI Revenue Recovery.

Run:
    python recovery_agent.py

Outputs:
    audit_trail.csv   -> every action taken, per payment, per attempt
    summary.json      -> aggregate recovery metrics
"""

import random
import json
import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta

random.seed(42)  # reproducible demo run

# ---------------------------------------------------------------------
# 1. SYNTHETIC DATA: failed / at-risk payments
#    (in production this would come from Razorpay webhooks / Payments API)
# ---------------------------------------------------------------------

FAILURE_REASONS = [
    "insufficient_funds",
    "bank_server_timeout",
    "card_declined_issuer",
    "network_error",
    "otp_not_entered",
    "invalid_vpa",
]

CUSTOMER_SEGMENTS = ["subscription", "one_time_checkout", "b2b_invoice"]


def generate_payments(n=60):
    payments = []
    for i in range(1, n + 1):
        payments.append({
            "payment_id": f"pay_{1000 + i}",
            "amount": round(random.uniform(150, 12000), 2),
            "failure_reason": random.choice(FAILURE_REASONS),
            "segment": random.choices(
                CUSTOMER_SEGMENTS, weights=[0.4, 0.45, 0.15]
            )[0],
            "customer_opted_out": random.random() < 0.05,  # 5% opted out of retries
            "created_at": datetime.now() - timedelta(hours=random.randint(1, 72)),
        })
    return payments


# ---------------------------------------------------------------------
# 2. DIAGNOSIS: map failure reason -> root cause category
# ---------------------------------------------------------------------

ROOT_CAUSE_MAP = {
    "insufficient_funds": "customer_fund_issue",
    "bank_server_timeout": "transient_infra_issue",
    "card_declined_issuer": "issuer_policy_issue",
    "network_error": "transient_infra_issue",
    "otp_not_entered": "customer_action_incomplete",
    "invalid_vpa": "customer_input_error",
}

# ---------------------------------------------------------------------
# 3. RECOVERY ACTION POLICY: root cause -> ordered list of bounded actions
#    each action has an assumed recovery probability (from playbook /
#    would be learned from historical data in production)
# ---------------------------------------------------------------------

ACTION_POLICY = {
    "transient_infra_issue": [
        ("auto_retry_same_method", 0.55),
        ("auto_retry_backup_method", 0.30),
        ("notify_customer_sms", 0.10),
    ],
    "customer_fund_issue": [
        ("delay_retry_24h", 0.35),
        ("notify_customer_sms", 0.20),
        ("escalate_manual_followup", 0.10),
    ],
    "customer_action_incomplete": [
        ("notify_customer_sms", 0.45),
        ("send_payment_link_whatsapp", 0.30),
    ],
    "customer_input_error": [
        ("send_payment_link_whatsapp", 0.40),
        ("notify_customer_sms", 0.15),
    ],
    "issuer_policy_issue": [
        ("auto_retry_backup_method", 0.25),
        ("send_payment_link_whatsapp", 0.15),
        ("escalate_manual_followup", 0.10),
    ],
}

MAX_ATTEMPTS = 3


@dataclass
class AuditEntry:
    payment_id: str
    attempt: int
    action: str
    outcome: str
    amount: float
    timestamp: str


def recover_payment(payment, audit_log):
    """Run the bounded recovery workflow for a single payment.
    Returns True if recovered, False otherwise. Appends every step to audit_log.
    """
    root_cause = ROOT_CAUSE_MAP[payment["failure_reason"]]
    actions = ACTION_POLICY[root_cause]

    # Stopping rule 1: respect customer opt-out — never retry
    if payment["customer_opted_out"]:
        audit_log.append(AuditEntry(
            payment["payment_id"], 0, "skipped_opted_out", "not_attempted",
            payment["amount"], datetime.now().isoformat(timespec="seconds")
        ))
        return False

    attempt = 0
    for action, recover_prob in actions:
        attempt += 1
        # Stopping rule 2: hard cap on attempts per payment
        if attempt > MAX_ATTEMPTS:
            break

        recovered = random.random() < recover_prob
        outcome = "recovered" if recovered else "failed"

        audit_log.append(AuditEntry(
            payment["payment_id"], attempt, action, outcome,
            payment["amount"], datetime.now().isoformat(timespec="seconds")
        ))

        if recovered:
            return True

    # Stopping rule 3: exhausted playbook without success -> exception queue
    return False


def main():
    payments = generate_payments(60)
    audit_log = []

    total_at_risk = sum(p["amount"] for p in payments)
    recovered_payments = []
    unresolved_payments = []

    for p in payments:
        success = recover_payment(p, audit_log)
        if success:
            recovered_payments.append(p)
        else:
            unresolved_payments.append(p)

    total_recovered = sum(p["amount"] for p in recovered_payments)
    recovery_rate = len(recovered_payments) / len(payments) * 100
    amount_recovery_rate = (total_recovered / total_at_risk) * 100

    # breakdown by failure reason
    breakdown = {}
    for reason in FAILURE_REASONS:
        reason_payments = [p for p in payments if p["failure_reason"] == reason]
        reason_recovered = [p for p in reason_payments if p in recovered_payments]
        if reason_payments:
            breakdown[reason] = {
                "total": len(reason_payments),
                "recovered": len(reason_recovered),
                "recovery_rate_pct": round(
                    len(reason_recovered) / len(reason_payments) * 100, 1
                ),
            }

    summary = {
        "batch_size": len(payments),
        "total_amount_at_risk": round(total_at_risk, 2),
        "total_amount_recovered": round(total_recovered, 2),
        "amount_recovery_rate_pct": round(amount_recovery_rate, 1),
        "payment_count_recovery_rate_pct": round(recovery_rate, 1),
        "unresolved_count": len(unresolved_payments),
        "unresolved_payment_ids": [p["payment_id"] for p in unresolved_payments],
        "breakdown_by_failure_reason": breakdown,
    }

    # write audit trail
    with open("audit_trail.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["payment_id", "attempt", "action", "outcome", "amount", "timestamp"])
        for e in audit_log:
            writer.writerow([e.payment_id, e.attempt, e.action, e.outcome, e.amount, e.timestamp])

    with open("summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # console report (this is what you show in the demo video)
    print("=" * 60)
    print("AI REVENUE RECOVERY AGENT — RUN SUMMARY")
    print("=" * 60)
    print(f"Batch size            : {summary['batch_size']} payments")
    print(f"Amount at risk        : Rs. {summary['total_amount_at_risk']:,}")
    print(f"Amount recovered      : Rs. {summary['total_amount_recovered']:,}")
    print(f"Recovery rate (amount): {summary['amount_recovery_rate_pct']}%")
    print(f"Recovery rate (count) : {summary['payment_count_recovery_rate_pct']}%")
    print(f"Unresolved (exceptions): {summary['unresolved_count']}")
    print("-" * 60)
    print("Breakdown by failure reason:")
    for reason, stats in breakdown.items():
        print(f"  {reason:25s} {stats['recovered']}/{stats['total']} recovered "
              f"({stats['recovery_rate_pct']}%)")
    print("-" * 60)
    print("Full audit trail -> audit_trail.csv")
    print("Full summary     -> summary.json")


if __name__ == "__main__":
    main()
