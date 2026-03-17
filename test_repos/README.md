# Test Repositories

Sample codebases for exercising the Bumblebee graph import pipeline.

## sample_app

A small Python application with realistic cross-file relationships:

- **models.py** — Domain models (`User`, `Order`, `Product`, `BaseRepository`)
- **auth.py** — Password hashing and token management
- **repository.py** — In-memory data access (`UserRepository`, `OrderRepository`)
- **services.py** — Business logic orchestrating auth + repos + models
- **handlers.py** — Async API handlers calling into services
- **utils.py** — Shared utilities (validation, ID generation, formatting)

### Expected graph structure

- ~30+ LogicNodes (classes, methods, functions)
- CALLS edges (handlers -> services -> repository/auth)
- MEMBER_OF edges (methods -> classes)
- INHERITS edges (UserRepository/OrderRepository -> BaseRepository)
- Variable dataflow (ASSIGNS, READS, RETURNS)
