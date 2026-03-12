"""SQLAlchemy ORM model for users."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone_number = Column(String(30), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # One user owns many receipts; deleting a user cascades to their receipts.
    receipts = relationship("Receipt", back_populates="user", cascade="all, delete")
