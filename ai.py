import os
import json
import requests
import pytesseract
import streamlit as st

FOLDER_ID = "b1gqit7sg06eelrvh80t"

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
            "maxTokens": str(max_tokens)
        },
        "messages": messages
    }

    response = requests.post(
        YANDEX_COMPLETION_URL,
        headers=get_yandex_headers(),
        json=data,
        timeout=60
    )

    if not response.ok:
        raise RuntimeError(
            f"Yandex API вернул {response.status_code}: {response.text}"
        )

    return response.json()


tesseract_path = os.getenv("TESSERACT_CMD")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path


def extract_json(text: str):
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {
            "action": "error",
            "value": "Некорректный JSON от модели"
        }


def call_yandex_lite(messages, temperature=0.3, max_tokens=1500):
    result = post_to_yandex(
        messages=messages,
        model_name=YANDEX_MODEL_LITE,
        temperature=temperature,
        max_tokens=max_tokens
    )

    return result["result"]["alternatives"][0]["message"]["text"]


def detect_profile_type(profile: str) -> str:
    p = (profile or "").lower()

    if any(x in p for x in [
        "информатика",
        "вычислительная техника",
        "информационные технологии",
        "программ",
        "09.03",
        "09.04"
    ]):
        return "technical"

    if any(x in p for x in [
        "педагог",
        "образование",
        "учитель",
        "44.03",
        "44.04"
    ]):
        return "pedagogical"

    if any(x in p for x in [
        "живопись",
        "искусств",
        "дизайн",
        "художе",
        "54.05",
        "50.03"
    ]):
        return "art"

    if any(x in p for x in [
        "математика",
        "физика",
        "прикладные математика и физика",
        "03.04",
        "03.03"
    ]):
        return "science"

    return "generic"


def get_profile_warning(profile: str) -> str:
    profile_type = detect_profile_type(profile)

    if profile_type == "technical":
        return """
Профиль технический.
Запрещено использовать педагогические дисциплины, воспитательную работу,
методику преподавания, образовательные технологии, учащихся и обучающихся.
Фокус: программирование, алгоритмы, базы данных, операционные системы,
архитектура вычислительных систем, сети, разработка ПО.
"""

    if profile_type == "science":
        return """
Профиль физико-математический.
Запрещено использовать педагогические дисциплины, воспитательную работу,
методику преподавания, образовательные технологии, учащихся и обучающихся.
Фокус: математическое моделирование, физика, численные методы,
дифференциальные уравнения, вычислительные методы.
"""

    if profile_type == "art":
        return """
Профиль художественный.
Запрещено использовать ИТ-дисциплины и педагогический шаблон.
Фокус: академический рисунок, живопись, композиция, история искусств,
цветоведение, художественные материалы, реставрация.
"""

    if profile_type == "pedagogical":
        return """
Профиль педагогический.
Разрешены педагогика, психология, методика обучения, образовательные технологии,
воспитательная деятельность.
"""

    return f"""
Профиль: {profile}.
Выбирай только те компетенции и формулировки, которые соответствуют этому профилю.
"""


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

{get_profile_warning(profile)}
"""

        disciplines_list = plan_context.get("disciplines_list", [])
        if disciplines_list:
            context_info += "\nДисциплины в плане:\n"
            for i, disc in enumerate(disciplines_list[:30], 1):
                context_info += f"{i}. {disc}\n"

    system_prompt = f"""
Ты — методист вуза РФ.

Твоя роль:
- консультировать по учебным планам;
- анализировать соответствие ФГОС и профстандартам;
- давать рекомендации по улучшению учебного плана.

{context_info}

ВАЖНО:
1. Не переноси дисциплины и формулировки из других профилей.
2. Не используй педагогический шаблон для непедагогических направлений.
3. Если профиль технический, художественный или физико-математический,
   не предлагай педагогические дисциплины.
4. Отвечай только по текущему профилю.

ОТВЕЧАЙ:
- на русском языке;
- профессионально;
- конкретно;
- без лишней воды.
"""

    messages = [{"role": "system", "text": system_prompt}]

    messages.append({"role": "user", "text": prompt})

    try:
        result = post_to_yandex(
            messages=messages,
            model_name=YANDEX_MODEL_CHAT,
            temperature=0.3,
            max_tokens=2000
        )

        return result["result"]["alternatives"][0]["message"]["text"]

    except Exception as e:
        return f"Извините, произошла ошибка при обращении к методисту: {e}"


def completion_with_ai(prompt: str) -> str:
    system_prompt = """
Ты — система редактирования учебного плана.

ТВОЯ ЗАДАЧА:
Преобразовать команду пользователя в один JSON-объект.

ТЫ НЕ ДОЛЖЕН:
- писать пояснения;
- писать текст до JSON;
- писать текст после JSON;
- добавлять новую дисциплину, если пользователь просит изменить существующую;
- менять профиль подготовки;
- придумывать педагогические дисциплины;
- возвращать Markdown.

ВАЖНОЕ ПРАВИЛО:
Если пользователь пишет "добавь экзамен по дисциплине X",
это значит нужно ОБНОВИТЬ поле "Форма контроля" у существующей дисциплины X,
а НЕ добавлять новую дисциплину.

Если пользователь пишет "увеличь часы по дисциплине X",
нужно обновить поле "Часы", но не уменьшать значение случайно.
Если точное значение не указано, верни error.

ФОРМАТЫ JSON:

UPDATE:
{
  "action": "update",
  "discipline": "Название дисциплины",
  "field": "Часы",
  "value": 144
}

UPDATE ФОРМЫ КОНТРОЛЯ:
{
  "action": "update",
  "discipline": "Операционные системы",
  "field": "Форма контроля",
  "value": "экзамен"
}

MOVE:
{
  "action": "update",
  "discipline": "Архитектура вычислительных систем",
  "field": "Семестр",
  "value": 4
}

DELETE:
{
  "action": "delete",
  "discipline": "Название дисциплины"
}

ADD:
{
  "action": "add",
  "field": "row",
  "value": {
    "Блок": "Блок 1. Вариативная часть",
    "Семестр": 1,
    "Дисциплина": "Название дисциплины",
    "Часы": 72,
    "Форма контроля": "зачёт",
    "Компетенции ФГОС": [],
    "Трудовые функции": "",
    "Обоснование": "Добавлено через ИИ-консультанта"
  }
}

ERROR:
{
  "action": "error",
  "value": "Причина ошибки"
}

Верни только JSON.
"""

    messages = [
        {"role": "system", "text": system_prompt},
        {"role": "user", "text": prompt}
    ]

    try:
        result = post_to_yandex(
            messages=messages,
            model_name=YANDEX_MODEL_CHAT,
            temperature=0.02,
            max_tokens=500
        )

        text = result["result"]["alternatives"][0]["message"]["text"]
        parsed = extract_json(text)

        return json.dumps(parsed, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "action": "error",
            "value": f"Ошибка обращения к модели: {e}"
        }, ensure_ascii=False)


def enrich_discipline_metadata(discipline, df_fgos, tf_struct, profile="", fgos_text=""):
    import pandas as pd

    discipline_name = discipline.get("name", "") if isinstance(discipline, dict) else str(discipline)

    if df_fgos is None or (isinstance(df_fgos, pd.DataFrame) and df_fgos.empty):
        fgos_json = "[]"
        competencies_list = []
    else:
        try:
            fgos_json = df_fgos.to_json(orient="records", force_ascii=False)
            competencies_list = df_fgos["code"].tolist()
        except Exception:
            fgos_json = "[]"
            competencies_list = []

    tf_list = tf_struct.get("TF", []) if tf_struct else []

    tf_info = []
    for tf in tf_list[:15]:
        tf_code = tf.get("code", "")
        tf_name = tf.get("name", "")[:120]

        if tf_code and tf_name:
            tf_info.append(f"{tf_code}: {tf_name}")
        elif tf_code:
            tf_info.append(tf_code)

    profile_warning = get_profile_warning(profile)

    prompt = f"""
Ты — методист российского вуза.

Дисциплина:
{discipline_name}

Профиль подготовки:
{profile}

{profile_warning}

Доступные компетенции ФГОС:
{', '.join(competencies_list[:25]) if competencies_list else 'Не указаны'}

Полный список компетенций:
{fgos_json[:2500]}

Трудовые функции профстандарта:
{chr(10).join(tf_info) if tf_info else 'Не указаны'}

ЗАДАЧА:
1. Выбери 2-4 компетенции ФГОС, которые реально формирует дисциплина.
2. Выбери 0-3 трудовые функции, которые реально поддерживает дисциплина.
3. Напиши короткое конкретное обоснование.

ЖЁСТКИЕ ПРАВИЛА:
1. Не используй педагогические формулировки для непедагогического профиля.
2. Не связывай технические дисциплины с воспитанием, обучающимися и методикой преподавания.
3. Не связывай художественные дисциплины с программированием, если это не указано в названии.
4. Используй только компетенции из списка.
5. Верни только JSON.

Формат:
{{
  "competencies": ["УК-1", "ОПК-2"],
  "TF": ["A/01.3"],
  "reason": "Краткое обоснование"
}}
"""

    try:
        raw = call_yandex_lite(
            [{"role": "user", "text": prompt}],
            temperature=0.03,
            max_tokens=800
        )

        result = extract_json(raw)

        if not isinstance(result.get("competencies"), list):
            result["competencies"] = []

        if not isinstance(result.get("TF"), list):
            result["TF"] = []

        if not isinstance(result.get("reason"), str):
            result["reason"] = ""

        valid_competencies = set(str(x) for x in competencies_list)

        result["competencies"] = [
            c for c in result["competencies"]
            if str(c) in valid_competencies
        ][:4]

        result["TF"] = result["TF"][:3]

        return result

    except Exception:
        return {
            "competencies": [],
            "TF": [],
            "reason": ""
        }