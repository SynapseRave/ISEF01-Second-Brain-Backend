---
paths:
  - "app/db/**/*.py"
  - "alembic/**/*.py"
  - "app/schemas/**/*.py"
---

# Database Patterns

## SQLAlchemy Models

- Use `DeclarativeBase` with `mapped_column()`
- Every model needs: `id` (UUID PK), `created_at`, `updated_at` timestamps
- Use `user_id` (from Keycloak JWT sub) as FK for user-owned resources
- Table names: plural snake_case (e.g., `user_inputs`, `credentials`)

## Model Template

```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class UserInput(Base):
    __tablename__ = "user_inputs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

## Migrations

- Use `alembic revision --autogenerate` to create migrations
- Review every generated migration before applying
- Message format: lowercase, descriptive (e.g., "add credentials table")
- Never edit migrations already applied to shared environments

## Pydantic Schemas

- `ResourceCreate` — POST request bodies
- `ResourceUpdate` — PUT/PATCH bodies (all fields Optional)
- `ResourceResponse` — API responses (includes id, timestamps)
- Use `model_config = ConfigDict(from_attributes=True)` for ORM compatibility

## Credential Storage

- User API keys (OpenAI, Anthropic, external services) must be encrypted at rest
- Use a dedicated `credentials` table with `encrypted_value` column
- Never return decrypted keys in API responses
- Never log API key values
