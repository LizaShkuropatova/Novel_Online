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

# маленька Pydantic-схема для віддачі тільки ID
class CharacterIdResponse(BaseModel):
    character_id: str

@router.get("/genres",response_model=List[Genre],summary="List all available genres")
async def list_genres():
    """
    Повертає список усіх жанрів, що підтримуються додатком.
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

    # зберігаємо
    db.collection("novels").document(novel.novel_id).set(novel.model_dump())

    # додаємо в created_novels автора
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
    low = q.lower()
    snaps = db.collection("novels").stream()
    result: List[Novel] = []
    for doc in snaps:
        data = doc.to_dict()
        title = data.get("title", "")
        if low in title.lower():
            result.append(Novel.model_validate(data))
    return result


# Знайти новелу за novel_id
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
    summary="Partially update a novel (title, description, genres, setting, is_public)",
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

    # Збираємо тільки ті поля, які прийшли
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    # Додаємо мітку часу
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Пушим в Firestore
    ref.update(update_data)

    # Повертаємо свіжі дані
    new_snap = ref.get()
    return Novel.model_validate(new_snap.to_dict())

# Видаляє новелу, очищає всі згадки в профілях користувачів і видаляє пов'язані з нею сеанси.
@router.delete("/{novel_id}")
async def delete_novel(
    novel_id: str,
    db:        FirestoreClient = Depends(get_db),
    current_user: User          = Depends(get_current_user),
):
    """
    Видаляє новелу, очищає всі згадки в профілях користувачів
    і видаляє пов'язані з нею сеанси.
    """
    # Перевіряємо, що новела є
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Novel not found")

    # перевіряємо, що поточний юзер - один з авторів
    novel = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in novel.users_author:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Author of the short story can delete"
        )

    # Видаляємо сам документ новели
    ref.delete()

    # Видаляємо всі сесії, прив'язані до цієї новели
    sessions = db.collection("sessions").where("novel_id", "==", novel_id).stream()
    for sess_doc in sessions:
        sess_doc.reference.delete()

    # Видаляємо novel_id з масивів у всіх користувачів (created_novels, saved_novels, completed_novels)
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

# Створення копії новели, з новим автором, гравцем і тд.
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
    payload:      CharacterCreate,
    current_user: User            = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    """
    Створення персонажу з обов'язковим полем `role`.
    """
    novel_ref = db.collection("novels").document(novel_id)
    if not novel_ref.get().exists:
        raise HTTPException(404, "Novel not found")

    # Если создаётся именно роль "player" — проверяем, не создавал ли уже игрок персонажа
    if payload.role == "player":
        existing_player = (
            novel_ref
            .collection("characters")
            .where("user_id", "==", current_user.user_id)
            .where("role",    "==", "player")
            .limit(1)
            .stream()
        )
        if any(True for _ in existing_player):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "You already have a player character in this novel"
            )

    # Якщо payload.name == None, замінюємо на порожній рядок
    name       = payload.name or ""
    appearance = payload.appearance or ""
    backstory  = payload.backstory or ""
    traits     = payload.traits or ""

    # Створюємо Pydantic-модель
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

    # зберігаємо в Firestore
    novel_ref.collection("characters") \
             .document(char.character_id) \
             .set(char.model_dump())

    # додаємо юзера до списку гравців новели
    novel_ref.update({
        "user_players": firestore.ArrayUnion([current_user.user_id])
    })

    return char

# Список персонажів конкретної новели
@router.get("/{novel_id}/characters",response_model=List[Character])
async def list_characters(
    novel_id: str,
    db:        FirestoreClient = Depends(get_db),
):
    """
    Повертає всіх персонажів певної новели.
    """
    char_snaps = (db.collection("novels")
                    .document(novel_id)
                    .collection("characters")
                    .stream())
    return [Character.model_validate(doc.to_dict()) for doc in char_snaps]

# Оновити персонажа
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

# Отримати ID персонажа поточного користувача в цій новелі
@router.get("/{novel_id}/characters/me", response_model=CharacterIdResponse,
    summary="Get the character ID of the current user's character in this novel")
async def get_my_character(
    novel_id:     str,
    current_user: User            = Depends(get_current_user),
    db:           FirestoreClient = Depends(get_db),
):
    """
    Шукає в підколекції `characters` документа `novels/{novel_id}`
    персонажа, у якого поле user_id збігається з поточним.
    Якщо знайдений - повертає його character_id, інакше 404.
    """
    # посилання на підколекцію
    chars_coll = db.collection("novels") \
                   .document(novel_id) \
                   .collection("characters")

    # запит за полем user_id
    snaps = chars_coll.where("user_id", "==", current_user.user_id).stream()
    for doc in snaps:
        return CharacterIdResponse(character_id=doc.id)

    # якщо жодного не знайшли - 404
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="The current user doesn't have a character in this novel yet"
    )

# Зберігаємо текст у сегмент (вручну написаний) і навіть якщо це як пролог (1-й)
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
    # Перевіряємо, що новела існує
    novel_ref = db.collection("novels").document(novel_id)
    if not novel_ref.get().exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Novel not found")

    # Зберігається новий сегмент
    segment_id = str(uuid.uuid4())
    seg = TextSegment(
        segment_id=segment_id,
        author_id=current_user.user_id,
        content=edit.content,
        created_at=datetime.now(timezone.utc),
    )
    novel_ref.collection("text_segments").document(segment_id).set(seg.model_dump())

    # Оновлюється поточна позиція і час оновлення самої новели
    novel_ref.update({
        "current_position": segment_id,
        "updated_at": datetime.now(timezone.utc)
    })
    return seg

# Редагувати сегмент Новели
@router.put( "/{novel_id}/text/segments/{segment_id}",
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

    # перевіряємо права автора
    data = snap.to_dict()
    if data.get("author_id") != current_user.user_id:
        raise HTTPException(403, "Not allowed to edit this segment")
    # зберігаємо оновлений контент, але зберігаємо оригінальну дату створення
    updated = {
        "content":    edit.content,
        "created_at": data["created_at"],  # зберігаємо оригінальну дату
    }

    # оновлюємо у новели мітку часу
    db.collection("novels").document(novel_id).update({
        "updated_at": datetime.now(timezone.utc)
    })

    seg_ref.set(updated, merge=True)
    out = TextSegment(segment_id=segment_id, **updated)
    return out

# Отримати всі сегменти новели за айді новели
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
    "/{novel_id}/text/segments/{segment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a text segment (author or session participant only)"
)
async def delete_text_segment(
    novel_id: str,
    segment_id: str,
    db: FirestoreClient = Depends(get_db),
    current_user: User  = Depends(get_current_user),
):
    novel_ref = db.collection("novels").document(novel_id)
    if not novel_ref.get().exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Novel not found")

    # load segment
    seg_ref = novel_ref.collection("text_segments").document(segment_id)
    seg_snap = seg_ref.get()
    if not seg_snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")

    seg_data = seg_snap.to_dict()

    # check permission: either the original author…
    if seg_data.get("author_id") == current_user.user_id:
        allowed = True
    else:
        # …або учасник (в тому числі host) у будь-якій мультплеєрній сесії для цієї новели
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

    # delete the segment
    seg_ref.delete()

    # if this was the novel’s current_position, clear it
    novel = novel_ref.get().to_dict()
    if novel.get("current_position") == segment_id:
        novel_ref.update({
            "current_position": None,
            "updated_at": datetime.now(timezone.utc)
        })
    else:
        novel_ref.update({"updated_at": datetime.now(timezone.utc)})

    return Response(status_code=status.HTTP_204_NO_CONTENT)

# Список новел, створених користувачем (не враховує ті де бере участь)
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

# Список новел за 1 жанром
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
    Поверне тільки ті новели, масив genres яких містить **все**
    передані в запиті значення.
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

@router.get(
    "/public/by-all-genres",
    response_model=List[Novel],
    summary="List public novels matching ALL of the given genres",
)
async def list_public_novels_by_all_genres(
    genres: List[Genre] = Query(...),
    db: FirestoreClient = Depends(get_db),
):
    genre_values = [g.value for g in genres]
    if not genre_values:
        return []

    # спочатку фільтрація за першим жанром + публічність
    first = genre_values[0]
    snaps = (
        db.collection("novels")
          .where("is_public", "==", True)              # ← только публичные
          .where("genres", "array_contains", first)
          .stream()
    )

    result: List[Novel] = []
    for doc in snaps:
        data = doc.to_dict()
        # проверяем, что все жанры есть
        if all(g in data.get("genres", []) for g in genre_values):
            result.append(Novel.model_validate(data))
    return result



@router.get("/user/{user_id}/both",response_model=List[Novel],summary="Novels where the user is both Author and Player")
async def list_author_and_player_novels(
    user_id: str,
    db: FirestoreClient = Depends(get_db),
):
    """
    Returns all novels in which user_id is both
    is present in both users_author and user_players.
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

# Збереження зображення новели в БД
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
    # Перевіряємо, що новела існує і поточний користувач - її автор
    ref = db.collection("novels").document(novel_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Novel not found")
    novel = Novel.model_validate(snap.to_dict())
    if current_user.user_id not in novel.users_author:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an author can upload images")

    # Заливаємо файл у Cloud Storage
    bucket = get_storage_bucket()
    blob = bucket.blob(f"novels/{novel_id}/{file.filename}")
    contents = await file.read()
    blob.upload_from_string(contents, content_type=file.content_type)
    blob.make_public()
    # Отримуємо публічний URL
    url = blob.public_url

    # Зберігаємо рядок URL у полі cover_image_url
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
    Видаляє цю новелу з усіх п'яти списків і додає в той, що вказаний у new_status.
    """
    user_ref = db.collection("users").document(current.user_id)

    # спочатку видаляємо з усіх списків
    updates = {}
    for field in ("playing_novels", "planned_novels", "completed_novels", "favorite_novels", "abandoned_novels"):
        updates[field] = firestore.ArrayRemove([novel_id])

    # потім додаємо в потрібний
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

    # перевіряємо кожен список по порядку
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

    # виймаємо з користувача потрібний список ID
    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")
    u = user_doc.to_dict()

    # map status → поле в документі User
    field_map = {
        "created":   "created_novels",
        "playing":   "playing_novels",
        "planned":   "planned_novels",
        "completed": "completed_novels",
        "favorite":  "favorite_novels",
        "abandoned": "abandoned_novels",
    }

    # збираємо set з потрібних списків
    ids = set()
    if user_status == "all":
        ids |= set(u.get("created_novels", []))
        ids |= set(u.get("playing_novels", []))
    else:
        ids |= set(u.get(field_map[user_status], []))

    # якщо після цього порожньо - повернемо порожній список
    if not ids:
        return []

    # робимо get за всіма цими novel_id
    novels = []
    for nid in ids:
        snap = db.collection("novels").document(nid).get()
        if not snap.exists:
            continue
        nov = Novel.model_validate(snap.to_dict())
        if genre is None or genre in nov.genres:
            novels.append(nov)

    return novels