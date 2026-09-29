# Ekstrak Berkas BAST
    pip install -r requirements.txt pillow
    export ANTHROPIC_API_KEY=...
    streamlit run app.py
Alur: PDF -> OCR Claude vision per halaman -> cocokkan faktur/sertifikat/KTP + BAST -> 3 Excel + gambar ter-rename (ZIP).
Sheet "PERINGATAN" di DATA BERKAS memuat semua data kurang/tidak cocok. Tes: `pytest`.
