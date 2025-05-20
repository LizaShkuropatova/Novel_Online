from fastapi import APIRouter, HTTPException, Depends, status, Query, File, UploadFile, Response
from typing import List, Literal, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid
from itertools import islice

from models import NovelCreate, Novel, Character, User, TextSegment,TextEdit, Genre, Status, StatusFilter, CharacterCreate, MultiplayerSession
from utils.firebase import get_db, get_storage_bucket
from google.cloud.firestore import Client as FirestoreClient
from routes.auth_routes import get_current_user
from firebase_admin import firestore  # firestore.ArrayUnion, ArrayRemove

router = APIRouter()

# маленькая Pydantic-схема для отдачи только ID
class CharacterIdResponse(BaseModel):
    character_id: str

@router.get("/genres",response_model=List[Genre],summary="List all available genres")
async def list_genres():
    """
    Returns a list of all genres supported by the application.
    """
    return list(Genre)

@router.post("/", response_model=Novel, status_code=status.HTTP_201_CREATED)
async def create_novel(
    data: NovelCreate,
    current_user: User           = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    novel = Novel(
        novel_id     = str(uuid.uuid4()),
        users_author = [current_user.user_id],
        user_players = [current_user.user_id],
        created_at   = now,
        updated_at   = now,
        genres       = data.genres,
        title        = data.title or "",
        description  = data.description or "",
        setting      = data.setting or "",
        is_public    = data.is_public,
    )

    # сохраняем
    db.collection("novels").document(novel.novel_id).set(novel.model_dump())

    # добавляем в created_novels автора
    db.collection("users").document(current_user.user_id).update({
        "created_novels": firestore.ArrayUnion([novel.novel_id])
    })
    return novel

# Список усіх новел в БД
@router.get("/", response_model=List[Novel])
async def list_novels(db: FirestoreClient = Depends(get_db)):
    snaps = db.collection("novels").stream()
    return [Novel.model_validate(doc.to_dict()) for doc in snaps]

# Список Публічних новел
@router.get("/public", response_model=List[Novel], summary="List of Public Novels (is_public=True)")
async def list_public_novels(
    db: FirestoreClient = Depends(get_db),
):
    snaps = db.collection("novels").where("is_public", "==", True).stream()
    return [ Novel.model_validate(doc.to_dict()) for doc in snaps ]

# Пошук новели за назвою/частиною
@router.get("/search",response_model=List[Novel], summary="Пошук новелли по частині назви")
async def search_novels(
    q: str = Query(..., min_length=1, description="Фрагмент назви для пошуку"),
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
        raise HTTPException(status_code=404, detail="Novel not found")
    return Novel.model_validate(doc.to_dict())


@router.put("/{novel_id}", response_model=Novel)
async def update_novel(
    novel_id: str,
    payload:  Novel,
    db:        FirestoreClient = Depends(get_db),
    current_user: User          = Depends(get_current_user),
):
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Novel not found")

    # проверяем, что текущий юзер — один из авторов
    novel = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in novel.users_author:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Author of the novella can update it"
        )

    payload.updated_at = datetime.now(timezone.utc)
    ref.set(payload.model_dump(), merge=True)
    return payload

class NovelPatch(BaseModel):
    title:        Optional[str]       = None
    description:  Optional[str]       = None
    genres:       Optional[List[Genre]] = None
    setting:      Optional[str]       = None
    is_public:    Optional[bool]      = None

@router.patch(
    "/{novel_id}",
    response_model=Novel,
    summary="Partially update a novel (title, description, genres, setting, is_public",
    status_code=status.HTTP_200_OK,
)
async def patch_novel(
    novel_id: str,
    payload:  NovelPatch,
    db:        FirestoreClient = Depends(get_db),
    current_user: User        = Depends(get_current_user),
):
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Novel not found")

    stored = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in stored.users_author:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the Author can update")

    # Собираем только те поля, которые пришли
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    # Добавляем метку времени
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Пушим в Firestore
    ref.update(update_data)

    # Возвращаем свежие данные
    new_snap = ref.get()
    return Novel.model_validate(new_snap.to_dict())

# Удаляет новелу, очищает все его упоминания в профилях пользователей и удаляет связанные с ним сеансы.
@router.delete("/{novel_id}")
async def delete_novel(
    novel_id: str,
    db:        FirestoreClient = Depends(get_db),
    current_user: User          = Depends(get_current_user),
):
    """
    Deletes the novel, clears all its occurrences in user profiles
    and deletes related sessions.
    """
    # Проверяем, что новелла есть
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Novel not found")

    # проверяем, что текущий юзер — один из авторов
    novel = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in novel.users_author:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Author of the short story can delete"
        )

    # Удаляем сам документ новеллы
    ref.delete()

    # Удаляем все сессии, привязанные к этой новелле
    sessions = db.collection("sessions").where("novel_id", "==", novel_id).stream()
    for sess_doc in sessions:
        sess_doc.reference.delete()

    # Удаляем novel_id из массивов у всех пользователей (created_novels, saved_novels, completed_novels)
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
    return {"detail": "Novel and all references to it have been removed"}

# Создание копии новелы, с новым автором, игроком и тд.
@router.post("/{novel_id}/fork", response_model=Novel)
async def fork_novel(
    novel_id:     str,
    current_user: User            = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    """
    Fork the Novel: clone it, change the ID, put current_user as author and player.
    """
    orig_ref = db.collection("novels").document(novel_id)
    orig_snap = orig_ref.get()
    if not orig_snap.exists:
        raise HTTPException(status_code=404, detail="The original Novel was not found")

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
    Returns the original of the Forked Novel.
    """
    fork_snap = db.collection("novels").document(novel_id).get()
    if not fork_snap.exists:
        raise HTTPException(status_code=404, detail="Novel not found")

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
    payload:      CharacterCreate,            # <-- новая модель
    current_user: User            = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    """
    Creates a character with a mandatory `role` field.
    """
    novel_ref = db.collection("novels").document(novel_id)
    if not novel_ref.get().exists:
        raise HTTPException(404, "Novel not found")

    # Если payload.name == None, заменяем на пустую строку
    name       = payload.name or ""
    appearance = payload.appearance or ""
    backstory  = payload.backstory or ""
    traits     = payload.traits or ""

    # Создаём Pydantic-модель
    char = Character(
        character_id = str(uuid.uuid4()),
        novel_id     = novel_id,
        user_id      = current_user.user_id,
        role         = payload.role,
        name         = name,
        appearance   = appearance,
        backstory    = backstory,
        traits       = traits,
    )

    # сохраняем в Firestore
    novel_ref.collection("characters") \
             .document(char.character_id) \
             .set(char.model_dump())

    # добавляем юзера в список игроков новеллы
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
    Returns all characters in a particular Novel.
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
    payload:      CharacterCreate,
    db:           FirestoreClient = Depends(get_db),
):
    """
    Updates the Character's fields.
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

# Получить все сегменты новеллы по айди новеллы
@router.get(
    "/{novel_id}/text/segments",
    response_model=List[TextSegment],
    summary="List all text segments for a novel",
)
async def list_text_segments(
    novel_id: str,
    db: FirestoreClient = Depends(get_db),
):
    novel_ref = db.collection("novels").document(novel_id)
    if not novel_ref.get().exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Novel not found")

    snaps = (
        novel_ref
        .collection("text_segments")
        .order_by("created_at")
        .stream()
    )
    return [TextSegment.model_validate(doc.to_dict()) for doc in snaps]

@router.delete(
    "/novels/{novel_id}/text/segments/{segment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a text segment (author or session participant only)"
)
async def delete_text_segment(
    novel_id: str,
    segment_id: str,
    db: FirestoreClient = Depends(get_db),
    current_user: User  = Depends(get_current_user),
):
    # 1) ensure novel exists
    novel_ref = db.collection("novels").document(novel_id)
    if not novel_ref.get().exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Novel not found")

    # 2) load the segment
    seg_ref = novel_ref.collection("text_segments").document(segment_id)
    seg_snap = seg_ref.get()
    if not seg_snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")

    seg_data = seg_snap.to_dict()

    # 3) check permission: either the original author…
    if seg_data.get("author_id") == current_user.user_id:
        allowed = True
    else:
        # …or a participant (including host) in any multiplayer session for this novel
        allowed = False
        sessions = db.collection("sessions")\
                     .where("novel_id", "==", novel_id)\
                     .stream()
        for s in sessions:
            sess = MultiplayerSession.model_validate(s.to_dict())
            if current_user.user_id == sess.host_id \
               or current_user.user_id in sess.players:
                allowed = True
                break

    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not permitted to delete this segment")

    # 4) delete the segment
    seg_ref.delete()

    # 5) if this was the novel’s current_position, clear it
    novel = novel_ref.get().to_dict()
    if novel.get("current_position") == segment_id:
        novel_ref.update({
            "current_position": None,
            "updated_at": datetime.now(timezone.utc)
        })
    else:
        # just bump updated_at
        novel_ref.update({"updated_at": datetime.now(timezone.utc)})

    return Response(status_code=status.HTTP_204_NO_CONTENT)

# Список новелл, созданных пользователем (не учитывает те где участвывает)
@router.get("/user/{user_id}",response_model=List[Novel],summary="List of Novels created by the user")
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

# Список новелл по 1 жанру
@router.get("/genre/{genre}",response_model=List[Novel],summary="List of Novel by genre")
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

def chunked(iterable, size=10):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            break
        yield chunk


@router.get(
    "/novels/by-any-genres",
    response_model=List[Novel],
    summary="List novels matching ANY of the given genres"
)
async def list_novels_by_genres(
    genres: List[Genre] = Query(..., description="?genres=horror&genres=drama&…"),
    db: FirestoreClient = Depends(get_db),
):
    genre_values = [g.value for g in genres]
    seen_ids = set()
    result = []

    for chunk in chunked(genre_values, 10):
        snaps = db.collection("novels") \
                  .where("genres", "array_contains_any", chunk) \
                  .stream()
        for doc in snaps:
            if doc.id not in seen_ids:
                seen_ids.add(doc.id)
                result.append(Novel.model_validate(doc.to_dict()))

    return result

@router.get(
    "/novels/by-all-genres",
    response_model=List[Novel],
    summary="List all novels matching ALL of the given genres",
)
async def list_novels_by_all_genres(
    genres: List[Genre] = Query(
        ...,
        description="One or more genres to filter by (e.g. ?genres=horror&genres=drama)"
    ),
    db: FirestoreClient = Depends(get_db),
):
    """
    Вернет только те новеллы, массив genres которых содержит **все**
    переданные в запросе значения.
    """
    # Приводим Enum -> строки
    genre_values = [g.value for g in genres]
    if not genre_values:
        return []

    # Сначала фильтрация по первому жанру
    first = genre_values[0]
    snaps = db.collection("novels") \
              .where("genres", "array_contains", first) \
              .stream()

    result: List[Novel] = []
    for doc in snaps:
        data = doc.to_dict()
        # убеждаемся, что все жанры есть в массиве
        if all(g in data.get("genres", []) for g in genre_values):
            # валидирует через Pydantic
            result.append(Novel.model_validate(data))

    return result


@router.get("/user/{user_id}/both",response_model=List[Novel],summary="Novels where the user is both Author and Player")
async def list_author_and_player_novels(
    user_id: str,
    db: FirestoreClient = Depends(get_db),
):
    """
    Повертає всі новели, в яких user_id одночасно
    присутній і в users_author, і в user_players.
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
        # фильтруем по наличию в user_players
        if user_id in data.get("user_players", []):
            result.append(Novel.model_validate(data))

    return result

# Сохранение изображение новеллы в БД
@router.post(
    "/{novel_id}/images",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a cover image for a novel",
)
async def upload_novel_image(
    novel_id: str,
    file: UploadFile = File(...),
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Проверяем, что новелла существует и текущий пользователь — её автор
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Novel not found")
    novel = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in novel.users_author:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an author can upload images")

    # Заливаем файл в Cloud Storage
    bucket = get_storage_bucket()
    blob = bucket.blob(f"novels/{novel_id}/{file.filename}")
    contents = await file.read()
    blob.upload_from_string(contents, content_type=file.content_type)
    blob.make_public()
    # Получаем публичный URL
    url = blob.public_url

    # Сохраняем строку URL в поле cover_image_url
    ref.update({"cover_image_url": url})

    return {"cover_image_url": url}


@router.put(
    "/me/novels/{novel_id}/status",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set the Novel Status for the current user"
)
async def set_novel_status(
    novel_id: str,
    new_status: Status = Query(..., description="Select a Status"),
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
    summary="Find out which list the current user has the Novel in",
    response_model=Literal["playing", "planned", "completed", "favorite", "abandoned", None]
)
async def get_novel_status(
    novel_id: str,
    db: FirestoreClient     = Depends(get_db),
    current: User           = Depends(get_current_user),
):
    user_doc = db.collection("users").document(current.user_id).get()
    if not user_doc.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
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


@router.get(
    "/me/novels",
    response_model=List[Novel],
    summary="List my novels, with optional role/status and genre filters"
)
async def list_my_novels(
    user_status: StatusFilter = Query("all", description="all | created | playing | planned | completed | favorite | abandoned"),
    genre: Optional[Genre] = Query(None, description="Optional genre filter"),
    db: FirestoreClient = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """
    - status=all           → union(created_novels, playing_novels)
    - status=created       → only created_novels
    - status=playing       → only playing_novels
    - status=planned       → only planned_novels
    - status=completed     → only completed_novels
    - status=favorite      → only favorite_novels
    - status=abandoned     → only abandoned_novels
    """
    uid = me.user_id

    # вынимаем из пользователя нужный список ID
    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")
    u = user_doc.to_dict()

    # map status → поле в документе User
    field_map = {
        "created":   "created_novels",
        "playing":   "playing_novels",
        "planned":   "planned_novels",
        "completed": "completed_novels",
        "favorite":  "favorite_novels",
        "abandoned": "abandoned_novels",
    }

    # собираем set из нужных списков
    ids = set()
    if user_status == "all":
        ids |= set(u.get("created_novels", []))
        ids |= set(u.get("playing_novels", []))
    else:
        ids |= set(u.get(field_map[user_status], []))

    # если после этого пусто — вернём пустой список
    if not ids:
        return []

    # делаем get по всем этим novel_id
    novels = []
    for nid in ids:
        snap = db.collection("novels").document(nid).get()
        if not snap.exists:
            continue
        nov = Novel.model_validate(snap.to_dict())
        # 3) опционально фильтруем по жанру
        if genre is None or genre in nov.genres:
            novels.append(nov)

    return novels