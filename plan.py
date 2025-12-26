import pandas as pd
from disciplines import generate_disciplines
from ai import enrich_discipline_metadata
from competencies import detect_competencies, PROFILE_MAP


def remove_duplicates(discs):
    seen = set()
    unique = []
    for d in discs:
        name = d["name"].strip().lower()
        if name not in seen:
            seen.add(name)
            unique.append(d)
    return unique


def balanced_distribution(obligatory, variative):
    semester_plan = {s: [] for s in range(1, 8)}

    sems_obl = [1, 2, 3, 4, 5, 6]
    for i, disc in enumerate(obligatory):
        semester_plan[sems_obl[i % len(sems_obl)]].append(disc)

    sems_var = [3, 4, 5, 6, 7]
    for i, disc in enumerate(variative):
        semester_plan[sems_var[i % len(sems_var)]].append(disc)

    return semester_plan


def assign_assessment(name):
    name = name.lower()

    exam_keywords = [
        "математ", "механик", "программ", "алгоритм",
        "базы данных", "sql", "nosql", "архитектур",
        "сет", "безопас", "машин", "искусственный интеллект"
    ]

    diff_keywords = [
        "график", "вектор", "растров", "мультимед",
        "веб", "api", "cms", "ux", "ui"
    ]

    soft_keywords = [
        "культур", "истор", "философ", "психолог",
        "коммуник", "soft", "самоменедж", "управление временем"
    ]

    if any(k in name for k in exam_keywords):
        return "экзамен"
    if any(k in name for k in diff_keywords):
        return "диф. зачёт"
    if any(k in name for k in soft_keywords):
        return "зачёт"

    return "зачёт"


def generate_plan_pipeline(df_fgos, tf_struct, match_json, fgos_text):
    """
    Полный пайплайн:
    - определение профиля
    - генерация дисциплин
    - enrich метаданных
    - распределение по семестрам
    - назначение форм контроля
    - автоматическое определение компетенций
    - добавление практик и ГИА
    """

    from fgos import detect_profile_from_fgos
    raw_profiles = detect_profile_from_fgos(fgos_text)
    raw_text = " ".join(raw_profiles).lower()

    profile = None
    for key, val in PROFILE_MAP.items():
        if key in raw_text:
            profile = val
            break

    if profile is None:
        profile = "ИВТ"

    discs = generate_disciplines(profile)

    discs = remove_duplicates(discs)

    enriched = {
        d["name"]: enrich_discipline_metadata(d, df_fgos, tf_struct)
        for d in discs
    }

    obligatory = [d for d in discs if d["block_hint"] == "обязательная"]
    variative = [d for d in discs if d["block_hint"] == "вариативная"]

    semester_map = balanced_distribution(obligatory, variative)

    rows = []

    for sem, disc_list in semester_map.items():
        for disc in disc_list:
            name = disc["name"]
            meta = enriched.get(name, {})

            rows.append({
                "Блок": f"Блок 1. {'Обязательная' if disc['block_hint']=='обязательная' else 'Вариативная'} часть",
                "Семестр": sem,
                "Дисциплина": name,
                "Часы": 144 if disc["block_hint"] == "обязательная" else 108,
                "Форма контроля": assign_assessment(name),
                "Компетенции ФГОС": detect_competencies(profile, name),
                "Трудовые функции": ", ".join(meta.get("TF", [])),
                "Обоснование": meta.get("reason", "")
            })

    rows.extend([
        {
            "Блок": "Блок 2. Практика",
            "Семестр": 7,
            "Дисциплина": "Учебная практика",
            "Часы": 108,
            "Форма контроля": "зачёт",
            "Компетенции ФГОС": detect_competencies(profile, "Учебная практика"),
            "Трудовые функции": "",
            "Обоснование": "Практика по ФГОС"
        },
        {
            "Блок": "Блок 2. Практика",
            "Семестр": 8,
            "Дисциплина": "Преддипломная практика",
            "Часы": 108,
            "Форма контроля": "зачёт",
            "Компетенции ФГОС": detect_competencies(profile, "Преддипломная практика"),
            "Трудовые функции": "",
            "Обоснование": "Преддипломная практика по ФГОС"
        },
        {
            "Блок": "Блок 3. ГИА",
            "Семестр": 8,
            "Дисциплина": "ВКР",
            "Часы": 216,
            "Форма контроля": "защита",
            "Компетенции ФГОС": detect_competencies(profile, "ВКР"),
            "Трудовые функции": "",
            "Обоснование": "Государственная итоговая аттестация"
        }
    ])

    return pd.DataFrame(rows)
