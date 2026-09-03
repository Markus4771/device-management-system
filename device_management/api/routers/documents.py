"""PDF documentation generation for completed device records."""
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fpdf import FPDF
from ...config import settings

router = APIRouter()


class DeviceDocumentationRequest(BaseModel):
    pc_name: str
    customer: Optional[str] = None
    location: Optional[str] = None
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    operating_system: Optional[str] = None
    computer_type: Optional[str] = None
    user: Optional[str] = None
    technician: Optional[str] = None
    mac_address: Optional[str] = None
    teamviewer_id: Optional[str] = None
    rustdesk_id: Optional[str] = None
    notes: Optional[str] = None


def _text(value: Optional[str]) -> str:
    return value or "-"


@router.post("/documents/generate")
async def generate_device_document(data: DeviceDocumentationRequest):
    """Erzeugt die fertige PDF-Dokumentation und legt sie im Done-Ordner ab."""
    target_dir = Path(settings.ocr_done_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in data.pc_name)
    target = target_dir / f"{filename}-geraetedokumentation.pdf"
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_title(f"Gerätedokumentation {_text(data.pc_name)}")
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Gerätedokumentation", ln=True)
        pdf.set_font("Helvetica", size=11)
        pdf.ln(4)
        rows = [
            ("PC-Bezeichnung", data.pc_name), ("Kunde", data.customer),
            ("Standort", data.location), ("Seriennummer", data.serial_number),
            ("Hersteller", data.manufacturer), ("Modell", data.model),
            ("Betriebssystem", data.operating_system), ("Typ", data.computer_type),
            ("Benutzer", data.user), ("Techniker", data.technician),
            ("MAC-Adresse", data.mac_address), ("TeamViewer-ID", data.teamviewer_id),
            ("RustDesk-ID", data.rustdesk_id), ("Bemerkungen", data.notes),
        ]
        for label, value in rows:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(48, 7, label + ":")
            pdf.set_font("Helvetica", size=10)
            pdf.multi_cell(0, 7, _text(value))
        pdf.set_font("Helvetica", "I", 9)
        pdf.ln(5)
        pdf.cell(0, 7, "Status: FERTIG", ln=True)
        pdf.output(str(target))
        return {"success": True, "status": "FERTIG", "filename": target.name, "path": str(target)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF konnte nicht erzeugt werden: {exc}") from exc
