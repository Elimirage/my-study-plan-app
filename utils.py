import io
import pandas as pd


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """
    Преобразует DataFrame в Excel-файл (в байтах),
    чтобы Streamlit мог скачать его через download_button.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()
