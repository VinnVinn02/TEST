"""Verifikasi silang: DATA RENAME vs jenis halaman, dan DATA KENDARAAN vs REKAP."""
from collections import Counter

LABEL_TO_TYPE = {"FAKTUR KENDARAAN BERMOTOR": "FAKTUR", "SERTIFIKAT NIK": "SERTIFIKAT", "KTP": "KTP"}


def verify_rename(rename_rows, records, meta, doc_types=None):
    """rename_rows: (no, halaman, nama_lama, nama_baru, jenis)."""
    out = []
    for c, n in Counter(r[3] for r in rename_rows).items():
        if n > 1:
            out.append(f"Nama baru ganda: {c}")
    for c, n in Counter(r[1] for r in rename_rows).items():
        if n > 1:
            out.append(f"Halaman {c} dipakai {n}x di DATA RENAME")
    if doc_types:
        for no, pg, lama, baru, jenis in rename_rows:
            got, want = doc_types.get(pg), LABEL_TO_TYPE.get(jenis)
            if got != want:
                out.append(f"{lama} -> {baru}: halaman {pg} terbaca sebagai {got}, seharusnya {want}")
        used = {r[1] for r in rename_rows}
        for pg, t in doc_types.items():
            if t in LABEL_TO_TYPE.values() and pg not in used:
                out.append(f"Halaman {pg} ({t}) belum masuk DATA RENAME")
    for r, m in zip(records, meta):
        for kind, pg in m["pages"].items():
            if not pg:
                out.append(f"{r['NAMA LENGKAP']}: file {kind} tidak ada di DATA RENAME")
    return out


def verify_rekap(records, rekap_rows):
    """Nilai di REKAP harus sama dengan DATA KENDARAAN."""
    out = []
    pairs = (("NO. FAKTUR", 1), ("NAMA LENGKAP", 2), ("NO RANGKA", 5), ("NO MESIN", 6),
             ("WARNA", 8), ("NO HP", 9), ("EMAIL", 10))
    if len(records) != len(rekap_rows):
        return [f"Jumlah baris DATA KENDARAAN ({len(records)}) beda dengan REKAP ({len(rekap_rows)})"]
    for r, row in zip(records, rekap_rows):
        for col, idx in pairs:
            if str(r[col]) != str(row[idx]):
                out.append(f"{r['NAMA LENGKAP']}: {col} beda antara DATA KENDARAAN dan REKAP")
        if r["ALAMAT 1"] and not str(row[3]).startswith(r["ALAMAT 1"]):
            out.append(f"{r['NAMA LENGKAP']}: ALAMAT beda antara DATA KENDARAAN dan REKAP")
        if r["MERK"] + " " + r["TIPE"] != str(row[4]).strip() and (r["MERK"] or r["TIPE"]):
            out.append(f"{r['NAMA LENGKAP']}: TYPE beda antara DATA KENDARAAN dan REKAP")
    return out


def verify_all(records, meta, rename_rows, doc_types=None):
    from .export import rekap_rows
    return verify_rename(rename_rows, records, meta, doc_types) + verify_rekap(records, rekap_rows(records, meta))
