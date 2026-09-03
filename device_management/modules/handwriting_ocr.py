"""Layout- und Handschrift-OCR für das Arbeitsplatzrechner-Formular.

Die Vorlage arbeitet mit normierten Bildkoordinaten. TrOCR wird optional
verwendet; ohne das Modell fällt die Verarbeitung auf Tesseract zurück.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class HandwritingFormOCR:
    """Extrahiert Felder aus der festen Arbeitsplatzrechner-Vorlage."""

    # x1, y1, x2, y2 als Anteil der Bildbreite/-höhe.
    # Die Bereiche enthalten die handschriftlichen Werte, nicht die Labels.
    REGIONS = {
        "customer": (0.05, 0.055, 0.33, 0.125),
        "pc_name": (0.34, 0.055, 0.66, 0.125),
        "location": (0.67, 0.055, 0.96, 0.125),
        "manufacturer": (0.05, 0.135, 0.33, 0.205),
        "model": (0.34, 0.135, 0.66, 0.205),
        "serial_number": (0.67, 0.135, 0.96, 0.205),
        "operating_system": (0.05, 0.355, 0.33, 0.445),
        "local_admin": (0.05, 0.315, 0.33, 0.415),
        "local_user": (0.35, 0.315, 0.66, 0.415),
        "notes": (0.05, 0.70, 0.96, 0.94),
    }

    def __init__(self, use_trocr: bool = False):
        self.use_trocr = use_trocr
        self._trocr = None
        self._trocr_processor = None
        self.model_available = False
        if use_trocr:
            self._load_trocr()

    def _load_trocr(self) -> None:
        """Lädt TrOCR erst bei aktivierter Option und nur bei vorhandenen Paketen."""
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            self._trocr_processor = TrOCRProcessor.from_pretrained(
                "microsoft/trocr-base-handwritten"
            )
            self._trocr = VisionEncoderDecoderModel.from_pretrained(
                "microsoft/trocr-base-handwritten"
            )
            self.model_available = True
        except Exception as exc:
            logger.warning("TrOCR nicht verfügbar: %s", exc)
            self._trocr = None
            self._trocr_processor = None
            self.model_available = False

    @staticmethod
    def _prepare(image):
        from PIL import ImageOps
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)
        return image.resize((image.width * 2, image.height * 2))

    @staticmethod
    def _clean(text: str) -> str:
        value = " ".join((text or "").replace("\n", " ").split())
        value = value.strip(" _-|:")
        return value if len(value) >= 2 else ""

    def _read_tesseract(self, image) -> Tuple[str, float]:
        import pytesseract
        data = pytesseract.image_to_data(
            image, lang="deu+eng", config="--psm 7",
            output_type=pytesseract.Output.DICT
        )
        words = []
        confidence = []
        for text, raw_conf in zip(data.get("text", []), data.get("conf", [])):
            try:
                conf = float(raw_conf)
            except (TypeError, ValueError):
                continue
            if conf > 0 and text.strip():
                words.append(text.strip())
                confidence.append(conf)
        return self._clean(" ".join(words)), (sum(confidence) / len(confidence) if confidence else 0.0)

    def _read_trocr(self, image) -> Tuple[str, float]:
        import torch
        pixel_values = self._trocr_processor(images=image, return_tensors="pt").pixel_values
        with torch.no_grad():
            generated_ids = self._trocr.generate(pixel_values)
        text = self._trocr_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return self._clean(text), 70.0 if text.strip() else 0.0

    def extract(self, image) -> Dict[str, Any]:
        values: Dict[str, str] = {}
        confidences = []
        for field, (x1, y1, x2, y2) in self.REGIONS.items():
            crop = image.crop((
                int(image.width * x1), int(image.height * y1),
                int(image.width * x2), int(image.height * y2)
            ))
            crop = self._prepare(crop)
            if self.model_available:
                text, confidence = self._read_trocr(crop)
            else:
                text, confidence = self._read_tesseract(crop)
            if text:
                values[field] = text
                confidences.append(confidence)
        values["_layout_template"] = "arbeitsplatzrechner-v1"
        values["_handwriting_model"] = "trocr" if self.model_available else "tesseract-preprocessing"
        values["_confidence"] = round(sum(confidences) / len(confidences), 1) if confidences else 0.0
        return values

    def status(self) -> Dict[str, Any]:
        return {
            "requested": self.use_trocr,
            "available": self.model_available,
            "model": "microsoft/trocr-base-handwritten" if self.model_available else "tesseract-fallback",
        }
