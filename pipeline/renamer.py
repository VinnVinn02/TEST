"""Rename gambar sesuai Excel DATA RENAME (Nama Lama -> Nama Baru)."""
import io
import zipfile

import openpyxl


def read_mapping(xlsx) -> list[tuple[str, str]]:
    ws = openpyxl.load_workbook(xlsx, data_only=True).worksheets[0]
    rows = ws.iter_rows(values_only=True)
    head = [str(c or "").strip().upper() for c in next(rows)]
    lama, baru = head.index("NAMA LAMA"), head.index("NAMA BARU")
    return [(str(r[lama]).strip(), str(r[baru]).strip()) for r in rows if r[lama] and r[baru]]


def rename_files(mapping, files: dict[str, bytes]):
    """files: {nama_file: bytes} (boleh dari beberapa upload/ZIP). Return (zip_bytes, laporan)."""
    by_name = {n.split("/")[-1].lower(): b for n, b in files.items()}
    buf, report, seen = io.BytesIO(), [], set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for lama, baru in mapping:
            data = by_name.get(lama.lower())
            if data is None:
                report.append(f"Tidak ditemukan: {lama} (-> {baru})")
            elif baru in seen:
                report.append(f"Nama baru ganda dilewati: {baru}")
            else:
                z.writestr(baru, data)
                seen.add(baru)
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
