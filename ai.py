import requests 
import json 
import pytesseract 
import streamlit as st
YANDEX_API_KEY = st.secrets["YANDEX_API_KEY"]

FOLDER_ID = "b1gduq5bjgu0km5qubgu"

YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
YANDEX_MODEL_LITE = "yandexgpt-lite"

# Путь к Tesseract (Windows)
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

def call_yandex_lite(messages, temperature=0.3, max_tokens=1500):
    """
    Универсальная функция вызова YandexGPT Lite.
    messages — список сообщений [{"role": "user", "text": "..."}]
    """

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

    try:
        response = requests.post(
            YANDEX_API_URL,
            headers=headers,
            json=data,
            timeout=90
        )
    except Exception as e:
        return f"Ошибка сети при обращении к YandexGPT: {e}"

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


# ============================
# Обогащение дисциплины (ИИ)
# ============================

def enrich_discipline_metadata(discipline, df_fgos, tf_struct):
    """
    Определяет компетенции, ТФ и обоснование для дисциплины.
    """

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
        return {
            "competencies": [],
            "TF": [],
            "reason": ""
        }
