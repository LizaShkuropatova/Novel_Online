from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
from models import gen_uuid, now_utc

class MultiplayerSession(BaseModel):
    session_id:    str                   = Field(default_factory=gen_uuid)
    host_id:       str
    novel_id:      str
    invited:       List[str]             = Field(default_factory=list)
    players:       Dict[str, Optional[str]] = Field(default_factory=dict)
    votes:         Dict[str, str]         = Field(default_factory=dict)
    chat:          List[Dict]             = Field(default_factory=list)
    started_at:    Optional[datetime]     = Field(default_factory=now_utc)
    ended_at:      Optional[datetime]     = None