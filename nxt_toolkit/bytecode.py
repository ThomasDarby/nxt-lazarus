"""NXT bytecode opcode constants and instruction encoding helpers.

Reference: LEGO MINDSTORMS NXT Executable File Specification
"""

import struct

# ── Type codes (for DSTOC entries) ──────────────────────────────────────────

TC_VOID   = 0x00
TC_UBYTE  = 0x01
TC_SBYTE  = 0x02
TC_UWORD  = 0x03
TC_SWORD  = 0x04
TC_ULONG  = 0x05
TC_SLONG  = 0x06
TC_ARRAY  = 0x07
TC_CLUSTER = 0x08
TC_MUTEX  = 0x09

TYPE_SIZES = {
    TC_UBYTE: 1,
    TC_SBYTE: 1,
    TC_UWORD: 2,
    TC_SWORD: 2,
    TC_ULONG: 4,
    TC_SLONG: 4,
}

# ── Opcodes ─────────────────────────────────────────────────────────────────

OP_ADD       = 0x00
OP_SUB       = 0x01
OP_NEG       = 0x02
OP_MUL       = 0x03
OP_DIV       = 0x04
OP_MOD       = 0x05
OP_AND       = 0x06
OP_OR        = 0x07
OP_XOR       = 0x08
OP_NOT       = 0x09
OP_CMNT      = 0x0A  # complement
OP_LSL       = 0x0B  # logical shift left
OP_LSR       = 0x0C  # logical shift right
OP_ASL       = 0x0D  # arithmetic shift left
OP_ASR       = 0x0E  # arithmetic shift right
OP_ROTL      = 0x0F  # rotate left
OP_ROTR      = 0x10  # rotate right

OP_CMP       = 0x11
OP_TST       = 0x12
OP_INDEX     = 0x13
OP_REPLACE   = 0x14
OP_ARRSIZE   = 0x15
OP_ARRBUILD  = 0x16
OP_ARRSUBSET = 0x17
OP_ARRINIT   = 0x18

OP_MOV       = 0x19
OP_SET       = 0x1A

OP_FLATTEN   = 0x1B
OP_UNFLATTEN = 0x1C
OP_NUMTOSTR  = 0x1D
OP_STRTONUM  = 0x1E
OP_STRCAT    = 0x1F
OP_STRSUBSET = 0x20
OP_STRTOBYTEARR = 0x21
OP_BYTEARRTOSTR = 0x22

OP_JMP       = 0x23
OP_BRCMP     = 0x24
OP_BRTST     = 0x25
OP_SYSCALL   = 0x28
OP_STOP      = 0x29

OP_FINCLUMP       = 0x2A
OP_FINCLUMPIMMED  = 0x2B
OP_ACQUIRE        = 0x2C
OP_RELEASE        = 0x2D
OP_SUBCALL        = 0x2E
OP_SUBRET         = 0x2F

OP_SETIN     = 0x30
OP_SETOUT    = 0x31
OP_GETIN     = 0x32
OP_GETOUT    = 0x33

OP_WAIT      = 0x34
OP_GETTICK   = 0x35

# ── Comparison codes ────────────────────────────────────────────────────────

CC_LT  = 0x00
CC_GT  = 0x01
CC_LTEQ = 0x02
CC_GTEQ = 0x03
CC_EQ  = 0x04
CC_NEQ = 0x05

# ── IO Port/Field constants ─────────────────────────────────────────────────

# Input fields (for SETIN / GETIN)
IN_TYPE          = 0  # InType
IN_MODE          = 1  # InMode
IN_ADRAW         = 2  # InAdRaw — unused in user code
IN_NORMRAW       = 3  # InNormRaw — unused in user code
IN_SCALED        = 4  # InScaledVal — the one we read
IN_INVALID       = 5  # InInvalidData

# Sensor types (InType values)
SENSOR_TYPE_NONE        = 0x00
SENSOR_TYPE_TOUCH       = 0x01
SENSOR_TYPE_TEMPERATURE = 0x02
SENSOR_TYPE_REFLECTION  = 0x03
SENSOR_TYPE_ANGLE       = 0x04
SENSOR_TYPE_LIGHT_ACTIVE  = 0x05
SENSOR_TYPE_LIGHT_INACTIVE = 0x06
SENSOR_TYPE_SOUND_DB    = 0x07
SENSOR_TYPE_SOUND_DBA   = 0x08
SENSOR_TYPE_CUSTOM      = 0x09
SENSOR_TYPE_LOWSPEED    = 0x0A
SENSOR_TYPE_LOWSPEED_9V = 0x0B  # I2C (ultrasonic)

# Sensor modes (InMode values)
SENSOR_MODE_RAW          = 0x00
SENSOR_MODE_BOOLEAN      = 0x20
SENSOR_MODE_TRANSITIONCNT = 0x40
SENSOR_MODE_PERIODCNT    = 0x60
SENSOR_MODE_PCTFULLSCALE = 0x80
SENSOR_MODE_CELSIUS      = 0xA0
SENSOR_MODE_FAHRENHEIT   = 0xC0
SENSOR_MODE_ANGLESTEP    = 0xE0

# Output fields (for SETOUT / GETOUT)
OUT_FLAGS       = 0  # UpdateFlags
OUT_MODE        = 1  # OutputMode
OUT_SPEED       = 2  # Power/Speed
OUT_ACTUAL_SPEED = 3
OUT_TACHO_COUNT = 4
OUT_TACHO_LIMIT = 5
OUT_RUN_STATE   = 6
OUT_TURN_RATIO  = 7
OUT_REG_MODE    = 8
OUT_OVERLOAD    = 9
OUT_REG_P_VAL   = 10
OUT_REG_I_VAL   = 11
OUT_REG_D_VAL   = 12
OUT_BLOCK_TACHO = 13
OUT_ROTATION_COUNT = 14

# Output UpdateFlags bits
OUT_UPDATE_MODE       = 0x01
OUT_UPDATE_SPEED      = 0x02
OUT_UPDATE_TACHO_LIMIT = 0x04
OUT_UPDATE_RESET_COUNT = 0x08
OUT_UPDATE_PID_VALUES  = 0x10
OUT_UPDATE_RESET_BLOCK_COUNT = 0x20
OUT_UPDATE_RESET_ROTATION_COUNT = 0x40

# Output Modes
OUT_MODE_COAST     = 0x00
OUT_MODE_MOTORON   = 0x01
OUT_MODE_BRAKE     = 0x02
OUT_MODE_REGULATED = 0x04

# Output RunState
OUT_RUNSTATE_IDLE    = 0x00
OUT_RUNSTATE_RAMPUP  = 0x10
OUT_RUNSTATE_RUNNING = 0x20
OUT_RUNSTATE_RAMPDOWN = 0x40

# Output RegMode
OUT_REGMODE_IDLE  = 0
OUT_REGMODE_SPEED = 1
OUT_REGMODE_SYNC  = 2

# Motor port constants (used as byte values in port arrays)
MOTOR_A = 0
MOTOR_B = 1
MOTOR_C = 2

# Sensor port constants
SENSOR_1 = 0
SENSOR_2 = 1
SENSOR_3 = 2
SENSOR_4 = 3

# ── Syscall IDs ─────────────────────────────────────────────────────────────

SYSCALL_FILE_OPEN_READ    = 0
SYSCALL_FILE_OPEN_WRITE   = 1
SYSCALL_FILE_OPEN_APPEND  = 2
SYSCALL_FILE_READ         = 3
SYSCALL_FILE_WRITE        = 4
SYSCALL_FILE_CLOSE        = 5
SYSCALL_FILE_RESOLVE_HANDLE = 6
SYSCALL_FILE_RENAME       = 7
SYSCALL_FILE_DELETE       = 8
SYSCALL_SOUND_PLAY_FILE   = 9
SYSCALL_SOUND_PLAY_TONE   = 10
SYSCALL_SOUND_GET_STATE   = 11
SYSCALL_SOUND_SET_STATE   = 12
SYSCALL_DRAW_TEXT         = 13
SYSCALL_DRAW_POINT        = 14
SYSCALL_DRAW_LINE         = 15
SYSCALL_DRAW_RECT         = 16
SYSCALL_DRAW_CIRCLE       = 17
SYSCALL_SET_SCREEN_MODE   = 18
SYSCALL_READ_BUTTON       = 19
SYSCALL_COMM_LS_WRITE     = 20
SYSCALL_COMM_LS_READ      = 21
SYSCALL_COMM_LS_CHECKSTATUS = 22
SYSCALL_RANDOM_NUMBER     = 23
SYSCALL_GET_START_TICK    = 24
SYSCALL_MESSAGE_WRITE     = 25
SYSCALL_MESSAGE_READ      = 26
SYSCALL_COMM_BT_CHECK_STATUS = 27
SYSCALL_COMM_BT_WRITE    = 28
SYSCALL_KEEP_ALIVE        = 31
SYSCALL_IOMAP_READ        = 32
SYSCALL_IOMAP_WRITE       = 33
SYSCALL_CLEAR_SCREEN      = 38  # NXT 2.0 firmware

# ── Instruction encoding ────────────────────────────────────────────────────

# Instruction format (16-bit word):
#   Bits 15-12: size in bytes (encoded: 0=4, 1=6, 2=8, 3=10, 0xE=variable)
#   Bits 10-8:  comparison code (for CMP/BRCMP/BRTST)
#   Bits 7-0:   opcode

# Size encoding: the high nibble encodes the total instruction size
# 0x0xxx = 4 bytes (opcode word + 1 operand)
# 0x1xxx = 6 bytes (opcode word + 2 operands)
# 0x2xxx = 8 bytes (opcode word + 3 operands)
# 0x3xxx = 10 bytes (opcode word + 4 operands)
# 0xExxx = variable length (opcode word + count byte + N operands)

SIZE_4  = 0x0  # 2 bytes total: instruction word + 0 extra words (1 operand in spec = 4 bytes)
SIZE_6  = 0x1  # 3 words total
SIZE_8  = 0x2  # 4 words total
SIZE_10 = 0x3  # 5 words total
SIZE_12 = 0x4  # 6 words total
SIZE_14 = 0x5  # 7 words total
SIZE_VAR = 0xE  # variable-length

# Instruction sizes (in bytes) for each opcode
OPCODE_SIZES = {
    OP_ADD:   8,
    OP_SUB:   8,
    OP_NEG:   6,
    OP_MUL:   8,
    OP_DIV:   8,
    OP_MOD:   8,
    OP_AND:   8,
    OP_OR:    8,
    OP_XOR:   8,
    OP_NOT:   6,
    OP_CMP:   8,
    OP_TST:   6,
    OP_INDEX: 10,
    OP_REPLACE: 10,
    OP_ARRSIZE: 6,
    OP_ARRBUILD: None,  # variable
    OP_ARRSUBSET: 10,
    OP_ARRINIT: 8,
    OP_MOV:   6,
    OP_SET:   6,
    OP_FLATTEN: 6,
    OP_UNFLATTEN: 8,
    OP_NUMTOSTR: 6,
    OP_STRTONUM: 8,
    OP_STRCAT: None,    # variable
    OP_STRSUBSET: 10,
    OP_STRTOBYTEARR: 6,
    OP_BYTEARRTOSTR: 6,
    OP_JMP:   6,
    OP_BRCMP: 8,
    OP_BRTST: 6,
    OP_SYSCALL: 6,
    OP_STOP:  4,
    OP_FINCLUMP: 4,
    OP_FINCLUMPIMMED: 4,
    OP_ACQUIRE: 4,
    OP_RELEASE: 4,
    OP_SUBCALL: 6,
    OP_SUBRET: 4,
    OP_SETIN: 8,
    OP_SETOUT: None,    # variable
    OP_GETIN: 8,
    OP_GETOUT: 8,
    OP_WAIT:  4,
    OP_GETTICK: 6,
}


def encode_instruction(opcode, *operands, cc=0, size_bytes=None):
    """Encode an instruction as a list of signed 16-bit words.

    Args:
        opcode: The opcode byte (0x00–0xFF)
        *operands: DSTOC indices or immediate values (each becomes a 16-bit word)
        cc: Comparison code (0-5), used for CMP/BRCMP/BRTST
        size_bytes: Override the instruction size in bytes. If None, computed from
                    the opcode's known size or from operand count.

    Returns:
        List of signed 16-bit integers representing the instruction.
    """
    if size_bytes is None:
        known = OPCODE_SIZES.get(opcode)
        if known is not None:
            size_bytes = known
        else:
            # 2 bytes for instruction word + 2 bytes per operand
            size_bytes = 2 + 2 * len(operands)

    # Encode the size nibble
    if size_bytes == 4:
        size_nibble = 0x0
    elif size_bytes == 6:
        size_nibble = 0x1
    elif size_bytes == 8:
        size_nibble = 0x2
    elif size_bytes == 10:
        size_nibble = 0x3
    elif size_bytes == 12:
        size_nibble = 0x4
    elif size_bytes == 14:
        size_nibble = 0x5
    else:
        size_nibble = 0xE  # variable length

    instr_word = (size_nibble << 12) | ((cc & 0x7) << 8) | (opcode & 0xFF)

    # Convert to signed 16-bit
    words = [_to_i16(instr_word)]
    for op in operands:
        words.append(_to_i16(op))
    return words


def encode_setout(port_idx, *field_value_pairs):
    """Encode an OP_SETOUT instruction for motor control.

    OP_SETOUT is variable-length:
      instruction_word, port_ds_index, N_fields, field_id_1, val_ds_1, field_id_2, val_ds_2, ...

    But actually OP_SETOUT format is:
      instr_word(0xE031) | port_idx | num_field_value_pairs | field1 | val1 | field2 | val2 | ...

    Wait — let me re-check. The actual encoding for variable-length instructions:
      instruction_word | byte_count | operands...

    For SETOUT specifically, the NXT firmware expects:
      instr_word | port | propid1 | val1 | propid2 | val2 | ... (terminated by size)

    The size nibble 0xE means variable, and we need a count.

    Actually for variable-length instructions, after the instruction word the next
    value is the total number of following operand words.

    Args:
        port_idx: DSTOC index of the port variable
        *field_value_pairs: Alternating (field_dstoc_idx, value_dstoc_idx) pairs.
            Each field_dstoc_idx points to a DSTOC entry containing the OUT_* field ID.
            Each value_dstoc_idx points to a DSTOC entry containing the value.

    Returns:
        List of signed 16-bit words.
    """
    # Total operand count: port + all field/value pairs
    operand_count = 1 + len(field_value_pairs)
    size_bytes = 2 + 2 * (1 + operand_count)  # instr_word + count + operands

    instr_word = (SIZE_VAR << 12) | (OP_SETOUT & 0xFF)
    words = [_to_i16(instr_word), _to_i16(operand_count)]
    words.append(_to_i16(port_idx))
    for fv in field_value_pairs:
        words.append(_to_i16(fv))
    return words


def encode_syscall(syscall_id_idx, param_cluster_idx):
    """Encode OP_SYSCALL: syscall_id (DSTOC index), param_cluster (DSTOC index)."""
    return encode_instruction(OP_SYSCALL, syscall_id_idx, param_cluster_idx)


def _to_i16(val):
    """Convert an unsigned value to a signed 16-bit integer."""
    val = val & 0xFFFF
    if val >= 0x8000:
        val -= 0x10000
    return val


def words_to_bytes(words):
    """Convert a list of signed 16-bit words to bytes (little-endian)."""
    return b"".join(struct.pack("<h", w) for w in words)
