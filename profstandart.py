import re
import json
from ai import call_yandex_lite

def extract_tf_codes_smart(full_text):
    """
    Извлекает коды трудовых функций из текста профстандарта.
    Поддерживает различные форматы: A/01.1, A-01.1, A.01.1, A/01/1 и т.д.
    """
    codes = []
    
    pattern1 = r"\b([A-ZА-Я])\s*[/\-–—]\s*(\d{1,2})\s*[\.\-–—,·]\s*(\d{1,2})\b"
    matches1 = re.findall(pattern1, full_text, re.IGNORECASE)
    for letter, num1, num2 in matches1:
        code = f"{letter.upper()}/{num1.zfill(2)}.{num2}"
        if code not in codes:
            codes.append(code)
    
    pattern2 = r"\b([A-ZА-Я])\s*[/\-–—]\s*(\d{1,2})\s*[/\-–—]\s*(\d{1,2})\b"
    matches2 = re.findall(pattern2, full_text, re.IGNORECASE)
    for letter, num1, num2 in matches2:
        code = f"{letter.upper()}/{num1.zfill(2)}.{num2}"
        if code not in codes:
            codes.append(code)
    
    pattern3 = r"\b([A-ZА-Я])\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\b"
    matches3 = re.findall(pattern3, full_text, re.IGNORECASE)
    for letter, num1, num2 in matches3:
        code = f"{letter.upper()}/{num1.zfill(2)}.{num2}"
        if code not in codes:
            codes.append(code)
    
    pattern4 = r"(?:трудовая\s+функция|тф|функция)\s+([A-ZА-Я])\s*[/\-–—]\s*(\d{1,2})\s*[\.\-–—,·]\s*(\d{1,2})\b"
    matches4 = re.findall(pattern4, full_text, re.IGNORECASE)
    for letter, num1, num2 in matches4:
        code = f"{letter.upper()}/{num1.zfill(2)}.{num2}"
        if code not in codes:
            codes.append(code)
    
    if not codes:
        codes = extract_tf_codes_with_ai(full_text)
    
    return codes


def extract_tf_codes_with_ai(full_text):
    """
    Альтернативный метод извлечения кодов через ИИ,
    если регулярные выражения не нашли коды.
    """
    prompt = f"""
Ты — эксперт по профессиональным стандартам РФ.

В тексте профессионального стандарта найди все коды трудовых функций.
Коды могут быть в форматах: A/01.1, A-01.1, A.01.1, A/01/1 и т.д.

Верни строго JSON массив кодов:
{{
  "codes": ["A/01.1", "A/01.2", "B/02.1"]
}}

Если коды не найдены, верни пустой массив: {{"codes": []}}

Текст профстандарта (первые 8000 символов):
{full_text[:8000]}
"""

    try:
        raw = call_yandex_lite(
            [{"role": "user", "text": prompt}],
            temperature=0.1,
            max_tokens=500
        )
        
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        codes = data.get("codes", [])
        
        # Нормализуем коды к единому формату
        normalized = []
        for code in codes:
            if isinstance(code, str):
                # Приводим к формату A/01.1
                code = code.upper().strip()
                code = re.sub(r'[–—]', '/', code)  # Заменяем длинные тире
                code = re.sub(r'\.+', '.', code)  # Убираем множественные точки
                if code and '/' in code:
                    normalized.append(code)
        
        return normalized
    except Exception:
        return []

def get_context_for_tf(full_text, tf_code, window=25):
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
        "name": data.get("name") or "",
        "actions": data.get("actions") or [],
        "knowledge": data.get("knowledge") or [],
        "skills": data.get("skills") or [],
        "other": data.get("other") or []
    }

def analyze_prof_standard(full_text):
    """
    Анализирует профстандарт и извлекает трудовые функции.
    """
    if not full_text or len(full_text.strip()) < 50:
        return None, "Текст профстандарта слишком короткий или пустой."
    
    tf_codes = extract_tf_codes_smart(full_text)
    if not tf_codes:
        # Пробуем еще раз с более широким поиском
        # Ищем любые упоминания "трудовая функция" или "ТФ"
        if "трудовая функция" in full_text.lower() or "тф" in full_text.lower():
            return None, "Найдены упоминания трудовых функций, но не удалось извлечь коды. Возможно, используется нестандартный формат."
        return None, "Не найдено ни одного кода трудовых функций. Убедитесь, что файл содержит профессиональный стандарт с кодами ТФ (например, A/01.1, B/02.3)."

    tf_list = []
    for code in tf_codes:
        context = get_context_for_tf(full_text, code)
        tf_list.append(analyze_single_tf_with_ai(code, context))

    return {"TF": tf_list}, None

def match_fgos_and_prof(df_fgos, tf_struct):
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
