import streamlit as st
import pandas as pd
import io
import json

from plan import generate_plan_pipeline
from ai import completion_with_ai


# ============================================================
# Утилита: применение команды к DataFrame
# ============================================================

def apply_edit_command(df: pd.DataFrame, command: dict) -> tuple[pd.DataFrame, str]:
    """
    Применяет JSON-команду к DataFrame.
    Возвращает (обновленный_df, текст_результата).
    """

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


# ============================================================
# UI: две вкладки
# ============================================================

tab_plan, tab_chat = st.tabs(["📘 Учебный план", "💬 Чат с ИИ"])


# ============================================================
# 📘 Вкладка 1 — Генерация учебного плана
# ============================================================

with tab_plan:
    st.header("Генерация учебного плана")

    uploaded_fgos = st.file_uploader("Загрузите ФГОС", type=["pdf", "txt"])
    uploaded_tf = st.file_uploader("Загрузите профстандарт", type=["pdf", "txt"])

    if uploaded_fgos and uploaded_tf:

        try:
            fgos_text = uploaded_fgos.read().decode("utf-8", errors="ignore")
        except:
            fgos_text = ""

        df_fgos = pd.DataFrame()
        tf_struct = {}

        df = generate_plan_pipeline(df_fgos, tf_struct, {}, fgos_text)

        # сохраняем в сессию, чтобы чат мог редактировать
        st.session_state.df = df

        st.subheader("Сформированный учебный план")
        st.dataframe(df, use_container_width=True)

        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)

        st.download_button(
            label="📥 Скачать учебный план (Excel)",
            data=buffer,
            file_name="учебный_план.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# ============================================================
# 💬 Вкладка 2 — Чат с ИИ (редактирование плана)
# ============================================================

with tab_chat:
    st.header("Чат для редактирования учебного плана")

    if "df" not in st.session_state:
        st.info("Сначала сгенерируй учебный план во вкладке 'Учебный план'.")
    else:
        df = st.session_state.df

        st.subheader("Текущий учебный план")
        st.dataframe(df, use_container_width=True)

        if "messages" not in st.session_state:
            st.session_state.messages = []

        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])

        prompt = st.chat_input("Опиши, что изменить в плане (часы, форму контроля, добавить/удалить дисциплину)...")

        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})

            raw_reply = completion_with_ai(prompt)


            try:
                command = json.loads(raw_reply)
            except Exception:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Не удалось разобрать ответ ИИ как JSON:\n{raw_reply}"
                })
            else:
                df_updated, result_text = apply_edit_command(df, command)
                st.session_state.df = df_updated

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result_text
                })

            st.chat_message("assistant").write(st.session_state.messages[-1]["content"])

        st.subheader("Обновлённый учебный план")
        st.dataframe(st.session_state.df, use_container_width=True)
