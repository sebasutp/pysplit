"""Shared FastAPI dependencies.

Auth dependencies are added in Stage 4. Keep this module free of SQL queries;
routers depend on these aliases rather than importing the engine.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.database import get_session

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
