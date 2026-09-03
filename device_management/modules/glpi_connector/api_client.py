"""
GLPI API Client für REST API Kommunikation
"""

import httpx
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from ...config import settings

logger = logging.getLogger(__name__)


class GLPIAPIClient:
    """GLPI REST API Client"""
    
    def __init__(self):
        self.base_url = settings.glpi_base_url.rstrip("/")
        self.app_token = settings.glpi_app_token
        self.user_token = settings.glpi_user_token
        
        # Session Token muss vor dem Aufbau der Header initialisiert werden.
        self.session_token: Optional[str] = None

        # HTTP Client mit Session-Token
        self.client = httpx.Client(
            base_url=f"{self.base_url}/api.php/v1",
            timeout=30.0,
            headers=self._get_headers()
        )
    
    def _get_headers(self) -> Dict[str, str]:
        """Erstellt HTTP Header für GLPI API"""
        headers = {
            "Content-Type": "application/json",
            "App-Token": self.app_token,
        }

        # GLPI V1 authentifiziert die InitSession-Anfrage mit dem User Token.
        if self.user_token and not self.session_token:
            headers["Authorization"] = f"user_token {self.user_token}"

        if self.session_token:
            headers["Session-Token"] = self.session_token
        
        return headers
    
    def init_session(self) -> bool:
        """Initialisiert eine GLPI API Session"""
        try:
            response = self.client.get(
                "/initSession",
                headers={
                    "App-Token": self.app_token,
                    "Authorization": f"user_token {self.user_token}",
                    "Content-Type": "application/json",
                },
            )
            
            if response.status_code == 200:
                data = response.json()
                self.session_token = data.get("session_token")
                logger.info("GLPI Session erfolgreich initialisiert")
                return True
            else:
                logger.error(f"GLPI Session Initialisierung fehlgeschlagen: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Fehler bei GLPI Session Initialisierung: {e}")
            return False
    
    def kill_session(self) -> bool:
        """Beendet die GLPI API Session"""
        if not self.session_token:
            return True
            
        try:
            response = self.client.get(
                "/killSession",
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                self.session_token = None
                logger.info("GLPI Session beendet")
                return True
            else:
                logger.warning(f"GLPI Session Beendung fehlgeschlagen: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Fehler beim Beenden der GLPI Session: {e}")
            return False
    
    def get_entities(self, recursive: bool = True) -> List[Dict]:
        """Ruft alle GLPI Entities (Kunden) ab"""
        try:
            params = {"recursive": str(recursive).lower()}
            response = self.client.get(
                "/Entity",
                headers=self._get_headers(),
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Fehler beim Abrufen der Entities: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Exception beim Abrufen der Entities: {e}")
            return []
    
    def get_locations(self, entity_id: Optional[int] = None) -> List[Dict]:
        """Ruft GLPI Locations (Standorte) ab"""
        try:
            params = {}
            if entity_id:
                params["entity"] = entity_id
            
            response = self.client.get(
                "/Location",
                headers=self._get_headers(),
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Fehler beim Abrufen der Locations: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Exception beim Abrufen der Locations: {e}")
            return []
    
    def get_users(self, entity_id: Optional[int] = None) -> List[Dict]:
        """Ruft GLPI Users (Benutzer) ab"""
        try:
            params = {}
            if entity_id:
                params["entity"] = entity_id
            
            response = self.client.get(
                "/User",
                headers=self._get_headers(),
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Fehler beim Abrufen der Users: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Exception beim Abrufen der Users: {e}")
            return []
    
    def get_technicians(self, entity_id: Optional[int] = None) -> List[Dict]:
        """Ruft GLPI Technicians (Techniker) ab"""
        try:
            params = {"is_tech": "true"}
            if entity_id:
                params["entity"] = entity_id
            
            response = self.client.get(
                "/User",
                headers=self._get_headers(),
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Fehler beim Abrufen der Technicians: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Exception beim Abrufen der Technicians: {e}")
            return []
    
    def get_computer_types(self) -> List[Dict]:
        """Ruft Computer-Typen aus GLPI ab."""
        try:
            response = self.client.get("/ComputerType", headers=self._get_headers())
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, list) else []
            logger.error("Fehler beim Abrufen der Computer-Typen: %s", response.status_code)
        except Exception as exc:
            logger.error("Exception beim Abrufen der Computer-Typen: %s", exc)
        return []

    def get_manufacturers(self) -> List[Dict]:
        """Ruft Hersteller aus GLPI ab."""
        try:
            response = self.client.get("/Manufacturer", headers=self._get_headers())
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, list) else []
            logger.error("Fehler beim Abrufen der Hersteller: %s", response.status_code)
        except Exception as exc:
            logger.error("Exception beim Abrufen der Hersteller: %s", exc)
        return []

    def find_or_create_reference(self, itemtype: str, name: str) -> Optional[int]:
        """Findet ein GLPI-Referenzobjekt oder legt es bei Bedarf an."""
        try:
            response = self.client.get(f"/{itemtype}", headers=self._get_headers())
            if response.status_code == 200:
                items = response.json()
                if isinstance(items, list):
                    for item in items:
                        if str(item.get("name", "")).strip().lower() == name.strip().lower():
                            return item.get("id")
            response = self.client.post(f"/{itemtype}", headers=self._get_headers(), json={"input": {"name": name}})
            if response.status_code in (200, 201):
                data = response.json()
                if isinstance(data, dict):
                    return data.get("id")
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    return data[0].get("id")
        except Exception as e:
            logger.warning("GLPI reference %s could not be resolved: %s", itemtype, e)
        return None

    def create_computer(self, computer_data: Dict) -> Optional[int]:
        """Erstellt einen neuen Computer in GLPI"""
        try:
            response = self.client.post(
                "/Computer",
                headers=self._get_headers(),
                json={"input": computer_data}
            )

            if response.status_code in (200, 201):
                data = response.json()
                if isinstance(data, dict):
                    return data.get("id")
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    return data[0].get("id")
            else:
                logger.error(f"Fehler beim Erstellen des Computers: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Exception beim Erstellen des Computers: {e}")
            return None
    
    def update_computer(self, computer_id: int, computer_data: Dict) -> bool:
        """Aktualisiert einen vorhandenen Computer in GLPI"""
        try:
            response = self.client.put(
                f"/Computer/{computer_id}",
                headers=self._get_headers(),
                json={"input": computer_data}
            )

            return response.status_code in (200, 204)
                
        except Exception as e:
            logger.error(f"Exception beim Aktualisieren des Computers: {e}")
            return False
    
    def get_computer(self, computer_id: int) -> Optional[Dict]:
        """Ruft einen Computer aus GLPI ab"""
        try:
            response = self.client.get(
                f"/Computer/{computer_id}",
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Fehler beim Abrufen des Computers: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Exception beim Abrufen des Computers: {e}")
            return None
    
    def search_computers(self, search_criteria: Dict) -> List[Dict]:
        """Sucht Computer in GLPI basierend auf Suchkriterien"""
        try:
            # GLPI Suchparameter konvertieren
            params = {"criteria": []}
            
            for key, value in search_criteria.items():
                if isinstance(value, dict):
                    # Komplexe Suchkriterien
                    criterion = {
                        "field": key,
                        "searchtype": value.get("searchtype", "contains"),
                        "value": value.get("value", "")
                    }
                else:
                    # Einfache Suchkriterien
                    criterion = {
                        "field": key,
                        "searchtype": "contains",
                        "value": value
                    }
                
                params["criteria"].append(criterion)
            
            response = self.client.get(
                "/search/Computer",
                headers=self._get_headers(),
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            else:
                logger.error(f"Fehler bei der Computersuche: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Exception bei der Computersuche: {e}")
            return []
    
    def get_network_equipment(self, entity_id: Optional[int] = None) -> List[Dict]:
        """Ruft Netzwerkgeräte aus GLPI ab"""
        try:
            params = {}
            if entity_id:
                params["entity"] = entity_id
            
            response = self.client.get(
                "/NetworkEquipment",
                headers=self._get_headers(),
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Fehler beim Abrufen der Netzwerkgeräte: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Exception beim Abrufen der Netzwerkgeräte: {e}")
            return []
    
    def create_ticket(self, ticket_data: Dict) -> Optional[int]:
        """Erstellt ein neues Ticket in GLPI"""
        try:
            response = self.client.post(
                "/Ticket",
                headers=self._get_headers(),
                json=ticket_data
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                return data.get("id")
            else:
                logger.error(f"Fehler beim Erstellen des Tickets: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Exception beim Erstellen des Tickets: {e}")
            return None
    
    def __enter__(self):
        """Context Manager Entry"""
        self.init_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager Exit"""
        self.kill_session()
        self.client.close()