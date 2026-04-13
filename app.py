import streamlit as st
import pandas as pd
import io
import json
import time

from plan import generate_plan_pipeline
from ai import completion_with_ai
from fgos import extract_text_from_pdf_file, extract_competencies_full, detect_profile_from_fgos
from profstandart import analyze_prof_standard

import streamlit as st


def select_or_custom(label: str, options: list[str], default: str = "") -> str:
    """
    Выпадающий список с поиском + возможность ввести свой вариант.
    """
    normalized_options = []
    seen = set()

    if default and default not in options:
        options = [default] + options

    for item in options:
        value = str(item).strip()
        if value and value not in seen:
            normalized_options.append(value)
            seen.add(value)

    full_options = ["Свой вариант"] + normalized_options

    default_index = 0
    if default and default in full_options:
        default_index = full_options.index(default)

    selected = st.selectbox(
        label,
        full_options,
        index=default_index,
        key=f"select_{label}"
    )

    if selected == "Свой вариант":
        custom_value = st.text_input(
            f"{label} — введите свой вариант",
            value=default,
            key=f"custom_{label}"
        )
        return custom_value.strip()

    return selected

def apply_edit_command(df: pd.DataFrame, command: dict) -> tuple[pd.DataFrame, str]:
    action = command.get("action")

    if action == "update":
        disc = command.get("discipline")
        field = command.get("field")
        value = command.get("value")

        if disc is None or field is None:
            return df, "Команда некорректна: нет discipline или field."

        if field not in df.columns:
            return df, f"Поле '{field}' не найдено в таблице."

        mask = df["Дисциплина"] == disc
        if not mask.any():
            return df, f"Дисциплина '{disc}' не найдена."

        df.loc[mask, field] = value
        return df, f"Обновлено поле '{field}' у дисциплины '{disc}' → {value}."

    elif action == "delete":
        disc = command.get("discipline")
        if disc is None:
            return df, "Команда некорректна: нет discipline."

        before = len(df)
        df = df[df["Дисциплина"] != disc].reset_index(drop=True)
        after = len(df)

        if before == after:
            return df, f"Дисциплина '{disc}' не найдена."
        else:
            return df, f"Дисциплина '{disc}' удалена."

    elif action == "add":
        field = command.get("field")
        value = command.get("value")

        if field != "row" or not isinstance(value, dict):
            return df, "Команда add некорректна: ожидается field='row' и объект value."

        new_row = {}
        for col in df.columns:
            new_row[col] = value.get(col, None)

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        return df, f"Добавлена новая дисциплина '{value.get('Дисциплина', 'Без названия')}'."

    elif action == "error":
        return df, f"Ошибка на стороне ИИ: {command.get('value')}"

    else:
        return df, f"Неизвестное действие: {action}"


tab_plan, tab_chat, tab_rpd = st.tabs([
    "📘 Учебный план",
    "💬 Чат с ИИ",
    "📄 Рабочие программы"
])

with tab_plan:
    st.header("Генерация учебного плана")

    uploaded_fgos = st.file_uploader("Загрузите ФГОС", type=["pdf", "txt"], key="fgos_uploader")
    uploaded_tf = st.file_uploader(
        "Загрузите профстандарт (необязательно)",
        type=["pdf", "txt"],
        key="prof_uploader"
    )

    # Инициализация session_state
    if "df_fgos" not in st.session_state:
        st.session_state.df_fgos = pd.DataFrame()

    if "fgos_text" not in st.session_state:
        st.session_state.fgos_text = ""

    if "tf_struct" not in st.session_state:
        st.session_state.tf_struct = {"TF": []}

    if "prof_text" not in st.session_state:
        st.session_state.prof_text = ""

    if "detected_profiles" not in st.session_state:
        st.session_state.detected_profiles = []

    if uploaded_fgos:
        with st.spinner("Обработка ФГОС..."):
            try:
                if uploaded_fgos.name.endswith(".pdf"):
                    fgos_text = extract_text_from_pdf_file(uploaded_fgos)
                    if fgos_text.startswith("OCR error") or len(fgos_text.strip()) < 50:
                        st.warning("⚠️ Возможны проблемы с извлечением текста из PDF.")
                else:
                    fgos_text = uploaded_fgos.read().decode("utf-8", errors="ignore")
                    uploaded_fgos.seek(0)

                if not fgos_text or len(fgos_text.strip()) < 50:
                    st.error("❌ Не удалось извлечь текст из файла ФГОС.")
                    st.session_state.df_fgos = pd.DataFrame()
                    st.session_state.fgos_text = ""
                else:
                    st.session_state.fgos_text = fgos_text
                    competencies = extract_competencies_full(fgos_text)

                    if competencies:
                        df_fgos = pd.DataFrame(competencies)
                        st.session_state.df_fgos = df_fgos
                        st.success(f"✅ ФГОС обработан. Извлечено компетенций: {len(competencies)}")
                        st.dataframe(df_fgos, use_container_width=True, height=300)

                        try:
                            profiles = detect_profile_from_fgos(fgos_text)
                            if profiles:
                                st.session_state.detected_profiles = profiles
                                st.info(f"🎯 Определенный профиль: {', '.join(profiles)}")
                        except Exception as e:
                            st.warning(f"⚠️ Не удалось определить профиль: {e}")
                    else:
                        st.warning("⚠️ Компетенции не найдены.")
                        st.session_state.df_fgos = pd.DataFrame()

            except Exception as e:
                st.session_state.df_fgos = pd.DataFrame()
                st.session_state.fgos_text = ""
                st.error(f"Ошибка при обработке ФГОС: {e}")

    if uploaded_tf:
        with st.spinner("Обработка профстандарта..."):
            try:
                if uploaded_tf.name.endswith(".pdf"):
                    prof_text = extract_text_from_pdf_file(uploaded_tf)
                else:
                    prof_text = uploaded_tf.read().decode("utf-8", errors="ignore")
                    uploaded_tf.seek(0)

                if not prof_text or len(prof_text.strip()) < 50:
                    st.session_state.tf_struct = {"TF": []}
                    st.session_state.prof_text = ""
                    st.warning("⚠️ Не удалось извлечь текст из профстандарта.")
                else:
                    st.session_state.prof_text = prof_text
                    tf_struct, error = analyze_prof_standard(prof_text)

                    if error:
                        st.session_state.tf_struct = {"TF": []}
                        st.warning(f"⚠️ Ошибка анализа профстандарта: {error}")

                    elif tf_struct:
                        st.session_state.tf_struct = tf_struct
                        tf_list = tf_struct.get("TF", [])

                        if tf_list:
                            tf_display = []
                            for tf in tf_list:
                                tf_display.append({
                                    "Код": tf.get("code", ""),
                                    "Название": (tf.get("name") or "")[:100],
                                    "Действия": len(tf.get("actions") or []),
                                    "Знания": len(tf.get("knowledge") or []),
                                    "Умения": len(tf.get("skills") or [])
                                })

                            df_tf = pd.DataFrame(tf_display)
                            st.success(f"✅ Профстандарт обработан. Найдено ТФ: {len(tf_list)}")
                            st.dataframe(df_tf, use_container_width=True, height=300)
                        else:
                            st.session_state.tf_struct = {"TF": []}
                            st.warning("⚠️ Трудовые функции не найдены в профстандарте.")
                    else:
                        st.session_state.tf_struct = {"TF": []}
                        st.warning("⚠️ Не удалось обработать профстандарт.")

            except Exception as e:
                st.session_state.tf_struct = {"TF": []}
                st.session_state.prof_text = ""
                st.warning(f"Профстандарт не обработан: {e}")

    # Генерация плана теперь возможна и без профстандарта
    fgos_ready = not st.session_state.get("df_fgos", pd.DataFrame()).empty
    tf_struct = st.session_state.get("tf_struct", {"TF": []})

    if fgos_ready:
        if len(tf_struct.get("TF", [])) > 0:
            st.info(f"Профстандарт загружен: найдено ТФ {len(tf_struct.get('TF', []))}")
        else:
            st.info("Профстандарт не загружен или не распознан. План будет сгенерирован без него.")

        if st.button("🚀 Сгенерировать учебный план", type="primary", use_container_width=True):
            try:
                df = generate_plan_pipeline(
                    st.session_state.df_fgos,
                    tf_struct,
                    {},
                    st.session_state.get("fgos_text", "")
                )
                st.session_state.df = df
                st.success("✅ Учебный план успешно сгенерирован!")
                st.balloons()
            except Exception as e:
                st.error(f"Ошибка генерации учебного плана: {e}")

    if "df" in st.session_state:
        st.subheader("📊 Сформированный учебный план")
        st.dataframe(st.session_state.df, use_container_width=True)

        buffer = io.BytesIO()
        st.session_state.df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)

        st.download_button(
            "📥 Скачать учебный план (Excel)",
            buffer,
            "учебный_план.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )


with tab_chat:
    st.header("💬 Чат с ИИ-методистом")

    if "df" not in st.session_state:
        st.info("ℹ️ Сначала сгенерируйте учебный план.")
    else:
        df = st.session_state.df

        if "chat_mode" not in st.session_state:
            st.session_state.chat_mode = "consultation"

        col1, col2 = st.columns(2)

        if col1.button("🔵 Консультация", use_container_width=True):
            st.session_state.chat_mode = "consultation"
            st.session_state.consultation_messages = []
            st.rerun()

        if col2.button("⚙️ Редактирование", use_container_width=True):
            st.session_state.chat_mode = "editing"
            st.session_state.edit_messages = []
            st.rerun()

        if st.session_state.chat_mode == "consultation":
            from ai import consult_with_methodologist

            if "consultation_messages" not in st.session_state:
                st.session_state.consultation_messages = []

            plan_context = {
                "disciplines_count": len(df),
                "profile": st.session_state.get("detected_profiles", ["не определен"])[0]
                if st.session_state.get("detected_profiles") else "не определен",
                "competencies_count": len(st.session_state.get("df_fgos", pd.DataFrame())),
                "tf_count": len(st.session_state.get("tf_struct", {}).get("TF", [])),
                "disciplines_list": df["Дисциплина"].tolist() if "Дисциплина" in df.columns else [],
                "chat_history": st.session_state.consultation_messages
            }

            for msg in st.session_state.consultation_messages:
                st.chat_message(msg["role"]).write(msg["content"])

            prompt = st.chat_input("Вопрос методисту")

            if prompt:
                st.session_state.consultation_messages.append({"role": "user", "content": prompt})
                try:
                    response = consult_with_methodologist(prompt, plan_context)
                except Exception as e:
                    response = f"Ошибка при обращении к методисту: {str(e)}"
                st.session_state.consultation_messages.append({"role": "assistant", "content": response})
                st.rerun()

        else:
            if "edit_messages" not in st.session_state:
                st.session_state.edit_messages = []

            for msg in st.session_state.edit_messages:
                st.chat_message(msg["role"]).write(msg["content"])

            prompt = st.chat_input("Опишите изменение")

            if prompt:
                st.session_state.edit_messages.append({"role": "user", "content": prompt})
                raw = completion_with_ai(prompt)

                try:
                    command = json.loads(raw)
                    df, text = apply_edit_command(df, command)
                    st.session_state.df = df
                except Exception:
                    text = raw

                st.session_state.edit_messages.append({"role": "assistant", "content": text})
                st.rerun()

        st.subheader("📊 Обновлённый учебный план")
        st.dataframe(st.session_state.df, use_container_width=True)
with tab_rpd:
    st.header("📄 Рабочие программы дисциплин")

    if "df" not in st.session_state or st.session_state.df.empty:
        st.info("Сначала сгенерируйте учебный план.")
    else:
        from work_program import generate_work_program_content, create_work_program_docx

        df = st.session_state.df.copy()

        if "Дисциплина" not in df.columns:
            st.error("В учебном плане нет колонки 'Дисциплина'.")
        else:
            disciplines = df["Дисциплина"].dropna().tolist()

            selected = st.selectbox(
                "Выберите дисциплину",
                disciplines,
                key="selected_rpd_discipline"
            )

            profile = "не определен"
            detected_profiles = st.session_state.get("detected_profiles", [])
            if detected_profiles:
                profile = detected_profiles[0]

            direction_code = select_or_custom(
                "Код направления",
                [
                    "09.03.01",
                    "09.04.01",
                    "40.03.01",
                    "40.04.01",
                    "44.03.01",
                    "44.04.01",
                    "38.03.01",
                    "38.04.01",
                    "37.03.01",
                    "54.03.01",
                ],
                default="09.03.01"
            )

            direction_name = select_or_custom(
                "Направление подготовки",
                [
                    "Информатика и вычислительная техника",
                    "Прикладная информатика",
                    "Информационные системы и технологии",
                    "Юриспруденция",
                    "Педагогическое образование",
                    "Экономика",
                    "Менеджмент",
                    "Психология",
                    "Дизайн",
                ],
                default="Информатика и вычислительная техника"
            )

            qualification = select_or_custom(
                "Квалификация",
                [
                    "бакалавр",
                    "магистр",
                    "специалист",
                ],
                default="бакалавр"
            )

            education_form = select_or_custom(
                "Форма обучения",
                [
                    "очная",
                    "очно-заочная",
                    "заочная",
                ],
                default="очная"
            )

            university_name = select_or_custom(
                "Университет",
                [
                    "Ваш университет",
                    "Пензенский государственный университет",
                    "Московский государственный университет",
                    "Санкт-Петербургский государственный университет",
                    "Казанский федеральный университет",
                    "Уральский федеральный университет",
                ],
                default="Ваш университет"
            )

            faculty_name = select_or_custom(
                "Факультет",
                [
                    "Ваш факультет",
                    "Факультет вычислительной техники",
                    "Юридический факультет",
                    "Экономический факультет",
                    "Педагогический факультет",
                    "Факультет информационных технологий",
                ],
                default="Ваш факультет"
            )

            row = df[df["Дисциплина"] == selected].iloc[0].to_dict()

            if st.button("Сгенерировать рабочую программу DOCX", type="primary", use_container_width=True):
                try:
                    with st.spinner("Генерация рабочей программы..."):
                        content = generate_work_program_content(
                            discipline_row=row,
                            profile=profile,
                            direction_code=direction_code,
                            direction_name=direction_name,
                            qualification=qualification,
                            education_form=education_form,
                            university_name=university_name,
                            faculty_name=faculty_name,
                        )
                        docx_bytes = create_work_program_docx(content)

                    st.success("Рабочая программа сформирована.")

                    filename = f"Рабочая_программа_{selected.replace(' ', '_')}.docx"
                    st.download_button(
                        label="📥 Скачать DOCX",
                        data=docx_bytes,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )

                    with st.expander("Предпросмотр структуры"):
                        st.json(content)

                except Exception as e:
                    st.error(f"Ошибка генерации рабочей программы: {e}")