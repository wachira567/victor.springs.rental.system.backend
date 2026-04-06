from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime, date
from decimal import Decimal


# --- Users ---
class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: Optional[str] = "tenant"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: str
    is_approved: bool
    is_active: bool
    permissions: Optional[List[str]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserPermissionsUpdate(BaseModel):
    permissions: List[str]


class UserPaginationOut(BaseModel):
    total: int
    page: int
    limit: int
    users: List[UserOut]


# --- Properties ---
class PropertyCreate(BaseModel):
    name: str = Field(..., max_length=150)
    location: Optional[str] = Field(None, max_length=200)
    landlord_id: int
    management_commission_rate: Optional[Decimal] = Decimal("0.00")
    code: Optional[str] = None
    num_units: Optional[int] = 0
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None


class PropertyOut(BaseModel):
    id: int
    name: str
    location: Optional[str] = None
    landlord_id: int
    management_commission_rate: Optional[Decimal] = Decimal("0.00")
    code: Optional[str] = None
    num_units: Optional[int] = 0
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None
    units_count: Optional[int] = 0
    landlord_name: Optional[str] = None

    class Config:
        from_attributes = True


# --- Units ---
class UnitBase(BaseModel):
    unit_number: str
    unit_type: Optional[str] = None
    market_rent: Decimal
    is_vacant: Optional[bool] = True
    utilities: Optional[
        List[dict]
    ] = []  # [{"name": "Garbage", "amount": 500, "frequency": "monthly"}]
    meter_number: Optional[str] = None


class UnitCreate(UnitBase):
    property_id: int


class UnitOut(UnitBase):
    id: int
    property_id: int
    is_vacant: bool
    # Joined data
    property_name: Optional[str] = None

    class Config:
        from_attributes = True


# --- Tenants ---
class TenantCreate(BaseModel):
    full_name: str = Field(..., max_length=150)
    national_id: str = Field(..., max_length=50)
    phone_number: str = Field(..., max_length=50)
    email: Optional[EmailStr] = None
    emergency_contact: Optional[str] = Field(None, max_length=150)
    gender: Optional[str] = None


class TenantOut(BaseModel):
    id: int
    full_name: str
    national_id: Optional[str] = None
    phone_number: str
    email: Optional[str] = None
    emergency_contact: Optional[str] = None
    gender: Optional[str] = None
    user_id: Optional[int] = None
    current_unit: Optional[str] = None
    current_property: Optional[str] = None

    class Config:
        from_attributes = True


# --- Landlords ---
class LandlordCreate(BaseModel):
    name: str = Field(..., max_length=150)
    phone: str = Field(..., max_length=50)
    email: Optional[EmailStr] = None
    id_number: Optional[str] = None
    tax_pin: Optional[str] = None
    bank_details: Optional[str] = None
    property_ids: Optional[List[int]] = []

class LandlordOut(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str] = None
    id_number: Optional[str] = None
    tax_pin: Optional[str] = None
    bank_details: Optional[str] = None
    properties: Optional[List[str]] = []
    properties_count: Optional[int] = 0

    class Config:
        from_attributes = True


# --- Leases ---
class LeaseCreate(BaseModel):
    unit_id: int
    tenant_id: int
    start_date: date
    end_date: Optional[date] = None
    rent_amount: Decimal
    deposit_amount: Optional[Decimal] = Decimal("0.00")


class LeaseOut(BaseModel):
    id: int
    unit_id: int
    tenant_id: int
    start_date: date
    end_date: Optional[date] = None
    rent_amount: Decimal
    deposit_amount: Optional[Decimal] = Decimal("0.00")
    status: str
    # Joined data for display
    unit_number: Optional[str] = None
    property_name: Optional[str] = None
    tenant_name: Optional[str] = None

    class Config:
        from_attributes = True


# --- Invoices ---
class InvoiceCreate(BaseModel):
    lease_id: int
    billing_period: date
    type: Optional[str] = None
    amount: Decimal
    amount_paid: Optional[Decimal] = Decimal("0.00")
    is_paid: Optional[bool] = False


class InvoiceOut(BaseModel):
    id: int
    lease_id: int
    billing_period: date
    type: Optional[str] = None
    amount: Decimal
    amount_paid: Optional[Decimal] = Decimal("0.00")
    is_paid: bool
    # Joined data
    tenant_name: Optional[str] = None
    unit_number: Optional[str] = None
    property_name: Optional[str] = None
    tenant_balance: Optional[Decimal] = None
    amount_due: Optional[Decimal] = None

    class Config:
        from_attributes = True


# --- Configuration Schemas ---
class AttributeCreate(BaseModel):
    name: str = Field(..., max_length=100)


class AttributeOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class ExpenseCategoryCreate(BaseModel):
    name: str = Field(..., max_length=100)


class ExpenseCategoryOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class BankNameCreate(BaseModel):
    name: str = Field(..., max_length=100)


class BankNameOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class BankCreate(BaseModel):
    name: str = Field(..., max_length=150)
    branch_name: Optional[str] = Field(None, max_length=100)
    account_number: str = Field(..., max_length=100)
    bank_name_id: int


class BankOut(BaseModel):
    id: int
    name: str
    branch_name: Optional[str] = None
    account_number: str
    bank_name_id: int
    bank_name: Optional[str] = None

    class Config:
        from_attributes = True


# --- Bill Types ---
class BillTypeCreate(BaseModel):
    name: str = Field(..., max_length=100)


class BillTypeOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


# --- Payments ---
class PaymentCreate(BaseModel):
    lease_id: int
    invoice_id: Optional[int] = None
    amount: Decimal
    payment_method: str = Field(..., max_length=50)
    reference_number: Optional[str] = Field(None, max_length=100)


class PaymentOut(BaseModel):
    id: int
    lease_id: int
    invoice_id: Optional[int] = None
    amount: Decimal
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    payment_date: datetime

    # Joined data
    tenant_name: Optional[str] = None
    unit_number: Optional[str] = None
    property_name: Optional[str] = None

    class Config:
        from_attributes = True


# --- Expenditures ---
class ExpenditureCreate(BaseModel):
    property_id: int
    notes: Optional[str] = None
    category: str = Field(..., max_length=100)
    amount: Decimal
    date: Optional[date] = None


class ExpenditureOut(BaseModel):
    id: int
    property_id: int
    notes: Optional[str] = None
    category: str
    amount: Decimal
    date: date
    # Joined data
    property_name: Optional[str] = None

    class Config:
        from_attributes = True


# --- Landlord Remittances ---
class LandlordRemittanceCreate(BaseModel):
    landlord_id: int
    property_id: int
    payment_mode: Optional[str] = None
    ref_number: Optional[str] = None
    remarks: Optional[str] = None
    amount: Decimal
    date: Optional[date] = None


class LandlordRemittanceOut(BaseModel):
    id: int
    landlord_id: int
    property_id: int
    payment_mode: Optional[str] = None
    ref_number: Optional[str] = None
    remarks: Optional[str] = None
    amount: Decimal
    date: date
    # Joined data
    landlord_name: Optional[str] = None
    property_name: Optional[str] = None

    class Config:
        from_attributes = True


# --- Auth ---
class Token(BaseModel):
    access_token: str
    token_type: str


class GoogleLogin(BaseModel):
    token: str
    role: Optional[str] = "tenant"


# --- Meter Readings ---
class MeterReadingCreate(BaseModel):
    unit_id: int
    previous_reading: Decimal
    current_reading: Decimal
    consumption: Decimal
    rate: Decimal
    total_charge: Decimal
    reading_date: date


class MeterReadingOut(BaseModel):
    id: int
    unit_id: int
    previous_reading: Decimal
    current_reading: Decimal
    consumption: Decimal
    rate: Decimal
    total_charge: Decimal
    reading_date: date
    # Joined data
    unit_number: Optional[str] = None
    property_name: Optional[str] = None
    tenant_name: Optional[str] = None

    class Config:
        from_attributes = True


# --- Bank Transactions ---
class BankTransactionCreate(BaseModel):
    date: date
    type: str  # 'DEPOSIT' or 'WITHDRAWAL'
    amount: Decimal
    reference: Optional[str] = None
    notes: Optional[str] = None


class BankTransactionOut(BaseModel):
    id: int
    date: date
    type: str
    amount: Decimal
    reference: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


# --- SMS ---
class SmsTemplateCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: Optional[str] = Field(None, max_length=50)
    content: str


class SmsTemplateOut(SmsTemplateCreate):
    id: int

    class Config:
        from_attributes = True


class SmsScheduleCreate(BaseModel):
    template_id: int
    target_group: str = "ALL_TENANTS"
    send_day: int
    send_time: str
    is_active: bool = True


class SmsScheduleOut(SmsScheduleCreate):
    id: int

    class Config:
        from_attributes = True


class ManualDispatch(BaseModel):
    tenant_ids: List[int]
    message_content: str

# --- WhatsApp ---
class WhatsAppConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    allow_tenant_access: Optional[bool] = None
    allow_landlord_access: Optional[bool] = None
    tenant_allowed_features: Optional[List[str]] = None
    landlord_allowed_features: Optional[List[str]] = None
    inactivity_timeout_minutes: Optional[int] = None

class WhatsAppConfigOut(BaseModel):
    id: int
    is_enabled: bool
    allow_tenant_access: bool
    allow_landlord_access: bool
    tenant_allowed_features: List[str]
    landlord_allowed_features: List[str]
    inactivity_timeout_minutes: int

    class Config:
        from_attributes = True

class WhatsAppMessageOut(BaseModel):
    id: int
    session_id: int
    sender: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True

class WhatsAppSessionOut(BaseModel):
    id: int
    phone_number: str
    user_id: Optional[int] = None
    user_role: str
    user_name: Optional[str] = None
    current_state: str
    last_interaction_at: datetime
    messages: Optional[List[WhatsAppMessageOut]] = None

    class Config:
        from_attributes = True
