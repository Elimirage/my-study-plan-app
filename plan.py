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
        "сет", "безопас", "машин", "искусственный интеллект",
        "теория", "анализ", "проектирован"
    ]

    diff_keywords = [
        "график", "вектор", "растров", "мультимед",
        "веб", "api", "cms", "ux", "ui", "разработка"
    ]

    soft_keywords = [
        "культур", "истор", "философ", "психолог",
        "коммуник", "soft", "самоменедж", "управление временем",
        "педагогик", "методик", "практик"
    ]

    if any(k in name for k in exam_keywords):
        return "экзамен"
    if any(k in name for k in diff_keywords):
        return "диф. зачёт"
    if any(k in name for k in soft_keywords):
        return "зачёт"

    return "зачёт"


def find_competencies_by_discipline(discipline_name, df_fgos):
    if df_fgos.empty:
        return []

    discipline_lower = discipline_name.lower()
    found_competencies = []

    keywords_map = {
        "математ": ["УК-1", "ОПК-1", "ПК-3"],
        "программ": ["ПК-1", "ПК-2", "ОПК-2"],
        "базы данных": ["ПК-8", "ПК-9"],
        "педагог": ["ОПК-1", "ОПК-2", "ПК-1"],
        "психолог": ["УК-2", "ОПК-3"],
    }

    for keyword, comps in keywords_map.items():
        if keyword in discipline_lower:
            found_competencies.extend(comps)

    return list(set(found_competencies))[:4]


def generate_reason(discipline_name, competencies, tf_codes):
    if not competencies and not tf_codes:
        return "Дисциплина формирует профессиональные компетенции в соответствии с ФГОС"

    comps_str = ", ".join(competencies[:3]) if competencies else ""
    tf_str = ", ".join(tf_codes[:2]) if tf_codes else ""

    parts = []
    if comps_str:
        parts.append(f"формирует компетенции {comps_str}")
    if tf_str:
        parts.append(f"поддерживает трудовые функции {tf_str}")

    if parts:
        return f"Дисциплина {', '.join(parts)} в соответствии с требованиями ФГОС и профстандарта"

    return "Дисциплина формирует профессиональные компетенции в соответствии с ФГОС"


def detect_profile_advanced(fgos_text, detected_profiles):
    text_lower = fgos_text.lower()

    profile_keywords = {
        "Педагогика": ["педагог", "учитель", "преподаватель", "образование", "44.03"],
        "Экономика": ["экономик", "финанс", "бухгалтер", "38.03.01"],
        "Юриспруденция": ["юрист", "право", "закон", "40.03.01"],
        "Психология": ["психолог", "37.03.01"],
        "Менеджмент": ["менеджмент", "управлен", "38.03.02"],
        "Дизайн": ["дизайн", "график", "54.03.01"],
        "ИВТ": ["информатик", "программирован", "09.03.01", "вычислительн"],
    }

    scores = {}
    for profile_name, keywords in profile_keywords.items():
        score = sum(1 for keyword in keywords if keyword in text_lower)
        if score > 0:
            scores[profile_name] = score

    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]

    if detected_profiles:
        for detected in detected_profiles:
            detected_lower = detected.lower()
            for key, val in PROFILE_MAP.items():
                if key.lower() in detected_lower or detected_lower in key.lower():
                    return val

    return None


def match_tf_with_competencies(df_fgos, tf_struct):
    from profstandart import match_fgos_and_prof

    try:
        match_result, error = match_fgos_and_prof(df_fgos, tf_struct)
        if match_result and not error:
            tf_comp_map = {}
            for match in match_result.get("matches", []):
                tf_codes = match.get("related_TF", [])
                comp = match.get("competency", "")
                for tf_code in tf_codes:
                    tf_comp_map.setdefault(tf_code, [])
                    if comp:
                        tf_comp_map[tf_code].append(comp)
            return tf_comp_map
    except:
        pass

    return {}


def generate_plan_pipeline(df_fgos, tf_struct, match_json, fgos_text):
    if df_fgos is None or (isinstance(df_fgos, pd.DataFrame) and df_fgos.empty):
        df_fgos = pd.DataFrame(columns=["code", "description"])

    if tf_struct is None:
        tf_struct = {"TF": []}

    from fgos import detect_profile_from_fgos
    try:
        raw_profiles = detect_profile_from_fgos(fgos_text)
        raw_text = " ".join(raw_profiles).lower() if raw_profiles else ""
    except:
        raw_text = ""

    profile = None
    raw_text_lower = raw_text.lower()

    for key, val in PROFILE_MAP.items():
        if key.lower() in raw_text_lower:
            profile = val
            break

    if profile is None and fgos_text:
        profile = detect_profile_advanced(fgos_text, raw_profiles)

    if profile is None:
        if raw_profiles:
            first_profile = raw_profiles[0].lower()
            for key, val in PROFILE_MAP.items():
                if key.lower() in first_profile or first_profile in key.lower():
                    profile = val
                    break
        if profile is None:
            profile = "ИВТ"

    discs = generate_disciplines(profile, df_fgos, tf_struct, fgos_text)
    if not discs:
        raise ValueError("Не удалось сгенерировать дисциплины")

    discs = remove_duplicates(discs)

    enriched = {}
    for d in discs:
        enriched[d["name"]] = enrich_discipline_metadata(
            d, df_fgos, tf_struct, profile, fgos_text
        )

    obligatory = [d for d in discs if d["block_hint"] == "обязательная"]
    variative = [d for d in discs if d["block_hint"] == "вариативная"]

    semester_map = balanced_distribution(obligatory, variative)

    rows = []

    for sem, disc_list in semester_map.items():
        for disc in disc_list:
            name = disc["name"]
            meta = enriched.get(name, {})

            competencies = detect_competencies(profile, name)
            if not competencies and meta.get("competencies"):
                competencies = meta.get("competencies", [])
            if not competencies and not df_fgos.empty:
                competencies = find_competencies_by_discipline(name, df_fgos)

            tf_codes = meta.get("TF", [])
            if not isinstance(tf_codes, list):
                tf_codes = []

            rows.append({
                "Блок": f"Блок 1. {'Обязательная' if disc['block_hint']=='обязательная' else 'Вариативная'} часть",
                "Семестр": sem,
                "Дисциплина": name,
                "Часы": 144 if disc["block_hint"] == "обязательная" else 108,
                "Форма контроля": assign_assessment(name),
                "Компетенции ФГОС": competencies if isinstance(competencies, list) else [],
                "Трудовые функции": ", ".join(tf_codes) if tf_codes else "",
                "Обоснование": meta.get("reason", "") or generate_reason(name, competencies, tf_codes)
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
