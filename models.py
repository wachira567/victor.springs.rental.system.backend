from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, Numeric, DateTime, Date, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class AuditMixin:
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    updated_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)

class User(Base, AuditMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=True)
    google_id = Column(String(256), unique=True, nullable=True)
    name = Column(String(150), nullable=False)
    role = Column(String(50), nullable=False, default="tenant")
    is_approved = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50)) # e.g., UPDATE, DELETE, CREATE
    table_name = Column(String(50))
    record_id = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Optional if action by system
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class BillType(Base):
    __tablename__ = "bill_types"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)

    new_data = Column(JSON, nullable=True)

class Landlord(Base, AuditMixin):
    __tablename__ = "landlords"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    phone = Column(String(50))
    email = Column(String(120))
    id_number = Column(String(50))
    tax_pin = Column(String(50))
    bank_details = Column(Text)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    properties = relationship("Property", back_populates="landlord")

class Property(Base, AuditMixin):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    title = Column(String(200))
    code = Column(String(50), index=True)
    category = Column(String(100))
    description = Column(Text)
    location = Column(String(200))
    property_type = Column(String(50))
    num_units = Column(Integer, default=0)
    landlord_id = Column(Integer, ForeignKey('landlords.id'), nullable=False)
    management_commission_rate = Column(Numeric(5, 2), default=0.00)

    landlord = relationship("Landlord", back_populates="properties")
    units = relationship("Unit", back_populates="property")

class Unit(Base, AuditMixin):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey('properties.id'), nullable=False)
    unit_number = Column(String(50), nullable=False)
    unit_type = Column(String(100))
    market_rent = Column(Numeric(10, 2), nullable=False)
    is_vacant = Column(Boolean, default=True)

    property = relationship("Property", back_populates="units")
    leases = relationship("Lease", back_populates="unit")

class Tenant(Base, AuditMixin):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    national_id = Column(String(50), index=True)
    phone_number = Column(String(50), nullable=False)
    email = Column(String(120))
    gender = Column(String(20))
    emergency_contact = Column(String(150))
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    leases = relationship("Lease", back_populates="tenant")

class Lease(Base, AuditMixin):
    __tablename__ = "leases"

    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey('units.id'), nullable=False)
    tenant_id = Column(Integer, ForeignKey('tenants.id'), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    rent_amount = Column(Numeric(10, 2), nullable=False)
    deposit_amount = Column(Numeric(10, 2), default=0.00)
    status = Column(String(50), default="ACTIVE")

    unit = relationship("Unit", back_populates="leases")
    tenant = relationship("Tenant", back_populates="leases")
    invoices = relationship("Invoice", back_populates="lease")
    payments = relationship("Payment", back_populates="lease")

class Invoice(Base, AuditMixin):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    lease_id = Column(Integer, ForeignKey('leases.id'), nullable=False)
    billing_period = Column(Date, nullable=False)
    type = Column(String(200))
    amount = Column(Numeric(14, 2), nullable=False)
    amount_paid = Column(Numeric(14, 2), default=0.00)
    is_paid = Column(Boolean, default=False)

    lease = relationship("Lease", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice")

class Payment(Base, AuditMixin):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    lease_id = Column(Integer, ForeignKey('leases.id'), nullable=False)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String(50))
    reference_number = Column(String(100), unique=True, index=True, nullable=True)
    payment_date = Column(DateTime, default=datetime.utcnow)

    lease = relationship("Lease", back_populates="payments")
    invoice = relationship("Invoice", back_populates="payments")

class SmsTemplate(Base, AuditMixin):
    __tablename__ = "sms_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)

class SmsSchedule(Base, AuditMixin):
    __tablename__ = "sms_schedules"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey('sms_templates.id'), nullable=False)
    target_group = Column(String(50))
    is_active = Column(Boolean, default=True)
    send_day = Column(Integer, nullable=True)
    # SQLite does not have native TIME type support in Alembic that converts identically,
    # so we will store hour/minute independently or as a String. We will use string for now.
    send_time = Column(String(50), nullable=True) 

    template = relationship("SmsTemplate")

class SmsLog(Base):
    __tablename__ = "sms_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey('tenants.id'), nullable=False)
    phone_number = Column(String(50), nullable=False)
    message_content = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50))

    tenant = relationship("Tenant")

class Expenditure(Base, AuditMixin):
    __tablename__ = "expenditures"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey('properties.id'), nullable=False)
    notes = Column(Text, nullable=True)
    category = Column(String(100), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    date = Column(Date, default=datetime.utcnow)

    property = relationship("Property")

class MeterReading(Base, AuditMixin):
    __tablename__ = "meter_readings"

    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey('units.id'), nullable=False)
    previous_reading = Column(Numeric(10, 2), nullable=False)
    current_reading = Column(Numeric(10, 2), nullable=False)
    consumption = Column(Numeric(10, 2), nullable=False)
    rate = Column(Numeric(10, 2), nullable=False)
    total_charge = Column(Numeric(10, 2), nullable=False)
    reading_date = Column(Date, nullable=False)

    unit = relationship("Unit")
