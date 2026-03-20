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
