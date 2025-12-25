import streamlit as st
import fitz  # pymupdf
import re
import pandas as pd
import io
import requests
import json
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image


import streamlit as st

YANDEX_API_KEY = st.secrets["YANDEX_API_KEY"]

FOLDER_ID = "b1gduq5bjgu0km5qubgu"
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
YANDEX_MODEL_LITE = "yandexgpt-lite"

# Путь к Tesseract (Windows)
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"


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
    try:
        response = requests.post(YANDEX_API_URL, headers=headers, json=data, timeout=90)
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


def extract_text_from_pdf_file(uploaded_file):
    """
    1) Пытается извлечь текст через MuPDF.
    2) Если текста мало (скан) — включает OCR (Tesseract).
    """
    uploaded_file.seek(0)
    pdf_bytes = uploaded_file.read()

    text = ""
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
    except Exception:
        text = ""

    if len(text.strip()) > 50:
        return text

    # OCR
    ocr_text = ""
    try:
        images = convert_from_bytes(pdf_bytes)
        for img in images:
            ocr_text += pytesseract.image_to_string(img, lang="rus+eng") + "\n"
    except Exception as e:
        return f"OCR error: {e}"

    return ocr_text


def extract_competencies_full(text):
    """
    Извлекает УК, ОПК, ПК из текста ФГОС.
    """
    pattern = (
        r"(УК-\d+|ОПК-\d+|ПК-\d+)\.?\s*(.*?)\s*"
        r"(?=(УК-\d+|ОПК-\d+|ПК-\d+|IV\. Требования к условиям реализации программы бакалавриата|$))"
    )
    matches = re.findall(pattern, text, re.DOTALL)

    competencies = []
    for code, desc, _ in matches:
        desc = " ".join(desc.split())
        competencies.append({"code": code, "description": desc})
    return competencies


def dataframe_to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()




def extract_tf_codes_smart(full_text):
    """
    Ищет коды ТФ в любом виде (сканы, таблицы, разрывы).
    Примеры:
    A/01.3, A 01.3, A-01-3, A01.3 и т.п.
    """
    pattern = r"\b([A-D])\s*[/\-–—]?\s*(\d{2})\s*[\.\-–—,·]?\s*(\d)\b"
    matches = re.findall(pattern, full_text)

    codes = []
    for letter, num1, num2 in matches:
        code = f"{letter}/{num1}.{num2}"
        if code not in codes:
            codes.append(code)

    return codes


def get_context_for_tf(full_text, tf_code, window=25):
    """
    Находит строку с нормализованным кодом ТФ (A/01.3),
    учитывая, что в тексте он может быть написан по-разному.
    """
    lines = full_text.split("\n")

    letter, nums = tf_code.split("/")
    num1, num2 = nums.split(".")

    flex_pattern = rf"{letter}\s*[/\-–—]?\s*{num1}\s*[\.\-–—,·]?\s*{num2}"

    indices = [i for i, line in enumerate(lines) if re.search(flex_pattern, line)]

    if not indices:
        return ""

    i = indices[0]
    start = max(0, i - window)
    end = min(len(lines), i + window)
    return "\n".join(lines[start:end])


def analyze_single_tf_with_ai(tf_code, context_text):
    """
    Отправляет фрагмент текста по одной ТФ в ИИ и извлекает структуру.
    """
    prompt = f"""
Ты — эксперт по профессиональным стандартам РФ.

На входе — фрагмент текста профессионального стандарта,
относящийся к трудовой функции с кодом {tf_code}.

Извлеки строго по этому коду:
- name
- actions
- knowledge
- skills
- other

Верни строго JSON.
"""

    raw = call_yandex_lite(
        [{"role": "user", "text": prompt + context_text[:6000]}],
        max_tokens=1200,
        temperature=0.2
    )

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except:
        return {
            "code": tf_code,
            "name": "",
            "actions": [],
            "knowledge": [],
            "skills": [],
            "other": []
        }

    return {
        "code": tf_code,
        "name": data.get("name", ""),
        "actions": data.get("actions", []),
        "knowledge": data.get("knowledge", []),
        "skills": data.get("skills", []),
        "other": data.get("other", [])
    }


def analyze_prof_standard(full_text):
    tf_codes = extract_tf_codes_smart(full_text)
    if not tf_codes:
        return None, "Не найдено ни одного кода ТФ."

    tf_list = []
    for code in tf_codes:
        context = get_context_for_tf(full_text, code)
        tf_list.append(analyze_single_tf_with_ai(code, context))

    return {"TF": tf_list}, None
# =========================
# Сопоставление ФГОС ↔ профстандарт (Lite)
# =========================

def match_fgos_and_prof(df_fgos, tf_struct):
    """
    Устойчивое сопоставление ФГОС ↔ профстандарта на YandexGPT Lite.
    """

    fgos_short = df_fgos.copy()
    fgos_short["description"] = fgos_short["description"].apply(lambda x: str(x)[:300])

    tf_short = []
    for tf in tf_struct.get("TF", []):
        tf_short.append({
            "code": tf.get("code", ""),
            "name": (tf.get("name") or "")[:200],
            "actions": (tf.get("actions") or [])[:5],
            "knowledge": (tf.get("knowledge") or [])[:5],
            "skills": (tf.get("skills") or [])[:5],
        })

    prompt_match = f"""
Ты — эксперт по образовательным стандартам РФ.

Тебе даны:
- Компетенции ФГОС (коды и описания).
- Трудовые функции профессионального стандарта (код, название, действия, знания, умения).

Твоя задача — сопоставить компетенции и трудовые функции.

Верни строго JSON:

{{
  "matches": [
    {{
      "competency": "УК-1",
      "related_TF": ["A/01.3"],
      "comment": "Краткое пояснение"
    }}
  ],
  "gaps": [
    {{
      "TF": "B/03.4",
      "reason": "Почему не покрыта"
    }}
  ],
  "recommendations": ["Краткая рекомендация"]
}}

Компетенции ФГОС:
{fgos_short.to_json(orient="records", force_ascii=False)}

Трудовые функции:
{json.dumps(tf_short, ensure_ascii=False)}
"""

    raw = call_yandex_lite(
        [{"role": "user", "text": prompt_match}],
        temperature=0.25,
        max_tokens=1800
    )

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        return {
            "matches": data.get("matches", []),
            "gaps": data.get("gaps", []),
            "recommendations": data.get("recommendations", [])
        }, None
    except Exception:
        return {
            "matches": [],
            "gaps": [],
            "recommendations": ["ИИ вернул некорректный JSON при сопоставлении."]
        }, raw


def cluster_competencies_and_tf(df_fgos, tf_struct, profile_choice="Авто"):
    """
    Универсальная кластеризация компетенций и трудовых функций по тематическим группам.
    Работает для любого профиля.
    """

    prompt = f"""
Ты — эксперт по образовательным стандартам и профстандартам РФ.

Тебе даны:
- Компетенции ФГОС (код + описание),
- Трудовые функции профессионального стандарта (код + название + элементы содержания),
- Профиль подготовки: "{profile_choice}".

Задача:
1. Разбей ВСЕ компетенции ФГОС и трудовые функции на тематические группы (кластеры).
2. Для каждой группы опиши её тематический фокус.
3. Привяжи к каждой группе:
   - список кодов компетенций,
   - список кодов трудовых функций.

Верни строго JSON:

{{
  "clusters": [
    {{
      "name": "Название группы",
      "description": "Описание",
      "competencies": ["УК-1"],
      "TF": ["A/01.3"]
    }}
  ]
}}

Компетенции ФГОС:
{df_fgos.to_json(orient="records", force_ascii=False)}

Трудовые функции:
{json.dumps(tf_struct.get("TF", []), ensure_ascii=False)}
"""

    raw = call_yandex_lite(
        [{"role": "user", "text": prompt}],
        max_tokens=2500,
        temperature=0.25
    )

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        clusters = data.get("clusters", [])
        return clusters if isinstance(clusters, list) else []
    except:
        return []


def generate_disciplines_for_cluster(
    cluster, df_fgos, tf_struct, profile_choice="Авто",
    min_count=6, max_count=12
):
    cluster_name = cluster.get("name", "Тематический модуль")
    cluster_desc = cluster.get("description", "")
    comp_codes = cluster.get("competencies", [])
    tf_codes = cluster.get("TF", [])

    prompt = f"""
Ты — методист вуза РФ.

Профиль: "{profile_choice}".
Кластер: "{cluster_name}".
Описание: "{cluster_desc}".

Компетенции: {comp_codes}
Трудовые функции: {tf_codes}

Сгенерируй {min_count}–{max_count} дисциплин.

Важно:
- НЕ распределяй дисциплины по блокам.
- НЕ используй слова "обязательная" или "вариативная".
- Просто дай список дисциплин.

Верни строго JSON:
{{
  "disciplines": [
    {{
      "name": "Название дисциплины",
      "competencies": ["УК-1"],
      "TF": ["A/01.3"]
    }}
  ]
}}
"""

    raw = call_yandex_lite(
        [{"role": "user", "text": prompt}],
        max_tokens=2000,
        temperature=0.3
    )

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        discs = json.loads(raw[start:end]).get("disciplines", [])
    except:
        return []

    # --- распределение блоков Python ---
    obligatory = []
    variative = []

    for d in discs:
        name = d.get("name", "").lower()

        if is_fundamental(name):
            d["block_hint"] = "обязательная"
            obligatory.append(d)
        else:
            d["block_hint"] = "вариативная"
            variative.append(d)

    return obligatory + variative

def rebalance_blocks(all_discs):
    obligatory = [d for d in all_discs if d["block_hint"] == "обязательная"]
    variative = [d for d in all_discs if d["block_hint"] == "вариативная"]

    # ограничение: обязательных ≤ 20
    if len(obligatory) > 20:
        extra = obligatory[20:]
        for d in extra:
            d["block_hint"] = "вариативная"
        obligatory = obligatory[:20]
        variative.extend(extra)

    # ограничение: вариативных ≥ 20
    if len(variative) < 20:
        need = 20 - len(variative)
        candidates = [d for d in obligatory if not is_fundamental(d["name"])]
        for d in candidates[:need]:
            d["block_hint"] = "вариативная"
            variative.append(d)
            obligatory.remove(d)

    return obligatory + variative
def is_fundamental(name: str):
    name = name.lower()

    # 1. Фундаментальные признаки (приоритет)
    fundamental_keywords = [
        "математ", "анализ", "статистик", "вероятност",
        "исследование операций", "оптимизац", "механик",
        "моделирован", "расчёт", "расчет",
        "программирован", "python", "алгоритм", "структуры данных",
        "микроконтроллер", "кодирован",
        "архитектур", "операционн", "системн", "электротехн", "электроник",
        "сет", "network", "базы данных", "sql", "nosql", "субд",
        "автоматическ", "теория управления", "управление техническими системами",
        "информационные технологии", "it", "информационн систем",
    ]

    # 2. Прикладные признаки (только soft‑skills и гуманитарка)
    variative_keywords = [
        "маркетинг", "предприниматель", "бизнес",
        "управление качеством", "управление рисками",
        "управление персоналом", "медиаплан",
        "когнитив", "конфликтолог",
        "стресс", "чтение", "письмо",
        "риторика", "ораторское", "лидерство",
        "групповая динамика", "культур", "психолог", "социолог",
        "философ", "история", "экономик"
    ]

    # 3. Если есть фундаментальные признаки → ОБЯЗАТЕЛЬНАЯ
    if any(k in name for k in fundamental_keywords):
        return True

    # 4. Если есть soft‑skills → ВАРИАТИВНАЯ
    if any(k in name for k in variative_keywords):
        return False

    # 5. Всё остальное — вариативное
    return False


def generate_universal_disciplines(df_fgos, tf_struct, match_json, profile_choice="Авто"):
    """
    Этап 1: кластеризация → дисциплины → удаление дублей → догенерация → ребалансировка блоков.
    """

    clusters = cluster_competencies_and_tf(df_fgos, tf_struct, profile_choice)
    if not clusters:
        return []

    # 1. Генерация дисциплин по кластерам
    all_discs = []
    for cl in clusters:
        discs = generate_disciplines_for_cluster(cl, df_fgos, tf_struct, profile_choice)
        all_discs.extend(discs)

    # 2. Удаляем дубли
    seen = set()
    unique = []
    for d in all_discs:
        name = (d.get("name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            unique.append(d)

    # 3. Догенерация, если мало
    if len(unique) < 40:
        prompt_more = f"""
Ты ранее сгенерировал {len(unique)} дисциплин.
Нужно довести до 45–55.

Верни только новые дисциплины.
JSON:
{{
  "disciplines": [
    {{
      "name": "Название",
      "competencies": ["УК-1"],
      "TF": ["A/01.3"],
      "block_hint": "вариативная"
    }}
  ]
}}
"""
        raw = call_yandex_lite(
            [{"role": "user", "text": prompt_more}],
            max_tokens=2000,
            temperature=0.35
        )
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            extra = json.loads(raw[start:end]).get("disciplines", [])
        except:
            extra = []

        for d in extra:
            name = (d.get("name") or "").strip()
            if name and name not in seen:
                seen.add(name)
                unique.append(d)

    
    unique = rebalance_blocks(unique)

    return unique


def generate_disciplines_from_fgos_and_prof(df_fgos, tf_struct, match_json, profile_choice):
    discs = generate_universal_disciplines(df_fgos, tf_struct, match_json, profile_choice)
    st.session_state.debug_disciplines = discs
    return discs


def assign_hours_and_assessment(disciplines):
    """
    Lite назначает часы и форму контроля.
    """
    prompt = f"""
Ты — методист вуза РФ.

Назначь каждой дисциплине:
- количество часов (72–216),
- форму контроля: экзамен / зачёт / диф. зачёт.

Верни строго JSON:
{{
  "disciplines": [
    {{
      "name": "Название",
      "hours": 144,
      "assessment": "экзамен"
    }}
  ]
}}

Данные:
{json.dumps(disciplines, ensure_ascii=False, indent=2)}
"""

    raw = call_yandex_lite(
        [{"role": "user", "text": prompt}],
        temperature=0.2,
        max_tokens=2000
    )

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        return json.loads(raw[start:end]).get("disciplines", [])
    except:
        return disciplines

def assign_blocks(disciplines):
    blocks = []
    for d in disciplines:
        if d.get("block_hint") == "обязательная":
            blocks.append({"name": d["name"], "block": "Блок 1. Обязательная часть"})
        else:
            blocks.append({"name": d["name"], "block": "Блок 1. Вариативная часть"})
    return blocks




def enrich_discipline_metadata(discipline, df_fgos, tf_struct):
    """
    Улучшенная версия: передаём контекст ФГОС и ТФ,
    чтобы модель выбирала компетенции осознанно.
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



def prepare_block_structure(disciplines_with_hours):
    """
    Возвращает структуру:
    {
        "Блок 1. Обязательная часть": [список дисциплин],
        "Блок 1. Вариативная часть": [список дисциплин]
    }
    """
    block_assignments = assign_blocks(disciplines_with_hours)

    block_map = {
        "Блок 1. Обязательная часть": [],
        "Блок 1. Вариативная часть": []
    }

    for item in block_assignments:
        name = item.get("name")
        block = item.get("block", "Блок 1. Обязательная часть")
        if name:
            block_map.setdefault(block, []).append(name)

    return block_map


def distribute_evenly(items, semester_ranges):
    """
    Универсальная функция равномерного распределения.
    items — список дисциплин
    semester_ranges — список списков семестров, например:
        [[1,2,3], [4,5], [6], [7], [8]]
    Возвращает словарь: {дисциплина: семестр}
    """
    result = {}
    idx = 0

    for group in semester_ranges:
        count = len(group)
        # сколько дисциплин положить в эту группу
        portion = max(1, len(items) // len(semester_ranges))

        # если мало дисциплин — уменьшаем
        if portion > len(items) - idx:
            portion = len(items) - idx

        selected = items[idx: idx + portion]
        idx += portion

        
        for i, disc in enumerate(selected):
            sem = group[i % count]
            result[disc] = sem

        if idx >= len(items):
            break

    
    if idx < len(items):
        tail = items[idx:]
        last_group = semester_ranges[-1]
        for i, disc in enumerate(tail):
            result[disc] = last_group[i % len(last_group)]

    return result


def distribute_by_semesters(block_map):
    """
    Автоматическое распределение дисциплин по семестрам.
    block_map:
    {
        "Блок 1. Обязательная часть": [...],
        "Блок 1. Вариативная часть": [...]
    }
    """

    # 1) Обязательная часть — равномерно по 1–6 семестрам
    obligatory = block_map.get("Блок 1. Обязательная часть", [])
    obligatory_semesters = distribute_evenly(
        obligatory,
        [
            [1, 2],   # ранние семестры
            [3, 4],   # середина
            [5, 6]    # поздние обязательные
        ]
    )

    # 2) Вариативная часть — равномерно по 3–7 семестрам
    variative = block_map.get("Блок 1. Вариативная часть", [])
    variative_semesters = distribute_evenly(
        variative,
        [
            [3, 4],   # начало вариативных
            [5, 6],   # середина
            [7]       # поздние
        ]
    )

    # объединяем
    semester_map = {}
    semester_map.update(obligatory_semesters)
    semester_map.update(variative_semesters)

    return semester_map



def assign_semesters_and_blocks(disciplines_with_hours, df_fgos, tf_struct, structure_mode="old"):
    """
    Полностью новый Этап 3:
    - блоки (ИИ)
    - компетенции/ТФ/обоснование (ИИ)
    - семестры (Python, идеально)
    """

    # 3.1 — блоки
    block_map = prepare_block_structure(disciplines_with_hours)

    # 3.2 — семестры (Python)
    semester_map = distribute_by_semesters(block_map)

    # 3.3 — метаданные (ИИ)
    enriched = {}
    for d in disciplines_with_hours:
        enriched[d["name"]] = enrich_discipline_metadata(d, df_fgos, tf_struct)

    # 3.4 — сборка строк
    rows = []
    for d in disciplines_with_hours:
        name = d["name"]

        # блок
        block = None
        for b, names in block_map.items():
            if name in names:
                block = b
                break
        if block is None:
            block = "Блок 1. Обязательная часть"

        # семестр
        semester = semester_map.get(name, 1)

        meta = enriched.get(name, {})

        rows.append({
            "🛠 В разработке": block,
            "Семестр": semester,
            "Дисциплина": name,
            "Часы": d.get("hours", 144),
            "Форма контроля": d.get("assessment", "экзамен"),
            "Компетенции ФГОС": meta.get("competencies", ""),
            "Трудовые функции": meta.get("TF", []),
            "Обоснование": meta.get("reason", "")
        })

    # 3.5 — добавляем практику и ГИА
    rows.append({
        "🛠 В разработке": "Блок 2. Практика",
        "Семестр": 7,
        "Дисциплина": "Учебная практика",
        "Часы": 108,
        "Форма контроля": "зачёт",
        "Компетенции ФГОС": "",
        "Трудовые функции": [],
        "Обоснование": "Практика по ФГОС"
    })

    rows.append({
        "🛠 В разработке": "Блок 2. Практика",
        "Семестр": 8,
        "Дисциплина": "Преддипломная практика",
        "Часы": 108,
        "Форма контроля": "зачёт",
        "Компетенции ФГОС": "",
        "Трудовые функции": [],
        "Обоснование": "Преддипломная практика по ФГОС"
    })

    rows.append({
        "🛠 В разработке": "Блок 3. ГИА",
        "Семестр": 8,
        "Дисциплина": "ВКР",
        "Часы": 216,
        "Форма контроля": "защита",
        "Компетенции ФГОС": "",
        "Трудовые функции": [],
        "Обоснование": "Государственная итоговая аттестация"
    })

    return rows


def generate_plan_pipeline(df_fgos, tf_struct, match_json, profile_choice, structure_mode="old"):
    """
    Полный конвейер:
    1) Этап 1 — генерация дисциплин (универсально)
    2) Этап 2 — часы и формы контроля
    3) Этап 3 — блоки, семестры, метаданные
    """

    # Этап 1
    disciplines = generate_disciplines_from_fgos_and_prof(
        df_fgos, tf_struct, match_json, profile_choice
    )
    if not disciplines:
        return pd.DataFrame()

    st.session_state.debug_disciplines = disciplines

    # Этап 2
    disciplines_with_hours = assign_hours_and_assessment(disciplines)
    if not disciplines_with_hours:
        return pd.DataFrame()

    st.session_state.debug_disciplines_hours = disciplines_with_hours

    # Этап 3
    plan_rows = assign_semesters_and_blocks(
    disciplines_with_hours,
    df_fgos,
    tf_struct,
    structure_mode="old")

    if not plan_rows:
        return pd.DataFrame()

    df = pd.DataFrame(plan_rows)
    # Преобразуем списки в строки
    df["Трудовые функции"] = df["Трудовые функции"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
    df["Компетенции ФГОС"] = df["Компетенции ФГОС"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)

    # Нормализация столбцов
    required_cols = [
        "🛠 В разработке", "Семестр", "Дисциплина", "Часы",
        "Форма контроля", "Компетенции ФГОС",
        "Трудовые функции", "Обоснование"
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df = df[required_cols]

    # Сортировка
    df = df.sort_values(by=["🛠 В разработке", "Семестр", "Дисциплина"])

    return df



def build_tf_dataframes(tf_struct):
    """
    Преобразует структуру {"TF": [...]} в две таблицы:
    1) df_tf — список трудовых функций (код + название)
    2) df_content — содержание ТФ (действия, знания, умения, др.)
    """

    # Если структура пустая или некорректная — возвращаем пустые таблицы
    if tf_struct is None or "TF" not in tf_struct:
        return pd.DataFrame(), pd.DataFrame()

    tf_list = tf_struct.get("TF", [])

    tf_rows = []
    content_rows = []

    for tf in tf_list:
        code = (tf.get("code") or "").strip()
        name = (tf.get("name") or "").strip()

        if not code:
            continue

        # Основная таблица ТФ
        tf_rows.append({
            "Код ТФ": code,
            "Наименование трудовой функции": name
        })

        # Вспомогательная функция
        def add_items(items, label):
            for item in items or []:
                item = (item or "").strip()
                if item:
                    content_rows.append({
                        "Код ТФ": code,
                        "Тип": label,
                        "Значение": item
                    })

        # Добавляем элементы содержания
        add_items(tf.get("actions"), "Трудовое действие")
        add_items(tf.get("knowledge"), "Необходимое знание")
        add_items(tf.get("skills"), "Необходимое умение")
        add_items(tf.get("other"), "Другие характеристики")

    df_tf = pd.DataFrame(tf_rows)
    df_content = pd.DataFrame(content_rows)

    return df_tf, df_content



def apply_ai_edit_proposal(user_text, df_current):
    """
    ИИ формирует ПРЕДЛОЖЕНИЕ изменений (полный новый план).
    Пользователь подтверждает или отклоняет.
    """

    table_json = df_current.to_dict(orient="records")

    prompt_edit = f"""
Ты — методист вуза, помогающий корректировать учебный план.

Текущий учебный план (JSON):
{json.dumps(table_json, ensure_ascii=False, indent=2)}

Запрос преподавателя:
\"\"\"{user_text}\"\"\"


Сформируй ПРЕДЛОЖЕНИЕ изменений, но НЕ применяй их автоматически.
Верни строго JSON:

{{
  "comment": "Краткое описание изменений",
  "plan_proposed": [
    {{
      "Семестр": 1,
      "Дисциплина": "Название",
      "Часы": 144,
      "Форма контроля": "экзамен",
      "Компетенции ФГОС": "УК-1, ОПК-2",
      "Трудовые функции": ["A/01.3"],
      "Обоснование": "Короткое обоснование"
    }}
  ]
}}

Важно:
- "plan_proposed" должен быть ПОЛНЫМ обновлённым планом.
- Не добавляй ничего вне JSON.
"""

    raw = call_yandex_lite(
        [{"role": "user", "text": prompt_edit}],
        temperature=0.25,
        max_tokens=2500
    )

    # Парсинг
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except Exception as e:
        return None, f"Ошибка разбора ответа ИИ: {e}. Ответ: {raw[:300]}"

    plan_proposed = data.get("plan_proposed", [])
    comment = data.get("comment", "Предложены изменения.")

    if not isinstance(plan_proposed, list) or not plan_proposed:
        return None, f"Некорректное предложение ИИ: пустой план. Ответ: {data}"

    df_new = pd.DataFrame(plan_proposed)

    # Проверка обязательных столбцов
    required_cols = ["Семестр", "Дисциплина", "Форма контроля"]
    for col in required_cols:
        if col not in df_new.columns:
            return None, f"В предложенном плане отсутствует колонка '{col}'. Ответ ИИ: {data}"

    # Добавляем недостающие
    for col in ["Часы", "Компетенции ФГОС", "Трудовые функции", "Обоснование"]:
        if col not in df_new.columns:
            df_new[col] = ""

    df_new = df_new[[
        "Семестр", "Дисциплина", "Часы",
        "Форма контроля", "Компетенции ФГОС",
        "Трудовые функции", "Обоснование"
    ]]

    return df_new, comment


def main():
    st.set_page_config(
        page_title="Интеллектуальная система формирования учебного плана (Lite, универсальная)",
        layout="wide"
    )
    st.markdown("""
<style>

    /* ====== ГЛАВНЫЙ ФОН ====== */
    .stApp {
        background-color: #f8fbff !important;  /* белый с лёгким голубым */
    }

    /* ====== ЗАГОЛОВКИ ====== */
    h1, h2, h3 {
        color: #003366 !important;  /* тёмно-синий */
    }

    /* ====== ОБЫЧНЫЙ ТЕКСТ ====== */
    div, p, span, label {
        color: #003366 !important;
    }

    /* ====== КНОПКИ ====== */
    .stButton>button {
        background-color: #cc0000 !important;  /* красная кнопка */
        color: white !important;
        border-radius: 8px !important;
        padding: 10px 20px !important;
        font-size: 16px !important;
        border: none !important;
    }

    /* ====== ВКЛАДКИ ====== */
    .stTabs [data-baseweb="tab"] {
        background-color: #e6f0ff !important;  /* светло-голубой */
        color: #003366 !important;
        font-weight: bold !important;
        border-radius: 5px !important;
        padding: 10px !important;
        border: 2px solid #003366 !important;
        margin-right: 5px !important;
    }

    /* Фон содержимого вкладок */
    div[data-testid="stTabs"] > div {
        background-color: #f8fbff !important;
    }

    /* ====== БОКОВАЯ ПАНЕЛЬ ====== */
    section[data-testid="stSidebar"] {
        background-color: #f0f4ff !important;
        color: #003366 !important;
        border-right: 2px solid #003366 !important;
    }

    /* ====== SELECTBOX (ВЫПАДАЮЩИЙ СПИСОК) ====== */

    /* Контейнер */
    div[data-baseweb="select"] {
        background-color: #ffffff !important;
        border: 2px solid #003366 !important;
        border-radius: 6px !important;
        color: #003366 !important;
    }

    /* Текст */
    div[data-baseweb="select"] * {
        color: #003366 !important;
    }

    /* Выпадающее меню */
    ul[role="listbox"] {
        background-color: #ffffff !important;
        border: 2px solid #003366 !important;
        border-radius: 6px !important;
    }

    /* Элементы списка */
    ul[role="listbox"] li {
        color: #003366 !important;
    }

    /* Наведение */
    ul[role="listbox"] li:hover {
        background-color: #e6f0ff !important;
        color: #003366 !important;
    }

    /* ====== ЗОНА ЗАГРУЗКИ ФАЙЛОВ ====== */

    /* Внешний белый блок */
    div[data-testid="stFileUploader"] > section {
        background-color: #ffffff !important;
        border: 2px solid #003366 !important;
        border-radius: 8px !important;
        padding: 16px !important;
    }

    /* Внутренний голубой блок с пунктиром */
    div[data-testid="stFileUploader"] [data-testid="stFileDropzone"] {
        background-color: #f0f4ff !important;
        border: 2px dashed #003366 !important;
        border-radius: 6px !important;
    }

    /* Текст внутри зоны загрузки */
    div[data-testid="stFileUploader"] * {
        color: #003366 !important;
    }

    /* Кнопка Browse file — белая на тёмно-синем */
    div[data-testid="stFileUploader"] button {
        background-color: #ffffff !important;
        color: #003366 !important;
        border: 2px solid #003366 !important;
        border-radius: 6px !important;
        padding: 6px 14px !important;
    }

    /* ====== ТАБЛИЦЫ ====== */
    .stDataFrame {
        background-color: #ffffff !important;
        border: 2px solid #003366 !important;
        border-radius: 6px !important;
        padding: 10px !important;
        color: #003366 !important;
    }

    /* ====== ЧАТ-СООБЩЕНИЯ ====== */
    .stChatMessage {
        background-color: #f9f9f9 !important;
        border-left: 4px solid #cc0000 !important;
        padding: 10px !important;
        margin-bottom: 10px !important;
        color: #003366 !important;
    }
    /* ====== SELECTBOX — ПОЛНОЕ ПЕРЕКРАШИВАНИЕ ====== */

/* Внешний контейнер selectbox */
div[data-testid="stSelectbox"] {
    background-color: #ffffff !important;
}

/* Контейнер с текстом */
div[data-testid="stSelectbox"] > div {
    background-color: #ffffff !important;
}

/* Основной блок select */
div[data-baseweb="select"] {
    background-color: #ffffff !important;
    border: 2px solid #003366 !important;
    border-radius: 6px !important;
    color: #003366 !important;
}

/* Внутренние элементы */
div[data-baseweb="select"] * {
    background-color: #ffffff !important;
    color: #003366 !important;
}

/* Выпадающее меню */
ul[role="listbox"] {
    background-color: #ffffff !important;
    border: 2px solid #003366 !important;
    border-radius: 6px !important;
}

/* Элементы списка */
ul[role="listbox"] li {
    background-color: #ffffff !important;
    color: #003366 !important;
}

/* Наведение */
ul[role="listbox"] li:hover {
    background-color: #e6f0ff !important;
    color: #003366 !important;
}

/* Активный выбранный элемент */
ul[role="listbox"] li[aria-selected="true"] {
    background-color: #e6f0ff !important;
    color: #003366 !important;
}

/* Глубокие скрытые контейнеры (убирают чёрный фон полностью) */
div[role="combobox"] {
    background-color: #ffffff !important;
}

div[role="combobox"] * {
    background-color: #ffffff !important;
    color: #003366 !important;
}
/* ====== КНОПКИ: белый текст на красном фоне ====== */
.stButton > button,
.stButton > button * {
    color: #ffffff !important;
}


</style>
""", unsafe_allow_html=True)





    st.title("Интеллектуальная система формирования учебного плана")
    st.caption("YandexGPT Lite • Универсальная генерация • Автоматическое распределение по семестрам • Старая структура (3 блока)")

    tab_normative, tab_generate, tab_editor = st.tabs([
        "Нормативная база (ФГОС + профстандарты)",
        "Генерация учебного плана",
        "ИИ‑редактор учебного плана"
    ])

    
    with tab_normative:
        st.header("Нормативная база: ФГОС + профессиональные стандарты")

        # ---- ФГОС ----
        st.subheader("1. Компетенции ФГОС")

        uploaded_fgos = st.file_uploader(
            "Загрузите ФГОС (PDF)",
            type=["pdf"],
            key="fgos_upload"
        )

        if uploaded_fgos:
            text_fgos = extract_text_from_pdf_file(uploaded_fgos)
            competencies = extract_competencies_full(text_fgos)
            df_fgos = pd.DataFrame(competencies)
            st.session_state.df_fgos = df_fgos

            if df_fgos.empty:
                st.warning("Не удалось извлечь компетенции из ФГОС.")
            else:
                st.success("Компетенции ФГОС успешно извлечены!")
                st.dataframe(df_fgos, use_container_width=True)
                st.download_button(
                    "Скачать компетенции ФГОС (Excel)",
                    dataframe_to_excel_bytes(df_fgos),
                    "fgos_competencies.xlsx"
                )

        
        st.subheader("2. Профессиональные стандарты")

        uploaded_ps = st.file_uploader(
            "Загрузите профессиональный стандарт (PDF)",
            type=["pdf"],
            key="ps_upload"
        )

        if uploaded_ps:
            st.write("Извлечение текста профессионального стандарта...")
            full_text = extract_text_from_pdf_file(uploaded_ps)

            st.write("ИИ анализирует трудовые функции...")
            tf_struct, err_ps = analyze_prof_standard(full_text)

            if err_ps:
                st.error(err_ps)
            else:
                st.session_state.ps_struct = tf_struct

                df_tf, df_content = build_tf_dataframes(tf_struct)
                st.session_state.df_tf = df_tf
                st.session_state.df_ps_content = df_content

                st.success("Профессиональный стандарт успешно проанализирован!")

                st.markdown("### Список трудовых функций (ТФ)")
                st.dataframe(df_tf, use_container_width=True)

                st.download_button(
                    "Скачать список ТФ (Excel)",
                    dataframe_to_excel_bytes(df_tf),
                    "profstandart_tf_list.xlsx"
                )

                if not df_content.empty:
                    st.download_button(
                        "Скачать содержание ТФ (Excel)",
                        dataframe_to_excel_bytes(df_content),
                        "profstandart_tf_content.xlsx"
                    )

                st.markdown("### Содержание трудовых функций")
                for _, row in df_tf.iterrows():
                    code = row["Код ТФ"]
                    name = row["Наименование трудовой функции"] or ""
                    header = f"{code} — {name}" if name else code

                    with st.expander(header):
                        df_sub = df_content[df_content["Код ТФ"] == code]
                        st.dataframe(df_sub, use_container_width=True)

        
        st.subheader("3. Сопоставление ФГОС ↔ профстандарты")

        if "df_fgos" in st.session_state and "ps_struct" in st.session_state:
            df_fgos = st.session_state.df_fgos
            tf_struct = st.session_state.ps_struct

            if st.button("Выполнить сопоставление"):
                st.write("ИИ анализирует соответствие...")
                match_json, raw_err = match_fgos_and_prof(df_fgos, tf_struct)

                if raw_err:
                    st.error("Ошибка при обращении к ИИ, но возвращён безопасный результат.")
                    st.text_area("Сырой ответ ИИ", raw_err, height=150)

                st.session_state.match_json = match_json
                st.success("Сопоставление выполнено!")

                st.write("### Соответствия")
                st.json(match_json.get("matches", []))

                st.write("### Непокрытые ТФ")
                st.json(match_json.get("gaps", []))

                st.write("### Рекомендации")
                for rec in match_json.get("recommendations", []):
                    st.write("- " + rec)
        else:
            st.info("Для сопоставления загрузите ФГОС и профстандарт.")

    
    with tab_generate:
        st.header("Генерация учебного плана")

        profile_choice = st.selectbox(
            "Выберите профиль (можно оставить 'Авто')",
            [
                "Авто",
                "Педагогика",
                "Юриспруденция",
                "Психология",
                "Экономика",
                "Информационные технологии",
                "Социальная работа",
                "Медицина",
                "Другое"
            ],
            index=0
        )

        if "df_fgos" not in st.session_state or "ps_struct" not in st.session_state:
            st.info("Сначала загрузите ФГОС и профстандарт во вкладке 'Нормативная база'.")
        elif "match_json" not in st.session_state:
            st.info("Сначала выполните сопоставление ФГОС и профстандарта.")
        else:
            df_fgos = st.session_state.df_fgos
            tf_struct = st.session_state.ps_struct
            match_json = st.session_state.match_json

            if st.button("Сгенерировать учебный план"):
                st.write("ИИ формирует учебный план...")

                df_plan = generate_plan_pipeline(
                    df_fgos,
                    tf_struct,
                    match_json,
                    profile_choice,
                    structure_mode="old"
                )
                st.session_state.df_plan = df_plan

                st.success("Учебный план успешно сгенерирован!")
                st.dataframe(df_plan, use_container_width=True)

                st.download_button(
                    "Скачать учебный план (Excel)",
                    dataframe_to_excel_bytes(df_plan),
                    "uchebny_plan.xlsx"
                )

    with tab_editor:
        st.header("ИИ‑редактор учебного плана")

        if "df_plan" not in st.session_state or st.session_state.df_plan.empty:
            st.info("Сначала сгенерируйте учебный план.")
            return

        df_current = st.session_state.df_plan
        st.subheader("Текущий учебный план")
        st.dataframe(df_current, use_container_width=True)

        st.markdown("---")
        st.subheader("Чат с ИИ‑методистом")

        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        if "pending_edit_df" not in st.session_state:
            st.session_state.pending_edit_df = None
        if "pending_comment" not in st.session_state:
            st.session_state.pending_comment = None
        if "awaiting_confirmation" not in st.session_state:
            st.session_state.awaiting_confirmation = False

        # вывод истории
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        user_input = st.chat_input("Введите запрос к ИИ‑методисту...")

        if user_input:
            # если ждём подтверждения
            if st.session_state.awaiting_confirmation:
                st.session_state.chat_messages.append({"role": "user", "content": user_input})
                with st.chat_message("user"):
                    st.write(user_input)

                low = user_input.strip().lower()
                if low in ["да", "yes", "ок", "применить"]:
                    st.session_state.df_plan = st.session_state.pending_edit_df
                    st.session_state.pending_edit_df = None
                    st.session_state.pending_comment = None
                    st.session_state.awaiting_confirmation = False
                    answer = "Изменения применены."
                elif low in ["нет", "no", "отмена"]:
                    st.session_state.pending_edit_df = None
                    st.session_state.pending_comment = None
                    st.session_state.awaiting_confirmation = False
                    answer = "Изменения отменены."
                else:
                    answer = "Пожалуйста, ответьте 'да' или 'нет'."

                st.session_state.chat_messages.append({"role": "assistant", "content": answer})
                with st.chat_message("assistant"):
                    st.write(answer)

                st.rerun()

            # если это новый запрос
            else:
                st.session_state.chat_messages.append({"role": "user", "content": user_input})
                with st.chat_message("user"):
                    st.write(user_input)

                st.write("ИИ формирует предложение изменений...")

                df_proposed, comment = apply_ai_edit_proposal(user_input, df_current)

                if df_proposed is None:
                    st.session_state.chat_messages.append({"role": "assistant", "content": comment})
                    with st.chat_message("assistant"):
                        st.write(comment)
                else:
                    st.session_state.pending_edit_df = df_proposed
                    st.session_state.pending_comment = comment
                    st.session_state.awaiting_confirmation = True

                    answer = (
                        f"{comment}\n\n"
                        "Показан предлагаемый вариант учебного плана ниже. "
                        "Применить изменения? (да / нет)"
                    )
                    st.session_state.chat_messages.append({"role": "assistant", "content": answer})
                    with st.chat_message("assistant"):
                        st.write(answer)

                    st.subheader("Предлагаемый вариант (ещё не применён)")
                    st.dataframe(df_proposed, use_container_width=True)

                st.rerun()


if __name__ == "__main__":
    main()
