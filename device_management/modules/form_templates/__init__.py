"""
Formularvorlagen-Management für OCR-Erkennung

Dieses Modul verwaltet Vorlagen für verschiedene Kundenformulare
und ermöglicht die Zuordnung von OCR-Ergebnissen zu Gerätefeldern.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class FormTemplate:
    """Repräsentiert eine einzelne Formularvorlage"""
    
    def __init__(self, template_id: str, name: str, config: Dict[str, Any]):
        """
        Initialisiert eine Formularvorlage.
        
        Args:
            template_id: Eindeutige ID der Vorlage
            name: Anzeigename der Vorlage
            config: Vorlagenkonfiguration
        """
        self.template_id = template_id
        self.name = name
        self.config = config
        
        # Felder aus Konfiguration extrahieren
        self.field_mappings = config.get("field_mappings", {})
        self.validation_rules = config.get("validation_rules", {})
        self.keywords = config.get("keywords", {})
        self.regex_patterns = config.get("regex_patterns", {})
        self.expected_sections = config.get("expected_sections", [])
        
        logger.debug(f"FormTemplate initialized: {self.name} (ID: {self.template_id})")
    
    def extract_fields(self, ocr_text: str) -> Dict[str, Any]:
        """
        Extrahiert Felder aus OCR-Text basierend auf der Vorlage.
        
        Args:
            ocr_text: Erkannter OCR-Text
            
        Returns:
            Dictionary mit extrahierten Feldwerten
        """
        extracted = {
            "template_id": self.template_id,
            "template_name": self.name,
            "extraction_timestamp": datetime.utcnow().isoformat(),
            "raw_text_preview": ocr_text[:500] + ("..." if len(ocr_text) > 500 else "")
        }
        
        # 1. Keyword-basierte Extraktion
        keyword_results = self._extract_by_keywords(ocr_text)
        extracted.update(keyword_results)
        
        # 2. Regex-basierte Extraktion
        regex_results = self._extract_by_regex(ocr_text)
        extracted.update(regex_results)
        
        # 3. Feldmapping anwenden
        mapped_results = self._apply_field_mappings(extracted)
        
        # 4. Validierung durchführen
        validation_results = self._validate_extracted_data(mapped_results)
        
        final_result = {
            **mapped_results,
            "validation_results": validation_results,
            "extraction_methods_used": ["keywords", "regex", "mapping"]
        }
        
        logger.info(f"Extracted {len(mapped_results)} fields from text using template {self.name}")
        return final_result
    
    def _extract_by_keywords(self, text: str) -> Dict[str, Any]:
        """Extrahiert Felder basierend auf Schlüsselwörtern."""
        results = {}
        text_lower = text.lower()
        
        for field_name, keywords in self.keywords.items():
            for keyword in keywords:
                keyword_lower = keyword.lower()
                
                # Suche nach Keyword im Text
                if keyword_lower in text_lower:
                    # Versuche Wert nach Keyword zu extrahieren
                    pattern = f"{re.escape(keyword)}(?:\\s*[:=]?\\s*)([^\\n]+)"
                    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                    
                    if match:
                        value = match.group(1).strip()
                        if value and value not in keywords:  # Vermeide Rückgabe des Keywords selbst
                            results[f"keyword_{field_name}"] = value
                            break
        
        return results
    
    def _extract_by_regex(self, text: str) -> Dict[str, Any]:
        """Extrahiert Felder basierend auf regulären Ausdrücken."""
        results = {}
        
        for field_name, patterns in self.regex_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    # Versuche die erste Capture-Gruppe oder den gesamten Match
                    if match.groups():
                        value = match.group(1).strip()
                    else:
                        value = match.group(0).strip()
                    
                    if value:
                        results[f"regex_{field_name}"] = value
                        break
        
        return results
    
    def _apply_field_mappings(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Wendet Feldmappings auf extrahierte Daten an."""
        mapped_data = {}
        
        for target_field, source_info in self.field_mappings.items():
            source_field = source_info.get("source")
            transform = source_info.get("transform", "identity")
            
            if source_field and source_field in extracted_data:
                value = extracted_data[source_field]
                
                # Transformation anwenden
                transformed_value = self._apply_transform(value, transform)
                
                if transformed_value is not None:
                    mapped_data[target_field] = transformed_value
        
        return mapped_data
    
    def _apply_transform(self, value: Any, transform: str) -> Any:
        """Wendet eine Transformation auf einen Wert an."""
        if transform == "identity":
            return value
        elif transform == "uppercase":
            return str(value).upper() if value else value
        elif transform == "lowercase":
            return str(value).lower() if value else value
        elif transform == "normalize_mac":
            return self._normalize_mac_address(value) if value else value
        elif transform == "extract_first_word":
            return str(value).split()[0] if value else value
        elif transform.startswith("regex_replace:"):
            # Format: regex_replace:pattern:replacement
            parts = transform.split(":", 2)
            if len(parts) == 3:
                pattern = parts[1]
                replacement = parts[2]
                return re.sub(pattern, replacement, str(value)) if value else value
        
        return value
    
    def _normalize_mac_address(self, mac: str) -> Optional[str]:
        """Normalisiert eine MAC-Adresse ins Format AA:BB:CC:DD:EE:FF."""
        if not mac:
            return None
        
        # Entferne alle nicht-hexadezimalen Zeichen
        mac_clean = re.sub(r'[^a-fA-F0-9]', '', mac)
        
        # Prüfe Länge (48 Bits = 12 hex Zeichen)
        if len(mac_clean) != 12:
            return None
        
        # Formatiere ins gewünschte Format
        normalized = ':'.join(mac_clean[i:i+2].upper() for i in range(0, 12, 2))
        return normalized
    
    def _validate_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validiert extrahierte Daten basierend auf Validierungsregeln."""
        validation_results = {}
        
        for field_name, rules in self.validation_rules.items():
            value = data.get(field_name)
            
            if value is None:
                validation_results[field_name] = {
                    "valid": False,
                    "message": f"Field '{field_name}' not found"
                }
                continue
            
            field_validations = []
            
            # Typ-Validierung
            if "type" in rules:
                expected_type = rules["type"]
                if expected_type == "string":
                    is_valid = isinstance(value, str)
                elif expected_type == "integer":
                    is_valid = isinstance(value, int) or (isinstance(value, str) and value.isdigit())
                elif expected_type == "mac_address":
                    is_valid = bool(self._validate_mac_format(value))
                else:
                    is_valid = True
                
                field_validations.append({
                    "rule": f"type_{expected_type}",
                    "valid": is_valid,
                    "message": f"Value '{value}' is not of type {expected_type}"
                })
            
            # Längenvalidierung
            if "min_length" in rules and isinstance(value, str):
                is_valid = len(value) >= rules["min_length"]
                field_validations.append({
                    "rule": "min_length",
                    "valid": is_valid,
                    "message": f"Value too short (min {rules['min_length']})"
                })
            
            if "max_length" in rules and isinstance(value, str):
                is_valid = len(value) <= rules["max_length"]
                field_validations.append({
                    "rule": "max_length",
                    "valid": is_valid,
                    "message": f"Value too long (max {rules['max_length']})"
                })
            
            # Regex-Validierung
            if "pattern" in rules and isinstance(value, str):
                pattern = rules["pattern"]
                is_valid = bool(re.match(pattern, value))
                field_validations.append({
                    "rule": "pattern_match",
                    "valid": is_valid,
                    "message": f"Value does not match pattern {pattern}"
                })
            
            # Kombiniere alle Validierungen für dieses Feld
            all_valid = all(v["valid"] for v in field_validations)
            validation_results[field_name] = {
                "valid": all_valid,
                "validations": field_validations
            }
        
        return validation_results
    
    def _validate_mac_format(self, mac: str) -> bool:
        """Validiert MAC-Adressen-Format."""
        normalized = self._normalize_mac_address(mac)
        return normalized is not None


class TemplateManager:
    """Verwaltet mehrere Formularvorlagen"""
    
    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialisiert den Template Manager.
        
        Args:
            template_dir: Verzeichnis für Vorlagendateien (optional)
        """
        self.templates: Dict[str, FormTemplate] = {}
        self.template_dir = Path(template_dir) if template_dir else None
        
        if self.template_dir:
            self.template_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"TemplateManager initialized with template dir: {self.template_dir}")
    
    def load_template(self, template_id: str, name: str, config: Dict[str, Any]) -> FormTemplate:
        """
        Lädt eine Vorlage in den Manager.
        
        Args:
            template_id: Eindeutige ID der Vorlage
            name: Anzeigename der Vorlage
            config: Vorlagenkonfiguration
            
        Returns:
            Geladene FormTemplate Instanz
        """
        template = FormTemplate(template_id, name, config)
        self.templates[template_id] = template
        
        logger.info(f"Loaded template '{name}' (ID: {template_id})")
        return template
    
    def load_template_from_file(self, file_path: Path) -> Optional[FormTemplate]:
        """
        Lädt eine Vorlage aus einer JSON-Datei.
        
        Args:
            file_path: Pfad zur Vorlagendatei
            
        Returns:
            Geladene FormTemplate oder None bei Fehler
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
            
            template_id = template_data.get("id")
            name = template_data.get("name")
            config = template_data.get("config", {})
            
            if not template_id or not name:
                logger.error(f"Invalid template file {file_path}: missing id or name")
                return None
            
            template = self.load_template(template_id, name, config)
            logger.info(f"Loaded template from file: {file_path.name}")
            return template
            
        except Exception as e:
            logger.error(f"Error loading template from {file_path}: {e}")
            return None
    
    def load_templates_from_dir(self, directory: Optional[Path] = None) -> List[FormTemplate]:
        """
        Lädt alle Vorlagen aus einem Verzeichnis.
        
        Args:
            directory: Verzeichnis mit Vorlagendateien (optional)
            
        Returns:
            Liste geladener Templates
        """
        if directory is None and self.template_dir is None:
            logger.error("No template directory specified")
            return []
        
        dir_path = directory or self.template_dir
        if not dir_path or not dir_path.exists():
            logger.warning(f"Template directory does not exist: {dir_path}")
            return []
        
        loaded_templates = []
        
        for file_path in dir_path.glob("*.json"):
            template = self.load_template_from_file(file_path)
            if template:
                loaded_templates.append(template)
        
        logger.info(f"Loaded {len(loaded_templates)} templates from {dir_path}")
        return loaded_templates
    
    def save_template_to_file(self, template: FormTemplate, 
                             file_path: Optional[Path] = None) -> bool:
        """
        Speichert eine Vorlage in eine Datei.
        
        Args:
            template: Zu speichernde Vorlage
            file_path: Ziel-Pfad (optional)
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            if file_path is None:
                if self.template_dir is None:
                    logger.error("No template directory specified for saving")
                    return False
                
                file_path = self.template_dir / f"{template.template_id}.json"
            
            template_data = {
                "id": template.template_id,
                "name": template.name,
                "config": template.config,
                "created_at": datetime.utcnow().isoformat(),
                "version": "1.0"
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(template_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved template '{template.name}' to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving template to file: {e}")
            return False
    
    def get_template(self, template_id: str) -> Optional[FormTemplate]:
        """Gibt eine Vorlage anhand der ID zurück."""
        return self.templates.get(template_id)
    
    def get_all_templates(self) -> List[FormTemplate]:
        """Gibt alle geladenen Vorlagen zurück."""
        return list(self.templates.values())
    
    def find_template_by_keywords(self, ocr_text: str) -> Optional[FormTemplate]:
        """
        Findet die passendste Vorlage für einen OCR-Text basierend auf Keywords.
        
        Args:
            ocr_text: Erkannter OCR-Text
            
        Returns:
            Passendste Vorlage oder None
        """
        best_template = None
        best_score = 0
        
        for template in self.templates.values():
            score = self._calculate_template_match_score(template, ocr_text)
            
            if score > best_score:
                best_score = score
                best_template = template
        
        if best_template and best_score > 0:
            logger.debug(f"Best template match: {best_template.name} (score: {best_score})")
        
        return best_template if best_score > 0 else None
    
    def _calculate_template_match_score(self, template: FormTemplate, text: str) -> float:
        """Berechnet den Match-Score zwischen Vorlage und Text."""
        text_lower = text.lower()
        score = 0.0
        
        # Keyword-Matches zählen
        for field_name, keywords in template.keywords.items():
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in text_lower:
                    score += 1.0
        
        # Section-Matches zählen
        for section in template.expected_sections:
            if section.lower() in text_lower:
                score += 2.0
        
        return score
    
    def create_standard_templates(self):
        """Erstellt Standardvorlagen für häufige Formulartypen."""
        
        # Standard-Kundenformularvorlage
        customer_form_template = {
            "id": "standard_customer_form",
            "name": "Standard Kundenformular",
            "config": {
                "description": "Standardformular für Geräteerfassung",
                "keywords": {
                    "pc_name": ["PC", "Computer", "Rechner", "Workstation", "Laptop", "Notebook"],
                    "user": ["Benutzer", "User", "Mitarbeiter", "Anwender", "Name"],
                    "serial": ["Seriennummer", "Serial", "SN", "S/N", "Serien-Nr"],
                    "mac": ["MAC", "MAC-Adresse", "Ethernet-Adresse", "MAC-Adr"],
                    "ip": ["IP", "IP-Adresse", "Internet-Adresse", "IP-Adr"],
                    "technician": ["Techniker", "Erfasst durch", "Bearbeiter"],
                    "manufacturer": ["Hersteller", "Manufacturer", "Marke"],
                    "model": ["Modell", "Type", "Baureihe"],
                    "os": ["Betriebssystem", "OS", "Windows", "Linux"]
                },
                "regex_patterns": {
                    "mac_address": [
                        r"MAC\s*(?:Adresse)?\s*[:=]?\s*([0-9A-Fa-f:]{17})",
                        r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}"
                    ],
                    "ip_address": [
                        r"IP\s*(?:Adresse)?\s*[:=]?\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                        r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
                    ]
                },
                "field_mappings": {
                    "pc_name": {"source": "keyword_pc_name", "transform": "uppercase"},
                    "user": {"source": "keyword_user", "transform": "identity"},
                    "serial_number": {"source": "keyword_serial", "transform": "uppercase"},
                    "mac_address": {"source": "regex_mac_address", "transform": "normalize_mac"},
                    "ip_address": {"source": "regex_ip_address", "transform": "identity"},
                    "technician": {"source": "keyword_technician", "transform": "identity"},
                    "manufacturer": {"source": "keyword_manufacturer", "transform": "identity"},
                    "model": {"source": "keyword_model", "transform": "identity"},
                    "operating_system": {"source": "keyword_os", "transform": "identity"}
                },
                "validation_rules": {
                    "mac_address": {"type": "mac_address", "pattern": "^([0-9A-F]{2}:){5}[0-9A-F]{2}$"},
                    "ip_address": {"type": "string", "pattern": "^\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}$"}
                },
                "expected_sections": [
                    "Gerätedaten",
                    "Benutzerinformationen",
                    "Netzwerkinformationen",
                    "Herstellerangaben"
                ]
            }
        }
        
        self.load_template(
            customer_form_template["id"],
            customer_form_template["name"],
            customer_form_template["config"]
        )
        
        logger.info("Created standard customer form template")