import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_bytes
import re
import json
from ai import call_yandex_lite



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

    # Если текст нормальный — возвращаем
    if len(text.strip()) > 50:
        return text

    # Иначе — OCR
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



def detect_profile_from_fgos(text):
    """
    Автоматическое определение профиля подготовки по тексту ФГОС.
    Возвращает список 1–3 наиболее вероятных профилей.
    """

    prompt = f"""
Ты — эксперт по образовательным стандартам РФ.

На входе — текст ФГОС. 
Определи 1–3 наиболее вероятных профиля подготовки.

Верни строго JSON:
{{
  "profiles": ["Профиль1", "Профиль2"]
}}

Текст ФГОС:
{text[:12000]}
"""

    raw = call_yandex_lite(
        [{"role": "user", "text": prompt}],
        temperature=0.2,
        max_tokens=800
    )
    print("RAW PROFILE RESPONSE >>>", raw)

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        profiles = data.get("profiles", [])
        if isinstance(profiles, list) and profiles:
            return profiles
    except:
        pass

    return ["Не удалось определить профиль"]
