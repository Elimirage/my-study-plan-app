import re
import json
from ai import call_yandex_lite


# ============================
# 1. Извлечение кодов ТФ
# ============================

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


# ============================
# 2. Поиск контекста ТФ
# ============================

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


# ============================
# 3. Анализ одной ТФ через ИИ
# ============================

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


# ============================
# 4. Анализ всего профстандарта
# ============================

def analyze_prof_standard(full_text):
    """
    Извлекает все ТФ и анализирует каждую через ИИ.
    """
    tf_codes = extract_tf_codes_smart(full_text)
    if not tf_codes:
        return None, "Не найдено ни одного кода ТФ."

    tf_list = []
    for code in tf_codes:
        context = get_context_for_tf(full_text, code)
        tf_list.append(analyze_single_tf_with_ai(code, context))

    return {"TF": tf_list}, None


# ============================
# 5. Сопоставление ФГОС ↔ профстандарт
# ============================

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
