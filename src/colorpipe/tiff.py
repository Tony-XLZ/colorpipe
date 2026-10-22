"""Small typed classic-TIFF metadata codec; pixel encoding stays uncompressed."""

from dataclasses import dataclass
import struct

import numpy as np

FORMATS = {1: 'B', 3: 'H', 4: 'I', 5: 'II', 7: 'B', 9: 'i', 10: 'ii', 11: 'f', 12: 'd'}
SIZES = {kind: struct.calcsize('<' + code) for kind, code in FORMATS.items()} | {2: 1}


@dataclass(frozen=True)
class Field:
    kind: int
    count: int
    data: bytes  # canonical little-endian value bytes, never an external pointer

    def numbers(self):
        if self.kind not in FORMATS:
            raise ValueError('expected a numeric TIFF field')
        if self.kind in (5, 10):
            pairs = np.frombuffer(self.data, dtype='<u4' if self.kind == 5 else '<i4').reshape(-1, 2)
            if np.any(pairs[:, 1] == 0):
                raise ValueError('zero rational denominator')
            return pairs[:, 0].astype(np.float64) / pairs[:, 1]
        dtype = {1: 'u1', 3: '<u2', 4: '<u4', 7: 'u1', 9: '<i4', 11: '<f4', 12: '<f8'}[self.kind]
        return np.frombuffer(self.data, dtype=dtype)

    def text(self):
        if self.kind != 2 or not self.data.endswith(b'\0'):
            raise ValueError('expected a null-terminated UTF-8 string')
        return self.data[:-1].decode('utf-8')


def field(kind, values):
    if kind == 2:
        body = values.encode('utf-8') + b'\0'
        return Field(kind, len(body), body)
    if kind in (1, 7):
        return Field(kind, len(values), bytes(values))
    values = tuple(values)
    flat = tuple(n for pair in values for n in pair) if kind in (5, 10) else values
    return Field(kind, len(values), struct.pack('<' + FORMATS[kind] * len(values), *flat))


def read_directory(data, offset, endian='<'):
    if offset < 8 or offset + 2 > len(data):
        raise ValueError('IFD offset outside file')
    count = struct.unpack_from(endian + 'H', data, offset)[0]
    end = offset + 2 + count * 12 + 4
    if not 0 < count <= 4096 or end > len(data):
        raise ValueError('invalid or truncated IFD')
    result = {}
    for i in range(count):
        position = offset + 2 + i * 12
        code, kind, size = struct.unpack_from(endian + 'HHI', data, position)
        if code in result or kind not in SIZES or size < 1:
            raise ValueError('duplicate tag, invalid type or empty field')
        length = size * SIZES[kind]
        start = position + 8 if length <= 4 else struct.unpack_from(endian + 'I', data, position + 8)[0]
        if start < 0 or start + length > len(data):
            raise ValueError('field extends beyond file')
        body = data[start:start + length]
        if endian == '>' and kind not in (1, 2, 7):
            values = struct.unpack('>' + FORMATS[kind] * size, body)
            body = struct.pack('<' + FORMATS[kind] * size, *values)
        result[code] = Field(kind, size, body)
    return result, struct.unpack_from(endian + 'I', data, end - 4)[0]


def dng_header(root, exif):
    """Build new root/Exif directories; never transplant source offsets."""
    root = dict(root)
    if exif:
        root[34665] = field(4, [8 + 2 + 12 * (len(root) + 1) + 4])
    root_size = 2 + 12 * len(root) + 4
    directories = [(8, root)] + ([(8 + root_size, exif)] if exif else [])
    size = 8 + root_size + (2 + 12 * len(exif) + 4 if exif else 0)
    buffer = bytearray(size)
    buffer[:8] = b'II' + struct.pack('<HI', 42, 8)
    strip_position = None
    for offset, tags in directories:
        struct.pack_into('<H', buffer, offset, len(tags))
        for i, (code, entry) in enumerate(sorted(tags.items())):
            if len(entry.data) != entry.count * SIZES[entry.kind]:
                raise ValueError('metadata type/count mismatch')
            position = offset + 2 + i * 12
            struct.pack_into('<HHI', buffer, position, code, entry.kind, entry.count)
            if len(entry.data) <= 4:
                buffer[position + 8:position + 12] = entry.data.ljust(4, b'\0')
            else:
                buffer.extend(b'\0' * (-len(buffer) % 4))
                struct.pack_into('<I', buffer, position + 8, len(buffer))
                buffer.extend(entry.data)
            if offset == 8 and code == 273:
                strip_position = position + 8
    buffer.extend(b'\0' * (-len(buffer) % 8))
    if strip_position is None:
        raise ValueError('missing output strip offset')
    struct.pack_into('<I', buffer, strip_position, len(buffer))
    return bytes(buffer)
