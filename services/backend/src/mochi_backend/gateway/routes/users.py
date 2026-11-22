"""The web app's people (D-56): create one, read one, their saved words and their sessions."""

import unicodedata

from fastapi import APIRouter
from pydantic import BaseModel, field_validator, model_validator

from mochi_backend.gateway.container import AppContainer
from mochi_backend.gateway.errors import NotFoundError
from mochi_backend.gateway.routes.dependencies import ContainerDep, UserIdPath
from mochi_backend.storage.session_record import SessionRecord
from mochi_contracts import Language, LearningEvent, User

router = APIRouter()
NAME_LIMIT = 40


class NewUserBody(BaseModel):
    """`{"display_name": "Luís Felipe", "comfortable_language": "pt-BR", "target_language": "en"}`.

    Validated here, so FastAPI answers a bad one with its normal 422.
    """

    display_name: str
    comfortable_language: Language = Language.PT_BR
    target_language: Language = Language.EN

    @field_validator("display_name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        name = value.strip()
        if not 1 <= len(name) <= NAME_LIMIT:
            raise ValueError(f"display_name has {len(name)} characters; expected 1 to {NAME_LIMIT}")
        if any(unicodedata.category(char).startswith("C") for char in name):
            raise ValueError("display_name has a control character; expected printable text")
        return name

    @model_validator(mode="after")
    def _two_languages(self) -> "NewUserBody":
        if self.comfortable_language == self.target_language:
            raise ValueError(
                f"comfortable_language and target_language are both "
                f"{self.target_language.value!r}; expected two different languages"
            )
        return self


def _known(container: AppContainer, user_id: str) -> User:
    user = container.users.find(user_id) or container.roster.user(user_id)
    if user is None:
        raise NotFoundError(f"unknown user {user_id!r}; create one with POST /api/users")
    return user


@router.post("/api/users", status_code=201)
async def create_user(body: NewUserBody, container: ContainerDep) -> User:
    """A new person, with an id made from the name: `"Luís Felipe"` -> `"luis-felipe-3f9c1a"`."""
    return container.users.create(
        body.display_name, body.comfortable_language, body.target_language
    )


@router.get("/api/users/{user_id}")
async def read_user(user_id: UserIdPath, container: ContainerDep) -> User:
    """The user; 404 for an unknown one and for the reserved `guest`."""
    return _known(container, user_id)


@router.get("/api/users/{user_id}/words")
async def user_words(user_id: UserIdPath, container: ContainerDep) -> list[LearningEvent]:
    """The user's saved words, newest first (the `learning_event.created` payloads)."""
    _known(container, user_id)
    return container.core.intelligence.words_for(user_id)


@router.get("/api/users/{user_id}/sessions")
async def user_sessions(user_id: UserIdPath, container: ContainerDep) -> list[SessionRecord]:
    """The user's finished sessions, newest first by `ended_at`, at most 50."""
    _known(container, user_id)
    return container.history.for_user(user_id)
