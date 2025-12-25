import pandas as pd
from disciplines import generate_disciplines
from ai import enrich_discipline_metadata


# ============================
# 1. Распределение по семестрам
# ============================
def distribute_semesters(obligatory, variative):
    """
    Равномерное распределение дисциплин по семестрам.
    Обязательные растягиваются по 1–6, вариативные — по 3–7.
    """

    semester_plan = {s: [] for s in range(1, 8)}

    max_per_sem_oblig = 4
    max_per_sem_var = 4

    obligatory_semesters = [1, 2, 3, 4, 5, 6]
    variative_semesters = [3, 4, 5, 6, 7]

    # --- обязательные: равномерно по 1–6 ---
    sem_idx = 0
    counters = {s: 0 for s in obligatory_semesters}

    for disc in obligatory:
        # крутимся по семестрам, пока не найдём тот, где есть место
        for _ in range(len(obligatory_semesters)):
            sem = obligatory_semesters[sem_idx]
            if counters[sem] < max_per_sem_oblig:
                semester_plan[sem].append(disc)
                counters[sem] += 1
                sem_idx = (sem_idx + 1) % len(obligatory_semesters)
                break
            sem_idx = (sem_idx + 1) % len(obligatory_semesters)

    # --- вариативные: равномерно по 3–7 ---
    sem_idx = 0
    counters_var = {s: 0 for s in variative_semesters}

    for disc in variative:
        for _ in range(len(variative_semesters)):
            sem = variative_semesters[sem_idx]
            if counters_var[sem] < max_per_sem_var:
                semester_plan[sem].append(disc)
                counters_var[sem] += 1
                sem_idx = (sem_idx + 1) % len(variative_semesters)
                break
            sem_idx = (sem_idx + 1) % len(variative_semesters)

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

    # 3. Разделяем по блокам
    obligatory = [d["name"] for d in discs if d["block_hint"] == "обязательная"]
    variative = [d["name"] for d in discs if d["block_hint"] == "вариативная"]

    # 4. Распределяем по семестрам
    semester_map = distribute_semesters(obligatory, variative)

    # 5. Метаданные от ИИ
    enriched = {}
    for d in discs:
        enriched[d["name"]] = enrich_discipline_metadata(d, df_fgos, tf_struct)

    # 6. Сборка строк
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


    # 7. Практика + ГИА
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
