"""
Hauptanwendung für Device Management System

FastAPI-App mit allen Routen und Abhängigkeiten für Phase 1.
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
from typing import List, Optional

from .schemas import DeviceResponse, DeviceCreate, CustomerResponse, UserResponse
from ..config import settings
from ..models import Base
from .dependencies.database import SessionLocal, get_db

# Logger konfigurieren
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


def create_application() -> FastAPI:
    """
    Erstellt und konfiguriert die FastAPI-Anwendung.
    """
    
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description="Modulare Software zur Erfassung und Verwaltung von Kundengeräten mit GLPI-Integration",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    
    # CORS Middleware für Frontend-Integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In Produktion einschränken
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Die Anwendung läuft hinter Nginx auch im internen HTTP-Betrieb.
    # HTTPS-Terminierung kann später am Reverse Proxy aktiviert werden.

    # API-Router importieren und einbinden
    from .routers import devices, customers, users, auth, glpi, ocr, setup
    
    app.include_router(auth.router, prefix=settings.api_prefix, tags=["Authentication"])
    app.include_router(devices.router, prefix=settings.api_prefix, tags=["Devices"])
    app.include_router(customers.router, prefix=settings.api_prefix, tags=["Customers"])
    app.include_router(users.router, prefix=settings.api_prefix, tags=["Users"])
    app.include_router(glpi.router, prefix=settings.api_prefix, tags=["GLPI"])
    app.include_router(ocr.router, prefix=settings.api_prefix, tags=["OCR Processing"])
    app.include_router(setup.router, prefix=f"{settings.api_prefix}/setup", tags=["Setup"])
    
    # Health Check Endpoint
    @app.get("/", tags=["Health"])
    async def root():
        return {
            "message": "Device Management System API",
            "version": settings.api_version,
            "docs": "/docs",
            "api_prefix": settings.api_prefix,
        }
    
    @app.get("/health", tags=["Health"])
    async def health_check():
        return {
            "status": "healthy",
            "service": "device-management-api",
            "version": settings.api_version,
        }
    
    # Error Handler
    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Ein interner Serverfehler ist aufgetreten.",
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
        )
    
    return app


# Globale Anwendungsinstanz
app = create_application()


@app.on_event("startup")
async def startup_event():
    """
    Wird beim Start der Anwendung ausgeführt.
    """
    logger.info(f"Starting Device Management System API v{settings.api_version}")
    logger.info(f"Environment: {'Development' if settings.debug else 'Production'}")
    logger.info(f"Host: {settings.host}:{settings.port}")
    logger.info(f"Database: {settings.database_url}")
    
    # Datenbank initialisieren
    from sqlalchemy import create_engine
    engine = create_engine(settings.database_url)
    
    try:
        # Tabellen erstellen (nur für Entwicklung)
        if settings.debug:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables created successfully")
        
        logger.info("Application startup completed")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """
    Wird beim Herunterfahren der Anwendung ausgeführt.
    """
    logger.info("Shutting down Device Management System API")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "device_management.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )