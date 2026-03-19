# Test Repositories

Sample codebases for exercising the Bumblebee graph import pipeline.

## sample_app

A Python application with realistic cross-file relationships, designed to
exercise LogicNode extraction, variable dataflow, and TypeShape structural
type matching.

### Root modules (e-commerce domain)

- **models.py** — Domain models (`User`, `Order`, `Product`, `BaseRepository`)
- **auth.py** — Password hashing and token management
- **repository.py** — In-memory data access (`UserRepository`, `OrderRepository`)
- **services.py** — Business logic orchestrating auth + repos + models
- **handlers.py** — Async API handlers calling into services
- **utils.py** — Shared utilities (validation, ID generation, formatting)

### Package modules (TypeShape-heavy patterns)

- **core/** — Shared types (`Request`, `Response`), config dict patterns, `BaseModel`, `Event`
- **models/** — `User(BaseModel)`, `Post(BaseModel)`, `Comment`, `QueryBuilder` with row dict subset patterns
- **services/** — Auth (token/cred/session dicts, hasher methods), data pipeline (DataFrame attrs, DB conn methods, file I/O, ETL chain), event bus (event attrs, message dicts, emitter methods)
- **api/** — HTTP routes (request/response attrs, config dicts, cross-module calls to auth), middleware (CORS, session, shared request shapes with routes and auth)
- **utils/** — Math helpers (float/int primitive sharing, vector/matrix attrs, stats dicts), graph algorithms (node attrs, edge dicts, stack/queue/set methods), text processing

### Expected graph structure

- ~200 LogicNodes (classes, methods, functions)
- ~750 Variables with dataflow edges
- ~370 shape evidence entries → ~130 unique TypeShape nodes
- ~46 TypeShapes shared across multiple functions/files
- CALLS edges (handlers -> services -> repository/auth, api -> services -> models)
- MEMBER_OF edges (methods -> classes)
- INHERITS edges (User/Post/Comment -> BaseModel, UserRepository/OrderRepository -> BaseRepository)
- HAS_SHAPE / ACCEPTS / PRODUCES edges connecting variables and functions to TypeShape hub nodes
- COMPATIBLE_WITH edges between superset/subset shapes (e.g., token dict with 4 keys → token dict with 2 keys)
- Cross-module TypeShape sharing: same `request` attr shape used in api/routes.py, api/middleware.py, and services/auth_service.py
