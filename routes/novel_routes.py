from fastapi import APIRouter, HTTPException, Depends, status, Query, File, UploadFile
from typing import List, Literal, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

from models import NovelCreate, Novel, Character, User, TextSegment,TextEdit, Genre, Status, StatusFilter, CharacterCreate
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
    current_user: User          = Depends(get_current_user),
):
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Новелла не найдена")

    # проверяем, что текущий юзер — один из авторов
    novel = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in novel.users_author:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Обновлять может только автор новеллы"
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Новелла не найдена")

    stored = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in stored.users_author:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Обновлять может только автор")

    # Собираем только те поля, которые пришли
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Нет полей для обновления")

    # Добавляем метку времени
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Пушим в Firestore
    ref.update(update_data)

    # Возвращаем свежие данные
    new_snap = ref.get()
    return Novel.model_validate(new_snap.to_dict())


@router.delete("/{novel_id}")
async def delete_novel(
    novel_id: str,
    db:        FirestoreClient = Depends(get_db),
    current_user: User          = Depends(get_current_user),
):
    """
    Удаляет новеллу, очищает все её вхождения в профилях пользователей
    и удаляет связанные сессии.
    """
    # Проверяем, что новелла есть
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Новелла не найдена")

    # проверяем, что текущий юзер — один из авторов
    novel = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in novel.users_author:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Удалить может только автор новеллы"
        )

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
    payload:      CharacterCreate,            # <-- новая модель
    current_user: User            = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    """
    Создаёт персонажа с обязательным полем `role`.
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
    payload:      CharacterCreate,
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