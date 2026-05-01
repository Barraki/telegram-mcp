#!/usr/bin/env python3
"""
Авто-дайджест: JSON с новостями → текст → MP3.

Принимает JSON через stdin. Формат:
[
  {"channel": "РИА Новости", "text": "...", "date": "2026-04-10 10:00"},
  {"channel": "РБК", "text": "...", "date": "2026-04-10 11:00"}
]

Использование:
    # Из stdin
    echo '[{"channel":"РИА","text":"текст новости","date":"2026-04-10 10:00"}]' | python3 auto_digest.py

    # Из файла
    python3 auto_digest.py news.json

    # Только текст
    python3 auto_digest.py news.json --no-audio

    # С другим голосом
    python3 auto_digest.py news.json --voice svetlana

    # Кастомный выход
    python3 auto_digest.py news.json --output today.mp3
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime

import edge_tts

# ─── Фильтры ───────────────────────────────────────────────
SKIP = [
    "Подписаться", "Надсилайте нам фото", "📲 Надіслати фото",
    "Прислать новость", "Реклама на канале", "Приложение РБК",
    "Канал РБК в MAX", "Не грузятся фото", "Читайте нас в MAX",
    "Если у вас не загружается", "🐚 Если у вас не загружается",
    'Сайт "Страна"', "Подписаться | Предложить новость",
    "🧡🧡", "💰🩶", "🛠Установка", "🚗Доставка", "🪙Оплата",
    "🏠Наш адрес", "График работы", "В НАЛИЧИИ", "Цена со скидкой",
]

MEDIA_ONLY = "[Media/No text]"


def is_skip(text: str) -> bool:
    s = text.strip()
    if not s or s == MEDIA_ONLY or len(s) < 25:
        return True
    hits = sum(1 for p in SKIP if p in s)
    return hits >= 2


def clean(text: str) -> str:
    lines = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line == MEDIA_ONLY:
            continue
        if any(p in line for p in SKIP):
            continue
        lines.append(line)
    return " ".join(lines)


def normalize(text: str) -> str:
    emoji = re.compile(
        "["
        "\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0\U000024C2-\U0001F251"
        "\U0001f926-\U0001f937\U00010000-\U0010FFFF"
        "\u2640-\u2642\u2600-\u2B55\u200d\u23cf\u23e9"
        "\u23f3\u23f8\ufe00-\ufe0f"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    """Простое TF-подобное сходство по общим словам."""
    wa = set(w.lower().strip(".,:;!?\"'()—–-") for w in a.split() if len(w) > 3)
    wb = set(w.lower().strip(".,:;!?\"'()—–-") for w in b.split() if len(w) > 3)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def group_posts(posts: list[dict], threshold: float = 0.35) -> list[dict]:
    """
    Группируем по сходству текстов.
    Результат: [{"channels": [...], "texts": [...]}]
    """
    groups: list[dict] = []

    for p in posts:
        placed = False
        for g in groups:
            # Сравниваем с каждым текстом в группе
            best = max(similarity(p["text"], t) for t in g["texts"])
            if best >= threshold:
                if p["channel"] not in g["channels"]:
                    g["channels"].append(p["channel"])
                if p["text"] not in g["texts"]:
                    g["texts"].append(p["text"])
                placed = True
                break
        if not placed:
            groups.append({"channels": [p["channel"]], "texts": [p["text"]]})

    return groups


def build_script(groups: list[dict], target_date: str) -> str:
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_str = dt.strftime("%-d %B %Y")

    lines = [
        f"Дайджест новостей за {date_str}.",
        "Девять каналов: РИА, Страна, РБК, Дніпро, Донецк, Форбс, Новое Издание, Маш и ДС.",
        "",
    ]

    for g in groups:
        ch = ", ".join(g["channels"])
        # Основной текст + доп. детали
        main_text = g["texts"][0]
        extras = g["texts"][1:]
        if extras:
            # Берём самое длинное дополнение для контекста
            extra = max(extras, key=len)[:200]
            main_text += ". " + extra
        lines.append(f"[{ch}]")
        lines.append(main_text)
        lines.append("")

    lines.append("Это был дайджест. Хотите подробнее по какой-то теме?")
    return "\n".join(lines)


def load_news(file_arg: str) -> list[dict]:
    if file_arg == "-":
        return json.load(sys.stdin)
    with open(file_arg, "r", encoding="utf-8") as f:
        return json.load(f)


VOICES = {"dmitry": "ru-RU-DmitryNeural", "svetlana": "ru-RU-SvetlanaNeural"}


async def tts(text: str, voice: str, output: str):
    comm = edge_tts.Communicate(text, voice)
    await comm.save(output)
    size = os.path.getsize(output) / (1024 * 1024)
    print(f"✅ {output} ({size:.1f} MB)", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="JSON новости → MP3 дайджест")
    p.add_argument("file", nargs="?", default="-", help="JSON файл или '-' stdin")
    p.add_argument("--voice", "-v", default="dmitry")
    p.add_argument("--output", "-o", default=None)
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--pretty", action="store_true", help="Красивый вывод текста")
    args = p.parse_args()

    # Загрузка
    raw = load_news(args.file)

    # Фильтр
    posts = []
    for item in raw:
        text = item.get("text", "").strip()
        if is_skip(text):
            continue
        text = normalize(clean(text))
        if len(text) < 30:
            continue
        posts.append({
            "channel": item.get("channel", "?"),
            "text": text,
            "date": item.get("date", "")[:10],
        })

    if not posts:
        print("❌ Нет постов после фильтрации", file=sys.stderr)
        sys.exit(1)

    # Группировка
    groups = group_posts(posts)

    # Дата
    target_date = posts[0]["date"] or str(date.today())

    # Скрипт
    script = build_script(groups, target_date)

    # Вывод
    if args.pretty:
        print("═══ ТЕКСТ ДАЙДЖЕСТА ═══")
        print(script)
        print("═══ КОНЕЦ ═══")
    else:
        print(script)

    if args.no_audio:
        return

    # Аудио
    voice = VOICES.get(args.voice.lower(), args.voice)
    output = args.output or f"digest_{target_date}.mp3"

    print(f"🎙️ {voice} | 📝 {len(script)} ch", file=sys.stderr)
    asyncio.run(tts(script, voice, output))


if __name__ == "__main__":
    main()
