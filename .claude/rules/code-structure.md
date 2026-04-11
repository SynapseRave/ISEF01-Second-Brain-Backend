# Code Structure & Style

## Style

- PEP 8, enforced by ruff (`ruff check . --fix && ruff format .`)
- Type hints on all function signatures
- Google-style docstrings on all public functions/classes
- `snake_case` for variables/functions, `PascalCase` for classes
- Max line length: 88 (ruff default)
- Max function length: 50 lines — use private helpers to split longer functions

## File Structure

### Services (`app/services/*.py`)

```
# 1. Module-level constants (UPPER_CASE, _prefixed if internal)
# 2. Private helper functions (_prefix) — utilities, never called from outside
# 3. Public functions — the module's API, imported by routes
```

### Routes (`app/api/routes/*.py`)

```
# 1. Router definition
# 2. Private helper functions (_prefix)
# 3. Endpoint handlers in HTTP method order: GET → POST → PUT → DELETE
```

### Classes (e.g. `app/services/llm/`)

```
# 1. Class attributes / constants
# 2. __init__
# 3. Private methods (_prefix) — internal logic and helpers
# 4. Public methods — implement the interface (overrides)
```

## Naming Rules

- `_underscore` prefix = private/internal — never imported or called from outside the module
- Public functions/methods always have a docstring
- Constants at module level: `UPPER_CASE` or `_UPPER_CASE` if internal
