"""Fast numpy readers for .dbf columns and point .shp files inside the raw zips (stdlib + numpy)."""
from __future__ import annotations

import struct
import zipfile

import numpy as np


def read_dbf_columns(zip_path, member: str, want: list[str]) -> dict[str, np.ndarray]:
    """{field: array of stripped str} for the wanted fields of a .dbf inside a zip."""
    with zipfile.ZipFile(zip_path) as z:
        data = z.read(member)
    n, hl, rl = struct.unpack("<IHH", data[4:12])
    fields, off, pos = {}, 1, 32
    while data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\0")[0].decode("ascii")
        length = data[pos + 16]
        fields[name] = (off, length)
        off += length
        pos += 32
    recs = np.frombuffer(data, dtype=f"S{rl}", count=n, offset=hl)
    raw = recs.view(np.uint8).reshape(n, rl)
    out = {}
    for f in want:
        o, ln = fields[f]
        col = np.ascontiguousarray(raw[:, o:o + ln]).view(f"S{ln}").ravel()
        out[f] = np.char.strip(np.char.decode(col, "latin1"))
    return out


def read_shp_points(zip_path, member: str) -> np.ndarray:
    """(n, 2) lon/lat for a point shapefile inside a zip; NaN rows for null shapes."""
    with zipfile.ZipFile(zip_path) as z:
        data = z.read(member)
    pts, pos, size = [], 100, len(data)
    while pos + 8 <= size:
        _, cl = struct.unpack_from(">2i", data, pos)
        t = struct.unpack_from("<i", data, pos + 8)[0]
        pts.append(struct.unpack_from("<2d", data, pos + 12) if t in (1, 11, 21) else (np.nan, np.nan))
        pos += 8 + cl * 2
    return np.asarray(pts, dtype=np.float64)
