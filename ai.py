import os
import requests
import json
import pytesseract
import streamlit as st

FOLDER_ID = "b1gduq5bjgu0km5qubgu"

YANDEX_MODEL_LITE = "yandexgpt-lite"
YANDEX_MODEL_CHAT = "yandexgpt"

YANDEX_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


def get_yandex_api_key() -> str:
    try:
        return st.secrets["YANDEX_API_KEY"]
    except Exception as e:
        raise RuntimeError(
            "Не найден YANDEX_API_KEY. Добавь ключ в .streamlit/secrets.toml"
        ) from e


def get_yandex_headers() -> dict:
    return {
        "Authorization": f"Api-Key {get_yandex_api_key()}",
        "Content-Type": "application/json"
    }


def post_to_yandex(messages, model_name: str, temperature: float, max_tokens: int) -> dict:
    data = {
        "modelUri": f"gpt://{FOLDER_ID}/{model_name}",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": max_tokens
        },
        "messages": messages
    }

    try:
        response = requests.post(
            YANDEX_COMPLETION_URL,
            headers=get_yandex_headers(),
            json=data,
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        raise RuntimeError(f"HTTP-ошибка YandexGPT: {e}") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Ошибка сети при обращении к YandexGPT: {e}") from e
    except ValueError as e:
        raise RuntimeError("YandexGPT вернул некорректный JSON.") from e


tesseract_path = os.getenv("TESSERACT_CMD")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path


def consult_with_methodologist(prompt: str, plan_context: dict = None) -> str:
    context_info = ""
    if plan_context:
        disciplines_count = plan_context.get("disciplines_count", 0)
        profile = plan_context.get("profile", "не определен")
        competencies_count = plan_context.get("competencies_count", 0)
        tf_count = plan_context.get("tf_count", 0)

        context_info = f"""
КОНТЕКСТ УЧЕБНОГО ПЛАНА:
- Профиль подготовки: {profile}
- Количество дисциплин: {disciplines_count}
- Компетенций ФГОС: {competencies_count}
- Трудовых функций: {tf_count}
"""

        disciplines_list = plan_context.get("disciplines_list", [])
        if disciplines_list:
            context_info += "\nДисциплины в плане:\n"
            for i, disc in enumerate(disciplines_list[:30], 1):
                context_info += f"{i}. {disc}\n"

    system_prompt = f"""
Ты — опытный методист вуза РФ с 20+ годами опыта в разработке учебных планов.

Твоя роль:
- Консультируешь по вопросам учебных планов
- Анализируешь соответствие ФГОС и профстандартам
- Даешь профессиональные рекомендации
- Отвечаешь на вопросы о компетенциях, дисциплинах, структуре плана
- Помогаешь улучшить учебный план

{context_info}

СТИЛЬ ОБЩЕНИЯ:
- Профессиональный, но дружелюбный
- Конкретный и по делу
- С примерами и рекомендациями
- Структурированные ответы

ОТВЕЧАЙ:
- На русском языке
- Развернуто, но по существу
- С конкретными рекомендациями
- Учитывая контекст учебного плана

ЕСЛИ СПРАШИВАЮТ О РЕДАКТИРОВАНИИ ПЛАНА:
- Объясни, что нужно сделать
- Предложи конкретные изменения
- Укажи, в каком режиме это лучше сделать (редактирование)
"""

    messages = [{"role": "system", "text": system_prompt}]

    if plan_context and plan_context.get("chat_history"):
        history = []
        for msg in plan_context["chat_history"][-5:]:
            role = msg.get("role")
            content = msg.get("content")
            if role and content:
                history.append({"role": role, "text": content})
        messages.extend(history)

    messages.append({"role": "user", "text": prompt})

    try:
        result = post_to_yandex(
            messages=messages,
            model_name=YANDEX_MODEL_CHAT,
            temperature=0.7,
            max_tokens=2000
        )
        return result["result"]["alternatives"][0]["message"]["text"]
    except Exception as e:
        return f"Извините, произошла ошибка при обращении к методисту: {e}"

def completion_with_ai(prompt: str) -> str:
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

    messages = [
        {"role": "system", "text": system_prompt},
        {"role": "user", "text": prompt}
    ]

    try:
        result = post_to_yandex(
            messages=messages,
            model_name=YANDEX_MODEL_CHAT,
            temperature=0.1,
            max_tokens=500
        )
        text = result["result"]["alternatives"][0]["message"]["text"]
    except Exception as e:
        return f"Ошибка обращения к модели: {e}"

    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return text[start:end]
    except ValueError:
        return f"Не удалось извлечь JSON.\nОтвет модели:\n{text}"
def call_yandex_lite(messages, temperature=0.3, max_tokens=1500):
    try:
        result = post_to_yandex(
            messages=messages,
            model_name=YANDEX_MODEL_LITE,
            temperature=temperature,
            max_tokens=max_tokens
        )
    except Exception as e:
        return f"Ошибка при обращении к YandexGPT: {e}"

    if "error" in result:
        return f"Ошибка сервиса YandexGPT: {result.get('error')}"

    try:
        return result["result"]["alternatives"][0]["message"]["text"]
    except Exception:
        return f"Ошибка при разборе ответа YandexGPT: {result}"

def enrich_discipline_metadata(discipline, df_fgos, tf_struct, profile="", fgos_text=""):
    import pandas as pd

    if df_fgos is None or (isinstance(df_fgos, pd.DataFrame) and df_fgos.empty):
        fgos_json = "[]"
        competencies_list = []
    else:
        try:
            fgos_json = df_fgos.to_json(orient="records", force_ascii=False)
            competencies_list = df_fgos["code"].tolist()
        except:
            fgos_json = "[]"
            competencies_list = []

    tf_list = tf_struct.get("TF", []) if tf_struct else []

    tf_info = []
    for tf in tf_list[:15]:
        tf_code = tf.get("code", "")
        tf_name = tf.get("name", "")[:100]
        if tf_code:
            tf_info.append(f"{tf_code}: {tf_name}")

    profile_hints = {
        "педагогика": "\nВАЖНО: Это педагогический профиль. Компетенции должны быть педагогическими (ОПК, ПК педагогические).",
        "образован": "\nВАЖНО: Это педагогический профиль. Компетенции должны быть педагогическими (ОПК, ПК педагогические).",
        "ивт": "\nПрофиль: ИТ. Компетенции должны быть техническими (ПК-1, ПК-2, ПК-3 и т.д.).",
        "информатик": "\nПрофиль: ИТ. Компетенции должны быть техническими (ПК-1, ПК-2, ПК-3 и т.д.).",
        "экономика": "\nПрофиль: Экономика. Компетенции должны быть экономическими (ПК-1, ПК-2, ПК-3 экономические).",
        "юриспруденция": "\nПрофиль: Юриспруденция. Компетенции должны быть юридическими (ПК-1, ПК-2, ПК-3 юридические).",
        "психология": "\nПрофиль: Психология. Компетенции должны быть психологическими (ПК-1, ПК-2, ПК-3 психологические).",
        "менеджмент": "\nПрофиль: Менеджмент. Компетенции должны быть управленческими (ПК-1, ПК-2, ПК-3 управленческие).",
        "дизайн": "\nПрофиль: Дизайн. Компетенции должны быть дизайнерскими (ПК-1, ПК-2, ПК-3 дизайнерские).",
    }

    profile_lower = profile.lower()
    profile_hint = ""
    for key, hint in profile_hints.items():
        if key in profile_lower:
            profile_hint = hint
            break

    if not profile_hint:
        profile_hint = f"\nПрофиль: {profile}. Выбирай компетенции, соответствующие данному профилю."

    prompt = f"""
Ты — опытный методист вуза РФ с 15+ годами опыта.

Дисциплина: "{discipline['name']}"
Профиль: {profile}
{profile_hint}

Доступные компетенции ФГОС (первые 20):
{', '.join(competencies_list[:20]) if competencies_list else 'Не указаны'}

Полный список компетенций:
{fgos_json[:2000]}

Трудовые функции профстандарта:
{chr(10).join(tf_info) if tf_info else 'Не указаны'}

ТВОЯ ЗАДАЧА:
1. Выбрать 2-4 компетенции ФГОС, которые РЕАЛЬНО формирует эта дисциплина
2. Выбрать 0-3 трудовые функции, которые РЕАЛЬНО поддерживает эта дисциплина
3. Написать КОНКРЕТНОЕ обоснование (не шаблонное!)

Верни строго JSON:
{{
  "competencies": ["УК-1", "ОПК-2"],
  "TF": ["A/01.3"],
  "reason": "Конкретное обоснование (до 150 символов)"
}}
"""

    try:
        raw = call_yandex_lite(
            [{"role": "user", "text": prompt}],
            temperature=0.1,
            max_tokens=800
        )

        start = raw.index("{")
        end = raw.rindex("}") + 1
        result = json.loads(raw[start:end])

        if not isinstance(result.get("competencies"), list):
            result["competencies"] = []
        if not isinstance(result.get("TF"), list):
            result["TF"] = []
        if not isinstance(result.get("reason"), str):
            result["reason"] = ""

        return result
    except:
        return {"competencies": [], "TF": [], "reason": ""}
