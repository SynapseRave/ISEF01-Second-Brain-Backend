import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.db.models.user_input import UserInput
from app.services.input import (
    delete_input,
    get_conversation,
    get_input_by_id,
    get_inputs,
    save_input,
)

_USER_A = "user-a"
_USER_B = "user-b"


# ---------------------------------------------------------------------------
# save_input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_input_creates_new_conversation_when_none_given(
    db_session: AsyncSession,
) -> None:
    record = await save_input(db_session, _USER_A, "Test prompt")
    assert record.conversation_id is not None
    assert isinstance(record.conversation_id, uuid.UUID)


@pytest.mark.asyncio
async def test_save_input_uses_provided_conversation_id(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    record = await save_input(db_session, _USER_A, "Folge-Nachricht", cid)
    assert record.conversation_id == cid


@pytest.mark.asyncio
async def test_save_input_appends_to_existing_conversation(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    r1 = await save_input(db_session, _USER_A, "Erste", cid)
    r2 = await save_input(db_session, _USER_A, "Zweite", cid)

    assert r1.conversation_id == r2.conversation_id == cid

    result = await db_session.execute(
        select(UserInput).where(UserInput.conversation_id == cid)
    )
    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_save_input_each_new_call_without_cid_gets_different_conversation(
    db_session: AsyncSession,
) -> None:
    r1 = await save_input(db_session, _USER_A, "Erste")
    r2 = await save_input(db_session, _USER_A, "Zweite")
    assert r1.conversation_id != r2.conversation_id


# ---------------------------------------------------------------------------
# get_inputs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_inputs_returns_only_user_records(
    db_session: AsyncSession,
) -> None:
    await save_input(db_session, _USER_A, "A Prompt")
    await save_input(db_session, _USER_B, "B Prompt")

    records, total = await get_inputs(db_session, _USER_A, page=1, page_size=20)
    assert total == 1
    assert records[0].user_id == _USER_A


@pytest.mark.asyncio
async def test_get_inputs_pagination(
    db_session: AsyncSession,
) -> None:
    for i in range(5):
        await save_input(db_session, _USER_A, f"Prompt {i}")

    records, total = await get_inputs(db_session, _USER_A, page=2, page_size=2)
    assert total == 5
    assert len(records) == 2


@pytest.mark.asyncio
async def test_get_inputs_empty_returns_zero(
    db_session: AsyncSession,
) -> None:
    records, total = await get_inputs(db_session, _USER_A, page=1, page_size=20)
    assert records == []
    assert total == 0


# ---------------------------------------------------------------------------
# get_input_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_input_by_id_returns_record(
    db_session: AsyncSession,
) -> None:
    saved = await save_input(db_session, _USER_A, "Mein Input")
    record = await get_input_by_id(db_session, _USER_A, saved.id)
    assert record.id == saved.id


@pytest.mark.asyncio
async def test_get_input_by_id_raises_not_found_for_missing_id(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFoundException):
        await get_input_by_id(db_session, _USER_A, 99999)


@pytest.mark.asyncio
async def test_get_input_by_id_raises_not_found_for_wrong_user(
    db_session: AsyncSession,
) -> None:
    saved = await save_input(db_session, _USER_B, "B's Input")
    with pytest.raises(NotFoundException):
        await get_input_by_id(db_session, _USER_A, saved.id)


# ---------------------------------------------------------------------------
# delete_input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_input_removes_record(
    db_session: AsyncSession,
) -> None:
    saved = await save_input(db_session, _USER_A, "Zu löschen")
    await delete_input(db_session, _USER_A, saved.id)

    result = await db_session.execute(select(UserInput).where(UserInput.id == saved.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_input_raises_not_found_for_missing_id(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFoundException):
        await delete_input(db_session, _USER_A, 99999)


@pytest.mark.asyncio
async def test_delete_input_raises_not_found_for_wrong_user(
    db_session: AsyncSession,
) -> None:
    saved = await save_input(db_session, _USER_B, "B's Input")
    with pytest.raises(NotFoundException):
        await delete_input(db_session, _USER_A, saved.id)


@pytest.mark.asyncio
async def test_delete_input_does_not_cascade_to_conversation(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    r1 = await save_input(db_session, _USER_A, "Erste", cid)
    r2 = await save_input(db_session, _USER_A, "Zweite", cid)

    await delete_input(db_session, _USER_A, r1.id)

    result = await db_session.execute(select(UserInput).where(UserInput.id == r2.id))
    assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# get_conversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_conversation_returns_messages_in_order(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    await save_input(db_session, _USER_A, "Erste", cid)
    await save_input(db_session, _USER_A, "Zweite", cid)

    messages = await get_conversation(db_session, _USER_A, cid)
    assert len(messages) == 2
    assert messages[0].prompt == "Erste"
    assert messages[1].prompt == "Zweite"


@pytest.mark.asyncio
async def test_get_conversation_returns_empty_for_unknown_id(
    db_session: AsyncSession,
) -> None:
    messages = await get_conversation(db_session, _USER_A, uuid.uuid4())
    assert messages == []


@pytest.mark.asyncio
async def test_get_conversation_does_not_return_other_users_messages(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    await save_input(db_session, _USER_B, "B's Nachricht", cid)

    messages = await get_conversation(db_session, _USER_A, cid)
    assert messages == []
