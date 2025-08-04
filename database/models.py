from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union

@dataclass
class User:
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    language: str
    balance: int
    free_service_used: bool
    promocode_used: Optional[str]
    created_at: Union[datetime, str]
    updated_at: Union[datetime, str]

@dataclass
class Payment:
    id: int
    user_id: int
    amount: int
    status: str  # pending, approved, rejected
    screenshot_file_id: Optional[str]
    created_at: datetime
    updated_at: datetime

@dataclass
class Channel:
    id: int
    channel_id: str
    channel_username: str
    title: str
    is_active: bool
    created_at: datetime

@dataclass
class Promocode:
    id: int
    code: str
    is_active: bool
    expires_at: datetime
    created_at: datetime

@dataclass
class UsedPromocode:
    id: int
    user_id: int
    promocode_id: int
    used_at: datetime

@dataclass
class DocumentOrder:
    id: int
    user_id: int
    document_type: str  # presentation, independent_work, referat
    topic: str
    specifications: str  # JSON with slide count, page count, etc.
    file_path: Optional[str]
    status: str  # generating, completed, failed
    created_at: datetime
    completed_at: Optional[datetime]

@dataclass
class BroadcastMessage:
    id: int
    message_text: str
    message_type: str  # text, photo, document
    file_id: Optional[str]
    target_audience: str  # all, active, custom
    sent_count: int
    failed_count: int
    created_at: datetime
    sent_at: Optional[datetime]
