#!/usr/bin/env python3
"""
Entwicklungssetup-Skript für Device Management System

Erstellt Datenbanktabellen und initiale Testdaten.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from datetime import datetime
import bcrypt

from device_management.config import settings
from device_management.models import Base, User, Customer, Location, Device


def setup_database():
    """Erstellt Datenbanktabellen und initiale Daten."""
    
    print(f"Setting up database: {settings.database_url}")
    
    # Engine erstellen
    engine = create_engine(settings.database_url)
    
    try:
        # Tabellen erstellen
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("✓ Tables created successfully")
        
    except OperationalError as e:
        print(f"✗ Database error: {e}")
        sys.exit(1)
    
    return engine


def create_initial_data(engine):
    """Erstellt initiale Testdaten."""
    
    print("\nCreating initial test data...")
    
    with Session(engine) as session:
        # Passwort Hashing mit bcrypt direkt
        
        # Prüfen ob Admin-User bereits existiert
        admin_user = session.query(User).filter(User.username == "admin").first()
        if not admin_user:
            # Einfaches Passwort für Entwicklung
            admin_user = User(
                username="admin",
                email="admin@example.com",
                full_name="Administrator",
                hashed_password=bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode(),
                is_active=True,
                is_superuser=True
            )
            session.add(admin_user)
            print("✓ Created admin user (username: admin, password: admin123)")
        
        # Prüfen ob Test-User existiert
        test_user = session.query(User).filter(User.username == "technician").first()
        if not test_user:
            test_user = User(
                username="technician",
                email="tech@example.com",
                full_name="Techniker Mustermann",
                hashed_password=bcrypt.hashpw("tech123".encode(), bcrypt.gensalt()).decode(),
                is_active=True,
                is_superuser=False
            )
            session.add(test_user)
            print("✓ Created technician user (username: technician, password: tech123)")
        
        # Test-Kunde erstellen
        test_customer = session.query(Customer).filter(Customer.name == "Testkunde GmbH").first()
        if not test_customer:
            test_customer = Customer(
                glpi_entity_id=9999,
                name="Testkunde GmbH",
                code="TEST-001",
                address="Musterstraße 1, 12345 Musterstadt",
                phone="+49 123 456789",
                email="info@testkunde.de",
                glpi_data={"id": 9999, "name": "Testkunde GmbH", "completename": "Testkunde GmbH"}
            )
            session.add(test_customer)
            print("✓ Created test customer 'Testkunde GmbH'")
        
        # Test-Standort erstellen
        test_location = session.query(Location).filter(Location.name == "Musterstadt Hauptsitz").first()
        if not test_location:
            test_location = Location(
                glpi_location_id=5000,
                name="Musterstadt Hauptsitz",
                address="Musterstraße 1, 12345 Musterstadt",
                glpi_data={"id": 5000, "name": "Musterstadt Hauptsitz"},
                customer=test_customer
            )
            session.add(test_location)
            print("✓ Created test location 'Musterstadt Hauptsitz'")
        
        # Test-Gerät erstellen
        test_device = session.query(Device).filter(Device.pc_name == "PC-MUSTER-001").first()
        if not test_device:
            test_device = Device(
                customer=test_customer,
                location=test_location,
                pc_name="PC-MUSTER-001",
                user="Max Mustermann",
                technician="Anna Techniker",
                manufacturer="Dell",
                model="OptiPlex 7080",
                serial_number="ABC123XYZ",
                mac_address="00:1A:2B:3C:4D:5E",
                ip_address="192.168.1.100",
                operating_system="Windows 10 Pro",
                domain="testkunde.local",
                teamviewer_id="123456789",
                antivirus="Windows Defender",
                notes="Testgerät für Entwicklung",
                status="active",
                source="manual",
                created_by=admin_user.id if admin_user.id else "system",
                sync_status="pending"
            )
            session.add(test_device)
            print("✓ Created test device 'PC-MUSTER-001'")
        
        session.commit()
        print("✓ All data committed to database")
    
    print("\nSetup completed successfully!")
    print("\nAvailable users:")
    print("  - Admin:     username: admin, password: admin123")
    print("  - Technician: username: technician, password: tech123")
    print("\nAPI can be started with: python -m device_management.api.main")


def main():
    """Hauptfunktion."""
    print("=" * 60)
    print("Device Management System - Development Setup")
    print("=" * 60)
    
    try:
        engine = setup_database()
        create_initial_data(engine)
        
        print("\n" + "=" * 60)
        print("Next steps:")
        print("1. Start the API server: python -m device_management.api.main")
        print("2. Open browser to: http://localhost:8000/docs")
        print("3. Login with admin credentials")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()