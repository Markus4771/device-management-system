"""Secure KeePass export for credentials belonging to one device."""
from __future__ import annotations

import io
import os
import re
import tempfile
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, SecretStr
from pykeepass import create_database

router = APIRouter()


class KeepassExportRequest(BaseModel):
    pc_name: str = Field(..., min_length=1, max_length=120)
    customer: Optional[str] = None
    location: Optional[str] = None
    serial_number: Optional[str] = None
    local_user: Optional[str] = None
    local_user_password: Optional[SecretStr] = None
    local_admin: Optional[str] = None
    local_admin_password: Optional[SecretStr] = None
    teamviewer_id: Optional[str] = None
    teamviewer_user: Optional[str] = None
    teamviewer_password: Optional[SecretStr] = None
    rustdesk_id: Optional[str] = None
    rustdesk_user: Optional[str] = None
    rustdesk_password: Optional[SecretStr] = None
    master_password: SecretStr = Field(
        ..., min_length=12, description="KeePass-Masterpasswort"
    )


def _safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return (value.strip("-") or "geraet")[:80]


def _secret(value: Optional[SecretStr]) -> str:
    return value.get_secret_value() if value else ""


@router.post("/credentials/keepass", response_class=Response)
async def export_keepass(data: KeepassExportRequest):
    """Erzeugt eine verschlüsselte KeePass-Datei für genau einen Rechner."""
    if not any(
        (
            data.local_user_password,
            data.local_admin_password,
            data.teamviewer_password,
            data.rustdesk_password,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens ein Zugangspasswort muss angegeben werden.",
        )

    file_buffer = io.BytesIO()
    temp_path = None
    try:
        temp_file = tempfile.NamedTemporaryFile(suffix=".kdbx", delete=False)
        temp_path = temp_file.name
        temp_file.close()

        keepass = create_database(temp_path, password=_secret(data.master_password))
        group = keepass.add_group(keepass.root_group, data.pc_name.strip())
        metadata = [
            f"Kunde: {data.customer or '-'}",
            f"Standort: {data.location or '-'}",
            f"Seriennummer: {data.serial_number or '-'}",
        ]
        entries = [
            ("Lokaler Benutzer", data.local_user, _secret(data.local_user_password)),
            (
                "Lokaler Administrator",
                data.local_admin,
                _secret(data.local_admin_password),
            ),
            (
                "TeamViewer",
                data.teamviewer_id,
                _secret(data.teamviewer_password),
            ),
            ("RustDesk", data.rustdesk_id, _secret(data.rustdesk_password)),
        ]
        for title, username, password in entries:
            if username or password:
                keepass.add_entry(
                    group,
                    title,
                    username=username or "",
                    password=password,
                    notes="\n".join(metadata),
                )
        keepass.save()
        with open(temp_path, "rb") as exported_file:
            file_buffer.write(exported_file.read())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"KeePass-Datei konnte nicht erzeugt werden: {exc}",
        ) from exc
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    filename = f"{_safe_filename(data.pc_name)}-zugangsdaten.kdbx"
    return Response(
        content=file_buffer.getvalue(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
