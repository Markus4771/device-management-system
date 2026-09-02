"""
Dateiüberwachungsmodul für Samba-Freigaben

Überwacht Verzeichnisse auf neue Dateien und startet OCR-Verarbeitung.
"""

import os
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

logger = logging.getLogger(__name__)


class FileWatchHandler(FileSystemEventHandler):
    """Watchdog Event Handler für Dateiänderungen"""
    
    def __init__(self, callback_function, file_extensions: List[str]):
        self.callback = callback_function
        self.file_extensions = [ext.lower() for ext in file_extensions]
        logger.debug(f"FileWatchHandler initialized for extensions: {file_extensions}")
    
    def on_created(self, event):
        """Wird aufgerufen bei Dateierstellung"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        file_ext = file_path.suffix.lower()
        
        if file_ext in self.file_extensions:
            logger.info(f"New file detected: {file_path.name}")
            self.callback(file_path)


class DirectoryWatcher:
    """Überwacht ein Verzeichnis auf neue Dateien"""
    
    def __init__(self, watch_path: str, callback_function, 
                 file_extensions: Optional[List[str]] = None):
        """
        Initialisiert den Directory Watcher.
        
        Args:
            watch_path: Pfad zum zu überwachenden Verzeichnis
            callback_function: Funktion, die bei neuer Datei aufgerufen wird
            file_extensions: Liste unterstützter Dateiendungen (optional)
        """
        self.watch_path = Path(watch_path)
        self.callback = callback_function
        
        if file_extensions is None:
            self.file_extensions = [".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"]
        else:
            self.file_extensions = file_extensions
        
        self.observer = Observer()
        self.event_handler = FileWatchHandler(callback_function, self.file_extensions)
        self.watching = False
        
        # Verzeichnis erstellen falls nicht existent
        self.watch_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"DirectoryWatcher initialized for {self.watch_path}")
    
    def start(self):
        """Startet die Dateiüberwachung"""
        if self.watching:
            logger.warning("Watcher is already running")
            return
        
        try:
            self.observer.schedule(self.event_handler, str(self.watch_path), recursive=True)
            self.observer.start()
            self.watching = True
            logger.info(f"Started watching directory: {self.watch_path}")
            
        except Exception as e:
            logger.error(f"Failed to start watcher for {self.watch_path}: {e}")
            raise
    
    def stop(self):
        """Stoppt die Dateiüberwachung"""
        if not self.watching:
            logger.warning("Watcher is not running")
            return
        
        try:
            self.observer.stop()
            self.observer.join(timeout=10)
            self.watching = False
            logger.info(f"Stopped watching directory: {self.watch_path}")
            
        except Exception as e:
            logger.error(f"Error stopping watcher: {e}")
    
    def scan_existing_files(self) -> List[Path]:
        """
        Scannt vorhandene Dateien im Verzeichnis.
        
        Returns:
            Liste von Path-Objekten für vorhandene Dateien
        """
        existing_files = []
        
        for ext in self.file_extensions:
            files = list(self.watch_path.glob(f"*{ext}"))
            files.extend(list(self.watch_path.glob(f"*{ext.upper()}")))
            
            for file_path in files:
                if file_path.is_file():
                    existing_files.append(file_path)
        
        logger.info(f"Found {len(existing_files)} existing files in {self.watch_path}")
        return existing_files


class MultiDirectoryWatcher:
    """Überwacht mehrere Verzeichnisse gleichzeitig"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialisiert Multi-Directory Watcher.
        
        Args:
            config: Dictionary mit Watch-Pfaden und Callback-Funktionen
        """
        self.watchers: Dict[str, DirectoryWatcher] = {}
        self.config = config
        logger.info("MultiDirectoryWatcher initialized")
    
    def add_watcher(self, name: str, watch_path: str, callback_function,
                   file_extensions: Optional[List[str]] = None):
        """
        Fügt einen neuen Watcher hinzu.
        
        Args:
            name: Name des Watchers (für Referenzierung)
            watch_path: Pfad zum zu überwachenden Verzeichnis
            callback_function: Funktion, die bei neuer Datei aufgerufen wird
            file_extensions: Liste unterstützter Dateiendungen (optional)
        """
        if name in self.watchers:
            logger.warning(f"Watcher '{name}' already exists, replacing")
        
        watcher = DirectoryWatcher(watch_path, callback_function, file_extensions)
        self.watchers[name] = watcher
        logger.info(f"Added watcher '{name}' for path: {watch_path}")
    
    def start_all(self):
        """Startet alle Watcher"""
        logger.info("Starting all directory watchers")
        
        successful = 0
        failed = 0
        
        for name, watcher in self.watchers.items():
            try:
                watcher.start()
                successful += 1
                logger.debug(f"Started watcher '{name}'")
            except Exception as e:
                failed += 1
                logger.error(f"Failed to start watcher '{name}': {e}")
        
        logger.info(f"Started {successful} watchers, {failed} failed")
    
    def stop_all(self):
        """Stoppt alle Watcher"""
        logger.info("Stopping all directory watchers")
        
        for name, watcher in self.watchers.items():
            try:
                watcher.stop()
                logger.debug(f"Stopped watcher '{name}'")
            except Exception as e:
                logger.error(f"Error stopping watcher '{name}': {e}")
    
    def scan_all_existing(self) -> Dict[str, List[Path]]:
        """
        Scannt alle überwachten Verzeichnisse nach vorhandenen Dateien.
        
        Returns:
            Dictionary mit Watcher-Namen als Keys und Listen von Dateien als Values
        """
        results = {}
        
        for name, watcher in self.watchers.items():
            files = watcher.scan_existing_files()
            results[name] = files
            logger.debug(f"Watcher '{name}' found {len(files)} existing files")
        
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """
        Gibt Statusinformationen aller Watcher zurück.
        
        Returns:
            Dictionary mit Statusinformationen
        """
        status = {
            "total_watchers": len(self.watchers),
            "watchers": {}
        }
        
        for name, watcher in self.watchers.items():
            status["watchers"][name] = {
                "watching": watcher.watching,
                "watch_path": str(watcher.watch_path),
                "file_extensions": watcher.file_extensions
            }
        
        return status


class IntervalScanner:
    """
    Alternativer Scanner, der Verzeichnisse in Intervallen scannt
    (fallback falls watchdog nicht verfügbar ist).
    """
    
    def __init__(self, watch_path: str, callback_function,
                 file_extensions: Optional[List[str]] = None,
                 interval_seconds: int = 30):
        """
        Initialisiert den Interval Scanner.
        
        Args:
            watch_path: Pfad zum zu scannenden Verzeichnis
            callback_function: Funktion, die bei neuer Datei aufgerufen wird
            file_extensions: Liste unterstützter Dateiendungen (optional)
            interval_seconds: Scan-Intervall in Sekunden
        """
        self.watch_path = Path(watch_path)
        self.callback = callback_function
        self.interval = interval_seconds
        
        if file_extensions is None:
            self.file_extensions = [".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"]
        else:
            self.file_extensions = file_extensions
        
        self.scanning = False
        self.thread = None
        self.processed_files = set()
        
        # Verzeichnis erstellen falls nicht existent
        self.watch_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"IntervalScanner initialized for {self.watch_path}, interval: {interval_seconds}s")
    
    def _scan_loop(self):
        """Haupt-Scan-Schleife"""
        logger.info(f"Starting scan loop for {self.watch_path}")
        
        while self.scanning:
            try:
                self._perform_scan()
            except Exception as e:
                logger.error(f"Error during scan: {e}")
            
            time.sleep(self.interval)
    
    def _perform_scan(self):
        """Führt einen einzelnen Scan-Durchgang durch"""
        for ext in self.file_extensions:
            files = list(self.watch_path.glob(f"*{ext}"))
            files.extend(list(self.watch_path.glob(f"*{ext.upper()}")))
            
            for file_path in files:
                if not file_path.is_file():
                    continue
                
                file_key = str(file_path.resolve())
                
                if file_key not in self.processed_files:
                    logger.info(f"New file detected via interval scan: {file_path.name}")
                    self.processed_files.add(file_key)
                    self.callback(file_path)
    
    def start(self):
        """Startet den Interval Scanner"""
        if self.scanning:
            logger.warning("Scanner is already running")
            return
        
        self.scanning = True
        self.thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.thread.start()
        logger.info(f"Started interval scanner for {self.watch_path}")
    
    def stop(self):
        """Stoppt den Interval Scanner"""
        if not self.scanning:
            logger.warning("Scanner is not running")
            return
        
        self.scanning = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info(f"Stopped interval scanner for {self.watch_path}")
    
    def scan_existing(self) -> List[Path]:
        """Scannt vorhandene Dateien einmalig"""
        return self._perform_scan_once()
    
    def _perform_scan_once(self) -> List[Path]:
        """Führt einen einmaligen Scan durch"""
        existing_files = []
        
        for ext in self.file_extensions:
            files = list(self.watch_path.glob(f"*{ext}"))
            files.extend(list(self.watch_path.glob(f"*{ext.upper()}")))
            
            for file_path in files:
                if file_path.is_file():
                    existing_files.append(file_path)
        
        logger.info(f"Found {len(existing_files)} existing files in {self.watch_path}")
        return existing_files