import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Union

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext
from jose import jwt
from jose.exceptions import JWTError

from utils.firebase import get_db
from google.cloud.firestore import Client as FirestoreClient, FieldFilter
from models import User, gen_uuid, now_utc

# ─── JWT settings ───────────────────────────────────────────────────────────────
SECRET_KEY       = os.getenv("SECRET_KEY", "changeme")
ALGORITHM        = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_MIN = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
router  = APIRouter()

bearer_scheme = HTTPBearer()


# ─── Pydantic schemas ────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    email:    EmailStr
    username: str
    password: str = Field(..., min_length=6)
    birthday: Optional[datetime] = None
    avatar:   Optional[str]      = None

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"

class Me(BaseModel):
    user_id:    str
    email:      EmailStr
    username:   str
    birthday:   Optional[datetime] = None
    avatar:     Optional[str]     = None
    created_at: datetime
    last_login: datetime


# ─── Utility functions ─────────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    return pwd_ctx.hash(pw)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_jwt(user_id: str) -> str:
    expire  = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MIN)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_user_by_email(
    db:    FirestoreClient,
    email: Union[str, EmailStr],
) -> Tuple[Optional[str], Optional[dict]]:
    """
    Returns (user_id, user_dict) if a user with that email exists, else (None, None).
    """
    snaps = (
        db.collection("users")
          .where(
             filter=FieldFilter("email", "==", str(email))
          )
          .stream()
    )
    for doc in snaps:
        data = doc.to_dict()
        data["user_id"] = doc.id
        return doc.id, data
    return None, None


# ─── POST /auth/register ───────────────────────────────────────────────────────
@router.post("/register", response_model=Me, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    db:      FirestoreClient = Depends(get_db),
):
    existing_id, _ = get_user_by_email(db, payload.email)
    if existing_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")

    now = now_utc()
    user = User(
        user_id          = gen_uuid(),
        email            = payload.email,
        password         = hash_password(payload.password),
        username         = payload.username,
        birthday         = payload.birthday,
        avatar           = payload.avatar,
        created_at       = now,
        last_login       = now,
        friends          = [],
        created_novels   = [],
        saved_novels     = [],
        completed_novels = [],
    )
    db.collection("users").document(user.user_id).set(user.model_dump())
    return Me(**user.model_dump())


# ─── POST /auth/login ──────────────────────────────────────────────────────────
@router.post("/login", response_model=Token)
async def login(
    payload: LoginRequest,
    db:      FirestoreClient = Depends(get_db),
):
    user_id, data = get_user_by_email(db, payload.email)
    if not data or not verify_password(payload.password, data["password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    db.collection("users").document(user_id).update({"last_login": now_utc()})
    return Token(access_token=create_jwt(user_id))


# ─── Dependency: get_current_user ───────────────────────────────────────────────
async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db:    FirestoreClient             = Depends(get_db),
) -> User:
    token = creds.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid  = payload.get("sub")
        if not uid:
            raise HTTPException(401, "Invalid token")
    except JWTError:
        raise HTTPException(401, "Invalid token")
    doc = db.collection("users").document(uid).get()
    if not doc.exists:
        raise HTTPException(401, "User not found")
    return User.model_validate(doc.to_dict())

@router.get("/me", response_model=Me)
async def me(current: User = Depends(get_current_user)):
    return Me(**current.model_dump())
