import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Общая обёртка под любой чат-запрос
def chat_with_model(
    messages: list[dict],
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
        "Given the genre (and optionally description/setting), produce a concise title."
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
        "You are a creative writing assistant. "
        "Write an engaging blurb for a novel, focusing on:\n"
        "- The main conflict or hook\n"
        "- The protagonist and their goal\n"
        "- Unique elements of the world (e.g., dragons, magic)\n"
        "- Tone and atmosphere (drama, adventure)\n"
        "Keep it concise (1–2 paragraphs), evocative, and without bullet points."
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
        "You are a world-building assistant. "
        "Provide a concise, factual overview of the novel's setting. "
        "Focus on political structures, magic system, key factions, "
        "technological level and main locations. "
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
        "You are a character design assistant. "
        "Fill in only the missing or requested character fields based on the provided context. "
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

    # если нужны генерации дополнительных полей
    if fields:
        parts.append("")  # пустая строка, чтобы отделить
        parts.append("Generate:")
        for f in fields:
            parts.append(f"- {f.capitalize()}")

    user_msg = "\n".join(parts)

    # запрос в модель
    raw = chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # парсим ответ
    result: Dict[str, str] = {}
    for line in raw.splitlines():
        if ':' in line:
            key, val = line.split(':', 1)
            result[key.strip().lower()] = val.strip()
    return result

def generate_prologue(
    title: str,
    description: str,
    genres: List[str],
    setting: str,
    characters: List[Dict[str, str]],
    max_tokens: int = 400,
) -> str:
    system_msg = (
        "You are a creative writing assistant. "
        "Write an engaging prologue (1–2 paragraphs) for an interactive novel. "
        "Introduce the world, main conflict and characters."
    )
    genre_str = ", ".join(genres)
    user_msg = (
        f"Title: {title}\n"
        f"Genres: {genre_str}\n"
        f"Description: {description}\n"
        f"Setting: {setting}\n"
        "Characters:\n" +
        "\n".join(f"- {c['name']}: {c['backstory']}" for c in characters) +
        "\n\nWrite the prologue:"
    )
    return chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )

def generate_continuation(
    full_text: str,
    title: str,
    genres: List[str],
    max_tokens: int = 300,
) -> str:
    system_msg = (
        "You are a creative writing assistant. "
        "Continue the following interactive novel text, keeping style and tone consistent."
    )
    genre_str = ", ".join(genres)
    user_msg = (
        f"Title: {title}\n"
        f"Genres: {genre_str}\n\n"
        "Current text:\n"
        f"{full_text}\n\n"
        "Write the next passage:"
    )
    return chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=0.8,
    )

def generate_three_plot_options(
    full_text: str,
    title: str,
    genres: List[str],
    setting: str,
    max_tokens: int = 300,
) -> List[str]:
    system_msg = (
        "You are an interactive novel assistant. "
        "Based on the novel's text, propose exactly three distinct next-scene options. "
        "Label them '1.', '2.', '3.' at the start of each line."
    )
    genre_str = ", ".join(genres)
    user_msg = (
        f"Title: {title}\n"
        f"Genres: {genre_str}\n"
        f"Setting: {setting}\n\n"
        "Current full text:\n"
        f"{full_text}\n\n"
        "Provide three options for the next scene:"
    )
    raw = chat_with_model(
        [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=0.8,
    )
    # Ожидаем формат:
    # 1. Option A
    # 2. Option B
    # 3. Option C
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    opts = []
    for line in lines:
        if line[0].isdigit() and '.' in line:
            _, rest = line.split('.', 1)
            opts.append(rest.strip())
    return opts