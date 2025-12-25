import pandas as pd
from disciplines import generate_disciplines
from ai import enrich_discipline_metadata


# ============================
# 0. Удаление дублей дисциплин
# ============================

def remove_duplicates(discs):
    """
    Удаляет дубли дисциплин по названию.
    Сохраняет первую встреченную дисциплину.
    """
    seen = set()
    unique = []
    for d in discs:
        name = d["name"].strip().lower()
        if name not in seen:
            seen.add(name)
            unique.append(d)
    return unique


# ============================
# 1. Идеальное распределение по семестрам
# ============================

def balanced_distribution(obligatory, variative):
    """
    Равномерное распределение дисциплин по семестрам.
    Обязательные → 1–6
    Вариативные → 3–7
    Разница между семестрами ≤ 1 дисциплина.
    """

    semester_plan = {s: [] for s in range(1, 8)}

    # --- распределяем обязательные ---
    sems_obl = [1, 2, 3, 4, 5, 6]
    idx = 0
    for disc in obligatory:
        sem = sems_obl[idx % len(sems_obl)]
        semester_plan[sem].append(disc)
        idx += 1

    # --- распределяем вариативные ---
    sems_var = [3, 4, 5, 6, 7]
    idx = 0
    for disc in variative:
        sem = sems_var[idx % len(sems_var)]
        semester_plan[sem].append(disc)
        idx += 1

    return semester_plan


# ============================
# 2. Назначение формы контроля
# ============================

def assign_assessment(name):
    name = name.lower()

    exam_keywords = [
        "математ", "механик", "программирован", "алгоритм",
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


# ============================
# 3. Финальная сборка учебного плана
# ============================

def generate_plan_pipeline(df_fgos, tf_struct, match_json, fgos_text):
    """
    Полный пайплайн:
    - определение профиля
    - генерация дисциплин
    - удаление дублей
    - распределение по семестрам
    - назначение форм контроля
    - enrich дисциплин
    - добавление практики и ГИА
    """

    # 1. Определяем профиль
    from fgos import detect_profile_from_fgos
    profiles = detect_profile_from_fgos(fgos_text)
    profile = profiles[0]

    # 2. Генерируем дисциплины под профиль
    discs = generate_disciplines(profile)

    # 3. Удаляем дубли
    discs = remove_duplicates(discs)

    # 4. Разделяем по блокам
    obligatory = [d["name"] for d in discs if d["block_hint"] == "обязательная"]
    variative = [d["name"] for d in discs if d["block_hint"] == "вариативная"]

    # 5. Равномерное распределение
    semester_map = balanced_distribution(obligatory, variative)

    # 6. Метаданные от ИИ
    enriched = {}
    for d in discs:
        enriched[d["name"]] = enrich_discipline_metadata(d, df_fgos, tf_struct)

    # 7. Сборка строк
    rows = []

    for sem, names in semester_map.items():
        for name in names:
            meta = enriched.get(name, {})
            is_oblig = name in obligatory

            rows.append({
                "Блок": f"Блок 1. {'Обязательная' if is_oblig else 'Вариативная'} часть",
                "Семестр": sem,
                "Дисциплина": name,
                "Часы": 144 if is_oblig else 108,
                "Форма контроля": assign_assessment(name),
                "Компетенции ФГОС": ", ".join(meta.get("competencies", [])),
                "Трудовые функции": ", ".join(meta.get("TF", [])),
                "Обоснование": meta.get("reason", "")
            })

    # 8. Практика + ГИА
    rows.extend([
        {
            "Блок": "Блок 2. Практика",
            "Семестр": 7,
            "Дисциплина": "Учебная практика",
            "Часы": 108,
            "Форма контроля": "зачёт",
            "Компетенции ФГОС": "",
            "Трудовые функции": "",
            "Обоснование": "Практика по ФГОС"
        },
        {
            "Блок": "Блок 2. Практика",
            "Семестр": 8,
            "Дисциплина": "Преддипломная практика",
            "Часы": 108,
            "Форма контроля": "зачёт",
            "Компетенции ФГОС": "",
            "Трудовые функции": "",
            "Обоснование": "Преддипломная практика по ФГОС"
        },
        {
            "Блок": "Блок 3. ГИА",
            "Семестр": 8,
            "Дисциплина": "ВКР",
            "Часы": 216,
            "Форма контроля": "защита",
            "Компетенции ФГОС": "",
            "Трудовые функции": "",
            "Обоснование": "Государственная итоговая аттестация"
        }
    ])

    return pd.DataFrame(rows)
