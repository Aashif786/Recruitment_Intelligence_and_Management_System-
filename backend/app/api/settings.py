from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.infrastructure.database import get_db
from app.domain.models import GlobalSettings, User
from app.domain.schemas import GlobalSettingsUpdate, GlobalSettingsResponse
from app.core.auth import get_current_hr

router = APIRouter(prefix="/api/settings", tags=["settings"])


def ensure_global_settings_table(db: Session) -> None:
    """Create the settings table on demand for legacy databases."""
    GlobalSettings.__table__.create(bind=db.get_bind(), checkfirst=True)


@router.get("", response_model=GlobalSettingsResponse)
def get_settings(
    db: Session = Depends(get_db)
):
    """Fetch global settings (public - used for branding on login/register pages)."""
    ensure_global_settings_table(db)
    settings_records = db.query(GlobalSettings).all()
    settings_dict = {s.key: s.value for s in settings_records}
    
    return {
        "company_logo_url": settings_dict.get("company_logo_url", ""),
        "company_name": settings_dict.get("company_name", ""),
        "company_address": settings_dict.get("company_address", ""),
        "hr_email": settings_dict.get("hr_email", ""),
        "hr_name": settings_dict.get("hr_name", ""),
        "hr_phone": settings_dict.get("hr_phone", ""),
        "offer_letter_template": settings_dict.get("offer_letter_template", "")
    }

@router.post("", response_model=GlobalSettingsResponse)
def update_settings(
    settings_data: GlobalSettingsUpdate,
    current_user: User = Depends(get_current_hr),
    db: Session = Depends(get_db)
):
    """Update global settings (HR only)."""
    ensure_global_settings_table(db)
    data = settings_data.model_dump(exclude_unset=True)
    
    for key, value in data.items():
        if value is None:
            continue
            
        setting = db.query(GlobalSettings).filter(GlobalSettings.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = GlobalSettings(key=key, value=value)
            db.add(setting)
            
    db.commit()
    
    # Return updated settings
    return get_settings(db=db)
