from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal, Dict
from datetime import datetime, timezone
import uuid
from enum import Enum

def gen_uuid() -> str:
    return str(uuid.uuid4())

def now_utc() -> datetime:
    """Возвращает текущий момент в UTC с tzinfo."""
    return datetime.now(timezone.utc)

class Genre(str, Enum):
    horror = "horror"
    drama = "drama"
    tragedy = "tragedy"
    comedy = "comedy"
    romance = "romance"
    fantasy = "fantasy"
    science_fiction = "science_fiction"
    mystery = "mystery"
    thriller = "thriller"
    historical = "historical"
    adventure = "adventure"
    slice_of_life = "slice_of_life"
    dystopian = "dystopian"
    magical_realism = "magical_realism"
    steampunk = "steampunk"
    noir = "noir"
    crime = "crime"
    young_adult = "young_adult"
    biography = "biography"

class NovelCreate(BaseModel):
    genres:      List[Genre]
    title:       Optional[str] = None
    description: Optional[str] = None
    setting:     Optional[str] = None
    is_public:   Optional[bool]  = False

class Novel(BaseModel):
    # ——— Метаданные Новеллы ———
    novel_id:          str = Field(default_factory=gen_uuid)
    novel_original_id: Optional[str] = None
    users_author:      List[str] = Field(default_factory=list)
    user_players:      List[str] = Field(default_factory=list)
    title:             str
    description:       str
    genres: List[Genre] = Field(default_factory=list)
    setting:           str
    created_at:        datetime          = Field(default_factory=now_utc)
    updated_at:        datetime          = Field(default_factory=now_utc)
    is_public:         bool = False
    cover_image_url: Optional[str] = None #ссылка на изображение новеллы

    # ——— Поля «статуса» в рамках этой копии новеллы ———
    state:            Literal["in_progress", "planned", "completed", "abandoned"] = "planned"
    current_position: Optional[str]   = None  # checkpoint-id или офсет
    ended_at:         Optional[datetime] = None  # когда state=="completed"

class Character(BaseModel):
    character_id: str = Field(default_factory=gen_uuid)
    novel_id:     str
    user_id:      Optional[str] = None                   # заполнено только у игровых персонажей
    role:         Literal["player", "npc"]
    name:         str
    appearance:   str                                    # внешний вид
    backstory:    str                                    # пред-история
    traits:       str                                    # Дополнительные черты, привычки или предпочтения персонажа в виде одной строки

Status = Literal["in_progress", "planned", "completed", "favorite", "abandoned"]

class User(BaseModel):
    user_id:          str = Field(default_factory=gen_uuid)
    email:            EmailStr
    password: str
    username:         str
    birthday:         Optional[datetime] = None
    avatar:           Optional[str]      = None
    created_at:     datetime           = Field(default_factory=now_utc)
    last_login:     datetime           = Field(default_factory=now_utc)
    friends:          List[str]          = Field(default_factory=list)  # Список друзей [user_id]
    created_novels:   List[str]          = Field(default_factory=list)  # Созданные пользователем новеллы
    playing_novels: List[str] = Field(default_factory=list) # Играю
    planned_novels:     List[str]          = Field(default_factory=list)  # В планах
    completed_novels: List[str]          = Field(default_factory=list)  # Закончено/Пройдено
    favorite_novels: List[str] = Field(default_factory=list) # Любимые
    abandoned_novels: List[str] = Field(default_factory=list) # Брошено

StatusFilter = Literal["all", "created", "playing", "planned", "completed", "favorite", "abandoned"]

class Multiplayer(BaseModel):
    session_id:    str                 = Field(default_factory=gen_uuid)
    host_id:       str                 # user_id хозяина сессии
    novel_id:      str                 # к какой новелле привязана сессия
    players: Dict[str, str] = Field(default_factory=dict)
    chat_messages: List[Dict[str, str]] = Field(default_factory=list) # [{"user_id":..., "msg":..., "time":...}, …]
    started_at:    datetime                = Field(default_factory=now_utc)
    ended_at:      Optional[datetime]  = None

# Модель “Choice” и в БД храним поддокумент choices/{choice_id}
class Choice(BaseModel):
    choice_id:   str = Field(default_factory=lambda: str(uuid.uuid4()))
    proposer_id: Optional[str]  # user_id игрока или None для ИИ
    content:     str
    created_at:  datetime = Field(default_factory=now_utc)

class MultiplayerSession(BaseModel):
    session_id:  str                 = Field(default_factory=gen_uuid)
    host_id:     str                 # user_id хозяина сессии
    novel_id:    str

    invited:     List[str]           = Field(default_factory=list)
    players:     Dict[str, Optional[str]] = Field(default_factory=dict)
    votes:       Dict[str, str]      = Field(default_factory=dict)
    chat:        List[Dict[str, str]]= Field(default_factory=list)
    choices:     Dict[str, Choice]   = Field(default_factory=dict)

    started_at:  datetime            = Field(default_factory=now_utc)
    ended_at:    Optional[datetime]  = None

class TextSegment(BaseModel):
    segment_id: str
    author_id:  Optional[str] = None
    content:    str
    created_at: datetime

class TextEdit(BaseModel):
    content: str