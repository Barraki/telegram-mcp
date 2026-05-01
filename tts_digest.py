#!/usr/bin/env python3
"""
Генератор аудио-дайджеста из текста.

Использование:
    # Из файла
    python3 tts_digest.py script.txt

    # Из stdin (пайп)
    echo "Привет мир" | python3 tts_digest.py -

    # Из аргумента
    python3 tts_digest.py --text "Привет мир"

    # С выбором голоса
    python3 tts_digest.py script.txt --voice ru-RU-SvetlanaNeural

    # Задать выход
    python3 tts_digest.py script.txt --output digest.mp3
"""

import argparse
import asyncio
import os
import sys

import edge_tts

VOICES = {
    "dmitry": "ru-RU-DmitryNeural",
    "svetlana": "ru-RU-SvetlanaNeural",
}

DEFAULT_VOICE = VOICES["dmitry"]
DEFAULT_OUTPUT = "digest.mp3"


async def generate_audio(text: str, voice: str, output: str) -> str:
    """Сгенерировать MP3 из текста."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output)
    size = os.path.getsize(output) / (1024 * 1024)
    print(f"✅ Готово: {output} ({size:.1f} MB)", file=sys.stderr)
    return output


def resolve_voice(name: str) -> str:
    """Вернуть полный ID голоса по короткому имени или вернуть как есть."""
    return VOICES.get(name.lower(), name)


def read_text(args: argparse.Namespace) -> str:
    """Прочитать текст из файла, stdin или --text."""
    if args.text:
        return args.text
    if args.file == "-":
        return sys.stdin.read()
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            return f.read()
    # По умолчанию читаем stdin
    return sys.stdin.read()


def main():
    parser = argparse.ArgumentParser(
        description="TTS: текст → MP3 (Edge TTS)"
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="-",
        help="Файл с текстом или '-' для stdin (по умолчанию)",
    )
    parser.add_argument(
        "--text", "-t",
        default=None,
        help="Текст напрямую из аргумента",
    )
    parser.add_argument(
        "--voice", "-v",
        default=DEFAULT_VOICE,
        help="Голос: dmitry, svetlana или полный ID (по умолчанию dmitry)",
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help=f"Путь к выходному MP3 (по умолчанию {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    text = read_text(args).strip()
    if not text:
        print("❌ Пустой текст. Передайте текст через файл, stdin или --text", file=sys.stderr)
        sys.exit(1)

    voice = resolve_voice(args.voice)
    print(f"🎙️ Голос: {voice}", file=sys.stderr)
    print(f"📝 Символов: {len(text)}", file=sys.stderr)

    asyncio.run(generate_audio(text, voice, args.output))


if __name__ == "__main__":
    main()
