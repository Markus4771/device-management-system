"""
OCR-Verarbeitungs-Router für die Geräteerfassung

Bietet Endpoints für OCR-Verarbeitung, Formularvorlagen und Dateiüberwachung.
"""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse

from ..dependencies import get_current_active_user, get_current_superuser
from ...modules.ocr_service import OCRService
from ...config import settings
from ..schemas import OCRProcessResult, OCRTemplateInfo, OCRProcessingStatus

logger = logging.getLogger(__name__)

router = APIRouter()

# OCR Service als Singleton (in echtem Betrieb würde dies über Dependency Injection kommen)
_ocr_service = None


def get_ocr_service() -> OCRService:
    """Factory-Funktion für OCR-Service (Singleton Pattern)."""
    global _ocr_service
    
    if _ocr_service is None:
        ocr_config = {
            "input_watch_path": settings.ocr_input_watch_path,
            "processing_path": settings.ocr_processing_path,
            "done_path": settings.ocr_done_path,
            "error_path": settings.ocr_error_path,
            "archive_path": settings.ocr_archive_path,
            "ocr_language": settings.ocr_language,
            "preferred_engine": settings.ocr_preferred_engine,
            "template_dir": settings.ocr_template_dir,
            "scan_interval": 30
        }
        
        _ocr_service = OCRService(ocr_config)
        logger.info("OCR Service initialized")
    
    return _ocr_service


class OCRManager:
    """Klassenbasierte Verwaltung für OCR-Funktionalitäten"""
    
    def __init__(self):
        self.service = get_ocr_service()
    
    def start_watching(self) -> Dict[str, Any]:
        """Startet die Dateiüberwachung."""
        if self.service.running:
            return {"status": "already_running", "message": "OCR Service is already running"}
        
        try:
            self.service.start_watching()
            return {
                "status": "started",
                "message": "OCR Service started successfully",
                "watching_path": str(settings.ocr_input_watch_path)
            }
        except Exception as e:
            logger.error(f"Failed to start OCR watching: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start OCR watching: {str(e)}"
            )
    
    def stop_watching(self) -> Dict[str, Any]:
        """Stoppt die Dateiüberwachung."""
        if not self.service.running:
            return {"status": "not_running", "message": "OCR Service is not running"}
        
        self.service.stop_watching()
        return {
            "status": "stopped",
            "message": "OCR Service stopped successfully"
        }
    
    def upload_and_process(self, file: UploadFile, template_id: Optional[str] = None, handwriting_mode: bool = False) -> Dict[str, Any]:
        """
        Lädt eine Datei hoch und verarbeitet sie sofort.
        
        Args:
            file: Hochgeladene Datei
            template_id: Optional: Vorlagen-ID
            
        Returns:
            Verarbeitungsergebnisse
        """
        try:
            # Originaldatei für die Kontrollansicht im Bearbeitungsordner ablegen.
            import uuid
            
            file_ext = Path(file.filename).suffix.lower() if file.filename else ".tmp"
            review_name = f"review-{uuid.uuid4().hex}{file_ext}"
            review_dir = Path(settings.ocr_processing_path)
            review_dir.mkdir(parents=True, exist_ok=True)
            source_path = review_dir / review_name
            
            content = file.file.read()
            source_path.write_bytes(content)
            logger.info(f"Uploaded OCR source file {file.filename} to {source_path}")
            
            # Upload direkt verarbeiten. Ein Upload liegt bereits im
            # Bearbeitungsordner und darf nicht nochmals dorthin kopiert werden.
            effective_template_id = template_id or "standard_customer_form"
            result = self.service.ocr_processor.process_file(
                source_path,
                effective_template_id,
                handwriting_mode=handwriting_mode,
                use_trocr=use_trocr
            )
            template = self.service.template_manager.get_template(effective_template_id)
            if template and result.get("ocr_text"):
                result["extracted_data"] = template.extract_fields(result["ocr_text"])
            layout_fields = {
                key: value for key, value in result.get("layout_fields", {}).items()
                if not key.startswith("_") and value
            }
            if layout_fields:
                result.setdefault("extracted_data", {}).update(layout_fields)
            result["template_id"] = effective_template_id
            result["source_file_name"] = review_name
            result["source_file_type"] = file.content_type or "application/octet-stream"
            return result
            
        except Exception as e:
            logger.error(f"Error processing uploaded file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing file: {str(e)}"
            )
    
    def get_processing_results(self, file_hash: Optional[str] = None) -> Dict[str, Any]:
        """Gibt Verarbeitungsergebnisse zurück."""
        return self.service.get_processing_status(file_hash)
    
    def get_templates(self) -> List[Dict[str, Any]]:
        """Gibt verfügbare Vorlagen zurück."""
        return self.service.get_available_templates()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Gibt OCR-Verarbeitungsstatistiken zurück."""
        return self.service.get_statistics()


ocr_manager = OCRManager()


@router.get("/ocr/source/{file_name}", tags=["OCR Processing"])
async def get_ocr_source_file(file_name: str):
    """Liefert die Originaldatei für die interne OCR-Kontrollansicht."""
    safe_name = Path(file_name).name
    if safe_name != file_name or not safe_name.startswith("review-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger OCR-Dateiname")
    source_path = Path(settings.ocr_processing_path) / safe_name
    if not source_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Originaldatei nicht gefunden")
    return FileResponse(source_path)


@router.get("/ocr/status", response_model=Dict[str, Any], tags=["OCR Processing"])
async def get_ocr_status():
    """
    Gibt den Status des OCR-Services zurück.
    """
    try:
        return {
            "service_running": ocr_manager.service.running,
            "statistics": ocr_manager.get_statistics(),
            "available_templates": len(ocr_manager.get_templates()),
            "watch_path": settings.ocr_input_watch_path
        }
    except Exception as e:
        logger.error(f"Error getting OCR status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting OCR status: {str(e)}"
        )


@router.post("/ocr/start", tags=["OCR Processing"])
async def start_ocr_service(
    current_user = Depends(get_current_superuser)
):
    """
    Startet den OCR-Service (nur für Superuser).
    """
    try:
        result = ocr_manager.start_watching()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error starting OCR service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting OCR service: {str(e)}"
        )


@router.post("/ocr/stop", tags=["OCR Processing"])
async def stop_ocr_service(
    current_user = Depends(get_current_superuser)
):
    """
    Stoppt den OCR-Service (nur für Superuser).
    """
    try:
        result = ocr_manager.stop_watching()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error stopping OCR service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error stopping OCR service: {str(e)}"
        )


@router.post("/ocr/process-upload", response_model=OCRProcessResult, tags=["OCR Processing"])
async def process_uploaded_file(
    file: UploadFile = File(...),
    template_id: Optional[str] = Form(None),
    handwriting_mode: bool = Form(False),
    use_trocr: bool = Form(False)
):
    """
    Lädt eine Datei hoch und verarbeitet sie mit OCR.
    
    Unterstützt PDF, JPG, PNG, TIFF, BMP Dateien.
    """
    # Dateityp validieren
    allowed_extensions = [".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"]
    file_ext = Path(file.filename).suffix.lower() if file.filename else ""
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file_ext}' not supported. Allowed: {', '.join(allowed_extensions)}"
        )
    
    try:
        result = ocr_manager.upload_and_process(file, template_id, handwriting_mode)
        
        # Schema-Konvertierung für Response
        return OCRProcessResult(
            filename=result.get("filename", file.filename),
            status=result.get("status", "unknown"),
            ocr_confidence=result.get("ocr_confidence", 0.0),
            processing_time=result.get("processing_completed"),
            extracted_data=result.get("extracted_data", {}),
            raw_text_preview=result.get("ocr_text", "")[:500] if result.get("ocr_text") else "",
            template_applied=result.get("template_id"),
            source_file_url=f"/api/v1/ocr/source/{result.get('source_file_name')}" if result.get("source_file_name") else None,
            source_file_type=result.get("source_file_type"),
            error_message=result.get("error_message"),
            layout_fields=result.get("layout_fields", {}),
            handwriting_model=result.get("handwriting_model", {})
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing uploaded file {file.filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}"
        )


@router.get("/ocr/templates", response_model=List[OCRTemplateInfo], tags=["OCR Processing"])
async def get_available_templates():
    """
    Gibt alle verfügbaren Formularvorlagen zurück.
    """
    try:
        templates = ocr_manager.get_templates()
        
        # Konvertieren in Schema-formatierte Liste
        template_list = []
        for template in templates:
            template_list.append(
                OCRTemplateInfo(
                    id=template["id"],
                    name=template["name"],
                    description=template.get("description", ""),
                    field_count=template.get("field_count", 0)
                )
            )
        
        return template_list
        
    except Exception as e:
        logger.error(f"Error getting templates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting templates: {str(e)}"
        )


@router.get("/ocr/results/{file_hash}", response_model=Dict[str, Any], tags=["OCR Processing"])
async def get_ocr_result(file_hash: str):
    """
    Gibt OCR-Verarbeitungsergebnisse für eine spezifische Datei zurück.
    """
    try:
        results = ocr_manager.get_processing_results(file_hash)
        return results
    except Exception as e:
        logger.error(f"Error getting OCR result for {file_hash}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting OCR result: {str(e)}"
        )


@router.get("/ocr/results", response_model=Dict[str, Any], tags=["OCR Processing"])
async def get_all_ocr_results(
    limit: int = 50,
    offset: int = 0
):
    """
    Gibt eine Seite von OCR-Verarbeitungsergebnissen zurück.
    """
    try:
        # Vereinfachte Implementierung - im echten Betrieb würde dies paginiert sein
        results = ocr_manager.service.processing_results
        
        # Ergebnisse sortieren (neueste zuerst)
        sorted_results = dict(sorted(
            results.items(),
            key=lambda x: x[1].get("processed_at", ""),
            reverse=True
        ))
        
        # Paginierung anwenden
        keys = list(sorted_results.keys())
        paginated_keys = keys[offset:offset + limit]
        
        paginated_results = {
            key: results[key]
            for key in paginated_keys
        }
        
        return {
            "results": paginated_results,
            "total": len(results),
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < len(results)
        }
        
    except Exception as e:
        logger.error(f"Error getting OCR results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting OCR results: {str(e)}"
        )


@router.post("/ocr/create-device", response_model=Dict[str, Any], tags=["OCR Processing"])
async def create_device_from_ocr(
    ocr_result_id: str,
    user_data: Dict[str, Any],
    current_user = Depends(get_current_active_user)
):
    """
    Erstellt ein GLPI-Gerät aus OCR-Ergebnissen mit Benutzerkorrekturen.
    
    Der Request-Body sollte Felder enthalten, die die OCR-Ergebnisse korrigieren oder ergänzen.
    """
    try:
        # Basis-Gerätedaten aus OCR extrahieren
        device_data = ocr_manager.service.create_device_from_ocr_result(ocr_result_id, user_data)
        
        if "error" in device_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=device_data["error"]
            )
        
        # Hier würde die GLPI-Integration kommen
        # Für jetzt geben wir nur das kombinierte Gerätedaten-Dictionary zurück
        
        return {
            "message": "Device data extracted from OCR",
            "device_data": device_data,
            "ready_for_glpi": True,
            "ocr_result_id": ocr_result_id,
            "created_by": current_user.username
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating device from OCR result {ocr_result_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating device from OCR: {str(e)}"
        )


@router.post("/ocr/process-samba-files", tags=["OCR Processing"])
async def process_existing_samba_files(
    background_tasks: BackgroundTasks
):
    """
    Verarbeitet vorhandene Dateien im Samba-Freigabe-Verzeichnis (Hintergrundtask).
    """
    try:
        async def process_files_background():
            """Hintergrundtask zum Verarbeiten vorhandener Dateien."""
            ocr_manager.service._process_existing_files()
        
        # Hintergrundtask starten
        background_tasks.add_task(process_files_background)
        
        return {
            "message": "Background processing started",
            "task": "process_existing_files",
            "started_at": "immediately"
        }
        
    except Exception as e:
        logger.error(f"Error starting background processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting background processing: {str(e)}"
        )