"""Binary .rxe file writer for NXT executables.

RXE file layout:
  1. Header (varies by version, we use version 5.0 = firmware 1.28+)
  2. DSTOC (Data Space Table of Contents)
  3. Static default data
  4. Dynamic default data (dope vectors + initial array contents)
  5. Clump records
  6. Codespace (bytecode)

Header format (version 5.0, 38 bytes total):
  Offset  Size  Field
  0       16    FormatString "MindstormsNXT\\0" (padded to 16 bytes)
  16      2     Version (0x0005 = 5.0)
  18      2     DSTOCCount (number of DSTOC entries)
  20      2     DSStaticSize (bytes of static default data)
  22      2     DSDefaultsSize (DSStaticSize; legacy alias)
  24      2     DSDynamicDefaultOffset (offset of dynamic defaults within DS)
  26      2     DSDynamicDefaultSize (bytes of dynamic default data)
  28      2     MemMgrHead (initial memory manager head, usually 0xFFFF)
  30      2     MemMgrTail (initial memory manager tail, usually 0xFFFF)
  32      2     DVArrayOffset (byte offset of first DopeVector in DS)
  34      2     ClumpCount (number of clumps)
  36      2     CodespaceCount (number of 16-bit code words)

Then:
  DSTOC entries (4 bytes each × DSTOCCount)
  Static defaults (DSStaticSize bytes)
  Dynamic defaults (DSDynamicDefaultSize bytes)
  Clump records (4 bytes each × ClumpCount):
    FireCount (1 byte): how many deps must fire before clump runs (usually 1)
    DependentCount (1 byte): 0 for simple programs
    CodeStartOffset (2 bytes): word offset into codespace
  Codespace (2 bytes each × CodespaceCount)

Reference: LEGO MINDSTORMS NXT Executable File Specification
"""

import struct
from .bytecode import words_to_bytes


# 16-byte format string (null-padded)
FORMAT_STRING = b"MindstormsNXT\x00\x00\x00"
VERSION = 0x0005  # version 5.0


def write_rxe(dstoc_bytes, static_defaults, dynamic_defaults,
              ds_static_size, code_words, output_path, clump_records=None):
    """Write a complete .rxe file.

    Args:
        dstoc_bytes: Serialized DSTOC entries (from DataspaceBuilder.serialize)
        static_defaults: Static default data bytes
        dynamic_defaults: Dynamic default data bytes (dope vectors + array data)
        ds_static_size: Size of static portion of dataspace
        code_words: List of signed 16-bit words (the codespace)
        output_path: Path to write the .rxe file
        clump_records: List of (fire_count, dep_count, code_start_offset) tuples.
                       Defaults to a single main clump if None.
    """
    if clump_records is None:
        clump_records = [(1, 0, 0)]

    dstoc_count = len(dstoc_bytes) // 4
    codespace_count = len(code_words)
    clump_count = len(clump_records)

    # Dynamic defaults start right after static data in the dataspace
    dv_array_offset = ds_static_size  # dope vectors are at the start of dynamic area

    # Pack clump records
    clump_record = b"".join(
        struct.pack("<BBH", fc, dc, cs)
        for fc, dc, cs in clump_records
    )

    # Build header
    header = bytearray()
    header.extend(FORMAT_STRING)                              # 0-15: format string
    header.extend(struct.pack("<H", VERSION))                 # 16-17: version
    header.extend(struct.pack("<H", dstoc_count))             # 18-19: DSTOC count
    header.extend(struct.pack("<H", ds_static_size))          # 20-21: DS static size
    header.extend(struct.pack("<H", ds_static_size))          # 22-23: DS defaults size (= static size)
    header.extend(struct.pack("<H", dv_array_offset))         # 24-25: dynamic default offset
    header.extend(struct.pack("<H", len(dynamic_defaults)))   # 26-27: dynamic default size
    header.extend(struct.pack("<H", 0xFFFF))                  # 28-29: mem mgr head
    header.extend(struct.pack("<H", 0xFFFF))                  # 30-31: mem mgr tail
    header.extend(struct.pack("<H", dv_array_offset))         # 32-33: DV array offset
    header.extend(struct.pack("<H", clump_count))             # 34-35: clump count
    header.extend(struct.pack("<H", codespace_count))         # 36-37: codespace count

    assert len(header) == 38, f"Header is {len(header)} bytes, expected 38"

    # Convert code words to bytes
    code_bytes = words_to_bytes(code_words)

    # Write the file
    with open(output_path, "wb") as f:
        f.write(bytes(header))
        f.write(dstoc_bytes)
        f.write(static_defaults)
        f.write(dynamic_defaults)
        f.write(clump_record)
        f.write(code_bytes)

    return output_path
