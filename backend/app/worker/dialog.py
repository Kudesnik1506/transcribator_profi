# Conservative for Cyrillic: BPE tokenizers typically split Russian text
# into more tokens per character than English (~2 chars/token vs ~4).
CHARS_PER_TOKEN = 2

SYSTEM_PROMPT = (
    "Ты отвечаешь на вопросы по транскрипту записи совещания. "
    "Используй только информацию из транскрипта ниже. "
    "Если ответа в транскрипте нет, прямо скажи, что в записи об этом не говорилось — не придумывай.\n\n"
    "Форматируй ответ в Markdown, чтобы его было легко читать с телефона: короткие "
    "абзацы вместо одного сплошного текста, нумерованный или маркированный список для "
    "перечислений, **жирный** для ключевых тезисов. Можно изредка добавить уместный "
    "эмодзи, но не в каждом предложении — тон живой и дружелюбный, но по делу."
)


class TranscriptTooLongError(RuntimeError):
    pass


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def build_dialog_messages(
    transcript_text: str,
    history: list[dict],
    question: str,
    max_context_tokens: int,
) -> list[dict]:
    total_tokens = (
        estimate_tokens(transcript_text)
        + sum(estimate_tokens(m["content"]) for m in history)
        + estimate_tokens(question)
    )
    if total_tokens > max_context_tokens:
        raise TranscriptTooLongError(
            f"диалог не помещается в контекст модели: ~{total_tokens} токенов при лимите {max_context_tokens}"
        )

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Транскрипт записи:\n\n{transcript_text}"},
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": question})
    return messages
