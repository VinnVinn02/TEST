"""Aturan penulisan data (semua HURUF BESAR, format tanggal, alamat, dll)."""
import re
from difflib import SequenceMatcher

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MEI": 5, "MAY": 5, "JUN": 6, "JUL": 7,
    "AGU": 8, "AUG": 8, "AGT": 8, "SEP": 9, "OKT": 10, "OCT": 10, "NOV": 11, "DES": 12, "DEC": 12,
}
CARI_KERJA = {"PELAJAR/MAHASISWA", "MENGURUS RUMAH TANGGA", "BELUM/TIDAK BEKERJA"}


def up(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("\xa0", " ")).strip().upper()


def ratio(a: str, b: str) -> float:
    a, b = up(a), up(b)
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def warna(s) -> str:
    return up(re.sub(r"\s*-\s*", " ", up(s)))


def cc(s) -> str:
    m = re.search(r"\d+(?:[.,]\d+)?", str(s or ""))
    if not m:
        return ""
    return str(int(float(m.group().replace(",", ".")) + 0.5))


def tanggal(s) -> str:
    s = up(s)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.search(r"(\d{1,2})[\s/.-]+(\d{1,2}|[A-Z]{3,})[A-Z]*[\s/.-]+(\d{4})", s)
    if not m:
        return ""
    mon = m[2]
    mon = int(mon) if mon.isdigit() else MONTHS.get(mon[:3])
    return f"{int(m[3]):04d}-{mon:02d}-{int(m[1]):02d}" if mon else ""


def faktur_digits(s) -> str:
    m = re.search(r"(\d{5,7})", str(s or ""))
    return m[1].zfill(6) if m else ""


def no_faktur(s) -> str:
    d = faktur_digits(s)
    return f"FH/BB6/{d}/Z" if d else ""  # akhiran selalu Z


def strip_no(s) -> str:
    return re.sub(r"^\s*NO\s*[.:]*\s*", "", up(s))


def alamat1(s) -> tuple[str, bool]:
    """Alamat sampai RW saja. Return (alamat, ok)."""
    s = up(s)
    m = re.search(r"^(.*?\bRW\s*\.?\s*(\d+))", s)
    if not m:
        return s, False
    out = re.sub(r"\bRT\s*\.?\s*(\d+)", r"RT \1", m[1])
    out = re.sub(r"\bRW\s*\.?\s*(\d+)", r"RW \1", out)
    return out, True


def _clean_wilayah(s: str) -> str:
    s = re.sub(r"^(KEC(AMATAN)?|KEL(URAHAN)?|DESA)\b\.?\s*", "", up(s))
    s = re.sub(r"\bSEI\b\.?", "SUNGAI", s)
    s = re.sub(r"\b(PULAU|P\.?)\s*SETOKOK\b", "P. SETOKOK", s)
    s = re.sub(r"\bP\.(?=\S)", "P. ", s)  # setelah "P." selalu spasi
    return s.strip(" -")


def alamat2(kelurahan, kecamatan, kota="") -> str:
    parts = [_clean_wilayah(kelurahan), _clean_wilayah(kecamatan)]
    k = up(kota)
    if k and "BATAM" not in k:
        parts.append(_clean_wilayah(re.sub(r"^KOTA\s+", "", k)))
    return " - ".join(p for p in parts if p)


def nik(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def alasan_beli(pekerjaan) -> str:
    p = up(pekerjaan)
    if not p:
        return ""
    return "CARI KERJA" if p in CARI_KERJA else "UNTUK KERJA"


def rangka(s) -> str:
    s = re.sub(r"[^A-Z0-9]", "", up(s))
    return s if not s or s.startswith("MH1") else "MH1" + s


def rangka_key(s) -> str:
    s = re.sub(r"[^A-Z0-9]", "", up(s))
    return s[3:] if s.startswith("MH1") else s


def mesin(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", up(s))


def hp(s) -> str:
    d = re.sub(r"\D", "", str(s or ""))
    if d.startswith("62"):
        d = "0" + d[2:]
    elif d.startswith("8"):
        d = "0" + d
    return d


def email(s) -> str:
    return str(s or "").replace("\xa0", " ").strip().lower()


def nama_file_base(nama) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]+", "_", up(nama))).strip("_")


def file_names(nama) -> dict:
    b = nama_file_base(nama)
    return {"FAKTUR": f"{b}_FAKTUR.jpg", "KTP": f"{b}_KTP.jpg", "SERTIFIKAT": f"{b}_SERTIFIKAT.jpg"}
