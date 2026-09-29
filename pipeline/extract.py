"""OCR + pemahaman dokumen memakai Claude vision (output JSON terstruktur)."""
import base64
import io
import os
from concurrent.futures import ThreadPoolExecutor

DEFAULT_MODEL = os.environ.get("BAST_MODEL", "claude-sonnet-5-5")

_S = {"type": "string"}
_row = {"type": "object", "properties": {k: _S for k in
        ("no", "no_faktur", "nama", "alamat", "no_rangka", "no_mesin", "tipe")}}
SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string", "enum": ["BAST", "FAKTUR", "SERTIFIKAT", "KTP", "LAINNYA"]},
        "terbaca": {"type": "string", "enum": ["JELAS", "KURANG_JELAS"]},
        "catatan": _S,
        "bast_nomor": _S,
        "bast_tanggal": _S,
        "bast_baris": {"type": "array", "items": _row},
        "faktur": {"type": "object", "properties": {k: _S for k in (
            "no_faktur", "tanggal", "nama", "alamat_baris1", "kelurahan", "kecamatan", "kota",
            "nik", "merk", "tipe", "tahun", "cc", "warna", "no_rangka", "no_mesin", "sut", "srut")}},
        "sertifikat": {"type": "object", "properties": {k: _S for k in ("no_faktur", "tipe", "no_mesin", "nik")}},
        "ktp": {"type": "object", "properties": {k: _S for k in ("nik", "nama", "alamat", "pekerjaan")}},
    },
    "required": ["doc_type", "terbaca"],
}

PROMPT = """Kamu adalah OCR untuk berkas biro jasa kendaraan (Honda/AHM). Baca halaman scan ini, tentukan jenisnya, \
lalu isi HANYA bagian yang sesuai:
- BAST: judul "BERITA ACARA SERAH TERIMA FAKTUR". Isi bast_nomor (mis. 047-FDB-2026-9-00024), bast_tanggal (mis. 26-September-2026) dan bast_baris \
(semua baris tabel: no, no_faktur persis seperti tercetak, nama, alamat, no_rangka, no_mesin, tipe).
- FAKTUR: "FAKTUR KENDARAAN BERMOTOR". Salin persis: no_faktur, tanggal, nama (ATAS NAMA), alamat_baris1 \
(baris alamat yang memuat RT/RW), kelurahan, kecamatan, kota (baris-baris di bawah alamat), nik (NO KTP/TDP, 16 digit), \
merk, tipe, tahun, cc (ISI SILINDER), warna, no_rangka, no_mesin, sut, srut (tanpa kata "NO.").
- SERTIFIKAT: "SERTIFIKAT NOMOR IDENTIFIKASI KENDARAAN BERMOTOR (NIK)". Isi no_faktur (Nomor), tipe, no_mesin, dan nik (17 karakter di kotak = no rangka).
- KTP: isi nik, nama, alamat, pekerjaan.
- LAINNYA: halaman lain.
Aturan: jangan menebak; bila karakter tidak terbaca kosongkan bagian itu dan set terbaca=KURANG_JELAS beserta catatan. \
Foto bisa miring/terbalik. Angka 0/O, 1/I/L, 5/S, 8/B perlu dicek dengan teliti."""


def _shrink(jpeg: bytes, max_side: int = 1600) -> bytes:
    try:
        from PIL import Image
    except ImportError:
        return jpeg
    im = Image.open(io.BytesIO(jpeg))
    if max(im.size) <= max_side:
        return jpeg
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=85)
    return buf.getvalue()


def extract_page(client, model: str, jpeg: bytes) -> dict:
    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        tools=[{"name": "simpan", "description": "Simpan hasil ekstraksi halaman", "input_schema": SCHEMA}],
        tool_choice={"type": "tool", "name": "simpan"},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(_shrink(jpeg)).decode()}},
            {"type": "text", "text": PROMPT},
        ]}],
    )
    for b in resp.content:
        if b.type == "tool_use":
            return b.input
    return {"doc_type": "LAINNYA", "terbaca": "KURANG_JELAS", "catatan": "Tidak ada hasil dari model"}


def extract_all(pages, api_key=None, model=DEFAULT_MODEL, workers=4, progress=None):
    """pages: [(no, jpeg)] -> [{'page': no, **data}] urut halaman."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    done = 0

    def job(item):
        nonlocal done
        no, jpeg = item
        try:
            data = extract_page(client, model, jpeg)
        except Exception as e:  # satu halaman gagal tidak menghentikan semuanya
            data = {"doc_type": "LAINNYA", "terbaca": "KURANG_JELAS", "catatan": f"Gagal OCR: {e}"}
        done += 1
        if progress:
            progress(done, len(pages))
        return {"page": no, **data}

    with ThreadPoolExecutor(workers) as ex:
        return sorted(ex.map(job, pages), key=lambda d: d["page"])
