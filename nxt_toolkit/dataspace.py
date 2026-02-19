"""DSTOC (Data Space Table Of Contents) builder and dataspace layout.

The NXT dataspace is a flat byte array. Every variable, constant, temporary,
and syscall parameter is represented as a DSTOC entry that records its type,
flags, and byte offset within the dataspace.

DSTOC entry format (4 bytes):
  - TypeCode (1 byte): TC_UBYTE, TC_SWORD, TC_ARRAY, TC_CLUSTER, etc.
  - Flags (1 byte): bit 0 = written-to-by-code
  - DataDescriptor (2 bytes, little-endian):
      For scalars: byte offset into the dataspace
      For arrays: dope vector index
      For clusters: number of members that follow

Reference: LEGO MINDSTORMS NXT Executable File Specification
"""

import struct
from .bytecode import (
    TC_UBYTE, TC_SBYTE, TC_UWORD, TC_SWORD, TC_ULONG, TC_SLONG,
    TC_ARRAY, TC_CLUSTER, TC_VOID, TC_MUTEX, TYPE_SIZES,
)

# DopeVector is 5 UWORDs = 10 bytes
DOPE_VECTOR_SIZE = 10


class DSTOCEntry:
    """A single entry in the DSTOC."""

    __slots__ = ("type_code", "flags", "data_desc", "name", "default_value")

    def __init__(self, type_code, flags, data_desc, name="", default_value=None):
        self.type_code = type_code
        self.flags = flags
        self.data_desc = data_desc
        self.name = name
        self.default_value = default_value

    def pack(self):
        return struct.pack("<BBH", self.type_code, self.flags, self.data_desc)


class DataspaceBuilder:
    """Builds the DSTOC and manages dataspace layout.

    Usage:
        ds = DataspaceBuilder()
        idx = ds.add_scalar(TC_SWORD, name="counter", default=0)
        str_idx = ds.add_string("Hello!", name="msg")
        cluster_idx = ds.add_cluster([TC_UWORD, TC_UWORD, TC_UBYTE], name="tone_args")
        ...
        dstoc_bytes, static_defaults, initial_size = ds.serialize()
    """

    def __init__(self):
        self.entries: list[DSTOCEntry] = []
        self._ds_offset = 0  # current byte offset in the dataspace
        self._dope_vectors: list[tuple[int, int, int, int, int]] = []
        # Each dope vector: (offset, elem_size, elem_count, link_idx, back_ptr_offset)

    @property
    def count(self):
        return len(self.entries)

    def add_scalar(self, type_code, name="", default=0, flags=0):
        """Add a scalar variable. Returns its DSTOC index."""
        size = TYPE_SIZES[type_code]
        # Align to type size
        self._align(size)
        offset = self._ds_offset
        self._ds_offset += size
        idx = len(self.entries)
        self.entries.append(DSTOCEntry(type_code, flags, offset, name, default))
        return idx

    def add_constant(self, type_code, value, name=""):
        """Add a constant (read-only) scalar. Returns its DSTOC index."""
        return self.add_scalar(type_code, name=name, default=value, flags=0)

    def add_string(self, value="", name=""):
        """Add a string (TC_ARRAY of TC_UBYTE with null terminator).

        Creates two DSTOC entries: the array entry and its element type entry.
        Also creates a dope vector.

        Returns the DSTOC index of the array entry.
        """
        dv_index = len(self._dope_vectors)

        # Array entry
        array_idx = len(self.entries)
        self.entries.append(DSTOCEntry(TC_ARRAY, 0, dv_index, name))

        # Element type entry (TC_UBYTE) — immediately follows the array entry
        self.entries.append(DSTOCEntry(TC_UBYTE, 0, 0, f"{name}[]"))

        # String data: bytes + null terminator
        string_bytes = value.encode("ascii", errors="replace") + b"\x00"
        elem_count = len(string_bytes)

        # Dope vector: we'll resolve offsets during serialize
        # For now store: (elem_size=1, elem_count, data=string_bytes)
        self._dope_vectors.append({
            "elem_size": 1,
            "elem_count": elem_count,
            "data": string_bytes,
            "array_dstoc_idx": array_idx,
        })

        return array_idx

    def add_cluster(self, member_types, name="", defaults=None):
        """Add a cluster (struct) with the given member types.

        Creates N+1 DSTOC entries: the cluster header + one per member.
        Returns (cluster_idx, [member_indices]).
        """
        cluster_idx = len(self.entries)
        num_members = len(member_types)

        # Cluster header: data_desc = number of members
        self.entries.append(DSTOCEntry(TC_CLUSTER, 0, num_members, name))

        member_indices = []
        for i, tc in enumerate(member_types):
            if defaults and i < len(defaults):
                default = defaults[i]
            else:
                default = 0
            midx = self.add_scalar(tc, name=f"{name}.{i}", default=default, flags=0)
            member_indices.append(midx)

        return cluster_idx, member_indices

    def add_cluster_with_string(self, scalar_types, string_defaults=None, name=""):
        """Add a cluster that contains scalars and strings.

        This is needed for syscalls like DrawText which take a cluster with
        a string member. The member types list can include TC_ARRAY to indicate
        a string member.

        Args:
            scalar_types: List of type codes. Use TC_ARRAY for string members.
            string_defaults: Dict mapping member index to default string value.
            name: Name for the cluster.

        Returns:
            (cluster_idx, member_indices)
        """
        if string_defaults is None:
            string_defaults = {}

        cluster_idx = len(self.entries)
        num_members = len(scalar_types)
        self.entries.append(DSTOCEntry(TC_CLUSTER, 0, num_members, name))

        member_indices = []
        for i, tc in enumerate(scalar_types):
            if tc == TC_ARRAY:
                # String member
                midx = self.add_string(string_defaults.get(i, ""), name=f"{name}.{i}")
                member_indices.append(midx)
            else:
                midx = self.add_scalar(tc, name=f"{name}.{i}", default=0, flags=0)
                member_indices.append(midx)

        return cluster_idx, member_indices

    def _align(self, alignment):
        """Align the current offset to the given boundary."""
        remainder = self._ds_offset % alignment
        if remainder:
            self._ds_offset += alignment - remainder

    def serialize(self):
        """Serialize the DSTOC and compute defaults.

        Returns:
            (dstoc_bytes, static_defaults_bytes, dynamic_defaults_bytes,
             ds_static_size, ds_default_size)

        The static defaults cover all scalar/cluster data.
        The dynamic defaults cover dope vectors + initial array data.
        """
        # First pass: compute static dataspace size (all scalars/clusters)
        # This is already tracked by self._ds_offset
        static_size = self._ds_offset

        # Align static size to 4 bytes
        if static_size % 4:
            static_size += 4 - (static_size % 4)

        # Build static default values
        static_defaults = bytearray(static_size)
        for entry in self.entries:
            if entry.type_code in TYPE_SIZES and entry.default_value is not None:
                size = TYPE_SIZES[entry.type_code]
                offset = entry.data_desc
                if offset + size <= static_size:
                    fmt = {1: "<B", 2: "<H", 4: "<I"}[size]
                    if entry.type_code in (TC_SBYTE, TC_SWORD, TC_SLONG):
                        fmt = fmt.lower()  # signed format
                    val = entry.default_value & ({1: 0xFF, 2: 0xFFFF, 4: 0xFFFFFFFF}[size])
                    struct.pack_into(fmt.replace("b", "B").replace("h", "H").replace("i", "I"),
                                     static_defaults, offset, val)

        # Build dynamic defaults: dope vectors + array initial data
        dynamic_data = bytearray()

        # Dope vectors come first in dynamic memory
        dv_base_offset = static_size
        num_dv = len(self._dope_vectors)

        # Reserve space for all dope vectors
        for _ in self._dope_vectors:
            dynamic_data.extend(b"\x00" * DOPE_VECTOR_SIZE)

        # Now append array data and fill in dope vectors
        for i, dv in enumerate(self._dope_vectors):
            data_offset = static_size + len(dynamic_data)
            data = dv["data"]
            dynamic_data.extend(data)

            # Fill in the dope vector
            # DopeVector format: offset(UWORD), elem_size(UWORD), count(UWORD), back_ptr(UWORD), link(UWORD)
            dv_offset = i * DOPE_VECTOR_SIZE
            struct.pack_into("<HHHHH", dynamic_data, dv_offset,
                             data_offset,           # offset to array data
                             dv["elem_size"],        # element size
                             dv["elem_count"],       # element count
                             0,                      # back pointer (unused, 0)
                             0xFFFF)                 # link index (0xFFFF = no link)

        # Total initial dataspace size
        ds_initial_size = static_size + len(dynamic_data)

        # DSTOC bytes
        dstoc_bytes = b"".join(entry.pack() for entry in self.entries)

        return (dstoc_bytes, bytes(static_defaults), bytes(dynamic_data),
                static_size, ds_initial_size)
