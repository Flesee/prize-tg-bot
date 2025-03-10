import sqlalchemy as sa
from datetime import datetime
from typing import List, Optional

from .base import Base


class TelegramUser(Base):
    """Модель пользователя Telegram."""
    __tablename__ = "prizes_telegramuser"
    
    id = sa.Column(sa.Integer, primary_key=True)
    telegram_id = sa.Column(sa.BigInteger, unique=True, nullable=False)
    full_name = sa.Column(sa.String(255), nullable=False)
    username = sa.Column(sa.String(255), nullable=True)
    is_admin = sa.Column(sa.Boolean, default=False, nullable=False)
    created_at = sa.Column(sa.DateTime, nullable=False)
    updated_at = sa.Column(sa.DateTime, nullable=False)
    
    def __repr__(self):
        return f"<TelegramUser(id={self.id}, telegram_id={self.telegram_id}, full_name={self.full_name})>"
    
    def to_dict(self):
        """Преобразует объект модели в словарь."""
        return {
            "id": self.id,
            "telegram_id": self.telegram_id,
            "full_name": self.full_name,
            "username": self.username,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at
        }


class Prize(Base):
    """Модель розыгрыша."""
    __tablename__ = "prizes_prize"
    
    id = sa.Column(sa.Integer, primary_key=True)
    title = sa.Column(sa.String(255), nullable=False)
    image = sa.Column(sa.String(255), nullable=True)
    start_date = sa.Column(sa.DateTime, nullable=False)
    end_date = sa.Column(sa.DateTime, nullable=False)
    ticket_price = sa.Column(sa.Numeric(10, 2), nullable=False)
    ticket_count = sa.Column(sa.Integer, nullable=False, default=0)
    is_active = sa.Column(sa.Boolean, nullable=False, default=False)
    created_at = sa.Column(sa.DateTime, nullable=False)
    updated_at = sa.Column(sa.DateTime, nullable=False)
    chat_message_id = sa.Column(sa.BigInteger, nullable=True)
    
    # Отношения
    tickets = sa.orm.relationship("Ticket", back_populates="prize", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Prize(id={self.id}, title={self.title}, is_active={self.is_active})>"
    
    def to_dict(self):
        """Преобразует объект модели в словарь."""
        return {
            "id": self.id,
            "title": self.title,
            "image": self.image,
            "start_date": self.start_date.isoformat() if isinstance(self.start_date, datetime) else self.start_date,
            "end_date": self.end_date.isoformat() if isinstance(self.end_date, datetime) else self.end_date,
            "ticket_price": float(self.ticket_price) if self.ticket_price else None,
            "ticket_count": self.ticket_count,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at
        }
    
    def get_available_tickets(self) -> List[int]:
        """Возвращает список доступных (не зарезервированных и не купленных) билетов."""
        available_tickets = []
        for i in range(1, self.ticket_count + 1):
            ticket = next((t for t in self.tickets if t.ticket_number == i), None)
            if not ticket or (not ticket.is_reserved and not ticket.is_paid):
                available_tickets.append(i)
        return available_tickets


class Ticket(Base):
    """Модель билета."""
    __tablename__ = "prizes_ticket"
    
    id = sa.Column(sa.Integer, primary_key=True)
    prize_id = sa.Column(sa.Integer, sa.ForeignKey('prizes_prize.id'), nullable=False)
    user_id = sa.Column(sa.Integer, sa.ForeignKey('prizes_telegramuser.id'), nullable=True)
    ticket_number = sa.Column(sa.Integer, nullable=False)
    is_reserved = sa.Column(sa.Boolean, nullable=False, default=False)
    is_paid = sa.Column(sa.Boolean, nullable=False, default=False)
    reserved_until = sa.Column(sa.DateTime, nullable=True)
    payment_id = sa.Column(sa.String(255), nullable=True)
    created_at = sa.Column(sa.DateTime, nullable=False)
    updated_at = sa.Column(sa.DateTime, nullable=False)
    
    # Отношения
    prize = sa.orm.relationship("Prize", back_populates="tickets")
    user = sa.orm.relationship("TelegramUser")
    
    __table_args__ = (
        sa.UniqueConstraint('prize_id', 'ticket_number', name='uix_prize_ticket_number'),
    )
    
    def __repr__(self):
        return f"<Ticket(id={self.id}, prize_id={self.prize_id}, ticket_number={self.ticket_number})>"
    
    def to_dict(self):
        """Преобразует объект модели в словарь."""
        return {
            "id": self.id,
            "prize_id": self.prize_id,
            "user_id": self.user_id,
            "ticket_number": self.ticket_number,
            "is_reserved": self.is_reserved,
            "is_paid": self.is_paid,
            "reserved_until": self.reserved_until.isoformat() if isinstance(self.reserved_until, datetime) else self.reserved_until,
            "payment_id": self.payment_id,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at
        }


class FAQ(Base):
    """Модель для хранения единого текста FAQ."""
    __tablename__ = "prizes_faq"
    
    id = sa.Column(sa.Integer, primary_key=True)
    text = sa.Column(sa.Text, nullable=False)
    is_active = sa.Column(sa.Boolean, default=True, nullable=False)
    created_at = sa.Column(sa.DateTime, nullable=False)
    updated_at = sa.Column(sa.DateTime, nullable=False)
    
    def __repr__(self):
        return f"<FAQ(id={self.id})>"
    
    def to_dict(self):
        """Преобразует объект модели в словарь."""
        return {
            "id": self.id,
            "text": self.text,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at
        } 