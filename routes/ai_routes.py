from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Literal, Dict, Optional
from datetime import datetime, timezone

from utils.ai_utils import (
    client,
    generate_title,
    generate_novel_description,
    generate_novel_setting,
    generate_character,
    generate_prologue,
    generate_continuation,
    generate_three_plot_options
)
from utils.firebase import get_db
from google.cloud.firestore import Client as FirestoreClient
from routes.auth_routes import get_current_user
from models import Character, Novel, User, TextSegment, Choice, now_utc
from models_multiplayer import MultiplayerSession

router = APIRouter()


@router.get("/health", summary="AI Health Check")
async def ai_health():
    try:
        resp = client.models.list()
        return {
            "status": "ok",
            "available_models": [m.id for m in resp.data]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI health check failed: {e}"
        )


class MetadataFieldsRequest(BaseModel):
    fields: List[Literal["title", "description", "setting"]]


@router.post(
    "/novels/{novel_id}/metadata",
    summary="Generate metadata (title/description/setting) without saving",
    status_code=status.HTTP_200_OK,
)
async def suggest_metadata(
    novel_id: str,
    req: MetadataFieldsRequest,
    db: FirestoreClient = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Load novel and check permissions
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(404, "Novel not found")
    novel = Novel.model_validate(snap.to_dict())

    if current_user.user_id not in novel.users_author:
        raise HTTPException(403, "Only an author can suggest metadata")

    # If nothing at all is filled yet, require at least one genre
    if not (novel.title or novel.description.strip() or novel.setting.strip()) and not novel.genres:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cannot suggest metadata: please select at least one genre first."
        )

    results: Dict[str, str] = {}

    # Title
    if "title" in req.fields and not novel.title:
        results["title"] = generate_title(
            genres=novel.genres,
            description=novel.description,
            setting=novel.setting,
        )
    # Description
    if "description" in req.fields and not novel.description.strip():
        results["description"] = generate_novel_description(
            title=results.get("title", novel.title),
            genres=novel.genres,
            existing_setting=novel.setting,
        )
    # Setting
    if "setting" in req.fields and not novel.setting.strip():
        results["setting"] = generate_novel_setting(
            title=results.get("title", novel.title),
            genres=novel.genres,
            existing_description=results.get("description", novel.description),
        )

    return results
# Для сохранения изменений вызов: PUT /novels/{novel_id} из routes/novel_routes


class CharacterRequest(BaseModel):
    role: Literal["player", "npc"]
    name: Optional[str] = None
    appearance: Optional[str] = None
    backstory: Optional[str] = None
    traits: Optional[str] = None


@router.post(
    "/novels/{novel_id}/character",
    summary="Generate complete character without saving",
    response_model=Character,
    status_code=status.HTTP_201_CREATED,
)
async def suggest_character(
    novel_id: str,
    req: CharacterRequest,
    db: FirestoreClient = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Проверяем, что новелла существует
    snap = db.collection("novels").document(novel_id).get()
    if not snap.exists:
        raise HTTPException(404, "Novel not found")
    stored = Novel.model_validate(snap.to_dict())

    # Собираем существующие поля
    existing = {
        "name":       req.name or "",
        "appearance": req.appearance or "",
        "backstory":  req.backstory or "",
        "traits":     req.traits or "",
    }
    to_generate = [k for k, v in existing.items() if not v]

    # Генерируем недостающие
    gen = generate_character(
        title=stored.title,
        genres=stored.genres,
        setting=stored.setting,
        fields=to_generate,
        existing=existing,
    )
    combined = {**existing, **gen}

    # Возвращаем Pydantic-модель (ещё не сохранённую)
    return Character(
        character_id = "",  # пустой, будет присвоен при сохранении
        novel_id     = novel_id,
        user_id      = None if req.role == "npc" else current_user.user_id,
        role         = req.role,
        name         = combined["name"],
        appearance   = combined["appearance"],
        backstory    = combined["backstory"],
        traits       = combined["traits"],
    )
# Для сохранения вызов: POST /novels/{novel_id}/characters из routes/novel_routes


@router.post(
    "/novels/{novel_id}/text/prologue",
    response_model=TextSegment,
    status_code=status.HTTP_201_CREATED,
    summary="Generate prologue without saving",
)
async def create_prologue(
    novel_id: str,
    db: FirestoreClient = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snap = db.collection("novels").document(novel_id).get()
    if not snap.exists:
        raise HTTPException(404, "Novel not found")
    if any(db.collection("novels").document(novel_id)
           .collection("text_segments").limit(1).stream()):
        raise HTTPException(400, "Prologue already exists")

    novel = Novel.model_validate(snap.to_dict())

    chars = [
        c.to_dict() for c in db.collection("novels").document(novel_id)
                                .collection("characters").stream()
    ]
    content = generate_prologue(
        title=novel.title,
        description=novel.description,
        genres=novel.genres,
        setting=novel.setting,
        characters=chars,
    )
    return TextSegment(
        segment_id="",
        author_id=current_user.user_id,
        content=content,
        created_at=datetime.now(timezone.utc),
    )
# Для сохранения вызов: POST /novels/{novel_id}/text/segments из routes/novel_routes


@router.post(
    "/novels/{novel_id}/text/continue",
    response_model=TextSegment,
    status_code=status.HTTP_201_CREATED,
    summary="Generate next segment without saving",
)
async def continue_text(
    novel_id: str,
    db: FirestoreClient = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snap = db.collection("novels").document(novel_id).get()
    if not snap.exists:
        raise HTTPException(404, "Novel not found")

    novel_data = snap.to_dict()
    # получаем список жанров из данных
    genres_list = novel_data.get("genres", [])

    all_text = "\n\n".join(
        seg.to_dict()["content"]
        for seg in db.collection("novels").document(novel_id)
        .collection("text_segments")
        .order_by("created_at")
        .stream()
    )
    cont = generate_continuation(
        full_text=all_text,
        title=novel_data.get("title", ""),
        genres=genres_list,
    )
    return TextSegment(
        segment_id="",
        author_id=current_user.user_id,
        content=cont,
        created_at=datetime.now(timezone.utc),
    )
# Для сохранения вызов: POST /novels/{novel_id}/text/segments из routes/novel_routes


# AI-generated choices
@router.post(
    "/{sid}/choices/ai",
    response_model=List[Choice],
    status_code=status.HTTP_201_CREATED,
    summary="AI: Generate three plot choices"
)
async def generate_choices_ai(
    sid: str,
    db: FirestoreClient = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # verify session and access
    sess_ref = db.collection("sessions").document(sid)
    snap = sess_ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    sess = MultiplayerSession.model_validate(snap.to_dict())
    if current.user_id not in (*sess.players, sess.host_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

    # load novel context...
    novel_ref = db.collection("novels").document(sess.novel_id)
    novel_snap = novel_ref.get()
    if not novel_snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Novel not found")
    novel_data = novel_snap.to_dict()

    title       = novel_data.get("title", "")
    setting     = novel_data.get("setting", "")
    genres_list = novel_data.get("genres", [])

    full_text = "\n\n".join(
        seg.to_dict().get("content", "")
        for seg in novel_ref.collection("text_segments").order_by("created_at").stream()
    )

    prompts = generate_three_plot_options(
        full_text=full_text,
        title=title,
        genres=genres_list,
        setting=setting,
    )

    out: List[Choice] = []
    for text in prompts:
        c = Choice(proposer_id=None, content=text, created_at=now_utc())
        sess_ref.collection("choices").document(c.choice_id).set(c.model_dump())
        out.append(c)

    return out
