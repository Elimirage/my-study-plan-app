import streamlit as st
import pandas as pd
import numpy as np
import json
from fgos import extract_text_from_pdf_file, extract_competencies_full, detect_profile_from_fgos
from profstandart import analyze_prof_standard, match_fgos_and_prof
from plan import generate_plan_pipeline
from utils import dataframe_to_excel_bytes




st.set_page_config(
    page_title="Генератор учебного плана",
    layout="wide"
)

st.title("📘 Генератор учебного плана по ФГОС и профстандарту")




tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📄 ФГОС",
    "📄 Профстандарт",
    "🔗 Сопоставление",
    "📚 Генерация плана",
    "📥 Экспорт"
])




with tab1:

    st.header("📄 Загрузка ФГОС")

    uploaded_fgos = st.file_uploader("Загрузите файл ФГОС (PDF)", type=["pdf"])

    if uploaded_fgos:
        text_fgos = extract_text_from_pdf_file(uploaded_fgos)
        df_fgos = pd.DataFrame(extract_competencies_full(text_fgos))

        st.session_state.df_fgos = df_fgos
        st.session_state.fgos_text = text_fgos
        st.subheader("Первые 500 символов текста ФГОС")
        st.text(text_fgos[:500])


        st.subheader("Извлечённые компетенции")
        st.dataframe(df_fgos, use_container_width=True)

        profiles = detect_profile_from_fgos(text_fgos)
        st.session_state.detected_profiles = profiles

        st.success(f"Определён профиль: {', '.join(profiles)}")




with tab2:
    st.header("📄 Загрузка профстандарта")

    uploaded_prof = st.file_uploader("Загрузите файл профстандарта (PDF)", type=["pdf"])

    if uploaded_prof:
        text_prof = extract_text_from_pdf_file(uploaded_prof)
        tf_struct, error = analyze_prof_standard(text_prof)

        if error:
            st.error(error)
        else:
            st.session_state.tf_struct = tf_struct
            st.success(f"Найдено {len(tf_struct['TF'])} трудовых функций")



with tab3:
    st.header("🔗 Сопоставление ФГОС и профстандарта")

    if "df_fgos" in st.session_state and "tf_struct" in st.session_state:
        match_json, error = match_fgos_and_prof(
            st.session_state.df_fgos,
            st.session_state.tf_struct
        )

        st.session_state.match_json = match_json

        st.success("Сопоставление выполнено")
        st.json(match_json)
    else:
        st.warning("Загрузите ФГОС и профстандарт")



with tab4:
    st.header("📚 Генерация учебного плана")

    ready = all(k in st.session_state for k in [
        "df_fgos", "tf_struct", "match_json", "fgos_text"
    ])

    if not ready:
        st.warning("Не хватает данных для генерации плана")
    else:
        # Кнопка генерации
        if st.button("🔄 Сгенерировать учебный план заново"):
            df_plan = generate_plan_pipeline(
                st.session_state.df_fgos,
                st.session_state.tf_struct,
                st.session_state.match_json,
                st.session_state.fgos_text
            )
            st.session_state.df_plan = df_plan

        # Показываем план, если он уже есть
        if "df_plan" in st.session_state:
            st.success("Учебный план готов")
            # Преобразуем списки компетенций в строки, чтобы PyArrow не падал
            df = st.session_state.df_plan.copy()

            

            df = st.session_state.df_plan.copy()

            def normalize_cell(x):
                if isinstance(x, (list, tuple, set, np.ndarray)):
                    return ", ".join(map(str, x))
                if isinstance(x, dict):
                    return json.dumps(x, ensure_ascii=False)
                return x

            for col in df.columns:
                df[col] = df[col].apply(normalize_cell)

            st.dataframe(df, use_container_width=True)


            st.dataframe(df, use_container_width=True)



with tab5:
    st.header("📥 Экспорт учебного плана")

    if "df_plan" in st.session_state:
        bytes_xlsx = dataframe_to_excel_bytes(st.session_state.df_plan)

        st.download_button(
            "📥 Скачать учебный план в Excel",
            data=bytes_xlsx,
            file_name="учебный_план.xlsx"
        )
    else:
        st.warning("Сначала сгенерируйте учебный план")
