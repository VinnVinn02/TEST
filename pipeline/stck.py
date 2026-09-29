"""Isi NO STCK berurutan dari rentang, mis. '6790758 - 6790813'."""
import re


def parse_range(text: str):
    nums = re.findall(r"\d+", text or "")
    if len(nums) != 2:
        return None
    a, b = int(nums[0]), int(nums[1])
    return (a, b) if a <= b else None


def fill_stck(records, text: str):
    """Isi kolom NO STCK. Return (pesan_peringatan, nomor_berikutnya)."""
    rng = parse_range(text)
    if not rng:
        return (["Rentang NO STCK tidak valid (contoh: 6790758 - 6790813)"] if (text or "").strip() else []), None
    a, b = rng
    total, msgs = b - a + 1, []
    for i, r in enumerate(records):
        r["NO STCK"] = str(a + i) if a + i <= b else ""
    if len(records) > total:
        msgs.append(f"Rentang NO STCK hanya {total} nomor, sedangkan konsumen {len(records)}: "
                    f"{len(records) - total} baris tidak terisi")
    nxt = a + len(records)
    if nxt <= b:
        msgs.append(f"INFO: sisa NO STCK {nxt} - {b} ({b - nxt + 1} nomor) untuk BAST berikutnya")
    return msgs, (nxt if nxt <= b else None)
