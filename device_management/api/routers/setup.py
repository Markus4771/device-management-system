"""Webbasierter Ersteinrichtungsassistent für die GLPI-Verbindung."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...config import settings
from ...modules.glpi_connector.api_client import GLPIAPIClient

router = APIRouter()


class GLPISetupData(BaseModel):
    base_url: str = Field(..., min_length=1)
    app_token: str = Field(..., min_length=1)
    user_token: str = Field(..., min_length=1)


def _configured() -> bool:
    return bool(
        settings.glpi_base_url
        and settings.glpi_app_token
        and settings.glpi_user_token
        and "your-glpi" not in settings.glpi_app_token
        and "your-glpi" not in settings.glpi_user_token
    )


def _test_connection(data: GLPISetupData) -> dict:
    old = (settings.glpi_base_url, settings.glpi_app_token, settings.glpi_user_token)
    settings.glpi_base_url = data.base_url.rstrip("/")
    settings.glpi_app_token = data.app_token
    settings.glpi_user_token = data.user_token
    try:
        with GLPIAPIClient() as client:
            if not client.session_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="GLPI-Verbindung fehlgeschlagen. URL und Token prüfen.",
                )
            entities = client.get_entities(recursive=False)
            return {
                "connected": True,
                "message": "GLPI-Verbindung erfolgreich.",
                "entities_count": len(entities),
            }
    finally:
        settings.glpi_base_url, settings.glpi_app_token, settings.glpi_user_token = old


def _write_env(data: GLPISetupData) -> None:
    env_path = Path(".env")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    values = {
        "GLPI_BASE_URL": data.base_url.rstrip("/"),
        "GLPI_APP_TOKEN": data.app_token,
        "GLPI_USER_TOKEN": data.user_token,
    }
    found = set()
    output = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in values:
            output.append(f"{key}={values[key]}")
            found.add(key)
        else:
            output.append(line)
    for key, value in values.items():
        if key not in found:
            output.append(f"{key}={value}")
    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    env_path.chmod(0o600)


@router.get("/status")
async def setup_status():
    return {"configured": _configured(), "setup_required": not _configured()}


@router.post("/glpi/test")
async def test_glpi_setup(data: GLPISetupData):
    return _test_connection(data)


@router.post("/glpi")
async def save_glpi_setup(data: GLPISetupData):
    if _configured():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GLPI ist bereits konfiguriert.",
        )
    result = _test_connection(data)
    _write_env(data)
    settings.glpi_base_url = data.base_url.rstrip("/")
    settings.glpi_app_token = data.app_token
    settings.glpi_user_token = data.user_token
    return {**result, "saved": True, "message": "GLPI-Konfiguration gespeichert."}
