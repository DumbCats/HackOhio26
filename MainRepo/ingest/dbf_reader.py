"""
High-performance streaming binary reader for dBase III/IV (.dbf) and ESRI Shapefile (.shp/.shx) files.
Runs using Python 3 standard library with zero external C-dependencies (GDAL, Fiona, PyShp).
"""

import struct
import zipfile
from typing import Generator, Dict, Any, List, Tuple, Optional


class DbfReader:
    """Streams records from a DBF file (either from a zip archive or standalone file)."""

    def __init__(self, zip_path: Optional[str], file_name: str):
        self.zip_path = zip_path
        self.file_name = file_name
        self.fields: List[Tuple[str, str, int]] = []
        self.num_records = 0
        self.header_len = 0
        self.record_len = 0

    def _open_stream(self):
        if self.zip_path:
            z = zipfile.ZipFile(self.zip_path)
            return z, z.open(self.file_name)
        else:
            return None, open(self.file_name, "rb")

    def read_header(self) -> List[Tuple[str, str, int]]:
        zip_obj, stream = self._open_stream()
        try:
            header = stream.read(32)
            self.num_records, self.header_len, self.record_len = struct.unpack('<IHH', header[4:12])
            self.fields = []
            while True:
                field_desc = stream.read(32)
                if not field_desc or field_desc[0] == 0x0D:
                    break
                name = field_desc[:11].split(b'\x00')[0].decode('ascii', errors='replace').strip()
                typ = chr(field_desc[11])
                length = field_desc[16]
                self.fields.append((name, typ, length))
            return self.fields
        finally:
            stream.close()
            if zip_obj:
                zip_obj.close()

    def stream_records(self, batch_size: int = 5000) -> Generator[List[Dict[str, Any]], None, None]:
        """Yields batches of records as dictionaries."""
        if not self.fields:
            self.read_header()

        zip_obj, stream = self._open_stream()
        try:
            stream.seek(self.header_len)
            batch = []
            for _ in range(self.num_records):
                rec_bytes = stream.read(self.record_len)
                if not rec_bytes or len(rec_bytes) < self.record_len:
                    break
                # skip deletion flag (byte 0)
                offset = 1
                row = {}
                for name, typ, length in self.fields:
                    raw_val = rec_bytes[offset:offset + length].decode('latin1', errors='replace').strip()
                    offset += length

                    # Convert types
                    if typ == 'N':  # Numeric
                        if '.' in raw_val:
                            try:
                                row[name] = float(raw_val)
                            except ValueError:
                                row[name] = None
                        else:
                            try:
                                row[name] = int(raw_val) if raw_val else 0
                            except ValueError:
                                row[name] = None
                    elif typ == 'F':  # Float
                        try:
                            row[name] = float(raw_val) if raw_val else None
                        except ValueError:
                            row[name] = None
                    else:
                        row[name] = raw_val

                batch.append(row)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []

            if batch:
                yield batch
        finally:
            stream.close()
            if zip_obj:
                zip_obj.close()


def read_shp_points(zip_path: str, shp_name: str, shx_name: str) -> List[Tuple[float, float]]:
    """
    Reads point coordinates (lon, lat) from ESRI Shapefile using SHX index.
    Returns list of (lon, lat) tuples matching the exact record sequence of the DBF.
    """
    with zipfile.ZipFile(zip_path) as z:
        # 1. Read record offsets from SHX
        offsets = []
        with z.open(shx_name) as shx:
            shx_header = shx.read(100)
            file_len_words = struct.unpack('>I', shx_header[24:28])[0]
            num_records = (file_len_words * 2 - 100) // 8
            for _ in range(num_records):
                offset_words, content_len = struct.unpack('>II', shx.read(8))
                offsets.append(offset_words * 2)

        # 2. Read points from SHP
        points = []
        with z.open(shp_name) as shp:
            for byte_offset in offsets:
                shp.seek(byte_offset)
                rec_header = shp.read(8)
                if not rec_header:
                    points.append((0.0, 0.0))
                    continue
                shape_type = struct.unpack('<I', shp.read(4))[0]
                if shape_type == 1:  # Point
                    x, y = struct.unpack('<dd', shp.read(16))
                    points.append((x, y))
                elif shape_type == 0:  # Null shape
                    points.append((0.0, 0.0))
                else:
                    # Point fallback
                    x, y = struct.unpack('<dd', shp.read(16))
                    points.append((x, y))

    return points
