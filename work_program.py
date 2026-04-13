import io
import json
from typing import Any, Dict, List

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from ai import call_yandex_lite


def _safe_json_from_text(text: str) -> Dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"Не найден JSON в ответе модели: {text[:1000]}")
    return json.loads(text[start:end])


def generate_work_program_content(
    discipline_row: Dict[str, Any],
    profile: str,
    direction_code: str = "09.03.01",
    direction_name: str = "Информатика и вычислительная техника",
    qualification: str = "бакалавр",
    education_form: str = "очная",
    university_name: str = "Ваш университет",
    faculty_name: str = "Ваш факультет",
) -> Dict[str, Any]:
    discipline_name = str(discipline_row.get("Дисциплина", "")).strip()
    semester = discipline_row.get("Семестр", "")
    hours = discipline_row.get("Часы", "")
    control_form = discipline_row.get("Форма контроля", "")
    competencies = discipline_row.get("Компетенции ФГОС", [])
    tf = discipline_row.get("Трудовые функции", "")

    if isinstance(competencies, str):
        competencies_text = competencies
    else:
        competencies_text = ", ".join(map(str, competencies))

    prompt = f"""
Ты — опытный методист российского вуза.

Сгенерируй РАБОЧУЮ ПРОГРАММУ ДИСЦИПЛИНЫ в формате СТРОГОГО JSON.
Без пояснений. Без markdown. Только один JSON-объект.

Данные дисциплины:
- Дисциплина: {discipline_name}
- Профиль: {profile}
- Код направления: {direction_code}
- Направление: {direction_name}
- Квалификация: {qualification}
- Форма обучения: {education_form}
- Семестр: {semester}
- Объем часов: {hours}
- Форма контроля: {control_form}
- Компетенции ФГОС: {competencies_text}
- Трудовые функции: {tf}

Нужно вернуть JSON такой структуры:
{{
  "title": "Рабочая программа дисциплины",
  "discipline_code": "Б1.О.01",
  "discipline_name": "{discipline_name}",
  "goals": "1-2 абзаца",
  "place_in_program": "1-2 абзаца",
  "results": [
    {{
      "code": "УК-1",
      "competence": "Формулировка компетенции",
      "indicator": "Индикатор",
      "know": "Что знает",
      "able": "Что умеет",
      "master": "Чем владеет"
    }}
  ],
  "total_credits": 3,
  "total_hours": {hours if str(hours).isdigit() else 108},
  "structure_rows": [
    {{
      "section": "Раздел 1. ...",
      "topic": "Тема 1.1. ...",
      "semester": {semester if str(semester).isdigit() else 1},
      "weeks": "1-2",
      "lectures": 4,
      "labs": 4,
      "other_contact": 0,
      "self_study": 8,
      "current_control": "Опрос",
      "intermediate_control": "{control_form or 'зачет'}"
    }}
  ],
  "lecture_topics": [
    "Тема ..."
  ],
  "lab_topics": [
    {{
      "name": "Лабораторная работа 1. ...",
      "hours": 2
    }}
  ],
  "education_technologies": [
    "Текст"
  ],
  "self_study_rows": [
    {{
      "weeks": "1-2",
      "topic": "Тема ...",
      "kind": "Подготовка к занятиям",
      "task": "Описание задания",
      "literature": "1-3",
      "hours": 6
    }}
  ],
  "assessment_tools": [
    "Опрос",
    "Проверка лабораторных работ",
    "Зачет"
  ],
  "literature": [
    "1. ..."
  ],
  "software": [
    "Python",
    "Jupyter Notebook"
  ],
  "equipment": [
    "Проектор",
    "Компьютерный класс"
  ]
}}

Требования:
1. Содержание должно быть реалистичным для дисциплины.
2. Компетенции возьми из входных данных, если они даны.
3. Если компетенций мало, добавь 2-4 правдоподобных результата обучения.
4. Таблицы должны быть разумными по часам.
5. Ответ только JSON.
"""

    raw = call_yandex_lite(
        [{"role": "user", "text": prompt}],
        temperature=0.2,
        max_tokens=3000,
    )
    data = _safe_json_from_text(raw)

    data["meta"] = {
        "university_name": university_name,
        "faculty_name": faculty_name,
        "direction_code": direction_code,
        "direction_name": direction_name,
        "profile": profile,
        "qualification": qualification,
        "education_form": education_form,
    }
    return data


def _set_base_style(doc: Document) -> None:
    styles = doc.styles
    if "Normal" in styles:
        styles["Normal"].font.name = "Times New Roman"
        styles["Normal"].font.size = Pt(12)


def _add_center_text(doc: Document, text: str, bold: bool = False, size: int = 12) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = bold
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)


def _add_left_text(doc: Document, text: str, bold: bool = False, size: int = 12) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(text)
    run.bold = bold
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)


def create_work_program_docx(data: Dict[str, Any]) -> bytes:
    doc = Document()
    _set_base_style(doc)

    meta = data.get("meta", {})
    university_name = meta.get("university_name", "Ваш университет")
    faculty_name = meta.get("faculty_name", "Ваш факультет")
    direction_code = meta.get("direction_code", "")
    direction_name = meta.get("direction_name", "")
    profile = meta.get("profile", "")
    qualification = meta.get("qualification", "бакалавр")
    education_form = meta.get("education_form", "очная")

    # Титульный лист
    _add_center_text(doc, "МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ", bold=True)
    _add_center_text(doc, "РОССИЙСКОЙ ФЕДЕРАЦИИ", bold=True)
    doc.add_paragraph()
    _add_center_text(doc, university_name, bold=True)
    _add_center_text(doc, faculty_name, bold=True)
    doc.add_paragraph()
    _add_center_text(doc, "РАБОЧАЯ ПРОГРАММА ДИСЦИПЛИНЫ", bold=True, size=14)
    doc.add_paragraph()
    _add_center_text(
        doc,
        f"{data.get('discipline_code', 'Б1.О.01')} {data.get('discipline_name', '')}",
        bold=True,
        size=13,
    )
    doc.add_paragraph()
    _add_left_text(doc, f"Направление подготовки: {direction_code} «{direction_name}»")
    _add_left_text(doc, f"Направленность подготовки: «{profile}»")
    _add_left_text(doc, f"Квалификация выпускника: {qualification}")
    _add_left_text(doc, f"Форма обучения: {education_form}")
    doc.add_page_break()

    # 1
    _add_left_text(doc, "1. Цели освоения дисциплины", bold=True)
    _add_left_text(doc, data.get("goals", ""))

    # 2
    _add_left_text(doc, "2. Место дисциплины в структуре ОПОП", bold=True)
    _add_left_text(doc, data.get("place_in_program", ""))

    # 3
    _add_left_text(doc, f"3. Результаты освоения дисциплины «{data.get('discipline_name', '')}»", bold=True)
    results = data.get("results", [])
    if results:
        table = doc.add_table(rows=1, cols=6)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text = "Код"
        hdr[1].text = "Компетенция"
        hdr[2].text = "Индикатор"
        hdr[3].text = "Знать"
        hdr[4].text = "Уметь"
        hdr[5].text = "Владеть"

        for item in results:
            row = table.add_row().cells
            row[0].text = str(item.get("code", ""))
            row[1].text = str(item.get("competence", ""))
            row[2].text = str(item.get("indicator", ""))
            row[3].text = str(item.get("know", ""))
            row[4].text = str(item.get("able", ""))
            row[5].text = str(item.get("master", ""))

    # 4
    _add_left_text(doc, f"4. Структура и содержание дисциплины «{data.get('discipline_name', '')}»", bold=True)
    total_credits = data.get("total_credits", 3)
    total_hours = data.get("total_hours", 108)
    _add_left_text(doc, f"Общая трудоемкость дисциплины составляет {total_credits} зачетных единиц, {total_hours} часов.")

    structure_rows = data.get("structure_rows", [])
    if structure_rows:
        table = doc.add_table(rows=1, cols=10)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text = "Раздел"
        hdr[1].text = "Тема"
        hdr[2].text = "Семестр"
        hdr[3].text = "Недели"
        hdr[4].text = "Лекции"
        hdr[5].text = "Лаб."
        hdr[6].text = "Иное"
        hdr[7].text = "СРС"
        hdr[8].text = "Текущий контроль"
        hdr[9].text = "Промежуточный контроль"

        for item in structure_rows:
            row = table.add_row().cells
            row[0].text = str(item.get("section", ""))
            row[1].text = str(item.get("topic", ""))
            row[2].text = str(item.get("semester", ""))
            row[3].text = str(item.get("weeks", ""))
            row[4].text = str(item.get("lectures", ""))
            row[5].text = str(item.get("labs", ""))
            row[6].text = str(item.get("other_contact", ""))
            row[7].text = str(item.get("self_study", ""))
            row[8].text = str(item.get("current_control", ""))
            row[9].text = str(item.get("intermediate_control", ""))

    _add_left_text(doc, "4.2.1. Содержание лекционных занятий", bold=True)
    for topic in data.get("lecture_topics", []):
        _add_left_text(doc, f"• {topic}")

    _add_left_text(doc, "4.2.2. Темы лабораторных работ", bold=True)
    lab_topics = data.get("lab_topics", [])
    if lab_topics:
        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text = "Наименование лабораторной работы"
        hdr[1].text = "Часы"
        for item in lab_topics:
            row = table.add_row().cells
            row[0].text = str(item.get("name", ""))
            row[1].text = str(item.get("hours", ""))

    # 5
    _add_left_text(doc, "5. Образовательные технологии", bold=True)
    for item in data.get("education_technologies", []):
        _add_left_text(doc, f"• {item}")

    # 6
    _add_left_text(
        doc,
        "6. Учебно-методическое обеспечение самостоятельной работы студентов. Оценочные средства.",
        bold=True,
    )
    ss_rows = data.get("self_study_rows", [])
    if ss_rows:
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text = "Недели"
        hdr[1].text = "Тема"
        hdr[2].text = "Вид работы"
        hdr[3].text = "Задание"
        hdr[4].text = "Часы"

        for item in ss_rows:
            row = table.add_row().cells
            row[0].text = str(item.get("weeks", ""))
            row[1].text = str(item.get("topic", ""))
            row[2].text = str(item.get("kind", ""))
            row[3].text = str(item.get("task", ""))
            row[4].text = str(item.get("hours", ""))

    _add_left_text(doc, "6.3. Оценочные средства", bold=True)
    for item in data.get("assessment_tools", []):
        _add_left_text(doc, f"• {item}")

    # 7
    _add_left_text(doc, "7. Учебно-методическое и материально-техническое обеспечение дисциплины", bold=True)

    _add_left_text(doc, "а) Литература", bold=True)
    for item in data.get("literature", []):
        _add_left_text(doc, item)

    _add_left_text(doc, "б) Программное обеспечение", bold=True)
    for item in data.get("software", []):
        _add_left_text(doc, f"• {item}")

    _add_left_text(doc, "в) Материально-техническое обеспечение", bold=True)
    for item in data.get("equipment", []):
        _add_left_text(doc, f"• {item}")

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()