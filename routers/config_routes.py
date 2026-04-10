from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
import models, schemas, auth
from database import get_db

router = APIRouter(prefix="/config", tags=["config"])


# --- System Settings ---
@router.get("/settings", response_model=List[schemas.SystemSettingOut])
def get_system_settings(
    db: Session = Depends(get_db)
):
    settings = db.query(models.SystemSetting).all()
    # Default to VictorSprings if not found
    if not any(s.setting_key == 'system_name' for s in settings):
        default_name = models.SystemSetting(setting_key='system_name', setting_value='VictorSprings')
        db.add(default_name)
        db.commit()
        db.refresh(default_name)
        settings.append(default_name)
    return settings

@router.put("/settings/{setting_key}", response_model=schemas.SystemSettingOut)
def update_system_setting(
    setting_key: str,
    setting_data: schemas.SystemSettingUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin"])),
):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.setting_key == setting_key).first()
    if not setting:
        setting = models.SystemSetting(setting_key=setting_key)
        db.add(setting)
    
    setting.setting_value = setting_data.setting_value
    setting.updated_by_id = current_user.id
    db.commit()
    db.refresh(setting)
    return setting


# --- Attributes ---
@router.get("/attributes", response_model=List[schemas.AttributeOut])
def get_attributes(
    response: Response,
    page: int = 1,
    limit: int = 20,
    search: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.Attribute)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(models.Attribute.name.ilike(search_filter))

    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    offset = (page - 1) * limit
    attributes = query.order_by(models.Attribute.name).offset(offset).limit(limit).all()
    return attributes


@router.post(
    "/attributes",
    response_model=schemas.AttributeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_attribute(
    attr: schemas.AttributeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    new_attr = models.Attribute(**attr.model_dump())
    new_attr.created_by_id = current_user.id
    db.add(new_attr)
    db.commit()
    db.refresh(new_attr)
    return new_attr


@router.put("/attributes/{attr_id}", response_model=schemas.AttributeOut)
def update_attribute(
    attr_id: int,
    attr_data: schemas.AttributeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    attr = db.query(models.Attribute).filter(models.Attribute.id == attr_id).first()
    if not attr:
        raise HTTPException(status_code=404, detail="Attribute not found")
    attr.name = attr_data.name
    attr.updated_by_id = current_user.id
    db.commit()
    db.refresh(attr)
    return attr


@router.delete("/attributes/{attr_id}")
def delete_attribute(
    attr_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    attr = db.query(models.Attribute).filter(models.Attribute.id == attr_id).first()
    if not attr:
        raise HTTPException(status_code=404, detail="Attribute not found")
    db.delete(attr)
    db.commit()
    return {"message": "Attribute deleted"}


# --- Expense Categories ---
@router.get("/expense-categories", response_model=List[schemas.ExpenseCategoryOut])
def get_expense_categories(
    response: Response,
    page: int = 1,
    limit: int = 20,
    search: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.ExpenseCategory)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(models.ExpenseCategory.name.ilike(search_filter))

    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    offset = (page - 1) * limit
    categories = (
        query.order_by(models.ExpenseCategory.name).offset(offset).limit(limit).all()
    )
    return categories


@router.post(
    "/expense-categories",
    response_model=schemas.ExpenseCategoryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_expense_category(
    cat: schemas.ExpenseCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    new_cat = models.ExpenseCategory(**cat.model_dump())
    new_cat.created_by_id = current_user.id
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    return new_cat


@router.put("/expense-categories/{cat_id}", response_model=schemas.ExpenseCategoryOut)
def update_expense_category(
    cat_id: int,
    cat_data: schemas.ExpenseCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    cat = (
        db.query(models.ExpenseCategory)
        .filter(models.ExpenseCategory.id == cat_id)
        .first()
    )
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat.name = cat_data.name
    cat.updated_by_id = current_user.id
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/expense-categories/{cat_id}")
def delete_expense_category(
    cat_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    cat = (
        db.query(models.ExpenseCategory)
        .filter(models.ExpenseCategory.id == cat_id)
        .first()
    )
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(cat)
    db.commit()
    return {"message": "Category deleted"}


# --- Bank Names ---
@router.get("/bank-names", response_model=List[schemas.BankNameOut])
def get_bank_names(
    response: Response,
    page: int = 1,
    limit: int = 20,
    search: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.BankName)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(models.BankName.name.ilike(search_filter))

    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    offset = (page - 1) * limit
    bank_names = query.order_by(models.BankName.name).offset(offset).limit(limit).all()
    return bank_names


@router.post(
    "/bank-names",
    response_model=schemas.BankNameOut,
    status_code=status.HTTP_201_CREATED,
)
def create_bank_name(
    bn: schemas.BankNameCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    new_bn = models.BankName(**bn.model_dump())
    new_bn.created_by_id = current_user.id
    db.add(new_bn)
    db.commit()
    db.refresh(new_bn)
    return new_bn


@router.put("/bank-names/{bn_id}", response_model=schemas.BankNameOut)
def update_bank_name(
    bn_id: int,
    bn_data: schemas.BankNameCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    bn = db.query(models.BankName).filter(models.BankName.id == bn_id).first()
    if not bn:
        raise HTTPException(status_code=404, detail="Bank name not found")
    bn.name = bn_data.name
    bn.updated_by_id = current_user.id
    db.commit()
    db.refresh(bn)
    return bn


@router.delete("/bank-names/{bn_id}")
def delete_bank_name(
    bn_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    bn = db.query(models.BankName).filter(models.BankName.id == bn_id).first()
    if not bn:
        raise HTTPException(status_code=404, detail="Bank name not found")
    db.delete(bn)
    db.commit()
    return {"message": "Bank name deleted"}


# --- Banks ---
@router.get("/banks", response_model=List[schemas.BankOut])
def get_banks(
    response: Response,
    page: int = 1,
    limit: int = 20,
    search: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.Bank).options(joinedload(models.Bank.bank_name))

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (models.Bank.name.ilike(search_filter))
            | (models.Bank.branch_name.ilike(search_filter))
            | (models.Bank.account_number.ilike(search_filter))
        )

    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    offset = (page - 1) * limit
    banks = query.order_by(models.Bank.name).offset(offset).limit(limit).all()

    result = []
    for bank in banks:
        data = schemas.BankOut.model_validate(bank).model_dump()
        data["bank_name"] = bank.bank_name.name if bank.bank_name else None
        result.append(data)
    return result


@router.post(
    "/banks", response_model=schemas.BankOut, status_code=status.HTTP_201_CREATED
)
def create_bank(
    bank: schemas.BankCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    new_bank = models.Bank(**bank.model_dump())
    new_bank.created_by_id = current_user.id
    db.add(new_bank)
    db.commit()
    db.refresh(new_bank)

    # Return with bank name
    data = schemas.BankOut.model_validate(new_bank).model_dump()
    data["bank_name"] = new_bank.bank_name.name if new_bank.bank_name else None
    return data


@router.put("/banks/{bank_id}", response_model=schemas.BankOut)
def update_bank(
    bank_id: int,
    bank_data: schemas.BankCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    bank = db.query(models.Bank).filter(models.Bank.id == bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")

    for key, value in bank_data.model_dump().items():
        setattr(bank, key, value)
    bank.updated_by_id = current_user.id

    db.commit()
    db.refresh(bank)

    data = schemas.BankOut.model_validate(bank).model_dump()
    data["bank_name"] = bank.bank_name.name if bank.bank_name else None
    return data


@router.delete("/banks/{bank_id}")
def delete_bank(
    bank_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    bank = db.query(models.Bank).filter(models.Bank.id == bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")
    db.delete(bank)
    db.commit()
    return {"message": "Bank deleted"}
