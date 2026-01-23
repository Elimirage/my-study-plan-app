import streamlit as st
import pandas as pd
import io
import json
import time

from plan import generate_plan_pipeline
from ai import completion_with_ai
from fgos import extract_text_from_pdf_file, extract_competencies_full, detect_profile_from_fgos
from profstandart import analyze_prof_standard


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


tab_plan, tab_chat = st.tabs(["📘 Учебный план", "💬 Чат с ИИ"])


with tab_plan:
    st.header("Генерация учебного плана")

    uploaded_fgos = st.file_uploader("Загрузите ФГОС", type=["pdf", "txt"], key="fgos_uploader")
    uploaded_tf = st.file_uploader("Загрузите профстандарт", type=["pdf", "txt"], key="prof_uploader")

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
                        except Exception:
                            pass
                    else:
                        st.warning("⚠️ Компетенции не найдены.")
                        st.session_state.df_fgos = pd.DataFrame()
            except Exception:
                st.session_state.df_fgos = pd.DataFrame()
                st.session_state.fgos_text = ""

    if uploaded_tf:
        with st.spinner("Обработка профстандарта..."):
            try:
                if uploaded_tf.name.endswith(".pdf"):
                    prof_text = extract_text_from_pdf_file(uploaded_tf)
                else:
                    prof_text = uploaded_tf.read().decode("utf-8", errors="ignore")
                    uploaded_tf.seek(0)

                if not prof_text or len(prof_text.strip()) < 50:
                    st.session_state.tf_struct = {}
                    st.session_state.prof_text = ""
                else:
                    st.session_state.prof_text = prof_text
                    tf_struct, error = analyze_prof_standard(prof_text)

                    if tf_struct and not error:
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
                            st.session_state.tf_struct = {}
                    else:
                        st.session_state.tf_struct = {}
            except Exception:
                st.session_state.tf_struct = {}
                st.session_state.prof_text = ""

    if uploaded_fgos and uploaded_tf:
        fgos_ready = not st.session_state.get("df_fgos", pd.DataFrame()).empty
        prof_ready = len(st.session_state.get("tf_struct", {}).get("TF", [])) > 0

        if fgos_ready and prof_ready:
            if st.button("🚀 Сгенерировать учебный план", type="primary", use_container_width=True):
                try:
                    df = generate_plan_pipeline(
                        st.session_state.df_fgos,
                        st.session_state.tf_struct,
                        {},
                        st.session_state.fgos_text
                    )
                    st.session_state.df = df
                    st.success("✅ Учебный план успешно сгенерирован!")
                    st.balloons()
                except Exception as e:
                    st.error(str(e))

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
                "profile": st.session_state.get("detected_profiles", ["не определен"])[0],
                "competencies_count": len(st.session_state.get("df_fgos", pd.DataFrame())),
                "tf_count": len(st.session_state.get("tf_struct", {}).get("TF", [])),
                "disciplines_list": df["Дисциплина"].tolist(),
                "chat_history": st.session_state.consultation_messages
            }

            for msg in st.session_state.consultation_messages:
                st.chat_message(msg["role"]).write(msg["content"])

            prompt = st.chat_input("Вопрос методисту")

            if prompt:
                st.session_state.consultation_messages.append({"role": "user", "content": prompt})
                response = consult_with_methodologist(prompt, plan_context)
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
