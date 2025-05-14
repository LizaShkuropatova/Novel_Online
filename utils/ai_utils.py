import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict, Optional
from google.cloud.firestore import Client as FirestoreClient
from models import Novel, TextSegment, Character


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Общая обёртка под любой чат-запрос
def chat_with_model(
    messages: List[dict],
    model: str = os.getenv("AI_MODEL", "gpt-3.5-turbo"),
    max_tokens: int = 200,
    temperature: float = 0.8,
) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()

# Генерация названия новеллы
def generate_title(
    genres: List[str],
    description: str = "",
    setting: str = "",
    max_tokens: int = 20,
) -> str:
    """
    Генерирует лаконичное название для новеллы на основе жанра
    (и при наличии — описания и сеттинга).
    """
    system_msg = (
        "You are a creative assistant specialized in generating evocative novel titles. "
        "Given the genre (and optionally description, setting), produce a concise title."
        "Do NOT include quotation marks or / in the output."
    )
    genre_str = ", ".join(genres)
    user_msg = f"Genres: {genre_str}\n"
    if description:
        user_msg += f"Description: {description}\n"
    if setting:
        user_msg += f"Setting: {setting}\n"
    user_msg += "\nGenerate a title (just the title)."

    return chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )


# Генерация описания новеллы
def generate_novel_description(
    title: str,
    genres: List[str],
    existing_setting: str = "",
    max_tokens: int = 300,
) -> str:
    system_msg = (
        "You are a creative writing assistant."
        "Write an appealing description for a novel in the third person, addressing the reader in the second person"
        "Do NOT invent new character names; focus on describing what happens to the protagonist and other figures in the world. "
        "Highlight the main conflict, unique elements of the world (e.g., magic, danger) and the emotional stakes."
        "Keep it concise (1 paragraph), evocative, and without bullet points."
    )
    genre_str = ", ".join(genres)
    user_msg = f"Title: {title}\nGenres: {genre_str}\n"
    if existing_setting:
        user_msg += f"Setting: {existing_setting}\n"
    user_msg += "\nWrite the novel’s description\nDescription:"

    return chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )


# Генерация сеттинга новеллы
def generate_novel_setting(
    title: str,
    genres: List[str],
    existing_description: str = "",
    max_tokens: int = 300,
) -> str:
    system_msg = (
        "You are a world-building assistant."
        "Provide a concise, factual overview of the novel's setting."
        "Focus on political structures, magic system, key factions, technological level and main locations."
        "Do not restate the title or use flowery prose."
    )
    genre_str = ", ".join(genres)
    user_msg = f"Title: {title}\nGenres: {genre_str}\n"
    if existing_description:
        user_msg += f"Description: {existing_description}\n"
    user_msg += "\n\nList 4–6 bullet points."

    return chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )

# Генерация персонажа: дополняем отсутствующие поля
def generate_character(
    title: str,
    genres: List[str],
    setting: Optional[str] = "",
    fields: Optional[List[str]] = None,
    existing: Optional[Dict[str, str]] = None,
    max_tokens: int = 200,
    temperature: float = 0.8,
) -> Dict[str, str]:
    existing = existing or {}

    system_msg = (
        "You are a character design assistant."
        "Fill in only the missing or requested character fields based on the provided context."
        "Respond using labels 'Name:', 'Appearance:', 'Backstory:', 'Traits:'."
    )

    # Правильная сборка списка строк
    genre_str = ", ".join(genres)
    parts: List[str] = [
        f"Title: {title}",
        f"Genres: {genre_str}",
    ]
    if setting:
        parts.append(f"Setting: {setting}")

    for field in ("name", "appearance", "backstory", "traits"):
        val = existing.get(field)
        if val:
            parts.append(f"{field.capitalize()}: {val}")

    # Если нужны генерации дополнительных полей
    if fields:
        parts.append("")  # пустая строка, чтобы отделить
        parts.append("Generate:")
        for f in fields:
            parts.append(f"- {f.capitalize()}")

    user_msg = "\n".join(parts)

    # Запрос в модель
    raw = chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # Парсим ответ
    result: Dict[str, str] = {}
    for line in raw.splitlines():
        if ':' in line:
            key, val = line.split(':', 1)
            result[key.strip().lower()] = val.strip()
    return result

def load_novel_context(
    novel_id: str,
    db: FirestoreClient
) -> dict:
    """
    Загружает:
        основной документ Novel,
        все текстовые сегменты (в порядке created_at),
        все персонажи,
        при наличии .novel_original_id — текст оригинала.
    """
    #Новелла
    doc = db.collection("novels").document(novel_id).get()
    if not doc.exists:
        raise ValueError("Novel not found")
    novel = Novel.model_validate(doc.to_dict())

    # Свои тексты
    own_snaps = (
        db.collection("novels")
          .document(novel_id)
          .collection("text_segments")
          .order_by("created_at")
          .stream()
    )
    own_texts = [s.to_dict()["content"] for s in own_snaps]

    # Персонажи
    char_snaps = (
        db.collection("novels")
          .document(novel_id)
          .collection("characters")
          .stream()
    )
    characters = [c.to_dict() for c in char_snaps]

    # Контекст оригинала
    orig_texts: List[str] = []
    if novel.novel_original_id:
        orig_snaps = (
            db.collection("novels")
              .document(novel.novel_original_id)
              .collection("text_segments")
              .order_by("created_at")
              .stream()
        )
        orig_texts = [s.to_dict()["content"] for s in orig_snaps]

    return {
        "novel": novel,
        "own_text": "\n\n".join(own_texts),
        "characters": characters,
        "original_context": orig_texts,
    }

def generate_prologue(
    title: str,
    description: str,
    genres: List[str],
    setting: str,
    characters: List[Dict[str, str]],
    initial_context: Optional[List[str]] = None,
    max_tokens: int = 400,
) -> str:
    system_msg = (
        "You are a creative writing assistant for interactive novel"
        "Write in the second or third person 1–2 paragraph prologue that introduces the world, main conflict and these characters,"
        "building on the existing story foundation but avoiding direct continuation of old characters."
    )
    # если есть фон оригинала, вставляем его
    user_parts = []
    if initial_context:
        user_parts.append("Background context (do not continue specific original characters):")
        user_parts.extend(f"- {line}" for line in initial_context)
        user_parts.append("")  # разделитель

    user_parts += [
        f"Title: {title}",
        f"Genres: {', '.join(genres)}",
        f"Description: {description}",
        f"Setting: {setting}",
        "Characters:",
    ]
    user_parts += [f"- {c['name']}: {c['backstory']}" for c in characters]
    user_parts.append("\nWrite the prologue:")

    return chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": "\n".join(user_parts)},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )

def generate_continuation(
    full_text: str,
    title: str,
    description: str,
    genres: List[str],
    setting: str,
    characters: List[Dict[str, str]],
    initial_context: Optional[List[str]] = None,
    max_tokens: int = 300,
) -> str:
    system_msg = (
        "You are a creative writing assistant."
        "Continue the following interactive novel, maintaining tone and advancing the main plot. Write in the second or third person."
        "Use the background context only as a foundation; do not reintroduce original characters."
    )
    user_parts = []
    if initial_context:
        user_parts.append("Background context (plot foundation):")
        user_parts.extend(f"- {line}" for line in initial_context)
        user_parts.append("")  # разделитель

    user_parts.extend([
        f"Title: {title}",
        f"Description: {description}",
        f"Genres: {', '.join(genres)}",
        f"Setting: {setting}",
        "",
        "Characters in this copy:",
    ])
    # список персонажей
    for char in characters:
        user_parts.append(f"- {char['name']}: {char.get('backstory','')}")

    user_parts.extend([
        "",
        "Current story text:",
        full_text,
        "",
        "Write the next passage:",
    ])

    user_msg = "\n".join(user_parts)

    return chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=0.8,
    )

def generate_three_plot_options(
    title: str,
    description: str,
    genres: List[str],
    setting: str,
    characters: List[Dict[str, str]],
    original_context: Optional[List[str]] = None,
    full_text: str = "",
    max_tokens: int = 300,
) -> List[str]:
    system_msg = (
        "You are an interactive novel assistant. "
        "Based on the novel’s world, existing text, and characters, "
        "propose exactly three distinct options for the next scene. "
        "Label them '1.', '2.', '3.' at the start of each line."
    )
    parts: List[str] = []
    if original_context:
        parts.append("Background context (foundation):")
        parts.extend(f"- {line}" for line in original_context)
        parts.append("")

    parts.extend([
        f"Title: {title}",
        f"Description: {description}",
        f"Genres: {', '.join(genres)}",
        f"Setting: {setting}",
        "",
        "Characters:",
    ])
    for c in characters:
        parts.append(f"- {c['name']}: {c.get('backstory','')}")

    if full_text:
        parts.extend(["", "Current story text:", full_text])

    parts.append("\nProvide three next-scene options:")

    user_msg = "\n".join(parts)

    raw = chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=0.8,
    )

    # Парсим:
    opts = []
    for line in raw.splitlines():
        if line.strip().startswith(("1.","2.","3.")):
            _, text = line.split(".",1)
            opts.append(text.strip())
    return opts