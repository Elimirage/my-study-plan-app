import pandas as pd

from disciplines import generate_disciplines
from ai import enrich_discipline_metadata
from competencies import detect_competencies


def remove_duplicates(discs):
    seen = set()
    unique = []

    for d in discs:
        name = str(d.get("name", "")).strip()
        low = name.lower()

        if not name:
            continue

        if low not in seen:
            seen.add(low)
            unique.append(d)

    return unique


def detect_profile_by_code(fgos_text: str):
    """
    Самый надёжный способ определить профиль — по коду направления.
    Это исправляет ошибку, когда любое слово 'образование' давало профиль 'Педагогика'.
    """
    text = (fgos_text or "").lower()

    if "09.03.01" in text or "09.04.01" in text:
        return "ИВТ"

    if "03.04.01" in text or "03.03.01" in text:
        return "Прикладные математика и физика"

    if "54.05.02" in text:
        return "Живопись"

    if "50.03.03" in text:
        return "История искусств"

    if "44.03.01" in text or "44.04.01" in text:
        return "Педагогика"

    if "38.03.01" in text or "38.04.01" in text:
        return "Экономика"

    if "40.03.01" in text or "40.04.01" in text:
        return "Юриспруденция"

    if "37.03.01" in text or "37.04.01" in text:
        return "Психология"

    if "38.03.02" in text or "38.04.02" in text:
        return "Менеджмент"

    if "54.03.01" in text:
        return "Дизайн"

    return None


def detect_profile_advanced(fgos_text, detected_profiles=None):
    """
    Резервное определение профиля, если код направления не найден.
    Важно: слово 'образование' НЕ используется как самостоятельный маркер педагогики.
    """
    text_lower = (fgos_text or "").lower()

    by_code = detect_profile_by_code(text_lower)
    if by_code:
        return by_code

    profile_keywords = {
        "ИВТ": [
            "информатика и вычислительная техника",
            "вычислительная техника",
            "программное обеспечение",
            "информационные системы",
            "алгоритмы",
            "программирование",
            "информационно-коммуникационные технологии"
        ],
        "Прикладные математика и физика": [
            "прикладные математика и физика",
            "математическое моделирование",
            "прикладная физика",
            "физико-математический",
            "численные методы",
            "дифференциальные уравнения"
        ],
        "Живопись": [
            "живопись",
            "изобразительное искусство",
            "художественная деятельность",
            "академический рисунок",
            "академическая живопись",
            "композиция",
            "реставрация"
        ],
        "История искусств": [
            "история искусств",
            "искусствоведение",
            "музейная деятельность",
            "культурно-просветительская деятельность"
        ],
        "Педагогика": [
            "педагогическое образование",
            "педагогическая деятельность",
            "учитель",
            "педагогический профиль"
        ],
        "Экономика": [
            "экономика",
            "экономическая деятельность",
            "финансы",
            "бухгалтерский учет"
        ],
        "Юриспруденция": [
            "юриспруденция",
            "правовое обеспечение",
            "правоохранительная деятельность",
            "гражданское право",
            "уголовное право"
        ],
        "Психология": [
            "психология",
            "психологическая деятельность",
            "психодиагностика"
        ],
        "Менеджмент": [
            "менеджмент",
            "управление персоналом",
            "управленческая деятельность"
        ],
        "Дизайн": [
            "дизайн",
            "графический дизайн",
            "проектная художественная деятельность"
        ],
    }

    scores = {}

    for profile_name, keywords in profile_keywords.items():
        score = sum(1 for keyword in keywords if keyword in text_lower)
        if score > 0:
            scores[profile_name] = score

    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]

    detected_profiles = detected_profiles or []
    joined = " ".join(detected_profiles).lower()

    if "информатика" in joined or "вычислительная техника" in joined:
        return "ИВТ"

    if "прикладные математика и физика" in joined:
        return "Прикладные математика и физика"

    if "живопись" in joined:
        return "Живопись"

    if "история искусств" in joined:
        return "История искусств"

    if "педагогическое образование" in joined:
        return "Педагогика"

    return "ИВТ"


def balanced_distribution(obligatory, variative, level="bachelor"):
    """
    Распределяет дисциплины по семестрам.
    """
    if level == "master":
        semester_plan = {s: [] for s in range(1, 5)}

        sems_obl = [1, 2]
        for i, disc in enumerate(obligatory):
            semester_plan[sems_obl[i % len(sems_obl)]].append(disc)

        sems_var = [2, 3]
        for i, disc in enumerate(variative):
            semester_plan[sems_var[i % len(sems_var)]].append(disc)

        return semester_plan

    if level == "specialist":
        semester_plan = {s: [] for s in range(1, 11)}

        sems_obl = [1, 2, 3, 4, 5, 6, 7]
        for i, disc in enumerate(obligatory):
            semester_plan[sems_obl[i % len(sems_obl)]].append(disc)

        sems_var = [4, 5, 6, 7, 8, 9]
        for i, disc in enumerate(variative):
            semester_plan[sems_var[i % len(sems_var)]].append(disc)

        return semester_plan

    semester_plan = {s: [] for s in range(1, 9)}

    sems_obl = [1, 2, 3, 4, 5, 6]
    for i, disc in enumerate(obligatory):
        semester_plan[sems_obl[i % len(sems_obl)]].append(disc)

    sems_var = [3, 4, 5, 6, 7]
    for i, disc in enumerate(variative):
        semester_plan[sems_var[i % len(sems_var)]].append(disc)

    return semester_plan


def detect_level(fgos_text: str, profile: str = ""):
    text = (fgos_text or "").lower()
    p = (profile or "").lower()

    if "54.05.02" in text or "специалитет" in text or "специалист" in p:
        return "specialist"

    if "03.04.01" in text or "09.04.01" in text or "магистратура" in text or "магистр" in p:
        return "master"

    return "bachelor"


def assign_assessment(name):
    name = str(name or "").lower()

    exam_keywords = [
        "математ", "механик", "программ", "алгоритм",
        "базы данных", "sql", "nosql", "архитектур",
        "сет", "безопас", "машин", "искусственный интеллект",
        "теория", "анализ", "проектирован", "живопись",
        "рисунок", "композиция", "физик", "уравнен"
    ]

    diff_keywords = [
        "график", "вектор", "растров", "мультимед",
        "веб", "api", "cms", "ux", "ui", "разработка",
        "практикум"
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
    if df_fgos is None or df_fgos.empty:
        return []

    discipline_lower = str(discipline_name or "").lower()
    found_competencies = []

    keywords_map = {
        "математ": ["УК-1", "ОПК-1"],
        "физик": ["УК-1", "ОПК-1"],
        "моделирован": ["УК-1", "ОПК-1"],
        "программ": ["ОПК-2", "ОПК-8"],
        "алгоритм": ["ОПК-1", "ОПК-8"],
        "базы данных": ["ОПК-2", "ОПК-3"],
        "операцион": ["ОПК-2", "ОПК-3"],
        "архитектур": ["ОПК-1", "ОПК-2"],
        "живопись": ["УК-1", "ОПК-1"],
        "рисунок": ["УК-1", "ОПК-1"],
        "композиция": ["УК-1", "ОПК-1"],
        "искусств": ["УК-5", "ОПК-1"],
        "педагог": ["ОПК-1", "ОПК-2"],
        "психолог": ["УК-2", "ОПК-3"],
    }

    for keyword, comps in keywords_map.items():
        if keyword in discipline_lower:
            found_competencies.extend(comps)

    available = set(str(x) for x in df_fgos["code"].tolist()) if "code" in df_fgos.columns else set()

    filtered = [c for c in found_competencies if c in available]

    return list(dict.fromkeys(filtered))[:4]


def generate_reason(discipline_name, competencies, tf_codes):
    if not competencies and not tf_codes:
        return "Дисциплина формирует профессиональные компетенции в соответствии с ФГОС."

    comps_str = ", ".join(competencies[:3]) if competencies else ""
    tf_str = ", ".join(tf_codes[:2]) if tf_codes else ""

    parts = []

    if comps_str:
        parts.append(f"формирует компетенции {comps_str}")

    if tf_str:
        parts.append(f"поддерживает трудовые функции {tf_str}")

    if parts:
        return f"Дисциплина {', '.join(parts)} в соответствии с требованиями ФГОС и профстандарта."

    return "Дисциплина формирует профессиональные компетенции в соответствии с ФГОС."


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

    except Exception:
        pass

    return {}


def _add_practice_and_gia(rows, profile, level):
    if level == "master":
        rows.extend([
            {
                "Блок": "Блок 2. Практика",
                "Семестр": 3,
                "Дисциплина": "Научно-исследовательская работа",
                "Часы": 216,
                "Форма контроля": "зачёт",
                "Компетенции ФГОС": detect_competencies(profile, "Научно-исследовательская работа"),
                "Трудовые функции": "",
                "Обоснование": "Практика по ФГОС."
            },
            {
                "Блок": "Блок 2. Практика",
                "Семестр": 4,
                "Дисциплина": "Преддипломная практика",
                "Часы": 216,
                "Форма контроля": "зачёт",
                "Компетенции ФГОС": detect_competencies(profile, "Преддипломная практика"),
                "Трудовые функции": "",
                "Обоснование": "Преддипломная практика по ФГОС."
            },
            {
                "Блок": "Блок 3. ГИА",
                "Семестр": 4,
                "Дисциплина": "ВКР",
                "Часы": 216,
                "Форма контроля": "защита",
                "Компетенции ФГОС": detect_competencies(profile, "ВКР"),
                "Трудовые функции": "",
                "Обоснование": "Государственная итоговая аттестация."
            }
        ])

        return rows

    if level == "specialist":
        rows.extend([
            {
                "Блок": "Блок 2. Практика",
                "Семестр": 8,
                "Дисциплина": "Учебная практика",
                "Часы": 216,
                "Форма контроля": "зачёт",
                "Компетенции ФГОС": detect_competencies(profile, "Учебная практика"),
                "Трудовые функции": "",
                "Обоснование": "Практика по ФГОС."
            },
            {
                "Блок": "Блок 2. Практика",
                "Семестр": 10,
                "Дисциплина": "Преддипломная практика",
                "Часы": 216,
                "Форма контроля": "зачёт",
                "Компетенции ФГОС": detect_competencies(profile, "Преддипломная практика"),
                "Трудовые функции": "",
                "Обоснование": "Преддипломная практика по ФГОС."
            },
            {
                "Блок": "Блок 3. ГИА",
                "Семестр": 10,
                "Дисциплина": "ВКР",
                "Часы": 324,
                "Форма контроля": "защита",
                "Компетенции ФГОС": detect_competencies(profile, "ВКР"),
                "Трудовые функции": "",
                "Обоснование": "Государственная итоговая аттестация."
            }
        ])

        return rows

    rows.extend([
        {
            "Блок": "Блок 2. Практика",
            "Семестр": 7,
            "Дисциплина": "Учебная практика",
            "Часы": 108,
            "Форма контроля": "зачёт",
            "Компетенции ФГОС": detect_competencies(profile, "Учебная практика"),
            "Трудовые функции": "",
            "Обоснование": "Практика по ФГОС."
        },
        {
            "Блок": "Блок 2. Практика",
            "Семестр": 8,
            "Дисциплина": "Преддипломная практика",
            "Часы": 108,
            "Форма контроля": "зачёт",
            "Компетенции ФГОС": detect_competencies(profile, "Преддипломная практика"),
            "Трудовые функции": "",
            "Обоснование": "Преддипломная практика по ФГОС."
        },
        {
            "Блок": "Блок 3. ГИА",
            "Семестр": 8,
            "Дисциплина": "ВКР",
            "Часы": 216,
            "Форма контроля": "защита",
            "Компетенции ФГОС": detect_competencies(profile, "ВКР"),
            "Трудовые функции": "",
            "Обоснование": "Государственная итоговая аттестация."
        }
    ])

    return rows


def generate_plan_pipeline(df_fgos, tf_struct, match_json, fgos_text):
    if df_fgos is None or (isinstance(df_fgos, pd.DataFrame) and df_fgos.empty):
        df_fgos = pd.DataFrame(columns=["code", "description"])

    if tf_struct is None:
        tf_struct = {"TF": []}

    profile = detect_profile_by_code(fgos_text)

    if profile is None:
        profile = detect_profile_advanced(fgos_text, [])

    if profile is None:
        profile = "ИВТ"

    level = detect_level(fgos_text, profile)

    discs = generate_disciplines(profile, df_fgos, tf_struct, fgos_text)

    if not discs:
        raise ValueError("Не удалось сгенерировать дисциплины")

    discs = remove_duplicates(discs)

    enriched = {}

    for d in discs:
        enriched[d["name"]] = enrich_discipline_metadata(
            d,
            df_fgos,
            tf_struct,
            profile,
            fgos_text
        )

    obligatory = [
        d for d in discs
        if d.get("block_hint") == "обязательная"
    ]

    variative = [
        d for d in discs
        if d.get("block_hint") == "вариативная"
    ]

    semester_map = balanced_distribution(obligatory, variative, level)

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

            if not isinstance(competencies, list):
                competencies = []

            tf_codes = meta.get("TF", [])

            if not isinstance(tf_codes, list):
                tf_codes = []

            block_name = (
                "Блок 1. Обязательная часть"
                if disc.get("block_hint") == "обязательная"
                else "Блок 1. Вариативная часть"
            )

            hours = 144 if disc.get("block_hint") == "обязательная" else 108

            rows.append({
                "Блок": block_name,
                "Семестр": sem,
                "Дисциплина": name,
                "Часы": hours,
                "Форма контроля": assign_assessment(name),
                "Компетенции ФГОС": competencies,
                "Трудовые функции": ", ".join(tf_codes) if tf_codes else "",
                "Обоснование": meta.get("reason", "") or generate_reason(name, competencies, tf_codes)
            })

    rows = _add_practice_and_gia(rows, profile, level)

    return pd.DataFrame(rows)