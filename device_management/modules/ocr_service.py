"""
Integrierter OCR-Service für das Device Management System

Verknüpft Dateiüberwachung, OCR-Verarbeitung und Formularvorlagen.
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import threading
import time

from .ocr_processor import OCRProcessor
from .file_watcher import MultiDirectoryWatcher, IntervalScanner
from .form_templates import TemplateManager

logger = logging.getLogger(__name__)


class OCRService:
    """Integrierter Service für OCR-Verarbeitung mit Hintergrundüberwachung"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialisiert den OCR-Service.
        
        Args:
            config: Komplette Konfiguration für OCR-Verarbeitung
        """
        self.config = config
        
        # OCR-Prozessor initialisieren
        self.ocr_processor = OCRProcessor(config)
        
        # Template-Manager initialisieren
        template_dir = config.get("template_dir")
        self.template_manager = TemplateManager(template_dir)
        
        # Standardvorlagen erstellen
        self.template_manager.create_standard_templates()
        
        # Dateiüberwachung initialisieren
        self.file_watcher = None
        self.interval_scanner = None
        
        # Verarbeitungsergebnisse speichern
        self.processing_results = {}
        self.running = False
        
        logger.info("OCR Service initialized")
    
    def start_watching(self):
        """Startet die automatische Dateiüberwachung."""
        if self.running:
            logger.warning("OCR Service is already running")
            return
        
        try:
            # Versuche watchdog-basierte Überwachung
            self._setup_watchdog_watcher()
            self.file_watcher.start_all()
            
            # Vorhandene Dateien sofort verarbeiten
            self._process_existing_files()
            
            self.running = True
            logger.info("Started OCR Service with watchdog watcher")
            
        except Exception as e:
            logger.warning(f"Watchdog failed, falling back to interval scanner: {e}")
            self._setup_interval_scanner()
            self.interval_scanner.start()
            
            self.running = True
            logger.info("Started OCR Service with interval scanner fallback")
    
    def _setup_watchdog_watcher(self):
        """Richtet den watchdog-basierten Watcher ein."""
        try:
            from watchdog.observers import Observer
            
            watcher_config = {
                "input_watch_path": self.config.get("input_watch_path"),
                "processing_path": self.config.get("processing_path")
            }
            
            self.file_watcher = MultiDirectoryWatcher(watcher_config)
            
            # Hauptüberwachung für Eingangsdateien
            self.file_watcher.add_watcher(
                name="input_watch",
                watch_path=self.config.get("input_watch_path"),
                callback_function=self._on_new_file_detected,
                file_extensions=self.ocr_processor.get_supported_file_types()
            )
            
        except ImportError:
            logger.error("Watchdog not available")
            raise
    
    def _setup_interval_scanner(self):
        """Richtet den Intervall-Scanner als Fallback ein."""
        self.interval_scanner = IntervalScanner(
            watch_path=self.config.get("input_watch_path"),
            callback_function=self._on_new_file_detected,
            file_extensions=self.ocr_processor.get_supported_file_types(),
            interval_seconds=self.config.get("scan_interval", 30)
        )
    
    def _on_new_file_detected(self, file_path: Path):
        """
        Callback für neu erkannte Dateien.
        
        Args:
            file_path: Pfad zur neuen Datei
        """
        logger.info(f"New file detected for processing: {file_path.name}")
        
        # In Hintergrundthread verarbeiten
        thread = threading.Thread(
            target=self.process_file,
            args=(file_path,),
            daemon=True
        )
        thread.start()
    
    def _process_existing_files(self):
        """Verarbeitet vorhandene Dateien im Verzeichnis."""
        logger.info("Processing existing files in input directory")
        
        watch_path = Path(self.config.get("input_watch_path"))
        if not watch_path.exists():
            logger.warning(f"Watch path does not exist: {watch_path}")
            return
        
        existing_files = []
        for ext in self.ocr_processor.get_supported_file_types():
            files = list(watch_path.glob(f"*{ext}"))
            files.extend(list(watch_path.glob(f"*{ext.upper()}")))
            existing_files.extend(files)
        
        logger.info(f"Found {len(existing_files)} existing files to process")
        
        for file_path in existing_files:
            if file_path.is_file():
                self._on_new_file_detected(file_path)
                time.sleep(0.5)  # Kleine Pause zwischen Dateien
    
    def process_file(self, file_path: Path, template_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Verarbeitet eine einzelne Datei komplett.
        
        Args:
            file_path: Pfad zur Datei
            template_id: Optional: Vorlagen-ID
            
        Returns:
            Verarbeitungsergebnisse
        """
        file_key = str(file_path.resolve())
        
        try:
            logger.info(f"Starting OCR processing for: {file_path.name}")
            
            # Wenn keine Template-ID gegeben, automatisch bestimmen
            if template_id is None:
                # OCR-Text vorab extrahieren für Template-Erkennung
                initial_result = self.ocr_processor.process_file(file_path)
                ocr_text = initial_result.get("ocr_text", "")
                
                # Beste passende Vorlage finden
                template = self.template_manager.find_template_by_keywords(ocr_text)
                template_id = template.template_id if template else "standard_customer_form"
            
            # Vollständige Verarbeitung durchführen
            result = self.ocr_processor.run_single_file(file_path, template_id)
            
            # Template anwenden falls verfügbar
            if template_id:
                template = self.template_manager.get_template(template_id)
                if template:
                    ocr_text = result.get("ocr_text", "")
                    if ocr_text:
                        extracted_data = template.extract_fields(ocr_text)
                        result["extracted_data"] = extracted_data
            
            # Ergebnisse speichern
            self.processing_results[file_key] = {
                "result": result,
                "processed_at": datetime.utcnow().isoformat(),
                "filename": file_path.name
            }
            
            logger.info(f"Successfully processed {file_path.name}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            
            error_result = {
                "filename": file_path.name,
                "status": "error",
                "error_message": str(e),
                "processed_at": datetime.utcnow().isoformat()
            }
            
            self.processing_results[file_key] = {
                "result": error_result,
                "processed_at": error_result["processed_at"],
                "filename": file_path.name
            }
            
            return error_result
    
    def get_processing_status(self, file_hash: Optional[str] = None) -> Dict[str, Any]:
        """
        Gibt den Verarbeitungsstatus zurück.
        
        Args:
            file_hash: Optional: Hash einer bestimmten Datei
            
        Returns:
            Statusinformationen
        """
        status = {
            "service_running": self.running,
            "total_files_processed": len(self.processing_results),
            "last_updated": datetime.utcnow().isoformat()
        }
        
        if file_hash:
            if file_hash in self.processing_results:
                status["file_status"] = self.processing_results[file_hash]
            else:
                status["file_status"] = {"error": "File not found"}
        
        return status
    
    def get_available_templates(self) -> List[Dict[str, Any]]:
        """Gibt verfügbare Vorlagen zurück."""
        templates = []
        
        for template in self.template_manager.get_all_templates():
            templates.append({
                "id": template.template_id,
                "name": template.name,
                "description": template.config.get("description", ""),
                "field_count": len(template.field_mappings)
            })
        
        return templates
    
    def create_device_from_ocr_result(self, ocr_result_id: str, 
                                    user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Erstellt ein Gerät aus OCR-Ergebnissen mit zusätzlichen Benutzerdaten.
        
        Args:
            ocr_result_id: ID des OCR-Ergebnisses
            user_data: Zusätzliche/überschriebene Daten vom Benutzer
            
        Returns:
            Kombiniertes Device-Dictionary für GLPI
        """
        if ocr_result_id not in self.processing_results:
            return {"error": "OCR result not found"}
        
        result_data = self.processing_results[ocr_result_id]["result"]
        extracted_data = result_data.get("extracted_data", {})
        
        # Basis-Gerätedaten aus extrahierten Daten
        device_data = {
            "source": "ocr",
            "ocr_confidence": result_data.get("ocr_confidence", 0),
            "ocr_processed_at": result_data.get("processing_completed"),
            "original_filename": result_data.get("filename")
        }
        
        # Extraktionsergebnisse mit Feld-Mappings integrieren
        for key, value in extracted_data.items():
            if key.startswith("keyword_") or key.startswith("regex_"):
                field_name = key.replace("keyword_", "").replace("regex_", "")
                device_data[field_name] = value
        
        # Benutzerdaten (Korrekturen/Ergänzungen) haben Vorrang
        device_data.update(user_data)
        
        # Validierung und Normalisierung
        device_data = self._normalize_device_data(device_data)
        
        return device_data
    
    def _normalize_device_data(self, device_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalisiert Gerätedaten."""
        normalized = device_data.copy()
        
        # MAC-Adresse normalisieren
        if "mac_address" in normalized:
            mac = normalized["mac_address"]
            # Entferne alle nicht-hexadezimalen Zeichen
            mac_clean = ''.join(c for c in str(mac) if c.isalnum()).upper()
            if len(mac_clean) == 12:
                normalized["mac_address"] = ':'.join(mac_clean[i:i+2] for i in range(0, 12, 2))
        
        # PC-Name in Großbuchstaben
        if "pc_name" in normalized:
            normalized["pc_name"] = str(normalized["pc_name"]).strip().upper()
        
        # Serial Number in Großbuchstaben
        if "serial_number" in normalized:
            normalized["serial_number"] = str(normalized["serial_number"]).strip().upper()
        
        return normalized
    
    def stop_watching(self):
        """Stoppt die Dateiüberwachung."""
        if not self.running:
            logger.warning("OCR Service is not running")
            return
        
        if self.file_watcher:
            self.file_watcher.stop_all()
        
        if self.interval_scanner:
            self.interval_scanner.stop()
        
        self.running = False
        logger.info("Stopped OCR Service")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Gibt Statistiken zur OCR-Verarbeitung zurück."""
        total_success = 0
        total_error = 0
        
        for file_key, data in self.processing_results.items():
            result = data.get("result", {})
            if result.get("status") == "completed":
                total_success += 1
            elif result.get("status") == "error":
                total_error += 1
        
        return {
            "total_files_processed": len(self.processing_results),
            "successful": total_success,
            "errors": total_error,
            "success_rate": (total_success / len(self.processing_results) * 100) if self.processing_results else 0,
            "available_templates": len(self.get_available_templates()),
            "service_running": self.running
        }