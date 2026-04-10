from fastapi import APIRouter, Depends, HTTPException, status, Response, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date, datetime
import models, schemas, auth
from database import get_db

router = APIRouter(prefix="/core", tags=["core"])


# ==============================================================================
# PROPERTIES
# ==============================================================================
@router.get("/properties", response_model=List[schemas.PropertyOut])
def get_properties(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Get all properties with landlord info
    properties = (
        db.query(models.Property)
        .options(joinedload(models.Property.landlord))
        .all()
    )

    result = []
    for prop in properties:
        # Get actual count of unit records from the database
        actual_units_count = db.query(models.Unit).filter(models.Unit.property_id == prop.id).count()
        
        data = schemas.PropertyOut.model_validate(prop).model_dump()
        data["landlord_name"] = prop.landlord.name if prop.landlord else "No Landlord"
        data["units_count"] = actual_units_count
        result.append(data)
    return result


@router.get("/properties/{property_id}")
def get_property(
    property_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    prop = (
        db.query(models.Property)
        .options(
            joinedload(models.Property.landlord), joinedload(models.Property.units)
        )
        .filter(models.Property.id == property_id)
        .first()
    )

    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    data = schemas.PropertyOut.model_validate(prop).model_dump()
    data["landlord_name"] = prop.landlord.name if prop.landlord else None
    data["units_count"] = len(prop.units) if prop.units else 0
    return data


@router.post(
    "/properties",
    response_model=schemas.PropertyOut,
    status_code=status.HTTP_201_CREATED,
)
def create_property(
    property: schemas.PropertyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role(["super_admin", "admin", "landlord"])
    ),
):

    new_property = models.Property(**property.model_dump())
    new_property.created_by_id = current_user.id

    db.add(new_property)
    db.commit()
    db.refresh(new_property)
    return new_property


@router.put("/properties/{property_id}")
def update_property(
    property_id: int,
    property_data: schemas.PropertyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    prop = db.query(models.Property).filter(models.Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    for key, value in property_data.model_dump().items():
        setattr(prop, key, value)
    prop.updated_by_id = current_user.id

    db.commit()
    db.refresh(prop)
    return {"message": "Property updated successfully", "id": prop.id}


@router.delete("/properties/{property_id}")
def delete_property(
    property_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    prop = db.query(models.Property).filter(models.Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Check if property has units with active leases
    active_leases = (
        db.query(models.Lease)
        .join(models.Unit)
        .filter(models.Unit.property_id == property_id, models.Lease.status == "ACTIVE")
        .count()
    )

    if active_leases > 0:
        raise HTTPException(
            status_code=400, detail="Cannot delete property with active leases"
        )

    db.delete(prop)
    db.commit()
    return {"message": "Property deleted successfully"}


# ==============================================================================
# UNITS
# ==============================================================================
@router.get("/units", response_model=List[schemas.UnitOut])
def get_units(
    property_id: int = None,
    vacant: bool = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.Unit).options(joinedload(models.Unit.property))

    if property_id is not None:
        query = query.filter(models.Unit.property_id == property_id)
    if vacant is not None:
        query = query.filter(models.Unit.is_vacant == vacant)

    units = query.all()
    result = []
    for unit in units:
        data = schemas.UnitOut.model_validate(unit).model_dump()
        data["property_name"] = unit.property.name if unit.property else None
        result.append(data)
    return result


@router.put("/units/{unit_id}")
def update_unit(
    unit_id: int,
    unit_data: schemas.UnitCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    unit = db.query(models.Unit).filter(models.Unit.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    # Check for duplicate unit number in same property (excluding current unit)
    existing = (
        db.query(models.Unit)
        .filter(
            models.Unit.property_id == unit_data.property_id,
            models.Unit.unit_number == unit_data.unit_number,
            models.Unit.id != unit_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Unit number already exists in this property"
        )

    for key, value in unit_data.model_dump().items():
        setattr(unit, key, value)
    unit.updated_by_id = current_user.id

    db.commit()
    db.refresh(unit)
    return {"message": "Unit updated successfully", "id": unit.id}


@router.get("/units/{unit_id}")
def get_unit(
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    unit = (
        db.query(models.Unit)
        .options(
            joinedload(models.Unit.property),
            joinedload(models.Unit.leases).joinedload(models.Lease.tenant),
        )
        .filter(models.Unit.id == unit_id)
        .first()
    )

    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    data = schemas.UnitOut.model_validate(unit).model_dump()
    data["property_name"] = unit.property.name if unit.property else None

    # Get active lease info
    active_lease = next((l for l in unit.leases if l.status == "ACTIVE"), None)
    if active_lease:
        data["active_lease"] = {
            "id": active_lease.id,
            "tenant_name": active_lease.tenant.full_name
            if active_lease.tenant
            else None,
            "rent_amount": float(active_lease.rent_amount),
            "start_date": str(active_lease.start_date),
        }
    else:
        data["active_lease"] = None

    return data


@router.post(
    "/units", response_model=schemas.UnitOut, status_code=status.HTTP_201_CREATED
)
def create_unit(
    unit: schemas.UnitCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):

    # Verify property exists
    prop = (
        db.query(models.Property).filter(models.Property.id == unit.property_id).first()
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Check for duplicate unit number in same property
    existing = (
        db.query(models.Unit)
        .filter(
            models.Unit.property_id == unit.property_id,
            models.Unit.unit_number == unit.unit_number,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Unit number already exists in this property"
        )

    new_unit = models.Unit(**unit.model_dump())
    new_unit.created_by_id = current_user.id

    db.add(new_unit)
    db.commit()
    db.refresh(new_unit)
    return new_unit


@router.put("/units/{unit_id}")
def update_unit(
    unit_id: int,
    unit_data: schemas.UnitCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    unit = db.query(models.Unit).filter(models.Unit.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    # Check for duplicate unit number in same property (excluding current unit)
    existing = (
        db.query(models.Unit)
        .filter(
            models.Unit.property_id == unit_data.property_id,
            models.Unit.unit_number == unit_data.unit_number,
            models.Unit.id != unit_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Unit number already exists in this property"
        )

    for key, value in unit_data.model_dump().items():
        setattr(unit, key, value)
    unit.updated_by_id = current_user.id

    db.commit()
    db.refresh(unit)
    return {"message": "Unit updated successfully", "id": unit.id}


@router.delete("/units/{unit_id}")
def delete_unit(
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    unit = db.query(models.Unit).filter(models.Unit.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    # Check if unit has active leases
    active_lease = (
        db.query(models.Lease)
        .filter(models.Lease.unit_id == unit_id, models.Lease.status == "ACTIVE")
        .first()
    )

    if active_lease:
        raise HTTPException(
            status_code=400, detail="Cannot delete unit with active lease"
        )

    db.delete(unit)
    db.commit()
    return {"message": "Unit deleted successfully"}


# ==============================================================================
# LANDLORDS
# ==============================================================================
@router.get("/landlords")
def get_landlords(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    landlords = (
        db.query(models.Landlord).options(joinedload(models.Landlord.properties)).all()
    )

    result = []
    for landlord in landlords:
        data = {
            "id": landlord.id,
            "name": landlord.name,
            "phone": landlord.phone,
            "email": landlord.email,
            "id_number": landlord.id_number,
            "tax_pin": landlord.tax_pin,
            "bank_details": landlord.bank_details,
            "properties_count": len(landlord.properties) if landlord.properties else 0,
            "properties": [p.name for p in landlord.properties] if landlord.properties else [],
            "property_ids": [p.id for p in landlord.properties] if landlord.properties else [],
        }
        result.append(data)
    return result


@router.post("/landlords", status_code=status.HTTP_201_CREATED)
def create_landlord(
    landlord_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):

    property_ids = landlord_data.pop("property_ids", [])
    new_landlord = models.Landlord(**landlord_data)
    new_landlord.created_by_id = current_user.id

    db.add(new_landlord)
    db.commit()
    db.refresh(new_landlord)

    if property_ids:
        db.query(models.Property).filter(models.Property.id.in_(property_ids)).update(
            {"landlord_id": new_landlord.id}, synchronize_session=False
        )
        db.commit()

    return {"message": "Landlord created successfully", "id": new_landlord.id}


@router.put("/landlords/{landlord_id}")
def update_landlord(
    landlord_id: int,
    landlord_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    landlord = (
        db.query(models.Landlord).filter(models.Landlord.id == landlord_id).first()
    )
    if not landlord:
        raise HTTPException(status_code=404, detail="Landlord not found")

    property_ids = landlord_data.pop("property_ids", [])

    for key, value in landlord_data.items():
        if hasattr(landlord, key):
            setattr(landlord, key, value)
    landlord.updated_by_id = current_user.id

    # Reset old properties linked to this landlord
    db.query(models.Property).filter(models.Property.landlord_id == landlord_id).update(
        {"landlord_id": None}, synchronize_session=False
    )
    
    if property_ids:
        db.query(models.Property).filter(models.Property.id.in_(property_ids)).update(
            {"landlord_id": landlord_id}, synchronize_session=False
        )

    db.commit()
    db.refresh(landlord)
    return {"message": "Landlord updated successfully", "id": landlord.id}


@router.delete("/landlords/{landlord_id}")
def delete_landlord(
    landlord_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    landlord = (
        db.query(models.Landlord).filter(models.Landlord.id == landlord_id).first()
    )
    if not landlord:
        raise HTTPException(status_code=404, detail="Landlord not found")

    # Check if landlord has properties
    if landlord.properties and len(landlord.properties) > 0:
        raise HTTPException(
            status_code=400, detail="Cannot delete landlord with associated properties"
        )

    db.delete(landlord)
    db.commit()
    return {"message": "Landlord deleted successfully"}


# ==============================================================================
# TENANTS
# ==============================================================================
@router.get("/tenants", response_model=List[schemas.TenantOut])
def get_tenants(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    from sqlalchemy.orm import selectinload
    tenants = (
        db.query(models.Tenant)
        .options(
            selectinload(models.Tenant.leases)
            .joinedload(models.Lease.unit)
            .joinedload(models.Unit.property)
        )
        .all()
    )

    result = []
    for tenant in tenants:
        data = schemas.TenantOut.model_validate(tenant).model_dump()

        # Get all active leases for this tenant
        active_leases = [l for l in tenant.leases if l.status == "ACTIVE"]
        if active_leases:
            # Show all active units with property names
            units_info = []
            for lease in active_leases:
                if lease.unit:
                    prop_name = (
                        lease.unit.property.name if lease.unit.property else None
                    )
                    units_info.append(
                        f"{lease.unit.unit_number} ({prop_name})"
                        if prop_name
                        else lease.unit.unit_number
                    )
            data["current_unit"] = ", ".join(units_info) if units_info else None
            data["current_property"] = None  # Already included in current_unit
        else:
            data["current_unit"] = None
            data["current_property"] = None

        result.append(data)
    return result


@router.get("/tenants/{tenant_id}")
def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    tenant = (
        db.query(models.Tenant)
        .options(
            joinedload(models.Tenant.leases)
            .joinedload(models.Lease.unit)
            .joinedload(models.Unit.property)
        )
        .filter(models.Tenant.id == tenant_id)
        .first()
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    data = schemas.TenantOut.model_validate(tenant).model_dump()

    # Get all leases
    leases_data = []
    for lease in tenant.leases:
        lease_info = {
            "id": lease.id,
            "unit_number": lease.unit.unit_number if lease.unit else None,
            "property_name": lease.unit.property.name
            if lease.unit and lease.unit.property
            else None,
            "start_date": str(lease.start_date),
            "end_date": str(lease.end_date) if lease.end_date else None,
            "rent_amount": float(lease.rent_amount),
            "status": lease.status,
        }
        leases_data.append(lease_info)

    data["leases"] = leases_data
    return data


@router.post(
    "/tenants", response_model=schemas.TenantOut, status_code=status.HTTP_201_CREATED
)
def create_tenant(
    tenant: schemas.TenantCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):

    db_tenant = (
        db.query(models.Tenant)
        .filter(models.Tenant.national_id == tenant.national_id)
        .first()
    )
    if db_tenant:
        raise HTTPException(
            status_code=400, detail="Tenant with this National ID already exists"
        )
        
    db_tenant_phone = (
        db.query(models.Tenant)
        .filter(models.Tenant.phone_number == tenant.phone_number)
        .first()
    )
    if db_tenant_phone:
        raise HTTPException(
            status_code=400, detail="Tenant with this phone number already exists"
        )

    new_tenant = models.Tenant(**tenant.model_dump())
    new_tenant.created_by_id = current_user.id
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    return new_tenant


@router.put("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: int,
    tenant_data: schemas.TenantCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Check for duplicate national ID (excluding current tenant)
    existing = (
        db.query(models.Tenant)
        .filter(
            models.Tenant.national_id == tenant_data.national_id,
            models.Tenant.id != tenant_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Tenant with this National ID already exists"
        )

    # Check for duplicate phone number
    existing_phone = (
        db.query(models.Tenant)
        .filter(
            models.Tenant.phone_number == tenant_data.phone_number,
            models.Tenant.id != tenant_id,
        )
        .first()
    )
    if existing_phone:
        raise HTTPException(
            status_code=400, detail="Tenant with this phone number already exists"
        )

    for key, value in tenant_data.model_dump().items():
        setattr(tenant, key, value)
    tenant.updated_by_id = current_user.id

    db.commit()
    db.refresh(tenant)
    return {"message": "Tenant updated successfully", "id": tenant.id}


@router.post("/tenants/{tenant_id}/document")
def upload_tenant_document(
    tenant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    import os
    try:
        import cloudinary
        import cloudinary.uploader
    except ImportError:
        raise HTTPException(status_code=500, detail="Cloudinary not configured. Please add cloudinary to Pipfile.")
    
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    api_key = os.environ.get("CLOUDINARY_API_KEY", "")
    api_secret = os.environ.get("CLOUDINARY_API_SECRET", "")
    
    if not cloud_name or not api_key or not api_secret:
        raise HTTPException(status_code=500, detail="Cloudinary credentials not configured in environment variables.")
    
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret
    )
    
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    tenant_name = tenant.full_name.replace(" ", "_")
    lease = db.query(models.Lease).filter(models.Lease.tenant_id == tenant_id, models.Lease.status == "ACTIVE").first()
    unit_info = ""
    if lease and lease.unit:
        unit_info = f"_{lease.unit.unit_number}"
    
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    
    public_id = f"{tenant_name}{unit_info}_{date_str}"
    
    try:
        result = cloudinary.uploader.upload(
            file.file,
            public_id=public_id,
            folder="tenant_agreements",
            resource_type="auto"
        )
        
        tenant.agreement_document_url = result.get("secure_url")
        db.commit()
        db.refresh(tenant)
        
        return {
            "message": "Document uploaded successfully",
            "url": result.get("secure_url"),
            "tenant_id": tenant.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/tenants/{tenant_id}")
def delete_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Check if tenant has active leases
    active_lease = (
        db.query(models.Lease)
        .filter(models.Lease.tenant_id == tenant_id, models.Lease.status == "ACTIVE")
        .first()
    )

    if active_lease:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete tenant with active lease. Terminate the lease first.",
        )

    tenant.is_active = False
    db.commit()
    return {"message": "Tenant logically terminated successfully"}


# ==============================================================================
# LEASES (with joined unit/property/tenant data)
# ==============================================================================
@router.get("/leases/{lease_id}/bank-accounts")
def get_lease_bank_accounts(
    lease_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get bank accounts associated with a lease's property landlord."""
    lease = (
        db.query(models.Lease)
        .options(
            joinedload(models.Lease.unit).joinedload(models.Unit.property).joinedload(models.Property.landlord)
        )
        .filter(models.Lease.id == lease_id)
        .first()
    )
    
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")
    
    bank_accounts = []
    if lease.unit and lease.unit.property and lease.unit.property.landlord:
        landlord = lease.unit.property.landlord
        if landlord.bank_details:
            bank_accounts.append({
                "bank_details": landlord.bank_details,
                "landlord_name": landlord.name
            })
    
    return bank_accounts


@router.get("/leases")
def get_leases(
    status: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.Lease).options(
        joinedload(models.Lease.tenant),
        joinedload(models.Lease.unit).joinedload(models.Unit.property),
    )

    if status:
        query = query.filter(models.Lease.status == status.upper())

    leases = query.order_by(models.Lease.start_date.desc()).all()

    result = []
    for lease in leases:
        data = {
            "id": lease.id,
            "unit_id": lease.unit_id,
            "tenant_id": lease.tenant_id,
            "start_date": str(lease.start_date),
            "end_date": str(lease.end_date) if lease.end_date else None,
            "rent_amount": float(lease.rent_amount),
            "deposit_amount": float(lease.deposit_amount)
            if lease.deposit_amount
            else 0,
            "status": lease.status,
            "unit_number": None,
            "property_name": None,
            "tenant_name": None,
            "tenant_phone": None,
        }
        # Join unit and property
        if lease.unit:
            data["unit_number"] = lease.unit.unit_number
            if lease.unit.property:
                data["property_name"] = lease.unit.property.name
        # Join tenant
        if lease.tenant:
            data["tenant_name"] = lease.tenant.full_name
            data["tenant_phone"] = lease.tenant.phone_number
        result.append(data)
    return result


@router.get("/leases/{lease_id}")
def get_lease(
    lease_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    lease = (
        db.query(models.Lease)
        .options(
            joinedload(models.Lease.tenant),
            joinedload(models.Lease.unit).joinedload(models.Unit.property),
            joinedload(models.Lease.invoices),
            joinedload(models.Lease.payments),
        )
        .filter(models.Lease.id == lease_id)
        .first()
    )

    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")

    data = {
        "id": lease.id,
        "unit_id": lease.unit_id,
        "tenant_id": lease.tenant_id,
        "start_date": str(lease.start_date),
        "end_date": str(lease.end_date) if lease.end_date else None,
        "rent_amount": float(lease.rent_amount),
        "deposit_amount": float(lease.deposit_amount) if lease.deposit_amount else 0,
        "status": lease.status,
        "unit_number": lease.unit.unit_number if lease.unit else None,
        "property_name": lease.unit.property.name
        if lease.unit and lease.unit.property
        else None,
        "tenant_name": lease.tenant.full_name if lease.tenant else None,
        "tenant_phone": lease.tenant.phone_number if lease.tenant else None,
        "total_invoices": len(lease.invoices) if lease.invoices else 0,
        "total_payments": sum(float(p.amount) for p in lease.payments)
        if lease.payments
        else 0,
    }
    return data


@router.post("/leases", status_code=status.HTTP_201_CREATED)
def create_lease(
    lease: schemas.LeaseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):

    # Check if unit exists and is vacant
    unit = db.query(models.Unit).filter(models.Unit.id == lease.unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    # Check if unit already has active lease
    existing_lease = (
        db.query(models.Lease)
        .filter(models.Lease.unit_id == lease.unit_id, models.Lease.status == "ACTIVE")
        .first()
    )
    if existing_lease:
        raise HTTPException(status_code=400, detail="Unit already has an active lease")

    # Check if tenant exists
    tenant = db.query(models.Tenant).filter(models.Tenant.id == lease.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Check if tenant already has active lease for this unit
    tenant_lease = (
        db.query(models.Lease)
        .filter(
            models.Lease.tenant_id == lease.tenant_id,
            models.Lease.unit_id == lease.unit_id,
            models.Lease.status == "ACTIVE",
        )
        .first()
    )
    if tenant_lease:
        raise HTTPException(
            status_code=400, detail="Tenant already has an active lease for this unit"
        )

    new_lease = models.Lease(**lease.model_dump())
    new_lease.created_by_id = current_user.id
    new_lease.status = "ACTIVE"

    # Mark unit as occupied
    unit.is_vacant = False

    db.add(new_lease)
    db.commit()
    db.refresh(new_lease)
    return {
        "id": new_lease.id,
        "status": new_lease.status,
        "message": "Lease created successfully",
    }


@router.put("/leases/{lease_id}")
def update_lease(
    lease_id: int,
    lease_data: schemas.LeaseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    lease = db.query(models.Lease).filter(models.Lease.id == lease_id).first()
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")

    if lease.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="Can only update active leases")

    for key, value in lease_data.model_dump().items():
        setattr(lease, key, value)
    lease.updated_by_id = current_user.id

    db.commit()
    db.refresh(lease)
    return {"message": "Lease updated successfully", "id": lease.id}


@router.post("/leases/{lease_id}/terminate")
def terminate_lease(
    lease_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    lease = db.query(models.Lease).filter(models.Lease.id == lease_id).first()
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")

    if lease.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="Lease is already terminated")

    # Check for unpaid invoices
    unpaid_invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.lease_id == lease_id, models.Invoice.is_paid == False)
        .count()
    )

    if unpaid_invoices > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot terminate lease with {unpaid_invoices} unpaid invoices. Clear all bills first.",
        )

    # Terminate lease
    lease.status = "TERMINATED"
    lease.end_date = date.today()
    lease.updated_by_id = current_user.id

    # Mark unit as vacant
    unit = db.query(models.Unit).filter(models.Unit.id == lease.unit_id).first()
    if unit:
        unit.is_vacant = True

    db.commit()
    return {"message": "Lease terminated successfully", "id": lease.id}


# ==============================================================================
# INVOICES
# ==============================================================================
@router.post("/invoices/generate", status_code=status.HTTP_201_CREATED)
def generate_monthly_invoices(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    active_leases = db.query(models.Lease).filter(models.Lease.status == "ACTIVE").all()
    current_month = date.today().replace(day=1)

    generated = 0
    for lease in active_leases:
        # Check if rent invoice for this exact month exists
        existing = (
            db.query(models.Invoice)
            .filter(
                models.Invoice.lease_id == lease.id,
                models.Invoice.type == "Rent",
                models.Invoice.billing_period == current_month,
            )
            .first()
        )

        if not existing:
            new_inv = models.Invoice(
                lease_id=lease.id,
                billing_period=current_month,
                type="Rent",
                amount=lease.rent_amount,
                amount_paid=0,
                is_paid=False,
                created_by_id=current_user.id,
            )
            db.add(new_inv)
            generated += 1

    db.commit()
    return {
        "message": f"Successfully generated {generated} new rent invoices for {current_month.strftime('%B %Y')}."
    }


@router.get("/invoices/totals")
def get_invoice_totals(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("view_kpis"))
):
    """Get total pending and total collected amounts from all invoices."""
    from sqlalchemy import func
    
    # Total pending: sum of (amount - amount_paid) for unpaid invoices
    pending_result = db.query(
        func.sum(models.Invoice.amount - models.Invoice.amount_paid)
    ).filter(models.Invoice.is_paid == False).scalar()
    
    # Total collected: sum of amount_paid for paid invoices
    collected_result = db.query(
        func.sum(models.Invoice.amount_paid)
    ).filter(models.Invoice.is_paid == True).scalar()
    
    return {
        "total_pending": float(pending_result or 0),
        "total_collected": float(collected_result or 0)
    }


@router.get("/invoices")
def get_invoices(
    response: Response,
    page: int = 1,
    limit: int = 20,
    lease_id: int = None,
    is_paid: bool = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    offset = (page - 1) * limit

    query = db.query(models.Invoice)

    if lease_id:
        query = query.filter(models.Invoice.lease_id == lease_id)
    if is_paid is not None:
        query = query.filter(models.Invoice.is_paid == is_paid)

    # Get total count for pagination via Response header
    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    # Use eager loading to prevent N+1 query timeouts on large datasets (12k+ invoices)
    invoices = (
        query.options(
            joinedload(models.Invoice.lease).joinedload(models.Lease.tenant),
            joinedload(models.Invoice.lease)
            .joinedload(models.Lease.unit)
            .joinedload(models.Unit.property),
        )
        .order_by(models.Invoice.billing_period.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    lease_balances = {} # Cache balances for efficiency

    for inv in invoices:
        data = schemas.InvoiceOut.model_validate(inv).model_dump()
        data["amount_due"] = float(inv.amount) - float(inv.amount_paid)

        # Real-time tenant balance for the lease
        if inv.lease_id not in lease_balances:
            unpaid_total = db.query(func.sum(models.Invoice.amount - models.Invoice.amount_paid)).filter(
                models.Invoice.lease_id == inv.lease_id,
                models.Invoice.is_paid == False
            ).scalar()
            lease_balances[inv.lease_id] = float(unpaid_total) if unpaid_total else 0.0
        
        data["tenant_balance"] = lease_balances[inv.lease_id]

        if inv.lease:
            if inv.lease.tenant:
                data["tenant_name"] = inv.lease.tenant.full_name
            if inv.lease.unit:
                data["unit_number"] = inv.lease.unit.unit_number
                if inv.lease.unit.property:
                    data["property_name"] = inv.lease.unit.property.name
        result.append(data)
    return result


@router.post(
    "/invoices", response_model=schemas.InvoiceOut, status_code=status.HTTP_201_CREATED
)
def create_invoice(
    invoice: schemas.InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    new_invoice = models.Invoice(**invoice.model_dump())
    new_invoice.created_by_id = current_user.id
    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)

    # Reload with joined data so frontend parsing matches InvoiceOut
    inv = (
        db.query(models.Invoice)
        .options(
            joinedload(models.Invoice.lease).joinedload(models.Lease.tenant),
            joinedload(models.Invoice.lease)
            .joinedload(models.Lease.unit)
            .joinedload(models.Unit.property),
        )
        .filter(models.Invoice.id == new_invoice.id)
        .first()
    )

    data = schemas.InvoiceOut.model_validate(inv).model_dump()
    if inv.lease:
        if inv.lease.tenant:
            data["tenant_name"] = inv.lease.tenant.full_name
        if inv.lease.unit:
            data["unit_number"] = inv.lease.unit.unit_number
            if inv.lease.unit.property:
                data["property_name"] = inv.lease.unit.property.name
    return data


@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_200_OK)
def reverse_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    inv = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if inv.amount_paid and inv.amount_paid > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot reverse an invoice that currently has payments allocated to it.",
        )

    # Serialize old state before deletion
    old_state = {
        "id": inv.id,
        "lease_id": inv.lease_id,
        "type": inv.type,
        "amount": str(inv.amount),
        "billing_period": str(inv.billing_period),
    }
    db.delete(inv)

    # Manually Inject REVERSE AuditLog
    new_log = models.AuditLog(
        action="REVERSE_INVOICE",
        table_name="invoices",
        record_id=invoice_id,
        user_id=current_user.id,
        old_data=old_state,
        new_data=None,
    )
    db.add(new_log)
    db.commit()

    return {"message": "Invoice reversed successfully"}


# ==============================================================================
# BILL TYPES
# ==============================================================================


@router.get("/bill-types", response_model=List[schemas.BillTypeOut])
def get_bill_types(db: Session = Depends(get_db)):
    # Auto-seed defaults if table is completely empty
    count = db.query(models.BillType).count()
    if count == 0:
        defaults = [
            "Rent",
            "Water Bill",
            "Garbage Collection",
            "Security Fee",
            "Service Charge",
            "Power",
            "Rent Deposit",
            "Water Deposit",
        ]
        for d in defaults:
            db.add(models.BillType(name=d))
        db.commit()

    return db.query(models.BillType).order_by(models.BillType.name).all()


@router.post(
    "/bill-types",
    response_model=schemas.BillTypeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_bill_type(
    bill_type: schemas.BillTypeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    existing = (
        db.query(models.BillType)
        .filter(models.BillType.name.ilike(bill_type.name))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Bill type with this name already exists"
        )
    new_bt = models.BillType(name=bill_type.name)
    db.add(new_bt)
    db.commit()
    db.refresh(new_bt)
    return new_bt


@router.delete("/bill-types/{bt_id}")
def delete_bill_type(
    bt_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    bt = db.query(models.BillType).filter(models.BillType.id == bt_id).first()
    if not bt:
        raise HTTPException(status_code=404, detail="Bill type not found")

    # Check if invoices use this type string (they store the strict string natively)
    in_use = db.query(models.Invoice).filter(models.Invoice.type == bt.name).first()
    if in_use:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete this bill type because it is actively used in existing invoices.",
        )

    db.delete(bt)
    db.commit()
    return {"message": "Bill type deleted"}


# ==============================================================================
# PAYMENTS
# ==============================================================================
@router.get("/payments", response_model=List[schemas.PaymentOut])
def get_payments(
    response: Response,
    page: int = 1,
    limit: int = 50,
    lease_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("payments")),
):
    offset = (page - 1) * limit

    query = db.query(models.Payment)
    if lease_id:
        query = query.filter(models.Payment.lease_id == lease_id)

    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    payments = (
        query.options(
            joinedload(models.Payment.lease).joinedload(models.Lease.tenant),
            joinedload(models.Payment.lease)
            .joinedload(models.Lease.unit)
            .joinedload(models.Unit.property),
        )
        .order_by(models.Payment.payment_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Enhance payments with lease details
    enhanced_payments = []
    for p in payments:
        pd = schemas.PaymentOut.model_validate(p).model_dump()

        if p.lease:
            if p.lease.tenant:
                pd["tenant_name"] = p.lease.tenant.full_name
            if p.lease.unit:
                pd["unit_number"] = p.lease.unit.unit_number
                if p.lease.unit.property:
                    pd["property_name"] = p.lease.unit.property.name

        enhanced_payments.append(pd)

    return enhanced_payments


@router.post(
    "/payments", response_model=schemas.PaymentOut, status_code=status.HTTP_201_CREATED
)
def create_payment(
    payment: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role(["super_admin", "admin", "tenant"])
    ),
):
    # Explicit uniqueness check for Payment Reference
    if payment.reference_number:
        existing_payment = (
            db.query(models.Payment)
            .filter(models.Payment.reference_number == payment.reference_number)
            .first()
        )
        if existing_payment:
            raise HTTPException(
                status_code=400, detail=f"Payment reference '{payment.reference_number}' has already been used."
            )

    # record the base payment record
    new_payment = models.Payment(**payment.model_dump())
    new_payment.created_by_id = current_user.id
    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)

    # --------------------------------------------------------------------------
    # CHRONOLOGICAL (FIFO) ALLOCATION
    # --------------------------------------------------------------------------
    # Find all unpaid invoices for this lease, ordered by billing period (oldest first)
    amount_to_allocate = float(payment.amount)
    unpaid_invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.lease_id == payment.lease_id, models.Invoice.is_paid == False)
        .order_by(models.Invoice.billing_period.asc())
        .all()
    )

    for inv in unpaid_invoices:
        if amount_to_allocate <= 0:
            break

        current_balance = float(inv.amount) - float(inv.amount_paid)
        
        if amount_to_allocate >= current_balance:
            # Fully pay this invoice
            inv.amount_paid = float(inv.amount)
            inv.is_paid = True
            amount_to_allocate -= current_balance
        else:
            # Partially pay this invoice
            inv.amount_paid = float(inv.amount_paid) + amount_to_allocate
            amount_to_allocate = 0

    db.commit()
    db.refresh(new_payment)
    return new_payment


@router.post(
    "/payments/bulk", status_code=status.HTTP_201_CREATED
)
def create_bulk_payment(
    bulk_payment: schemas.BulkPaymentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role(["super_admin", "admin"])
    ),
):
    # Explicit uniqueness check for Payment Reference across ALL chunks
    if bulk_payment.reference_number:
        existing_payment = (
            db.query(models.Payment)
            .filter(models.Payment.reference_number == bulk_payment.reference_number)
            .first()
        )
        if existing_payment:
            raise HTTPException(
                status_code=400, detail=f"Payment reference '{bulk_payment.reference_number}' has already been used."
            )

    created_payments = []

    for alloc in bulk_payment.allocations:
        if alloc.amount <= 0:
            continue
            
        new_payment = models.Payment(
            lease_id=alloc.lease_id,
            amount=alloc.amount,
            payment_method=bulk_payment.payment_method,
            reference_number=bulk_payment.reference_number,
            created_by_id=current_user.id
        )
        db.add(new_payment)
        
        # Chronological allocation for this specific lease
        amount_to_allocate = float(alloc.amount)
        unpaid_invoices = (
            db.query(models.Invoice)
            .filter(models.Invoice.lease_id == alloc.lease_id, models.Invoice.is_paid == False)
            .order_by(models.Invoice.billing_period.asc())
            .all()
        )

        for inv in unpaid_invoices:
            if amount_to_allocate <= 0:
                break

            current_balance = float(inv.amount) - float(inv.amount_paid)
            
            if amount_to_allocate >= current_balance:
                inv.amount_paid = float(inv.amount)
                inv.is_paid = True
                amount_to_allocate -= current_balance
            else:
                inv.amount_paid = float(inv.amount_paid) + amount_to_allocate
                amount_to_allocate = 0

        created_payments.append(new_payment)

    db.commit()
    return {"message": "Bulk payment allocated successfully", "count": len(created_payments)}


# --- Meter Readings ---


@router.get("/meter-readings", response_model=List[schemas.MeterReadingOut])
def get_meter_readings(
    response: Response,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("meter_readings")),
):
    offset = (page - 1) * limit
    total_count = db.query(models.MeterReading).count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    readings = (
        db.query(models.MeterReading)
        .options(
            joinedload(models.MeterReading.unit).joinedload(models.Unit.property),
            joinedload(models.MeterReading.unit)
            .joinedload(models.Unit.leases)
            .joinedload(models.Lease.tenant),
        )
        .order_by(models.MeterReading.reading_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    enhanced_readings = []
    for r in readings:
        rd = schemas.MeterReadingOut.model_validate(r).model_dump()
        if r.unit:
            rd["unit_number"] = r.unit.unit_number
            if r.unit.property:
                rd["property_name"] = r.unit.property.name

            # Find the active lease from the joined leases
            active_lease = next(
                (l for l in r.unit.leases if l.status == "ACTIVE"), None
            )
            if active_lease and active_lease.tenant:
                rd["tenant_name"] = active_lease.tenant.full_name

        enhanced_readings.append(rd)

    return enhanced_readings


@router.post(
    "/meter-readings",
    response_model=schemas.MeterReadingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_meter_reading(
    reading: schemas.MeterReadingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    new_reading = models.MeterReading(**reading.model_dump())
    new_reading.created_by_id = current_user.id
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    return new_reading


# ==============================================================================
# EXPENDITURES
# ==============================================================================
@router.get("/expenditures", response_model=List[schemas.ExpenditureOut])
def get_expenditures(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("expenditures")),
):
    expenditures = (
        db.query(models.Expenditure)
        .options(joinedload(models.Expenditure.property))
        .all()
    )
    result = []
    for exp in expenditures:
        data = {
            "id": exp.id,
            "property_id": exp.property_id,
            "notes": exp.notes,
            "category": exp.category,
            "amount": exp.amount,
            "date": exp.date,
            "property_name": exp.property.name if exp.property else None,
        }
        result.append(data)
    return result


@router.post(
    "/expenditures",
    response_model=schemas.ExpenditureOut,
    status_code=status.HTTP_201_CREATED,
)
def create_expenditure(
    expenditure: schemas.ExpenditureCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):

    new_expenditure = models.Expenditure(**expenditure.model_dump())
    new_expenditure.created_by_id = current_user.id
    db.add(new_expenditure)
    db.commit()
    db.refresh(new_expenditure)

    data = schemas.ExpenditureOut.model_validate(new_expenditure)
    data.property_name = (
        new_expenditure.property.name if new_expenditure.property else None
    )
    return data


# ==============================================================================
# LANDLORD REMITTANCES
# ==============================================================================
@router.get("/landlord-remittances", response_model=List[schemas.LandlordRemittanceOut])
def get_landlord_remittances(
    response: Response,
    page: int = 1,
    limit: int = 50,
    landlord_id: int = None,
    property_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("landlord_remittances")),
):
    offset = (page - 1) * limit

    query = db.query(models.LandlordRemittance)
    if landlord_id:
        query = query.filter(models.LandlordRemittance.landlord_id == landlord_id)
    if property_id:
        query = query.filter(models.LandlordRemittance.property_id == property_id)

    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    remittances = (
        query.options(
            joinedload(models.LandlordRemittance.landlord),
            joinedload(models.LandlordRemittance.property),
        )
        .order_by(models.LandlordRemittance.date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for rem in remittances:
        data = schemas.LandlordRemittanceOut.model_validate(rem).model_dump()
        if rem.landlord:
            data["landlord_name"] = rem.landlord.name
        if rem.property:
            data["property_name"] = rem.property.name
        result.append(data)
    return result


@router.post(
    "/landlord-remittances",
    response_model=schemas.LandlordRemittanceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_landlord_remittance(
    remittance: schemas.LandlordRemittanceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):

    new_remittance = models.LandlordRemittance(**remittance.model_dump())
    new_remittance.created_by_id = current_user.id
    db.add(new_remittance)
    db.commit()
    db.refresh(new_remittance)

    data = schemas.LandlordRemittanceOut.model_validate(new_remittance)
    data.landlord_name = (
        new_remittance.landlord.name if new_remittance.landlord else None
    )
    data.property_name = (
        new_remittance.property.name if new_remittance.property else None
    )
    return data


@router.delete("/landlord-remittances/{remittance_id}", status_code=status.HTTP_200_OK)
def delete_landlord_remittance(
    remittance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    remittance = (
        db.query(models.LandlordRemittance)
        .filter(models.LandlordRemittance.id == remittance_id)
        .first()
    )
    if not remittance:
        raise HTTPException(status_code=404, detail="Landlord remittance not found")

    db.delete(remittance)
    db.commit()
    return {"message": "Landlord remittance deleted successfully"}


# ==============================================================================
# BANK TRANSACTIONS
# ==============================================================================
@router.get("/bank-transactions", response_model=List[schemas.BankTransactionOut])
def get_bank_transactions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("bank_transactions")),
):
    transactions = (
        db.query(models.BankTransaction)
        .order_by(models.BankTransaction.date.desc())
        .all()
    )
    return transactions


@router.post(
    "/bank-transactions",
    response_model=schemas.BankTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_bank_transaction(
    transaction: schemas.BankTransactionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):

    new_tx = models.BankTransaction(**transaction.model_dump())
    new_tx.created_by_id = current_user.id
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)
    return new_tx


@router.delete("/bank-transactions/{tx_id}")
def delete_bank_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    tx = (
        db.query(models.BankTransaction)
        .filter(models.BankTransaction.id == tx_id)
        .first()
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    db.delete(tx)
    db.commit()
    return {"message": "Transaction deleted successfully"}


# ==============================================================================
# REPORTING & STATEMENTS
# ==============================================================================
@router.get("/tenant-bills")
def get_tenant_bills(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["tenant"])),
):
    # Find active leases for this tenant user
    # Note: Tenant model has national_id and phone, but User model has email.
    # In a full system, User and Tenant would be strictly linked.
    # For now, we assume tenant_user.id is used directly or query all invoices if they want to see them all.
    # We will just fetch invoices where lease.tenant corresponds to current user (fallback to returning testing data if None)

    tenant = (
        db.query(models.Tenant)
        .filter(models.Tenant.email == current_user.email)
        .first()
    )

    invoices = []
    if tenant:
        invoices = (
            db.query(models.Invoice)
            .join(models.Lease)
            .filter(models.Lease.tenant_id == tenant.id)
            .order_by(models.Invoice.billing_period.desc())
            .all()
        )
    else:
        invoices = (
            db.query(models.Invoice)
            .order_by(models.Invoice.billing_period.desc())
            .limit(20)
            .all()
        )  # Fallback for demo

    result = []
    for inv in invoices:
        result.append(
            {
                "id": inv.id,
                "type": inv.type,
                "amount": float(inv.amount),
                "date": str(inv.billing_period),
                "is_paid": inv.is_paid,
            }
        )
    return result


@router.get("/landlord-statements")
def get_landlord_statements(
    year: int = None,
    month: int = None,
    landlord_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("landlord_statements")),
):
    """Get landlord statements with optional time-based filtering.
    
    Args:
        year: Filter by specific year (e.g., 2026)
        month: Filter by specific month (1-12)
        landlord_id: Filter by specific landlord
    """
    from sqlalchemy import func, extract
    from datetime import datetime
    
    # Build base query for properties
    prop_query = db.query(models.Property).options(joinedload(models.Property.landlord))
    if landlord_id:
        prop_query = prop_query.filter(models.Property.landlord_id == landlord_id)
    properties = prop_query.all()
    
    # Get all property IDs
    property_ids = [prop.id for prop in properties]
    
    # Build invoice aggregate query with time filtering
    invoice_query = (
        db.query(
            models.Unit.property_id,
            func.sum(models.Invoice.amount_paid).label('total_collected')
        )
        .join(models.Lease, models.Lease.id == models.Invoice.lease_id)
        .join(models.Unit, models.Unit.id == models.Lease.unit_id)
        .filter(models.Unit.property_id.in_(property_ids), models.Invoice.is_paid == True)
    )
    
    # Build expenditure aggregate query with time filtering
    expense_query = (
        db.query(
            models.Expenditure.property_id,
            func.sum(models.Expenditure.amount).label('total_expenses')
        )
        .filter(models.Expenditure.property_id.in_(property_ids))
    )
    
    # Build remittance aggregate query with time filtering
    remittance_query = (
        db.query(
            models.LandlordRemittance.property_id,
            func.sum(models.LandlordRemittance.amount).label('total_remitted')
        )
        .filter(models.LandlordRemittance.property_id.in_(property_ids))
    )
    
    # Apply time filters if provided
    if year:
        invoice_query = invoice_query.filter(
            extract('year', models.Invoice.billing_period) == year
        )
        expense_query = expense_query.filter(
            extract('year', models.Expenditure.date) == year
        )
        remittance_query = remittance_query.filter(
            extract('year', models.LandlordRemittance.date) == year
        )
    
    if month:
        invoice_query = invoice_query.filter(
            extract('month', models.Invoice.billing_period) == month
        )
        expense_query = expense_query.filter(
            extract('month', models.Expenditure.date) == month
        )
        remittance_query = remittance_query.filter(
            extract('month', models.LandlordRemittance.date) == month
        )
    
    # Group by property_id
    invoice_query = invoice_query.group_by(models.Unit.property_id)
    expense_query = expense_query.group_by(models.Expenditure.property_id)
    remittance_query = remittance_query.group_by(models.LandlordRemittance.property_id)
    
    # Execute queries and create lookup dictionaries
    invoice_results = {row.property_id: float(row.total_collected or 0) for row in invoice_query.all()}
    expense_results = {row.property_id: float(row.total_expenses or 0) for row in expense_query.all()}
    remittance_results = {row.property_id: float(row.total_remitted or 0) for row in remittance_query.all()}
    
    # Format period string
    if year and month:
        period_str = datetime(year, month, 1).strftime("%B %Y")
    elif year:
        period_str = f"Year {year}"
    else:
        period_str = "ALL TIME SUMMARY"
    
    statements = []
    for prop in properties:
        total_collected = invoice_results.get(prop.id, 0)
        total_expenses = expense_results.get(prop.id, 0)
        management_fee = total_collected * 0.10  # 10% commission
        net_remittance = total_collected - management_fee - total_expenses
        total_remitted = remittance_results.get(prop.id, 0)

        status = (
            "Paid"
            if total_remitted >= net_remittance and total_remitted > 0
            else ("Pending" if net_remittance > 0 else "Cleared")
        )

        statements.append(
            {
                "id": prop.id,
                "property_name": prop.name,
                "period": period_str,
                "total_collected": total_collected,
                "management_fee": management_fee,
                "expenses": total_expenses,
                "net_remittance": net_remittance,
                "status": status,
                "year": year,
                "month": month,
            }
        )

    return statements


@router.get("/landlord-statements/periods")
def get_available_periods(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get all available periods (year/month combinations) with data."""
    from sqlalchemy import extract, func
    
    # Get distinct year/month combinations from invoices
    invoice_periods = (
        db.query(
            extract('year', models.Invoice.billing_period).label('year'),
            extract('month', models.Invoice.billing_period).label('month')
        )
        .filter(models.Invoice.is_paid == True)
        .distinct()
        .all()
    )
    
    # Get distinct year/month combinations from expenditures
    expense_periods = (
        db.query(
            extract('year', models.Expenditure.date).label('year'),
            extract('month', models.Expenditure.date).label('month')
        )
        .distinct()
        .all()
    )
    
    # Combine and deduplicate periods
    all_periods = set()
    for period in invoice_periods:
        if period.year and period.month:
            all_periods.add((int(period.year), int(period.month)))
    for period in expense_periods:
        if period.year and period.month:
            all_periods.add((int(period.year), int(period.month)))
    
    # Sort by year and month (newest first)
    sorted_periods = sorted(all_periods, reverse=True)
    
    # Format for response
    result = []
    for year, month in sorted_periods:
        result.append({
            "year": year,
            "month": month,
            "label": datetime(year, month, 1).strftime("%B %Y")
        })
    
    return result


# ==============================================================================
# AUDIT TRAIL
# ==============================================================================
@router.get("/audit-logs")
def get_audit_logs(
    response: Response,
    page: int = 1,
    limit: int = 20,
    search: str = None,
    table_filter: str = "all",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("audit_logs")),
):
    offset = (page - 1) * limit
    query = db.query(models.AuditLog).options(joinedload(models.AuditLog.user))

    if table_filter and table_filter.lower() != "all":
        query = query.filter(models.AuditLog.table_name == table_filter)

    if search:
        search_filter = f"%{search}%"
        # Use the relationship for joining to ensure consistency with joinedload
        query = query.outerjoin(models.AuditLog.user).filter(
            (models.AuditLog.action.ilike(search_filter))
            | (models.AuditLog.table_name.ilike(search_filter))
            | (models.User.email.ilike(search_filter))
        )

    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    logs = (
        query.order_by(models.AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for log in logs:
        result.append(
            {
                "id": log.id,
                "action": log.action,
                "table_name": log.table_name,
                "record_id": log.record_id,
                "old_data": log.old_data,
                "new_data": log.new_data,
                "timestamp": str(log.timestamp),
                "user_name": log.user.name if log.user else "System",
                "user_email": log.user.email if log.user else "System",
                "user_role": log.user.role if log.user else "System",
            }
        )
    return result
