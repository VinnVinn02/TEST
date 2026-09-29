"""Rename gambar sesuai Excel DATA RENAME (Nama Lama -> Nama Baru)."""
import io
import re
import zipfile

import openpyxl


def read_mapping(xlsx) -> list[tuple[str, str]]:
    ws = openpyxl.load_workbook(xlsx, data_only=True).worksheets[0]
    rows = ws.iter_rows(values_only=True)
    head = [str(c or "").strip().upper() for c in next(rows)]
    lama, baru = head.index("NAMA LAMA"), head.index("NAMA BARU")
    return [(str(r[lama]).strip(), str(r[baru]).strip()) for r in rows if r[lama] and r[baru]]


def _key(name: str):
    """(awalan tanpa spasi/underscore, nomor halaman tanpa nol di depan) dari 'CamScanner 28-09-26 21.33_04.jpg'."""
    base = re.sub(r"\.(jpe?g|png)$", "", name.split("/")[-1].strip(), flags=re.I)
    m = re.search(r"[\s_-]*0*(\d+)$", base)
    if not m:
        return re.sub(r"[\s_]+", "", base.lower()), None
    return re.sub(r"[\s_-]+", "", base[:m.start()].lower()), int(m[1])


def rename_files(mapping, files: dict[str, bytes]):
    """files: {nama_file: bytes}. Cocok persis dulu, lalu berdasarkan awalan+nomor halaman
    (abaikan spasi/underscore/nol di depan), terakhir nomor saja bila unik. Return (zip_bytes, laporan)."""
    exact = {n.split("/")[-1].lower(): n for n in files}
    keyed = {}
    for n in files:
        keyed.setdefault(_key(n), []).append(n)
    by_num = {}
    for (pre, num), ns in keyed.items():
        if num is not None:
            by_num.setdefault(num, []).extend(ns)
    buf, report, seen, used = io.BytesIO(), [], set(), set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for lama, baru in mapping:
            src = exact.get(lama.lower())
            if src is None:
                cand = [n for n in keyed.get(_key(lama), []) if n not in used]
                if len(cand) == 1:
                    src = cand[0]
                else:
                    num = _key(lama)[1]
                    cand = [n for n in by_num.get(num, []) if n not in used] if num is not None else []
                    if len(cand) == 1:
                        src = cand[0]
                        report.append(f"INFO: {lama} dicocokkan ke {src} berdasarkan nomor halaman")
            if src is None:
                report.append(f"Tidak ditemukan: {lama} (-> {baru})")
            elif baru in seen:
                report.append(f"Nama baru ganda dilewati: {baru}")
            else:
                z.writestr(baru, files[src])
                seen.add(baru)
                used.add(src)
    report.append(f"{len(seen)} dari {len(mapping)} file berhasil di-rename")
    return buf.getvalue(), report


def expand_uploads(uploads: list[tuple[str, bytes]]) -> dict[str, bytes]:
    out = {}
    for name, data in uploads:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                out.update({n: z.read(n) for n in z.namelist() if not n.endswith("/")})
        else:
            out[name] = data
    return out
