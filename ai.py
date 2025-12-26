import requests
import json
import pytesseract
import streamlit as st

YANDEX_API_KEY = st.secrets["YANDEX_API_KEY"]
FOLDER_ID = "b1gduq5bjgu0km5qubgu"

YANDEX_MODEL_LITE = "yandexgpt-lite"
YANDEX_MODEL_CHAT = "yandexgpt"

YANDEX_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"


def completion_with_ai(prompt: str) -> str:
    """
    Генерация JSON-команды редактирования таблицы через YandexGPT (completion API).
    Работает с ключом yc.ai.foundationModels.execute.
    """

    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = """
Ты — ИИ, который ДОЛЖЕН возвращать строго JSON.

ТВОИ ЖЁСТКИЕ ПРАВИЛА:
1) Никакого текста до JSON.
2) Никакого текста после JSON.
3) Никаких комментариев.
4) Никаких пояснений.
5) Только один объект JSON.

Формат JSON-команды:

UPDATE:
{
  "action": "update",
  "discipline": "Название",
  "field": "Часы",
  "value": 72
}

DELETE:
{
  "action": "delete",
  "discipline": "Название"
}

ADD:
{
  "action": "add",
  "field": "row",
  "value": {
    "Блок": "...",
    "Семестр": 1,
    "Дисциплина": "...",
    "Часы": 72,
    "Форма контроля": "зачёт",
    "Компетенции ФГОС": [],
    "Трудовые функции": "",
    "Обоснование": "Добавлено вручную"
  }
}

ЕСЛИ НЕ МОЖЕШЬ ПОНЯТЬ КОМАНДУ — ВЕРНИ:
{
  "action": "error",
  "value": "Причина"
}
"""

    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt",
        "completionOptions": {
            "stream": False,
            "temperature": 0.1,
            "maxTokens": 500
        },
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": prompt}
        ]
    }

    response = requests.post(
        YANDEX_COMPLETION_URL,
        headers=headers,
        json=data
    )

    raw = response.text

    try:
        result = response.json()
        text = result["result"]["alternatives"][0]["message"]["text"]
    except:
        return f"Ошибка: модель вернула не JSON.\nСырой ответ:\n{raw}"

    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        json_str = text[start:end]
        return json_str
    except:
        return f"Не удалось извлечь JSON.\nОтвет модели:\n{text}"


def call_yandex_lite(messages, temperature=0.3, max_tokens=1500):
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "modelUri": f"gpt://{FOLDER_ID}/{YANDEX_MODEL_LITE}",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": max_tokens
        },
        "messages": messages
    }

    response = requests.post(
        YANDEX_COMPLETION_URL,
        headers=headers,
        json=data
    )

    try:
        result = response.json()
    except Exception:
        return "Ошибка: не удалось декодировать ответ YandexGPT как JSON."

    if "error" in result:
        return f"Ошибка сервиса YandexGPT: {result.get('error')}"

    try:
        return result["result"]["alternatives"][0]["message"]["text"]
    except Exception:
        return f"Ошибка при разборе ответа YandexGPT: {result}"


def enrich_discipline_metadata(discipline, df_fgos, tf_struct):
    prompt = f"""
Ты — методист вуза РФ.

Тебе дана дисциплина: "{discipline['name']}".

Вот список компетенций ФГОС:
{df_fgos.to_json(orient="records", force_ascii=False)}

Вот список трудовых функций профстандарта:
{json.dumps(tf_struct.get("TF", []), ensure_ascii=False)}

Определи:
- какие компетенции формирует эта дисциплина (2–4 кода),
- какие трудовые функции она поддерживает (0–3 кода),
- короткое обоснование (до 150 символов).

Верни строго JSON:
{{
  "competencies": ["УК-1", "ОПК-2"],
  "TF": ["A/01.3"],
  "reason": "Короткое обоснование"
}}
"""

    raw = call_yandex_lite(
        [{"role": "user", "text": prompt}],
        temperature=0.2,
        max_tokens=700
    )

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        return json.loads(raw[start:end])
    except:
        return {"competencies": [], "TF": [], "reason": ""}
