import io, zipfile
from pipeline import normalize as N, export
from pipeline.assemble import assemble, COLUMNS


def test_rules():
    assert N.warna("BIRU-HITAM") == "BIRU HITAM"
    assert N.cc("109.51 CC") == "110" and N.cc("156.9") == "157"
    assert N.tanggal("24 Sep 2026") == "2026-09-24" and N.tanggal("24-09-2026") == "2026-09-24"
    assert N.no_faktur("BB6 /038039/Y") == "FH/BB6/038039/Z"
    assert N.strip_no("NO. SRUT/AJ.402/DJPD/AHM-03650228/2026") == "SRUT/AJ.402/DJPD/AHM-03650228/2026"
    assert N.alamat1("pulau setokok rt 002 rw 001 kel x")[0] == "PULAU SETOKOK RT 002 RW 001"
    assert N.alamat2("PULAU SETOKOK", "KEC. BULANG", "KOTA BATAM") == "P. SETOKOK - BULANG"
    assert N.alamat2("P.SETOKOK", "BULANG") == "P. SETOKOK - BULANG"
    assert N.alamat2("SEI BEDUK", "KEC. BATU AJI", "KOTA BATAM") == "SUNGAI BEDUK - BATU AJI"
    assert N.alamat2("SAGULUNG KOTA", "BATU AJI", "KOTA BATAM") == "SAGULUNG KOTA - BATU AJI"
    assert N.rangka("KFC115TK395005") == "MH1KFC115TK395005" and N.mesin("KFC1E 1394715") == "KFC1E1394715"
    assert N.alasan_beli("PELAJAR/MAHASISWA") == "CARI KERJA" and N.alasan_beli("NELAYAN/PERIKANAN") == "UNTUK KERJA"


def _pages():
    bast = {"page": 1, "doc_type": "BAST", "terbaca": "JELAS", "bast_nomor": "047-FDB-2026-9-00024",
            "bast_baris": [{"no": "1", "no_faktur": "BB6 /038641/Z", "nama": "ZULKIFLI", "no_rangka": "JME122TK415474",
                            "no_mesin": "JME1E 2413887"}]}
    faktur = {"page": 4, "doc_type": "FAKTUR", "terbaca": "JELAS", "faktur": {
        "no_faktur": "FH/BB6 /038641/Z", "tanggal": "24 Sep 2026", "nama": "ZULKIFLl", "alamat_baris1": "PULAU SETOKOK RT 002 RW 001",
        "kelurahan": "PULAU SETOKOK", "kecamatan": "KEC. BULANG", "kota": "KOTA BATAM", "nik": "1403070606696134",
        "merk": "HONDA", "tipe": "H1B02N41L1 A/T", "tahun": "2026", "cc": "109.51 CC", "warna": "BIRU-HITAM",
        "no_rangka": "MH1JME122TK415474", "no_mesin": "JME1E - 2413887", "sut": "NO. KP.1461/AJ.502/DRJD/2024",
        "srut": "NO. SRUT/AJ.402/DJPD/AHM-03650228/2026"}}
    sert = {"page": 5, "doc_type": "SERTIFIKAT", "terbaca": "JELAS", "sertifikat": {"no_faktur": "FH/BB6/038641/Z"}}
    ktp = {"page": 44, "doc_type": "KTP", "terbaca": "JELAS", "ktp": {"nik": "1403070606696134", "nama": "ZULKIFLI", "pekerjaan": "NELAYAN/PERIKANAN"}}
    return [bast, faktur, sert, ktp]


def test_assemble_and_export():
    hp = {"rangka": {"JME122TK415474": ("081371604033", "a@gmail.com")}, "mesin": {}}
    r = assemble(_pages(), hp)
    rec = r["records"][0]
    assert list(rec) == COLUMNS
    assert rec["NAMA LENGKAP"] == "ZULKIFLI" and rec["WARNA"] == "BIRU HITAM" and rec["CC"] == "110"
    assert rec["NO. FAKTUR"] == "FH/BB6/038641/Z" and rec["NO RANGKA"] == "MH1JME122TK415474"
    assert rec["NO MESIN"] == "JME1E2413887" and rec["ALAMAT 2"] == "P. SETOKOK - BULANG"
    assert rec["NO. SRUT"].startswith("SRUT/") and rec["ALASAN BELI"] == "UNTUK KERJA" and rec["NO HP"] == "081371604033"
    assert any("diperbaiki sesuai BAST" in w for w in r["warnings"][0])
    z = zipfile.ZipFile(io.BytesIO(export.build_zip(r["records"], r["warnings"], r["general"], r["meta"], r["bast_no"],
                                                    "CamScanner_28-09-26_21.33", {4: b"a", 5: b"b", 44: b"c"})))
    names = z.namelist()
    assert "DATA_BERKAS_KENDARAAN_BAST_047-00024.xlsx" in names and "BERKAS_RENAME/ZULKIFLI_KTP.jpg" in names


def test_missing_ktp_warns():
    p = [x for x in _pages() if x["doc_type"] != "KTP"]
    r = assemble(p, None)
    assert any("KTP tidak ditemukan" in w for w in r["warnings"][0])
    assert any("No HP" in w for w in r["warnings"][0])


def test_renamer(tmp_path):
    from pipeline import renamer
    rows = export.rename_rows(assemble(_pages(), None)["records"], assemble(_pages(), None)["meta"], "CamScanner_28-09-26_21.33")
    x = tmp_path / "r.xlsx"
    x.write_bytes(export.rename_xlsx(rows))
    m = renamer.read_mapping(x)
    assert m[0] == ("CamScanner 28-09-26 21.33_4.jpg", "ZULKIFLI_FAKTUR.jpg")
    z, rep = renamer.rename_files(m, {"CamScanner 28-09-26 21.33_4.jpg": b"x"})
    assert "ZULKIFLI_FAKTUR.jpg" in zipfile.ZipFile(io.BytesIO(z)).namelist() and any("Tidak ditemukan" in r for r in rep)


def test_bast_is_authoritative_for_name_and_faktur():
    p = _pages()
    p[1]["faktur"]["nama"] = "ZULKIFLl"            # salah OCR
    p[1]["faktur"]["no_faktur"] = "FH/BB6/038647/Z"  # angka salah OCR
    rec = assemble(p, None)["records"][0]
    assert rec["NAMA LENGKAP"] == "ZULKIFLI" and rec["NO. FAKTUR"] == "FH/BB6/038641/Z"
