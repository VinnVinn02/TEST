"""OCR offline (RapidOCR/ONNX) dengan DUA pass + penandaan bidang yang perlu dicek.

Pass A: gambar 150 dpi apa adanya. Pass B: 220 dpi, grayscale, autocontrast, sharpen.
Tiap bidang dari kedua pass dibandingkan: sama & valid -> OK; beda / tidak valid -> CEK.
Hasilnya berformat sama dengan extract.py (Claude) ditambah kunci "_flags".
"""
import io
import re
from difflib import get_close_matches

from . import normalize as N

_engine = None

PEKERJAAN = [
    "BELUM/TIDAK BEKERJA", "MENGURUS RUMAH TANGGA", "PELAJAR/MAHASISWA", "PENSIUNAN", "PEGAWAI NEGERI SIPIL",
    "TENTARA NASIONAL INDONESIA", "KEPOLISIAN RI", "PERDAGANGAN", "PETANI/PEKEBUN", "PETERNAK", "NELAYAN/PERIKANAN",
    "INDUSTRI", "KONSTRUKSI", "TRANSPORTASI", "KARYAWAN SWASTA", "KARYAWAN BUMN", "KARYAWAN BUMD", "KARYAWAN HONORER",
    "BURUH HARIAN LEPAS", "BURUH TANI/PERKEBUNAN", "BURUH NELAYAN/PERIKANAN", "BURUH PETERNAKAN", "PEMBANTU RUMAH TANGGA",
    "TUKANG CUKUR", "TUKANG LISTRIK", "TUKANG BATU", "TUKANG KAYU", "TUKANG SOL SEPATU", "TUKANG LAS/PANDAI BESI",
    "TUKANG JAHIT", "TUKANG GIGI", "PENATA RIAS", "PENATA BUSANA", "PENATA RAMBUT", "MEKANIK", "SENIMAN", "TABIB",
    "PARAJI", "PERANCANG BUSANA", "PENTERJEMAH", "IMAM MESJID", "PENDETA", "PASTOR", "WARTAWAN", "USTADZ/MUBALIGH",
    "JURU MASAK", "PROMOTOR ACARA", "ANGGOTA DPR-RI", "ANGGOTA DPD", "ANGGOTA BPK", "PRESIDEN", "WAKIL PRESIDEN",
    "ANGGOTA MAHKAMAH KONSTITUSI", "ANGGOTA KABINET/KEMENTERIAN", "DUTA BESAR", "GUBERNUR", "WAKIL GUBERNUR", "BUPATI",
    "WAKIL BUPATI", "WALIKOTA", "WAKIL WALIKOTA", "ANGGOTA DPRD PROVINSI", "ANGGOTA DPRD KABUPATEN/KOTA", "DOSEN", "GURU",
    "PILOT", "PENGACARA", "NOTARIS", "ARSITEK", "AKUNTAN", "KONSULTAN", "DOKTER", "BIDAN", "PERAWAT", "APOTEKER",
    "PSIKIATER/PSIKOLOG", "PENYIAR TELEVISI", "PENYIAR RADIO", "PELAUT", "PENELITI", "SOPIR", "PIALANG", "PARANORMAL",
    "PEDAGANG", "PERANGKAT DESA", "KEPALA DESA", "BIARAWATI", "WIRASWASTA", "LAINNYA",
]


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def _preprocess(jpeg: bytes, mode: str):
    from PIL import Image, ImageFilter, ImageOps
    im = Image.open(io.BytesIO(jpeg))
    if mode == "B":
        im = ImageOps.autocontrast(im.convert("L"), cutoff=2).filter(ImageFilter.UnsharpMask(2, 150, 3))
    return im


def _tess_lines(jpeg: bytes):
    """Tesseract (ind+eng) -> segmen teks per baris; celah lebar memisahkan label dan nilai seperti kotak RapidOCR."""
    import subprocess
    import tempfile
    im = _preprocess(jpeg, "B")
    im = im.resize((int(im.width * 1.33), int(im.height * 1.33)))
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        im.save(f.name)
        tsv = subprocess.run(["tesseract", f.name, "stdout", "-l", "ind+eng", "--psm", "6", "tsv"],
                             capture_output=True, text=True).stdout
    words = {}
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or not c[11].strip() or float(c[10]) < 0:
            continue
        words.setdefault(tuple(c[2:5]), []).append((int(c[6]), int(c[7]), int(c[8]), int(c[9]), float(c[10]), c[11]))
    out = []
    for ws in words.values():
        ws.sort()
        h = sorted(w[3] for w in ws)[len(ws) // 2] or 20
        seg = [ws[0]]
        for w in ws[1:]:
            if w[0] - (seg[-1][0] + seg[-1][2]) > 1.6 * h:
                out.append(seg)
                seg = []
            seg.append(w)
        out.append(seg)
    lines = []
    for seg in out:
        xs = [w[0] for w in seg] + [w[0] + w[2] for w in seg]
        ys = [w[1] + w[3] / 2 for w in seg]
        lines.append({"t": " ".join(w[5] for w in seg), "x": sum(xs) / len(xs) / 1.33, "y": sum(ys) / len(ys) / 1.33,
                      "s": sum(w[4] for w in seg) / len(seg) / 100})
    return sorted(lines, key=lambda l: (round(l["y"] / 10), l["x"]))


def ocr_lines(jpeg: bytes, mode: str = "A"):
    """A = RapidOCR gambar asli; C = RapidOCR gambar diperbesar+kontras; T = Tesseract.
    -> [{'t': teks, 'x', 'y', 's'}] urut baca."""
    if mode == "T":
        return _tess_lines(jpeg)
    import numpy as np
    im = _preprocess(jpeg, "B" if mode == "C" else "A")
    scale = 1.47 if mode == "C" else 1.0
    if mode == "C":
        im = im.resize((int(im.width * scale), int(im.height * scale)))
    res, _ = _get_engine()(np.array(im.convert("RGB")))
    out = []
    for box, txt, sc in res or []:
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        out.append({"t": txt, "x": sum(xs) / 4 / scale, "y": sum(ys) / 4 / scale, "s": float(sc)})
    return out


# ---------------------------------------------------------------- klasifikasi
def _c(s: str) -> str:
    return re.sub(r"[^A-Z0-9/.\-]", "", s.upper())


def classify(lines) -> str:
    t = "".join(_c(l["t"]) for l in lines)
    if "FAKTURKENDARAANBERMOTOR" in t or ("TAHUNPEMBUATAN" in t and "NOMORMESIN" in t):
        return "FAKTUR"
    if "SERTIFIKAT" in t and ("IDENTIFIKASI" in t or "NIK" in t):
        return "SERTIFIKAT"
    if "SERAHTERIMA" in t or ("NORANGKA" in t and "NOMESIN" in t and "DESKRIPSI" in t):
        return "BAST"
    if "PROVINSI" in t or "KEWARGANEGARAAN" in t or "BERLAKUHINGGA" in t or "AGAMA" in t:
        return "KTP"
    return "LAINNYA"


# ---------------------------------------------------------------- parser bidang
def _after(texts, label, skip=()):
    """Teks pertama setelah baris yang mengandung label (dibandingkan tanpa spasi)."""
    for i, t in enumerate(texts):
        if label in _c(t):
            for u in texts[i + 1:i + 4]:
                cu = _c(u)
                if cu and cu not in skip and not re.fullmatch(r"\d{1,2}\.?", cu) and cu != ":":
                    return u.strip(" :")
            return ""
    return ""


def fix_rt_rw(a: str) -> str:
    """Rapikan RT/RW hasil OCR: 'EW O01' -> 'RW 001', 'RT0O2' -> 'RT 002'."""
    digit = lambda x: x.upper().replace("O", "0").replace("I", "1").replace("L", "1").replace("S", "5")
    a = re.sub(r"\b[RE]W\s*([0-9OIlS]{2,3})\b", lambda m: "RW " + digit(m[1]), a)
    a = re.sub(r"\bRT\s*([0-9OIlS]{2,3})\b", lambda m: "RT " + digit(m[1]), a)
    return re.sub(r"RT (\d{3})RW", r"RT \1 RW", a)


def parse_faktur(lines) -> dict:
    texts = [l["t"] for l in lines]
    comp = "".join(_c(t) for t in texts)
    f = {}
    m = re.search(r"FH/?BB6/?(\d{5,7})/?Z", comp)
    f["no_faktur"] = f"FH/BB6/{m[1]}/Z" if m else ""
    m = re.search(r"(\d{1,2})(JAN|FEB|MAR|APR|MEI|JUN|JUL|AGU|AUG|SEP|OKT|OCT|NOV|DES|DEC)[A-Z]*(\d{4})", comp)
    f["tanggal"] = f"{m[1]} {m[2]} {m[3]}" if m else ""
    f["nama"] = _after(texts, "ATASNAMA", skip=("ALAMAT",))
    # alamat: semua baris di antara ALAMAT dan baris KEC.
    idx_al = next((i for i, t in enumerate(texts) if _c(t).startswith("ALAMAT") and len(_c(t)) <= 8), None)
    idx_kec = next((i for i, t in enumerate(texts) if re.match(r"KEC", _c(t))), None)
    alamat_lines = []
    if idx_al is not None and idx_kec is not None and idx_kec > idx_al:
        alamat_lines = [t for t in texts[idx_al + 1:idx_kec] if not re.fullmatch(r"\d{1,2}\.?|:", _c(t))]
    kel = alamat_lines[-1] if len(alamat_lines) >= 2 else ""
    a1 = " ".join(alamat_lines[:-1]) if kel else " ".join(alamat_lines)
    a1 = re.sub(r"(RW\s*\d+)\s+(\d)$", r"\1\2", a1)  # RW terpotong baris: "RW 01" + "1"
    a1 = fix_rt_rw(a1)
    f["alamat_baris1"], f["kelurahan"] = a1.strip(), kel.strip()
    f["kecamatan"] = texts[idx_kec].strip() if idx_kec is not None else ""
    f["kota"] = "KOTA BATAM" if "KOTABATAM" in comp else ""
    m = re.search(r"(?<!\d)(\d{16})(?!\d)", comp)
    f["nik"] = m[1] if m else ""
    f["merk"] = _after(texts, "MERK")
    f["tipe"] = _after(texts, "TYPE")
    m = re.search(r"TAHUNPEMBUATAN\D*?(20\d\d)", comp)
    f["tahun"] = m[1] if m else ""
    m = re.search(r"LISTRIK\D*?(\d{2,4}[.,]\d{1,2})", comp)
    f["cc"] = m[1] if m else ""
    f["warna"] = _after(texts, "WARNA")
    m = re.search(r"MH1[A-Z0-9]{14}", comp)
    f["no_rangka"] = m[0] if m else ""
    m = re.search(r"NOMORMESIN\D{0,3}([A-Z0-9]{3}[1I]E)[\-|]?(\d{6,7})", comp)
    f["no_mesin"] = f"{m[1]}{m[2]}" if m else ""
    m = re.search(r"KP\.?(\d+)/A[JD]\.?(\d+)/DR[JI]D/(\d{4})", comp)
    m2 = re.search(r"KP-?DRJD(\d+)TAHUN(\d{4})", comp)
    f["sut"] = f"KP.{m[1]}/AJ.{m[2]}/DRJD/{m[3]}" if m else (f"KP-DRJD {m2[1]} TAHUN {m2[2]}" if m2 else "")
    m = re.search(r"SRUT/AJ\.?402/DJPD/AHM-?(\d{6,9})/(\d{4})", comp)
    f["srut"] = f"SRUT/AJ.402/DJPD/AHM-{m[1]}/{m[2]}" if m else ""
    return f


def parse_sertifikat(lines) -> dict:
    comp = "".join(_c(l["t"]) for l in lines)
    m = re.search(r"FH/?BB6/?(\d{5,7})/?Z", comp)
    m2 = re.search(r"NOMESIN\D{0,3}([A-Z0-9]{4}E)[\-|]?(\d{6,7})", comp)
    return {"no_faktur": f"FH/BB6/{m[1]}/Z" if m else "", "no_mesin": f"{m2[1]}{m2[2]}" if m2 else ""}


def snap_pekerjaan(raw: str):
    """Cocokkan ke daftar pekerjaan KTP baku. Return (nilai, yakin)."""
    key = re.sub(r"[^A-Z]", "", raw.upper())
    if not key:
        return "", False
    table = {re.sub(r"[^A-Z]", "", p): p for p in PEKERJAAN}
    if key in table:
        return table[key], True
    hit = get_close_matches(key, table, n=1, cutoff=0.75)
    return (table[hit[0]], False) if hit else (raw.upper(), False)


def parse_ktp(lines) -> dict:
    texts = [l["t"] for l in lines]
    comp = "".join(_c(t) for t in texts)
    m = re.search(r"(?<!\d)(\d{16})(?!\d)", comp)
    pek_raw = ""
    for i, t in enumerate(texts):
        if "KERJAAN" in _c(t) and len(_c(t)) <= 12:
            pek_raw = next((u for u in texts[i + 1:i + 3] if len(_c(u)) > 3), "")
            break
    pek, ok = snap_pekerjaan(pek_raw)
    nm = ""
    for i, t in enumerate(texts):
        if re.fullmatch(r"[A-Z]{0,2}AMA", _c(t)) or _c(t) in ("NAMA", "AMA", "ANA"):
            nm = texts[i + 1].strip(" :") if i + 1 < len(texts) else ""
            break
    return {"nik": m[1] if m else "", "nama": nm, "alamat": "", "pekerjaan": pek, "_pek_yakin": ok}


def parse_bast(lines) -> dict:
    """Tabel BAST dibaca dari posisi kotak: kolom = posisi header, baris = posisi nomor urut."""
    comp = "".join(_c(l["t"]) for l in lines)
    m = re.search(r"(\d{3})-?FDB-?(\d{4})-?(\d{1,2})-?(\d{5})", comp)
    nomor = f"{m[1]}-FDB-{m[2]}-{m[3]}-{m[4]}" if m else ""
    heads = {}
    for l in lines:
        c = _c(l["t"])
        for key, lab in (("no_faktur", "NOFAKTUR"), ("nama", "NAMA"), ("alamat", "ALAMAT"),
                         ("no_rangka", "NO.RANGKA"), ("no_mesin", "NO.MESIN"), ("tipe", "DESKRIPSI")):
            if c.startswith(lab) and key not in heads:
                heads[key] = l
    if len(heads) < 5:
        return {"bast_nomor": nomor, "bast_baris": []}
    hy = max(h["y"] for h in heads.values())
    no_x = min(l["x"] for l in lines if _c(l["t"]) == "NO" and abs(l["y"] - hy) < 15) if any(
        _c(l["t"]) == "NO" and abs(l["y"] - hy) < 15 for l in lines) else 40
    nums = sorted((l for l in lines if l["y"] > hy + 10 and abs(l["x"] - no_x) < 40 and re.fullmatch(r"\d{1,2}", _c(l["t"]))),
                  key=lambda l: l["y"])
    cols = {k: h["x"] for k, h in heads.items()}
    rows = []
    for i, n in enumerate(nums):
        top = (nums[i - 1]["y"] + n["y"]) / 2 if i else hy + 10
        bot = (n["y"] + nums[i + 1]["y"]) / 2 if i + 1 < len(nums) else n["y"] + 60
        cells = {k: [] for k in cols}
        for l in lines:
            if top <= l["y"] < bot and abs(l["x"] - no_x) >= 40:
                k = min(cols, key=lambda kk: abs(cols[kk] - l["x"]))
                cells[k].append(l)
        row = {"no": _c(n["t"])}
        for k, ls in cells.items():
            row[k] = " ".join(x["t"] for x in sorted(ls, key=lambda z: (round(z["y"] / 12), z["x"])))
        rows.append(row)
    return {"bast_nomor": nomor, "bast_baris": rows}


# ---------------------------------------------------------------- dua pass + bendera
VALID = {
    "no_faktur": lambda v: bool(re.fullmatch(r"FH/BB6/\d{6}/Z", v)),
    "nik": lambda v: bool(re.fullmatch(r"\d{16}", v)),
    "no_rangka": lambda v: bool(re.fullmatch(r"MH1[A-Z0-9]{14}", v)),
    "no_mesin": lambda v: bool(re.fullmatch(r"[A-Z0-9]{4}E\d{6,7}", v)),
    "tanggal": lambda v: bool(N.tanggal(v)),
    "cc": lambda v: bool(re.fullmatch(r"\d{2,4}[.,]\d{1,2}", v)),
    "tahun": lambda v: bool(re.fullmatch(r"20\d\d", v)),
    "srut": lambda v: v.startswith("SRUT/"),
    "sut": lambda v: bool(re.match(r"KP", v)),
}


def _norm(k, v):
    v = N.up(v)
    return v.replace(" ", "") if k not in ("alamat_baris1",) else re.sub(r"\s+", "", v)


KNOWN_CC = {"109.51", "110.30", "124.89", "149.16", "155.00", "156.93", "157.30", "160.00", "163.90", "249.00"}
# untuk bidang angka/ID, RapidOCR lebih andal; untuk teks bebas & spasi, Tesseract
PREFER_TESS = {"alamat_baris1", "nama", "kelurahan", "kecamatan", "merk", "warna"}


def merge_fields(a: dict, b: dict):
    """a = RapidOCR, b = Tesseract. Return (nilai, flags{field: OK|BEDA|TIDAK_VALID|KOSONG})."""
    out, flags = {}, {}
    for k in a.keys() | b.keys():
        if k.startswith("_"):
            continue
        va, vb = str(a.get(k) or "").strip(), str(b.get(k) or "").strip()
        ok = VALID.get(k, lambda v: bool(v))
        if not va and not vb:
            out[k], flags[k] = "", "KOSONG"
        elif _norm(k, va) == _norm(k, vb):
            out[k] = va if va.count(" ") >= vb.count(" ") else vb  # ambil yang spasinya lengkap
            flags[k] = "OK" if ok(out[k]) else "TIDAK_VALID"
        else:
            cands = [v for v in (va, vb) if v and ok(v)]
            if k == "cc" and len(cands) > 1:
                known = [v for v in cands if v.replace(",", ".") in KNOWN_CC]
                cands = known[:1] or cands
            if len(cands) > 1:  # keduanya valid tapi beda: pilih mesin yang lebih andal untuk bidang ini
                cands = [vb if k in PREFER_TESS else va]
            out[k] = cands[0] if cands else (vb if k in PREFER_TESS else (va or vb))
            flags[k] = "BEDA" if cands else "TIDAK_VALID"
    return out, flags


def _compact(lines) -> str:
    return "".join(_c(l["t"]) for l in lines)


def extract_all(pages, progress=None):
    """pages: [(no, jpeg)] -> seperti extract.extract_all, plus '_flags' per bidang.
    Dua mesin berbeda: RapidOCR (A) vs Tesseract (T). BAST: A vs C (RapidOCR pra-proses) + Tesseract sebagai saksi."""
    results = []
    for n, (no, jpeg) in enumerate(pages, 1):
        la = ocr_lines(jpeg, "A")
        dt = classify(la)
        d = {"page": no, "doc_type": dt, "terbaca": "JELAS"}
        lt = ocr_lines(jpeg, "T")
        if dt == "LAINNYA":
            dt = d["doc_type"] = classify(lt)
        elif classify(lt) not in (dt, "LAINNYA"):
            d["catatan"] = f"Dua OCR beda jenis halaman ({dt} vs {classify(lt)})"
            d["terbaca"] = "KURANG_JELAS"
        parser = {"FAKTUR": parse_faktur, "SERTIFIKAT": parse_sertifikat, "KTP": parse_ktp}.get(dt)
        if parser:
            merged, flags = merge_fields(parser(la), parser(lt))
            if dt == "KTP":
                pek, yakin = snap_pekerjaan(merged.get("pekerjaan", ""))
                merged["pekerjaan"] = pek
                flags["pekerjaan"] = "KOSONG" if not pek else ("OK" if yakin and flags.get("pekerjaan") == "OK" else "BEDA")
                merged.pop("_pek_yakin", None)
            d[dt.lower()], d["_flags"] = merged, flags
        elif dt == "BAST":
            lc = ocr_lines(jpeg, "C")
            pa, pc = parse_bast(la), parse_bast(lc)
            best, alt = (pa, pc) if len(pa["bast_baris"]) >= len(pc["bast_baris"]) else (pc, pa)
            d.update(best)
            d["_bast_alt"] = alt["bast_baris"]
            d["_witness"] = _compact(lt)  # teks Tesseract untuk konfirmasi sel BAST
        if any(v != "OK" for v in d.get("_flags", {}).values()):
            d["terbaca"] = "KURANG_JELAS"
        results.append(d)
        if progress:
            progress(n, len(pages))
    return results
