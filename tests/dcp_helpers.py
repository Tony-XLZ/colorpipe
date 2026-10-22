"""Small synthetic profiles; no vendor payloads in tests or the repository."""
import struct


def profile_file(path, updates=None, *, endian='<'):
    cm = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    fm = [.9642, 0, 0, 0, 1, 0, 0, 0, .8249]
    tags = {50721: (10, [(int(v * 10000), 10000) for v in cm]),
            50778: (3, [21]), 50936: (2, 'Synthetic Test'),
            50941: (4, [0]), 50964: (10, [(int(v * 10000), 10000) for v in fm])}
    tags.update(updates or {})
    tags = {k: v for k, v in tags.items() if v is not None}
    table = bytearray(2 + 12 * len(tags) + 4)
    struct.pack_into(endian + 'H', table, 0, len(tags))
    extra = bytearray()
    for i, (code, (kind, values)) in enumerate(sorted(tags.items())):
        if kind == 2:
            body = values.encode('utf-8') + b'\0'
            count = len(body)
        elif kind in (5, 10):
            count = len(values)
            body = struct.pack(endian + ('II' if kind == 5 else 'ii') * count,
                               *(n for pair in values for n in pair))
        else:
            count = len(values)
            body = struct.pack(endian + {1: 'B', 3: 'H', 4: 'I', 11: 'f'}[kind] * count, *values)
        position = 2 + 12 * i
        struct.pack_into(endian + 'HHI', table, position, code, kind, count)
        if len(body) <= 4:
            table[position + 8:position + 12] = body.ljust(4, b'\0')
        else:
            struct.pack_into(endian + 'I', table, position + 8, 8 + len(table) + len(extra))
            extra.extend(body)
    header = (b'II' if endian == '<' else b'MM') + struct.pack(endian + 'HI', 0x4352, 8)
    path.write_bytes(header + table + extra)
    return path
