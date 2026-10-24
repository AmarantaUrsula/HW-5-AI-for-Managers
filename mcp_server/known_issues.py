"""Known-issue playbook: routine ticket patterns with a known solution, and when to escalate.

These are routing rules, not shop facts. triage_ticket in server.py matches each
ticket against them using live values from the database.

Tiers:
  1 = staff:       routine known issue with no blockers. Goes straight to the specialist(s) listed.
  2 = it_director: blocked, needs several teams, or no known solution. The IT Director assigns the minimum staff.
  3 = boss:        a cash conflict (obligations exceed cash), so the Boss sets priorities with a human.
"""

KNOWN_ISSUES = {
    "KI-ORDER-INSTOCK": {
        "ticket_type": "customer_order",
        "title": "Customer order, item in stock",
        "tier": 1,
        "route": ["customer_service"],
        "known_solution": "Confirm the stock, draft a confirmation to the customer, and mark the ticket waiting_on_customer.",
        "tools": ["get_ticket", "check_stock_and_price", "draft_message", "update_ticket"],
    },
    "KI-ORDER-RESTOCK": {
        "ticket_type": "customer_order",
        "title": "Customer order, out of stock, vendor can ship",
        "tier": 1,
        "route": ["inventory", "customer_service"],
        "known_solution": "Inventory finds the vendor (by specialty) and the arrival date (today + lead_days). Customer service drafts the date to the customer.",
        "tools": ["get_ticket", "check_stock_and_price", "list_vendors", "check_vendor_can_ship", "draft_message", "update_ticket"],
    },
    "KI-ORDER-VENDOR-BLOCKED": {
        "ticket_type": "customer_order",
        "title": "Customer order, out of stock, vendor blocked by an open invoice",
        "tier": 2,
        "route": ["inventory", "accounting", "customer_service"],
        "known_solution": "Confirm the blocking invoice. Accounting requests payment (needs human 2FA over $50). Customer service drafts an update to the customer.",
        "tools": ["check_stock_and_price", "check_vendor_can_ship", "get_cash_position", "preview_payment", "pay_invoice", "draft_message", "update_ticket"],
    },
    "KI-RENT-ROUTINE": {
        "ticket_type": "rent_notice",
        "title": "Rent notice matches the lease, not overdue, cash covers it",
        "tier": 1,
        "route": ["facilities", "accounting"],
        "known_solution": "Facilities checks the notice against the lease. Accounting requests the rent payment (needs human 2FA over $50).",
        "tools": ["get_ticket", "check_rent_due", "preview_payment", "pay_rent", "update_ticket"],
    },
    "KI-RENT-OVERDUE": {
        "ticket_type": "rent_notice",
        "title": "Rent overdue",
        "tier": 2,
        "route": ["facilities", "accounting", "customer_service"],
        "known_solution": "Pay as soon as a human approves, and draft a note to the landlord. The IT Director coordinates.",
        "tools": ["check_rent_due", "preview_payment", "pay_rent", "draft_message", "update_ticket"],
    },
    "KI-DISCOUNT-INSTOCK": {
        "ticket_type": "price_override",
        "title": "Bulk discount request, quantity in stock",
        "tier": 1,
        "route": ["customer_service"],
        "known_solution": "Quote a discount above unit cost and draft it as a proposal that needs human approval.",
        "tools": ["get_ticket", "check_stock_and_price", "quote_bulk_discount", "draft_message", "update_ticket"],
    },
    "KI-DISCOUNT-SHORTFALL": {
        "ticket_type": "price_override",
        "title": "Bulk discount request, quantity exceeds stock",
        "tier": 2,
        "route": ["inventory", "customer_service"],
        "known_solution": "Inventory confirms the shortfall and whether a restock is possible. Customer service drafts a partial or conditional offer above cost, pending human approval.",
        "tools": ["check_stock_and_price", "check_vendor_can_ship", "list_vendors", "quote_bulk_discount", "draft_message", "update_ticket"],
    },
}

UNKNOWN_ISSUE = {
    "id": "KI-UNKNOWN",
    "title": "No known solution",
    "tier": 2,
    "route": [],
    "known_solution": "None. The IT Director decides who handles it.",
    "tools": ["get_ticket"],
}

TIER_OWNER = {1: "staff", 2: "it_director", 3: "boss"}
