"""Gabungkan hasil OCR per halaman menjadi satu baris per konsumen + peringatan."""
import openpyxl

from . import normalize as N

COLUMNS = ["NAMA LENGKAP", "NAMA FILE", "WARNA", "CC", "MERK", "TIPE", "TANGGAL FAKTUR", "NO. FAKTUR",
           "NO. SUT", "NO. SRUT", "ALAMAT 1", "NIK", "PEKERJAAN", "ALASAN BELI", "ALAMAT 2",
           "NO RANGKA", "NO MESIN", "NO HP", "EMAIL", "NO STCK"]


def load_hp_lookup(path_or_file) -> dict:
    """Excel HP/EMAIL -> {'rangka': {key: (hp, email)}, 'mesin': {...}}."""
    ws = openpyxl.load_workbook(path_or_file, read_only=True, data_only=True).worksheets[0]
    rows = ws.iter_rows(values_only=True)
    head = [N.up(c) for c in next(rows)]
    col = lambda *names: next((i for i, h in enumerate(head) if any(n in h for n in names)), None)
    ir, im, ih, ie = col("RANGKA"), col("MESIN"), col("HP"), col("EMAIL")
    by_r, by_m = {}, {}
    for r in rows:
        val = (N.hp(r[ih]) if ih is not None else "", N.email(r[ie]) if ie is not None else "")
        for idx, d, key in ((ir, by_r, N.rangka_key), (im, by_m, N.mesin)):
            if idx is not None and r[idx]:
                k = key(r[idx])
                old = d.get(k, ("", ""))
                d[k] = (val[0] or old[0], val[1] or old[1])
    return {"rangka": by_r, "mesin": by_m}


def _st(flag, value=True):
    """Status sel: OK / CEK / KOSONG dari bendera OCR ('OK','BEDA','TIDAK_VALID','KOSONG')."""
    if not value or flag == "KOSONG":
        return "KOSONG"
    return "OK" if flag in (None, "OK") else "CEK"


def _worst(*st):
    for x in ("KOSONG", "CEK"):
        if x in st:
            return x
    return "OK"


def _bast_row_ok(row: dict, alt_by_no: dict, witness: str) -> dict:
    """Suara 2 dari 3 (RapidOCR utama, RapidOCR pra-proses, Tesseract) untuk sel BAST yang jadi patokan."""
    alt = alt_by_no.get(str(row.get("no")).strip(), {})
    same = lambda k, fn: bool(alt) and fn(row.get(k)) == fn(alt.get(k))
    w = lambda x: bool(x) and x in witness
    d = N.faktur_digits(row.get("no_faktur"))
    return {
        "nama": same("nama", N.up) or w(N.re.sub(r"[^A-Z0-9]", "", N.up(row.get("nama")))),
        "no_faktur": same("no_faktur", N.faktur_digits) or w(f"/{d}/"),
        "no_rangka": same("no_rangka", N.rangka_key) or w(N.rangka_key(row.get("no_rangka"))),
        "no_mesin": same("no_mesin", N.mesin) or w(N.mesin(row.get("no_mesin"))),
    }


def _score(f: dict, b: dict) -> float:
    dig = 1.0 if N.faktur_digits(f.get("no_faktur")) and \
        N.faktur_digits(f.get("no_faktur")) == N.faktur_digits(b.get("no_faktur")) else \
        N.ratio(N.faktur_digits(f.get("no_faktur")), N.faktur_digits(b.get("no_faktur")))
    return (0.35 * N.ratio(N.rangka_key(f.get("no_rangka")), N.rangka_key(b.get("no_rangka")))
            + 0.25 * N.ratio(N.mesin(f.get("no_mesin")), N.mesin(b.get("no_mesin")))
            + 0.25 * dig + 0.15 * N.ratio(f.get("nama"), b.get("nama")))


def assemble(pages: list[dict], hp_lookup: dict | None = None):
    """pages: hasil extract_all. Return dict(records, warnings, meta, bast_no)."""
    pages = sorted(pages, key=lambda p: p["page"])  # urutan data = urutan halaman scan
    by = lambda t: [p for p in pages if p.get("doc_type") == t]
    bast_no = next((p["bast_nomor"] for p in by("BAST") if p.get("bast_nomor")), "")
    bast_rows, seen = [], set()
    for p in by("BAST"):
        for r in p.get("bast_baris") or []:
            k = (N.faktur_digits(r.get("no_faktur")), N.rangka_key(r.get("no_rangka")))
            if k not in seen:
                seen.add(k)
                alt = {str(a.get("no")).strip(): a for a in p.get("_bast_alt") or []}
                r["_ok"] = _bast_row_ok(r, alt, p.get("_witness", "")) if (alt or p.get("_witness")) else None
                bast_rows.append(r)
    fakturs = by("FAKTUR")
    sertifs, ktps = list(by("SERTIFIKAT")), list(by("KTP"))
    general = []
    if not by("BAST"):
        general.append("Halaman BAST tidak ditemukan: nama, no faktur, rangka, mesin diambil dari faktur.")
    elif len(bast_rows) != len(fakturs):
        general.append(f"Jumlah baris BAST ({len(bast_rows)}) berbeda dengan jumlah faktur ({len(fakturs)}).")
    for p in pages:
        if p.get("doc_type") == "LAINNYA" or p.get("terbaca") == "KURANG_JELAS":
            general.append(f"Halaman {p['page']}: {p.get('catatan') or 'kurang jelas / tidak dikenali'}")

    # faktur -> baris BAST (skor tertinggi lebih dulu, tiap baris BAST dipakai sekali)
    cands = sorted(((_score(p.get("faktur") or {}, b), i, j) for i, p in enumerate(fakturs)
                    for j, b in enumerate(bast_rows)), reverse=True)
    match, used = {}, set()
    for s, i, j in cands:
        if s >= 0.6 and i not in match and j not in used:
            match[i] = j
            used.add(j)

    records, warnings, meta, cells = [], [], [], []
    for i, p in enumerate(fakturs):
        f = p.get("faktur") or {}
        w = []
        b = bast_rows[match[i]] if i in match else None
        if p.get("terbaca") == "KURANG_JELAS":
            w.append(f"Faktur hal. {p['page']} kurang jelas: {p.get('catatan', '')}")
        # nama
        nama_f = N.up(f.get("nama"))
        if b:
            nama = N.up(b.get("nama"))
            if nama_f and nama != nama_f:
                w.append(f"INFO: nama diperbaiki sesuai BAST ({nama_f} -> {nama})")
        else:
            nama = nama_f
            w.append("Tidak cocok dengan baris BAST manapun: data dari faktur belum terverifikasi")
        if not nama:
            w.append("Nama kosong")
        # no faktur
        nf_f = N.no_faktur(f.get("no_faktur"))
        nf = N.no_faktur(b.get("no_faktur")) if b and N.faktur_digits(b.get("no_faktur")) else nf_f
        if nf_f and nf != nf_f:
            w.append(f"INFO: no faktur diperbaiki sesuai BAST ({nf_f} -> {nf})")
        if not nf:
            w.append("No faktur kosong")
        # rangka / mesin (sumber BAST)
        rk = N.rangka(b.get("no_rangka")) if b and b.get("no_rangka") else N.rangka(f.get("no_rangka"))
        ms = N.mesin(b.get("no_mesin")) if b and b.get("no_mesin") else N.mesin(f.get("no_mesin"))
        if len(rk) != 17:
            w.append(f"No rangka tidak 17 karakter ({rk or 'kosong'})")
        if not ms:
            w.append("No mesin kosong")
        if b and f.get("no_rangka") and N.rangka(f["no_rangka"]) != rk:
            w.append(f"No rangka BAST ({rk}) beda dengan faktur ({N.rangka(f['no_rangka'])}); dipakai BAST")
        if b and f.get("no_mesin") and N.mesin(f["no_mesin"]) != ms:
            w.append(f"No mesin BAST ({ms}) beda dengan faktur ({N.mesin(f['no_mesin'])}); dipakai BAST")
        # sertifikat
        sert = _pick(sertifs, lambda s: N.faktur_digits((s.get("sertifikat") or {}).get("no_faktur")) == N.faktur_digits(nf) != ""
                     or N.mesin((s.get("sertifikat") or {}).get("no_mesin")) == ms != "", fallback_page=p["page"] + 1)
        if not sert:
            w.append("Sertifikat NIK tidak ditemukan")
        # NIK dari faktur, KTP untuk pekerjaan
        nik = N.nik(f.get("nik"))
        ktp = _pick(ktps, lambda k: (N.nik((k.get("ktp") or {}).get("nik")) == nik != "")
                    or N.ratio((k.get("ktp") or {}).get("nama"), nama) >= 0.85)
        if len(nik) != 16:
            w.append(f"NIK di faktur tidak 16 digit ({nik or 'kosong'})")
        pekerjaan = ""
        if ktp:
            k = ktp.get("ktp") or {}
            pekerjaan = N.up(k.get("pekerjaan"))
            kn = N.nik(k.get("nik"))
            if nik and kn and kn != nik:
                w.append(f"NIK KTP ({kn}) beda dengan faktur ({nik}); dipakai faktur")
            if not pekerjaan:
                w.append("Pekerjaan di KTP tidak terbaca")
        else:
            w.append("KTP tidak ditemukan: PEKERJAAN & ALASAN BELI kosong")
        # alamat
        a1, ok = N.alamat1(f.get("alamat_baris1"))
        if not ok:
            w.append("Alamat 1 tidak memuat RW; cek faktur")
        a2 = N.alamat2(f.get("kelurahan"), f.get("kecamatan"), f.get("kota"))
        if not a2:
            w.append("Alamat 2 (kelurahan - kecamatan) kosong")
        # field faktur lain
        cc, tgl = N.cc(f.get("cc")), N.tanggal(f.get("tanggal"))
        sut, srut = N.strip_no(f.get("sut")), N.strip_no(f.get("srut"))
        for label, v in (("Warna", f.get("warna")), ("CC", cc), ("Merk", f.get("merk")), ("Tipe", f.get("tipe")),
                         ("Tanggal faktur", tgl), ("No SUT", sut), ("No SRUT", srut)):
            if not v:
                w.append(f"{label} kosong / tidak terbaca")
        # HP & email
        h = e = ""
        if hp_lookup:
            h, e = hp_lookup["rangka"].get(N.rangka_key(rk)) or hp_lookup["mesin"].get(ms) or ("", "")
        if not h:
            w.append("No HP tidak ditemukan di Excel HP/EMAIL")
        if not e:
            w.append("Email tidak ditemukan di Excel HP/EMAIL")

        # ---- status sel: OK / CEK / KOSONG
        pf = p.get("_flags")
        ff = lambda key, val: _st((pf or {}).get(key) if pf is not None else (
            "BEDA" if p.get("terbaca") == "KURANG_JELAS" else None), val)
        bok = (b or {}).get("_ok") or {}
        bconf = lambda key: bok.get(key, True) if b else False    # BAST sendiri terkonfirmasi?
        kf = (ktp or {}).get("_flags") or {}
        sfak = N.faktur_digits((sert or {}).get("sertifikat", {}).get("no_faktur")) if sert else ""
        kn = N.nik((ktp or {}).get("ktp", {}).get("nik")) if ktp else ""
        cf = {
            "NAMA LENGKAP": "KOSONG" if not nama else ("OK" if b and bconf("nama") and (
                N.ratio(nama, nama_f) >= 0.85 or (ktp and N.ratio(nama, (ktp.get("ktp") or {}).get("nama")) >= 0.85)) else "CEK"),
            "NO. FAKTUR": "KOSONG" if not nf else ("OK" if b and bconf("no_faktur") and (
                N.faktur_digits(f.get("no_faktur")) == N.faktur_digits(nf) or sfak == N.faktur_digits(nf)) else "CEK"),
            "NO RANGKA": "KOSONG" if not rk else ("OK" if len(rk) == 17 and b and bconf("no_rangka") and
                                                 N.rangka(f.get("no_rangka")) == rk else "CEK"),
            "NO MESIN": "KOSONG" if not ms else ("OK" if b and bconf("no_mesin") and N.mesin(f.get("no_mesin")) == ms else "CEK"),
            "WARNA": ff("warna", f.get("warna")), "CC": ff("cc", cc), "MERK": ff("merk", f.get("merk")),
            "TIPE": ff("tipe", f.get("tipe")), "TANGGAL FAKTUR": ff("tanggal", tgl),
            "NO. SUT": ff("sut", sut), "NO. SRUT": ff("srut", srut),
            "ALAMAT 1": "OK" if ok and ff("alamat_baris1", a1) == "OK" else ("KOSONG" if not a1 else "CEK"),
            "ALAMAT 2": _worst(ff("kelurahan", a2), ff("kecamatan", a2)) if a2 else "KOSONG",
            "NIK": "KOSONG" if not nik else ("OK" if len(nik) == 16 and ff("nik", nik) == "OK" and kn == nik and
                                             kf.get("nik", "OK") == "OK" else "CEK"),
            "PEKERJAAN": "KOSONG" if not pekerjaan else _st(kf.get("pekerjaan") if kf else (
                "BEDA" if ktp and ktp.get("terbaca") == "KURANG_JELAS" else None)),
            "NO HP": "OK" if h else "KOSONG", "EMAIL": "OK" if e else "KOSONG",
        }
        cf["ALASAN BELI"] = cf["PEKERJAAN"]
        cf["NO STCK"] = "KOSONG"
        cek = [c for c in COLUMNS if cf.get(c) == "CEK"]
        if cek:
            w.append("PERLU CEK (dua OCR beda / tak terkonfirmasi): " + ", ".join(cek))
        cells.append(cf)
        fn = N.file_names(nama)
        records.append({
            "NAMA LENGKAP": nama, "NAMA FILE": "\n".join([fn["FAKTUR"], fn["KTP"], fn["SERTIFIKAT"]]),
            "WARNA": N.warna(f.get("warna")), "CC": cc, "MERK": N.up(f.get("merk")), "TIPE": N.up(f.get("tipe")),
            "TANGGAL FAKTUR": tgl, "NO. FAKTUR": nf, "NO. SUT": sut, "NO. SRUT": srut,
            "ALAMAT 1": a1, "NIK": nik, "PEKERJAAN": pekerjaan, "ALASAN BELI": N.alasan_beli(pekerjaan),
            "ALAMAT 2": a2, "NO RANGKA": rk, "NO MESIN": ms, "NO HP": h, "EMAIL": e, "NO STCK": "",
        })
        warnings.append(w)
        meta.append({"TAHUN": N.up(f.get("tahun")) or (tgl[:4] if tgl else ""),
                     "pages": {"FAKTUR": p["page"], "SERTIFIKAT": sert["page"] if sert else None,
                               "KTP": ktp["page"] if ktp else None}})
    for k in ktps + sertifs:
        if not k.get("_used"):
            general.append(f"Halaman {k['page']} ({k['doc_type']}) tidak cocok dengan faktur manapun")
    for j, b in enumerate(bast_rows):
        if j not in used:
            general.append(f"Baris BAST {b.get('no', j + 1)} ({N.up(b.get('nama'))}) tidak punya faktur di PDF")
    general.append("NO STCK tidak ada di dokumen sumber: diisi dari rentang nomor (sidebar) atau manual.")
    return {"records": records, "warnings": warnings, "general": general, "meta": meta, "bast_no": bast_no,
            "doc_types": {p["page"]: p.get("doc_type") for p in pages}, "cells": cells}


def _pick(pool, pred, fallback_page=None):
    for x in pool:
        if not x.get("_used") and pred(x):
            x["_used"] = True
            return x
    for x in pool:  # cadangan: halaman tepat setelah faktur
        if fallback_page and not x.get("_used") and x["page"] == fallback_page:
            x["_used"] = True
            return x
    return None
