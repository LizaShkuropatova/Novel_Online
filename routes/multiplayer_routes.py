from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response
from datetime import datetime, timezone
from typing import Dict, List, Optional
import random
from pydantic import BaseModel

from models import User, MultiplayerSession, Choice, now_utc
from utils.firebase import get_db
from google.cloud.firestore import Client as FirestoreClient

from routes.auth_routes import get_current_user
from firebase_admin import firestore  # for ArrayUnion, ArrayRemove
from routes.novel_routes import add_text_segment
from routes.novel_routes import TextEdit as NovelTextEdit


router = APIRouter()
MAX_PLAYERS = 4

class FriendInfo(BaseModel):
    user_id: str
    username: str
    avatar: Optional[str] = None

# Create a new session (на вход айди новеллы)
@router.post("/", response_model=MultiplayerSession, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: Dict[str, str],  # {"novel_id": ...}
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    novel_id = payload.get("novel_id")
    if not novel_id or not db.collection("novels").document(novel_id).get().exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Novel not found")

    # создаём объект сессии
    session = MultiplayerSession(
        host_id=current.user_id,
        novel_id=novel_id,
        # сразу добавляем хоста в players
        players={current.user_id: None}
    )
    db.collection("sessions").document(session.session_id).set(session.model_dump())
    return session

@router.get(
    "/{sid}/available_friends",
    response_model=List[User],
    summary="List your friends who are neither in the session nor already invited"
)
async def list_available_friends(
    sid: str,
    current_user: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    # Загружаем сессию
    snap = db.collection("sessions").document(sid).get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    sess = MultiplayerSession.model_validate(snap.to_dict())

    # Составляем множество всех user_id в сессии и уже приглашённых
    in_session = set(sess.players.keys())
    in_session.update(sess.invited)

    # Отфильтровываем друзей
    available_ids = [
        fid for fid in current_user.friends
        if fid not in in_session
    ]

    # Загружаем документы друзей из Firestore
    available: List[User] = []
    for fid in available_ids:
        user_snap = db.collection("users").document(fid).get()
        if not user_snap.exists:
            continue
        data = user_snap.to_dict()
        data["user_id"] = user_snap.id
        available.append(User.model_validate(data))

    return available

# Invite a player
@router.post("/{sid}/invite", status_code=status.HTTP_204_NO_CONTENT)
async def invite_player(
    sid: str,
    payload: Dict[str, str],  # {"user_id": ...}
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    user_to_invite = payload.get("user_id")
    if not user_to_invite:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Missing user_id")

    # Проверяем сессию
    ref = db.collection("sessions").document(sid)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    sess = MultiplayerSession.model_validate(snap.to_dict())

    # Только хост может приглашать
    if sess.host_id != current.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only host can invite")

    # Нельзя пригласить себя
    if user_to_invite == current.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot invite yourself")

    # Нельзя приглашать повторно или если уже в списке players
    if user_to_invite in sess.invited:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="User already invited")
    if user_to_invite in sess.players:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="User already joined")

    # Вместимость: учитываем и уже присоединившихся, и ещё предстоит приглашение
    total_after = len(sess.players) + len(sess.invited) + 1  # +1 для нового приглашения
    if total_after > MAX_PLAYERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Max players exceeded")

    # Собственно приглашаем
    ref.update({
        "invited": firestore.ArrayUnion([user_to_invite])
    })

# Join a session
@router.post("/{sid}/join", response_model=MultiplayerSession)
async def join_session(
    sid: str,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    ref = db.collection("sessions").document(sid)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    sess = MultiplayerSession.model_validate(snap.to_dict())
    if current.user_id not in (*sess.invited, sess.host_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not invited")
    if len(sess.players) >= MAX_PLAYERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Session is full")

    sess.players[current.user_id] = None
    ref.update({"players": sess.players})
    return sess

# Get session state
@router.get("/{sid}", response_model=MultiplayerSession)
async def get_session_state(
    sid: str,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    snap = db.collection("sessions").document(sid).get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    sess = MultiplayerSession.model_validate(snap.to_dict())
    if current.user_id not in (*sess.players, sess.host_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")
    return sess

# Send chat message
@router.post("/{sid}/chat", status_code=status.HTTP_204_NO_CONTENT)
async def send_chat(
    sid: str,
    payload: Dict[str, str],  # {"msg": "..."}
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    ref = db.collection("sessions").document(sid)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    sess = MultiplayerSession.model_validate(snap.to_dict())
    if current.user_id not in sess.players:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not in session")

    entry = {
        "user_id": current.user_id,
        "msg": payload["msg"],
        "ts": datetime.now(timezone.utc).isoformat()
    }
    ref.update({"chat": firestore.ArrayUnion([entry])})


# Vote for a choice
@router.post("/{sid}/vote", status_code=status.HTTP_204_NO_CONTENT)
async def vote(
    sid: str,
    payload: Dict[str, str],
    background_tasks: BackgroundTasks,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    ref = db.collection("sessions").document(sid)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    sess = MultiplayerSession.model_validate(snap.to_dict())
    if current.user_id not in sess.players:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not in session")

    # Сохраняем голос
    sess.votes[current.user_id] = payload["choice_id"]
    ref.update({"votes": sess.votes})

    # если все проголосовали — планируем finalize_choice
    if len(sess.votes) == len(sess.players):
        background_tasks.add_task(finalize_choice, sid, current, db)

    return Response(status_code=status.HTTP_204_NO_CONTENT)

class MultiChoiceRequest(BaseModel):
    contents: List[str]

# Player-proposed choice
@router.post(
    "/{sid}/choices/player",
    response_model=List[Choice],
    status_code=status.HTTP_201_CREATED,
    summary="Propose multiple player choices at once",
)
async def propose_choices(
    sid: str,
    req: MultiChoiceRequest,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    # Проверяем, что сессия есть
    sess_ref = db.collection("sessions").document(sid)
    if not sess_ref.get().exists:
        raise HTTPException(status_code=404, detail="Session not found")

    out: List[dict] = []
    for text in req.contents:
        choice = Choice(
            proposer_id=current.user_id,
            content=text,
            created_at=now_utc()
        )
        # сохраняем в Firestore
        sess_ref.collection("choices").document(choice.choice_id).set(choice.model_dump())
        # и сразу сериализуем в dict
        out.append(choice.model_dump())

    return out

# List all choices
@router.get("/{sid}/choices", response_model=List[Choice])
async def list_choices(
    sid: str,
    db: FirestoreClient = Depends(get_db),
):
    snaps = db.collection("sessions").document(sid).collection("choices").stream()
    return [Choice.model_validate(d.to_dict()) for d in snaps]


# Подведение итогов голосования: выбор победителя (популярное + случайный победитель если ничья)
# автоматически сохранить победивший текст в коллекцию text_segments основной новеллы.
@router.post(
    "/{sid}/choices/finalize",
    response_model=Choice,
    status_code=status.HTTP_200_OK,
    summary="Finalize votes, announce winner, append to novel text and clear choices"
)
async def finalize_choice(
    sid: str,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    sess_ref = db.collection("sessions").document(sid)
    snap = sess_ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    sess = MultiplayerSession.model_validate(snap.to_dict())

    if current.user_id not in (*sess.players, sess.host_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not in session")
    if not sess.votes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No votes to finalize")

    # Подсчитываем голоса
    tally: Dict[str, int] = {}
    for ch_id in sess.votes.values():
        tally[ch_id] = tally.get(ch_id, 0) + 1
    max_votes = max(tally.values())
    top = [ch for ch, cnt in tally.items() if cnt == max_votes]
    winner_id = random.choice(top)

    # Загружаем победивший Choice
    choice_snap = sess_ref.collection("choices").document(winner_id).get()
    if not choice_snap.exists:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Winning choice not found"
        )
    win_choice = Choice.model_validate(choice_snap.to_dict())

    # Отправляем объявление в чат
    announcement = {
        "user_id": None,
        "msg":     f"Choice «{win_choice.content}» selected ({max_votes} votes).",
        "ts":      datetime.now(timezone.utc).isoformat()
    }
    sess_ref.update({"chat": firestore.ArrayUnion([announcement])})

    # Добавляем текст в основную новеллу
    await add_text_segment(
        novel_id=sess.novel_id,
        edit=NovelTextEdit(content=win_choice.content),
        db=db,
        current_user=current
    )

    # Удаляем все варианты в subcollection "choices" и используем batch для эффективности
    batch = db.batch()
    choices_coll = sess_ref.collection("choices")
    for doc in choices_coll.stream():
        batch.delete(doc.reference)
    batch.commit()

    # Сбрасываем голоса в документе сессии
    sess_ref.update({"votes": {}})

    return win_choice

