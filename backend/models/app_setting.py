from sqlalchemy import Column, String
from database import Base

class AppSetting(Base):
    """Key/value store for runtime-configurable settings (DB-backed, works on read-only filesystems)."""
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String)
