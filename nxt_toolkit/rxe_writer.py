"""Binary .rxe file writer for NXT executables.

RXE file layout:
  1. Header (38 bytes)
  2. DSTOC (Data Space Table of Contents)
  3. Static default data
  4. Dynamic default data (dope vectors + initial array contents)
  5. Clump records
  6. Codespace (bytecode)

Header format (38 bytes total):
  Offset  Size  Field
  0       14    FormatString "MindstormsNXT\\0"
  14      2     Version (byte 14=major ≤1, byte 15=minor ≥4)
  16      2     DataspaceCount (number of DSTOC entries)
  18      2     DataspaceSize (total initial dataspace size in bytes)
  20      2     DSStaticSize (bytes of static dataspace)
  22      2     DSDefaultsSize (total default data: static + dynamic)
  24      2     DynDSDefaultsOffset (where dynamic defaults begin in DS)
  26      2     DynDSDefaultsSize (bytes of dynamic default data)
  28      2     MemMgrHead (0xFFFF = empty)
  30      2     MemMgrTail (0xFFFF = empty)
  32      2     DVArrayOffset (byte offset of DopeVector array in DS)
  34      2     ClumpCount (number of clumps)
  36      2     CodespaceCount (number of 16-bit code words)

Then:
  DSTOC entries (4 bytes each x DataspaceCount)
  Default data (DSDefaultsSize bytes = static defaults + dynamic defaults)
  Clump records (4 bytes each x ClumpCount):
    FireCount (1 byte): how many deps must fire before clump runs (usually 1)
    DependentCount (1 byte): 0 for simple programs
    CodeStartOffset (2 bytes): word offset into codespace
  Codespace (2 bytes each x CodespaceCount)

Reference: LEGO MINDSTORMS NXT Firmware source (c_cmd.c, c_cmd.h)
"""

import struct
from .bytecode import words_to_bytes


# Format string: "MindstormsNXT\0" (14 bytes)
FORMAT_STRING = b"MindstormsNXT\x00"

# File format version: two separate bytes at offset 14-15.
# Byte 14 = major (must be ≤ 1), byte 15 = minor (must be ≥ 4).
# Firmware 1.05 checks: major ≤ 1, minor ≥ VM_OLDEST_COMPATIBLE_VERSION (4).
FILE_VERSION_MAJOR = 0
FILE_VERSION_MINOR = 5


def write_rxe(dstoc_bytes, static_defaults, dynamic_defaults,
              ds_static_size, code_words, output_path, clump_records=None,
              mem_mgr_head=0xFFFF, mem_mgr_tail=0xFFFF):
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
        # FireCount=0 means this clump runs immediately (entry point).
        # FireCount>0 means the clump waits to be fired by dependents.
        clump_records = [(0, 0, 0)]

    dstoc_count = len(dstoc_bytes) // 4
    codespace_count = len(code_words)
    clump_count = len(clump_records)

    ds_dynamic_size = len(dynamic_defaults)
    ds_initial_size = ds_static_size + ds_dynamic_size
    # DSDefaultsSize and DynDSDefaultsOffset use the compact stream length,
    # NOT ds_static_size, because the firmware reads defaults sequentially.
    ds_defaults_size = len(static_defaults) + ds_dynamic_size
    dyn_defaults_offset = len(static_defaults)  # dynamic data starts after compact stream
    dv_array_offset = ds_static_size      # dope vectors are first in dynamic area

    # Pack clump records
    clump_record = b"".join(
        struct.pack("<BBH", fc, dc, cs)
        for fc, dc, cs in clump_records
    )

    # Build header (38 bytes)
    header = bytearray()

    # Bytes 0-15: format string (14 bytes) + version (UWORD LE)
    header.extend(FORMAT_STRING)                              # 0-13: "MindstormsNXT\0"
    header.extend(bytes([FILE_VERSION_MAJOR, FILE_VERSION_MINOR]))  # 14-15: version (major, minor)

    # Bytes 16-37: 11 UWORD fields
    header.extend(struct.pack("<H", dstoc_count))             # 16-17: DataspaceCount
    header.extend(struct.pack("<H", ds_initial_size))         # 18-19: DataspaceSize
    header.extend(struct.pack("<H", ds_static_size))          # 20-21: DSStaticSize
    header.extend(struct.pack("<H", ds_defaults_size))        # 22-23: DSDefaultsSize
    header.extend(struct.pack("<H", dyn_defaults_offset))     # 24-25: DynDSDefaultsOffset
    header.extend(struct.pack("<H", ds_dynamic_size))         # 26-27: DynDSDefaultsSize
    header.extend(struct.pack("<H", mem_mgr_head))             # 28-29: MemMgrHead
    header.extend(struct.pack("<H", mem_mgr_tail))             # 30-31: MemMgrTail
    header.extend(struct.pack("<H", dv_array_offset))         # 32-33: DVArrayOffset
    header.extend(struct.pack("<H", clump_count))             # 34-35: ClumpCount
    header.extend(struct.pack("<H", codespace_count))         # 36-37: CodespaceCount

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
