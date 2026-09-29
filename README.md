# Ekstrak Berkas BAST

Membaca PDF scan (BAST + faktur + sertifikat NIK + KTP) dan Excel HP/EMAIL, lalu menghasilkan:
`DATA_BERKAS_<jumlah>_<tanggal>.xlsx`, `DATA_RENAME_<jumlah>_<tanggal>.xlsx`, `REKAP_DATA_<jumlah>_<tanggal>.xlsx`
dan gambar yang sudah di-rename (semua dalam satu ZIP).

## Pasang & jalankan
    pip install -r requirements.txt
    streamlit run app.py          # buka http://localhost:8501

Untuk OCR offline dua mesin, pasang juga **Tesseract** (bahasa `ind` + `eng`):
- Windows: https://github.com/UB-Mannheim/tesseract/wiki (centang bahasa Indonesian, tambahkan ke PATH)
- Linux: `sudo apt install tesseract-ocr tesseract-ocr-ind`
- Mac: `brew install tesseract tesseract-lang`

Untuk OCR Claude: isi `ANTHROPIC_API_KEY` (atau ketik di sidebar aplikasi).

## Cara pakai
1. Sidebar: pilih mesin OCR, isi rentang NO STCK (mis. `6790758 - 6790813`).
2. Unggah PDF dan Excel HP/EMAIL, klik **Proses**.
3. Periksa tabel: sel KUNING = dua OCR beda / tidak terkonfirmasi, MERAH = kosong. Sel bisa diedit.
4. Unduh ZIP.

Aturan: BAST adalah patokan nama, no. faktur (akhiran selalu /Z), no. rangka (+MH1) dan no. mesin.
Tes: `pytest`.
