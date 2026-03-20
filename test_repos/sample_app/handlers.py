"""API request handlers — thin wrappers around the service layer."""

from __future__ import annotations

from api.middleware import run_middleware_chain
from api.routes import build_json_response, handle_api_call, route_request
from core.types import Request, Response
from models import Product
from services import (
    authenticate,
    flag_content,
    generate_user_report,
    get_user_orders,
    place_order,
    process_payment,
    register_user,
    run_bulk_import,
    send_notification,
    send_welcome,
)
from services.event_bus import broadcast
from utils import audit_log, format_currency, paginate


async def handle_register(request: dict) -> dict:
    """Handle a user registration request."""
    user = register_user(
        first_name=request["first_name"],
        last_name=request["last_name"],
        email=request["email"],
        password=request["password"],
    )
    return {"id": user.id, "name": user.full_name(), "email": user.email}


async def handle_login(request: dict) -> dict:
    """Handle a login request and return a token."""
    token = authenticate(request["email"], request["password"])
    if token is None:
        return {"error": "Invalid credentials", "status": 401}
    return {"token": token, "status": 200}


async def handle_create_order(request: dict) -> dict:
    """Handle an order creation request."""
    items = [
        (Product(id=item["product_id"], name=item["name"], price=item["price"]), item["quantity"])
        for item in request["items"]
    ]
    order = place_order(request["user_id"], items)
    return {
        "order_id": order.id,
        "total": format_currency(order.total()),
        "item_count": len(order.items),
    }


async def handle_list_orders(request: dict) -> dict:
    """Handle a request to list a user's orders."""
    orders = get_user_orders(request["user_id"])
    page = request.get("page", 1)
    size = request.get("page_size", 10)
    page_orders = paginate(orders, page, size)
    return {
        "orders": [
            {"id": o.id, "total": format_currency(o.total()), "status": o.status}
            for o in page_orders
        ],
        "total": len(orders),
        "page": page,
    }


# ---------------------------------------------------------------------------
# Chain 1: Notification Pipeline (5 hops)
# ---------------------------------------------------------------------------

async def handle_send_notification(request: dict) -> dict:
    """Handle a notification send request.

    Entry point for the notification pipeline chain:
    handle_send_notification → send_notification → resolve_user_context,
    format_notification, dispatch_event, audit_log.
    """
    result = send_notification(
        session=request["session"],
        template=request["template"],
        recipient=request["recipient"],
        context=request.get("context", {}),
    )
    return {"status": 200, "data": result}


# ---------------------------------------------------------------------------
# Chain 2: Payment Processing (6 hops — deepest)
# ---------------------------------------------------------------------------

async def handle_process_payment(request: dict) -> dict:
    """Handle a payment processing request.

    Entry point for the deepest chain:
    handle_process_payment → process_payment → resolve_user_context,
    calculate_order_total → Order.total → OrderItem.subtotal →
    Product.discounted_price, record_ledger_entry, audit_log, format_currency.
    """
    result = process_payment(
        session=request["session"],
        order=request["order"],
    )
    return {"status": 200, "data": result}


# ---------------------------------------------------------------------------
# Chain 3: User Onboarding (5 hops)
# ---------------------------------------------------------------------------

async def handle_onboard_user(request: dict) -> dict:
    """Handle a full user onboarding flow.

    Entry point for the onboarding chain:
    handle_onboard_user → register_user (validate_email, hash_password,
    user_repo.save) → send_welcome (format_notification, broadcast)
    → audit_log.
    """
    user = register_user(
        first_name=request["first_name"],
        last_name=request["last_name"],
        email=request["email"],
        password=request["password"],
    )
    send_welcome(user, request.get("emitter"))
    audit_log("user", user.id, "onboard", user.id)
    return {"status": 201, "user_id": user.id}


# ---------------------------------------------------------------------------
# Chain 4: Content Moderation (5 hops)
# ---------------------------------------------------------------------------

async def handle_flag_content(request: dict) -> dict:
    """Handle a content flagging request.

    Entry point for the moderation chain:
    handle_flag_content → flag_content → resolve_user_context,
    evaluate_content (count_words, slugify), handle_comment_flagged,
    format_notification, audit_log.
    """
    result = flag_content(
        session=request["session"],
        content_text=request["content"],
        content_id=request["content_id"],
    )
    return {"status": 200, "data": result}


# ---------------------------------------------------------------------------
# Chain 5: Report Generation (3 hops — shallowest)
# ---------------------------------------------------------------------------

async def handle_generate_report(request: dict) -> dict:
    """Handle a user activity report generation request.

    Entry point for the shallowest chain:
    handle_generate_report → generate_user_report → summarize_user_activity,
    format_currency, audit_log.
    """
    result = generate_user_report(
        user=request["user"],
        posts=request.get("posts", []),
        comments=request.get("comments", []),
    )
    return {"status": 200, "data": result}


# ---------------------------------------------------------------------------
# Chain 6: Authenticated API Request (6 hops)
# ---------------------------------------------------------------------------

async def handle_authenticated_request(request: dict) -> dict:
    """Handle an authenticated API request through the full middleware chain.

    Entry point for the middleware chain:
    handle_authenticated_request → run_middleware_chain (cors_middleware,
    auth_middleware) → route_request → handle_api_call →
    build_json_response → audit_log.
    """
    req = request["request"]
    resp = request["response"]
    context = request.get("context", {})
    chain = request.get("middleware_chain", [])

    run_middleware_chain(chain, req, resp, context)
    route = route_request(req)
    api_result = handle_api_call(req, context.get("config", {}), context.get("session", {}))
    build_json_response(resp, api_result)
    audit_log("api", context.get("user_id", "anonymous"), "request", req.path)
    return {"status": resp.status_code, "route": route, "data": api_result}


# ---------------------------------------------------------------------------
# Chain 7: Bulk Data Import (5 hops)
# ---------------------------------------------------------------------------

async def handle_bulk_import(request: dict) -> dict:
    """Handle a bulk data import request.

    Entry point for the import chain:
    handle_bulk_import → run_bulk_import (parse_input, validate_row,
    enrich, store_record) → broadcast → audit_log.
    """
    result = run_bulk_import(
        raw_data=request["data"],
        db=request.get("db"),
    )
    broadcast(request.get("emitter"), "bulk_import_complete", result)
    audit_log("import", request.get("actor_id", "system"), "bulk_import", result.get("record_id", ""))
    return {"status": 200, "data": result}
