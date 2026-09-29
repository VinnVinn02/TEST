import os

import pandas as pd
import streamlit as st

from pipeline import export
from pipeline.assemble import COLUMNS, assemble, load_hp_lookup
from pipeline.extract import DEFAULT_MODEL, extract_all
from pipeline.pdf import render_pages
from pipeline.stck import fill_stck

st.set_page_config(page_title="Ekstrak Berkas BAST", layout="wide")
st.title("Ekstrak Berkas BAST → DATA BERKAS, RENAME, REKAP")

with st.sidebar:
    api_key = st.text_input("Anthropic API key", type="password", value=os.environ.get("ANTHROPIC_API_KEY", ""))
    model = st.text_input("Model", DEFAULT_MODEL)
    stck_range = st.text_input("Rentang NO STCK", "6790758 - 6790813",
                               help="Diisi berurutan ke tiap konsumen. Kosongkan bila diisi manual.")

pdf = st.file_uploader("PDF scan (BAST + faktur + sertifikat + KTP)", type="pdf")
hp_xlsx = st.file_uploader("Excel NO HP & EMAIL", type="xlsx")

if pdf and st.button("Proses", type="primary"):
    pages = render_pages(pdf.getvalue())
    bar = st.progress(0.0, "OCR halaman...")
    ocr = extract_all(pages, api_key or None, model, progress=lambda d, t: bar.progress(d / t, f"OCR {d}/{t}"))
    st.session_state.result = assemble(ocr, load_hp_lookup(hp_xlsx) if hp_xlsx else None)
    st.session_state.images = dict(pages)
    st.session_state.stem = os.path.splitext(pdf.name)[0]
    st.session_state.raw = ocr

res = st.session_state.get("result")
if res:
    st.subheader(f"BAST {res['bast_no'] or '?'} — {len(res['records'])} konsumen")
    for g in res["general"]:
        st.warning(g)
    stck_msgs, _ = fill_stck(res["records"], stck_range)
    for m in stck_msgs:
        st.warning(m) if not m.startswith("INFO") else st.info(m)
    df = pd.DataFrame(res["records"], columns=COLUMNS)
    df["PERINGATAN"] = ["\n".join(w) for w in res["warnings"]]
    st.caption("Baris bertanda peringatan perlu dicek. Sel bisa diedit langsung sebelum diunduh.")
    edited = st.data_editor(df, use_container_width=True, num_rows="fixed", disabled=["PERINGATAN"])
    with st.expander("Output JSON (array of objects)"):
        st.json(edited[COLUMNS].to_dict("records"))
    records = edited[COLUMNS].fillna("").astype(str).to_dict("records")
    data = export.build_zip(records, res["warnings"], res["general"], res["meta"], res["bast_no"],
                            st.session_state.stem, st.session_state.images)
    st.download_button("Unduh ZIP (3 Excel + gambar ter-rename)", data,
                       f"BAST_{export.bast_tag(res['bast_no'])}.zip", "application/zip")    st.download_button("Unduh halaman PDF sebagai gambar (nama CamScanner_N)",
                       export.pages_zip(st.session_state.images, st.session_state.stem),
                       "halaman_pdf.zip", "application/zip")

st.divider()
st.subheader("Rename gambar sesuai DATA RENAME")
st.caption("Unggah gambar asli (JPG atau ZIP) dan Excel DATA RENAME; hasilnya ZIP dengan nama baru.")
imgs = st.file_uploader("Gambar asli (JPG / ZIP)", type=["jpg", "jpeg", "zip"], accept_multiple_files=True)
map_xlsx = st.file_uploader("Excel DATA RENAME", type="xlsx", key="map")
if imgs and map_xlsx and st.button("Rename file"):
    from pipeline import renamer
    zdata, rep = renamer.rename_files(renamer.read_mapping(map_xlsx),
                                      renamer.expand_uploads([(f.name, f.getvalue()) for f in imgs]))
    for line in rep:
        st.write(line)
    st.download_button("Unduh ZIP hasil rename", zdata, "berkas_rename.zip", "application/zip")
