from fastapi import APIRouter, HTTPException, Depends, status, Query, File, UploadFile
from typing import List, Literal
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

from models import Novel, Character, User, TextSegment,TextEdit, Genre, Status
from utils.firebase import get_db, get_storage_bucket
from google.cloud.firestore import Client as FirestoreClient
from routes.auth_routes import get_current_user
from firebase_admin import firestore  # firestore.ArrayUnion, ArrayRemove

router = APIRouter()

# ——— Схема для создания/обновления персонажа ———
class CharacterPayload(BaseModel):
    role:       Literal["player", "npc"]
    name:       str
    appearance: str
    backstory:  str
    traits:     str

# маленькая Pydantic-схема для отдачи только ID
class CharacterIdResponse(BaseModel):
    character_id: str

@router.post("/", response_model=Novel, status_code=status.HTTP_201_CREATED)
async def create_novel(
    novel: Novel,
    current_user: User           = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    """
    Создаёт новую новеллу и сразу ставит текущего пользователя
    её автором и первым игроком.
    """
    # Уникальный ID и метки времени
    novel.novel_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    novel.created_at = now
    novel.updated_at = now

    # Привязываем текущего пользователя
    novel.users_author = [current_user.user_id]
    novel.user_players = [current_user.user_id]

    # Сохранение
    db.collection("novels").document(novel.novel_id).set(novel.model_dump())

    # Обновляем массив created_novels у пользователя
    db.collection("users").document(current_user.user_id).update({
        "created_novels": firestore.ArrayUnion([novel.novel_id])
    })
    return novel

# Список всех новел в БД
@router.get("/", response_model=List[Novel])
async def list_novels(db: FirestoreClient = Depends(get_db)):
    snaps = db.collection("novels").stream()
    return [Novel.model_validate(doc.to_dict()) for doc in snaps]

# Список Публичных новел
@router.get("/public", response_model=List[Novel], summary="Список публичных новелл (is_public=True)")
async def list_public_novels(
    db: FirestoreClient = Depends(get_db),
):
    snaps = db.collection("novels").where("is_public", "==", True).stream()
    return [ Novel.model_validate(doc.to_dict()) for doc in snaps ]

# Поиск новел по названию/части
@router.get("/search",response_model=List[Novel], summary="Поиск новеллы по части названия")
async def search_novels(
    q: str = Query(..., min_length=1, description="Фрагмент названия для поиска"),
    db: FirestoreClient = Depends(get_db),
):
    # Firestore не поддерживает полноценный «contains» на строках, по этому простая фильтрация на клиенте
    low = q.lower()
    snaps = db.collection("novels").stream()
    result: List[Novel] = []
    for doc in snaps:
        data = doc.to_dict()
        title = data.get("title", "")
        if low in title.lower():
            result.append(Novel.model_validate(data))
    return result


# Найти новеллу по novel_id
@router.get("/{novel_id}", response_model=Novel)
async def get_novel(
    novel_id: str,
    db:        FirestoreClient = Depends(get_db),
):
    doc = db.collection("novels").document(novel_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Новелла не найдена")
    return Novel.model_validate(doc.to_dict())


@router.put("/{novel_id}", response_model=Novel)
async def update_novel(
    novel_id: str,
    payload:  Novel,
    db:        FirestoreClient = Depends(get_db),
):
    ref = db.collection("novels").document(novel_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Новелла не найдена")

    payload.updated_at = datetime.now(timezone.utc)
    ref.set(payload.model_dump(), merge=True)
    return payload


@router.delete("/{novel_id}")
async def delete_novel(
    novel_id: str,
    db:        FirestoreClient = Depends(get_db),
):
    """
    Удаляет новеллу, очищает все её вхождения в профилях пользователей
    и удаляет связанные сессии.
    """
    # 1) Проверяем, что новелла есть
    ref = db.collection("novels").document(novel_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Новелла не найдена")

    # Удаляем сам документ новеллы
    ref.delete()

    # Удаляем все сессии, привязанные к этой новелле
    sessions = db.collection("sessions").where("novel_id", "==", novel_id).stream()
    for sess_doc in sessions:
        sess_doc.reference.delete()

    # Удаляем novel_id из массивов у всех пользователей
    #    (created_novels, saved_novels, completed_novels)
    users = db.collection("users").where("created_novels", "array_contains", novel_id).stream()
    for u in users:
        u.reference.update({
            "created_novels":   firestore.ArrayRemove([novel_id])
        })
    users = db.collection("users").where("saved_novels", "array_contains", novel_id).stream()
    for u in users:
        u.reference.update({
            "saved_novels":     firestore.ArrayRemove([novel_id])
        })
    users = db.collection("users").where("completed_novels", "array_contains", novel_id).stream()
    for u in users:
        u.reference.update({
            "completed_novels": firestore.ArrayRemove([novel_id])
        })
    return {"detail": "Новелла и все её упоминания удалены"}

# Создание копии новелы, с новым автором, игроком и тд.
@router.post("/{novel_id}/fork", response_model=Novel)
async def fork_novel(
    novel_id:     str,
    current_user: User            = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    """
    Форкаем новеллу: клонируем, меняем ID, ставим current_user автором и игроком.
    """
    orig_ref = db.collection("novels").document(novel_id)
    orig_snap = orig_ref.get()
    if not orig_snap.exists:
        raise HTTPException(status_code=404, detail="Оригинальная новелла не найдена")

    original = Novel.model_validate(orig_snap.to_dict())
    new = original.model_copy(deep=True)

    new.novel_id          = str(uuid.uuid4())
    new.novel_original_id = original.novel_id

    now = datetime.now(timezone.utc)
    new.created_at = now
    new.updated_at = now

    new.users_author = [current_user.user_id]
    new.user_players = [current_user.user_id]

    db.collection("novels").document(new.novel_id).set(new.model_dump())
    return new


@router.get("/{novel_id}/original", response_model=Novel)
async def get_original(
    novel_id: str,
    db:        FirestoreClient = Depends(get_db),
):
    """
    Возвращает оригинал форкнутой новеллы.
    """
    fork_snap = db.collection("novels").document(novel_id).get()
    if not fork_snap.exists:
        raise HTTPException(status_code=404, detail="Novella not found")

    fork = Novel.model_validate(fork_snap.to_dict())
    if not fork.novel_original_id:
        raise HTTPException(status_code=400, detail="It's not a fork - the original is not listed")

    orig_snap = db.collection("novels").document(fork.novel_original_id).get()
    if not orig_snap.exists:
        raise HTTPException(status_code=404, detail="Original not found")

    return Novel.model_validate(orig_snap.to_dict())

# Создать персонажа
@router.post(
    "/{novel_id}/characters",
    response_model=Character,
    status_code=status.HTTP_201_CREATED
)
async def create_character(
    novel_id:     str,
    payload:      CharacterPayload,
    current_user: User            = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    """
    Создаёт игрового персонажа для текущего пользователя и
    пушит его user_id в массив user_players главной новеллы.
    """
    novel_ref = db.collection("novels").document(novel_id)
    if not novel_ref.get().exists:
        raise HTTPException(status_code=404, detail="Novella not found")

    char = Character(
        character_id = str(uuid.uuid4()),
        novel_id     = novel_id,
        user_id      = current_user.user_id,
        role         = payload.role,
        name         = payload.name,
        appearance   = payload.appearance,
        backstory    = payload.backstory,
        traits       = payload.traits,
    )

    novel_ref.collection("characters") \
             .document(char.character_id) \
             .set(char.model_dump())

    # Добавляем пользователя в список игроков новеллы
    novel_ref.update({
        "user_players": firestore.ArrayUnion([current_user.user_id])
    })

    return char

# Список персонажей конкретной новеллы
@router.get("/{novel_id}/characters",response_model=List[Character])
async def list_characters(
    novel_id: str,
    db:        FirestoreClient = Depends(get_db),
):
    """
    Возвращает всех персонажей конкретной новеллы.
    """
    char_snaps = (db.collection("novels")
                    .document(novel_id)
                    .collection("characters")
                    .stream())
    return [Character.model_validate(doc.to_dict()) for doc in char_snaps]

# Обновить персонажа
@router.put("/{novel_id}/characters/{character_id}", response_model=Character)
async def update_character(
    novel_id:     str,
    character_id: str,
    payload:      CharacterPayload,
    db:           FirestoreClient = Depends(get_db),
):
    """
    Обновляет поля персонажа.
    """
    char_ref = (db.collection("novels")
                  .document(novel_id)
                  .collection("characters")
                  .document(character_id))
    if not char_ref.get().exists:
        raise HTTPException(status_code=404, detail="Character not found")

    char_ref.set(payload.model_dump(), merge=True)
    return Character.model_validate(char_ref.get().to_dict())

# Получить ID персонажа текущего пользователя в этой новеллы
@router.get("/{novel_id}/characters/me", response_model=CharacterIdResponse,
    summary="Get the character ID of the current user's character in this novel")
async def get_my_character(
    novel_id:     str,
    current_user: User            = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    """
    Ищет в подколлекции `characters` документа `novels/{novel_id}`
    персонажа, у которого поле user_id совпадает с текущим.
    Если найден — возвращает его character_id, иначе 404.
    """
    # ссылка на подколлекцию
    chars_coll = db.collection("novels") \
                   .document(novel_id) \
                   .collection("characters")

    # запрос по полю user_id
    snaps = chars_coll.where("user_id", "==", current_user.user_id).stream()
    for doc in snaps:
        return CharacterIdResponse(character_id=doc.id)

    # если ни одного не нашли — 404
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="The current user doesn't have a character in this novel yet"
    )

# Сохраняем текст в сегмент (в ручную написанный) и даже если это как пролог (1-й)
@router.post("/{novel_id}/text/segments",
    response_model=TextSegment,
    status_code=status.HTTP_201_CREATED,
    summary="Add a manual text segment"
)
async def add_text_segment(
    novel_id: str,
    edit: TextEdit,
    db: FirestoreClient = Depends(get_db),
    current_user: User  = Depends(get_current_user),
):
    # Проверяем, что новелла существует
    novel_ref = db.collection("novels").document(novel_id)
    if not novel_ref.get().exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Novel not found")

    # Сохраняем новый сегмент
    segment_id = str(uuid.uuid4())
    seg = TextSegment(
        segment_id=segment_id,
        author_id=current_user.user_id,
        content=edit.content,
        created_at=datetime.now(timezone.utc),
    )
    novel_ref.collection("text_segments").document(segment_id).set(seg.model_dump())

    # Обновляем текущую позицию и время обновления самой новеллы
    novel_ref.update({
        "current_position": segment_id,
        "updated_at": datetime.now(timezone.utc)
    })

    return seg

# Редактировать сегмент Новеллы
@router.put( "/novels/{novel_id}/text/segments/{segment_id}",
    response_model=TextSegment,summary="Edit a specific text segment")
async def edit_segment(
    novel_id:     str,
    segment_id:   str,
    edit:         TextEdit,
    db:           FirestoreClient = Depends(get_db),
    current_user: User            = Depends(get_current_user),
):
    seg_ref = (
        db.collection("novels")
          .document(novel_id)
          .collection("text_segments")
          .document(segment_id)
    )
    snap = seg_ref.get()
    if not snap.exists:
        raise HTTPException(404, "Segment not found")

    # проверяем права автора
    data = snap.to_dict()
    if data.get("author_id") != current_user.user_id:
        raise HTTPException(403, "Not allowed to edit this segment")
    # сохраняем обновлённый контент, но сохраняем оригинальную дату создания
    updated = {
        "content":    edit.content,
        "created_at": data["created_at"],  # сохраняем оригинальную дату
    }

    # обновляем у новеллы метку времени
    db.collection("novels").document(novel_id).update({
        "updated_at": datetime.now(timezone.utc)
    })

    seg_ref.set(updated, merge=True)
    out = TextSegment(segment_id=segment_id, **updated)
    return out


# Список новелл, созданных пользователем (не учитывает те где участвывает)
@router.get("/user/{user_id}",response_model=List[Novel],summary="Список новелл, созданных пользователем")
async def list_user_novels(
    user_id: str,
    db: FirestoreClient = Depends(get_db),
):
    snaps = (
        db.collection("novels")
          .where("users_author", "array_contains", user_id)
          .stream()
    )
    return [ Novel.model_validate(doc.to_dict()) for doc in snaps ]

# Список новелл по жанру
@router.get("/genre/{genre}",response_model=List[Novel],summary="Список новелл по жанру")
async def list_genre_novels(
    genre: Genre,
    db: FirestoreClient = Depends(get_db),
):
    snaps = (
        db.collection("novels")
          .where("genres", "array_contains", genre.value)
          .stream()
    )
    return [ Novel.model_validate(doc.to_dict()) for doc in snaps ]


@router.get("/user/{user_id}/both",response_model=List[Novel],summary="Новеллы, где пользователь и автор, и игрок")
async def list_author_and_player_novels(
    user_id: str,
    db: FirestoreClient = Depends(get_db),
):
    """
    Возвращает все новеллы, в которых user_id одновременно
    присутствует и в users_author, и в user_players.
    """
    # сначала запрашиваем все новеллы, где user_id в users_author
    snaps = (
        db.collection("novels")
          .where("users_author", "array_contains", user_id)
          .stream()
    )

    result: List[Novel] = []
    for doc in snaps:
        data = doc.to_dict()
        # 2) фильтруем по наличию в user_players
        if user_id in data.get("user_players", []):
            result.append(Novel.model_validate(data))

    return result

# Сохранение изображение новеллы в БД
@router.post(
    "/{novel_id}/images",
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image for a novel",
)
async def upload_novel_image(
    novel_id: str,
    file: UploadFile = File(...),
    db = Depends(get_db),
    current_user: User  = Depends(get_current_user),
):
    # Проверяем, что новелла существует и текущий пользователь — её автор
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(404, "Novel not found")
    novel = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in novel.users_author:
        raise HTTPException(403, "Only an author can upload images")

    # Заливаем файл в Cloud Storage
    bucket = get_storage_bucket()  # после init_firebase() с storageBucket
    blob = bucket.blob(f"novels/{novel_id}/{file.filename}")

    contents = await file.read()

    blob.upload_from_string(contents, content_type=file.content_type)

    url = blob.public_url

    # Сохраняем URL-ку в Firestore
    ref.update({
        "image_urls": firestore.ArrayUnion([url])
    })

    return {"url": url}


@router.put(
    "/me/novels/{novel_id}/status",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Установить статус новеллы для текущего пользователя"
)
async def set_novel_status(
    novel_id: str,
    new_status: Status = Query(..., description="Выберите статус"),
    db: FirestoreClient = Depends(get_db),
    current: User       = Depends(get_current_user),
):
    """
    Снимает эту новеллу из всех пяти списков и добавляет в тот, который указан в new_status.
    """
    user_ref = db.collection("users").document(current.user_id)

    # сначала удаляем из всех списков
    updates = {}
    for field in ("playing_novels", "planned_novels", "completed_novels", "favorite_novels", "abandoned_novels"):
        updates[field] = firestore.ArrayRemove([novel_id])

    # потом добавляем в нужный
    field_to_add = f"{new_status}_novels"
    updates[field_to_add] = firestore.ArrayUnion([novel_id])

    # применяем всё одним вызовом update
    user_ref.update(updates)


@router.get(
    "/me/novels/{novel_id}/status",
    summary="Узнать, в каком списке находится новелла у текущего пользователя",
    response_model=Literal["playing", "planned", "completed", "favorite", "abandoned", None]
)
async def get_novel_status(
    novel_id: str,
    db: FirestoreClient     = Depends(get_db),
    current: User           = Depends(get_current_user),
):
    user_doc = db.collection("users").document(current.user_id).get()
    if not user_doc.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    data = user_doc.to_dict()

    # проверяем каждый список по порядку
    if novel_id in data.get("playing_novels", []):
        return "playing"
    if novel_id in data.get("planned_novels", []):
        return "planned"
    if novel_id in data.get("completed_novels", []):
        return "completed"
    if novel_id in data.get("favorite_novels", []):
        return "favorite"
    if novel_id in data.get("abandoned_novels", []):
        return "abandoned"
    return None