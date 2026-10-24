"""Human-approval tokens for payments.

The agent runner (backend/run.py) creates a random secret for each run and
passes it only to the MCP server process. After a human approves a payment (and
passes 2FA when the amount is over the threshold), the runner signs the exact
payment with that secret. The LLM never sees the secret, so it can't forge an
approval. Without a secret, for example when the vibe coder connects through
.mcp.json, every payment is refused.
"""

import hashlib
import hmac

TWO_FACTOR_THRESHOLD_USD = 50.00


def payment_message(kind: str, ref_id: int, amount: float, due: str, account: str,
                    approved_by: str, factor: str) -> str:
    # Includes the due date so an approval can't be replayed after rent's next_due moves.
    return f"{kind}|{ref_id}|{amount:.2f}|{due}|{account}|{approved_by}|{factor}"


def sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify(secret: str, message: str, token: str) -> bool:
    return bool(secret) and hmac.compare_digest(sign(secret, message), token or "")
