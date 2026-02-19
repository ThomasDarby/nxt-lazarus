"""Minimal NXT USB communication using pyusb.

Implements just enough of the NXT Direct Command and System Command protocols
to upload .rxe files and start programs.

Protocol reference: LEGO MINDSTORMS NXT Direct Commands / System Commands
"""

import struct
import time

# NXT USB identifiers
NXT_VENDOR_ID  = 0x0694
NXT_PRODUCT_ID = 0x0002

# USB endpoints
NXT_EP_OUT = 0x01
NXT_EP_IN  = 0x82

# Maximum payload per USB write (NXT protocol limit)
MAX_WRITE_PAYLOAD = 61  # 64 - 3 byte header

# Command types
CMD_SYSTEM_REPLY    = 0x01  # System command, response required
CMD_DIRECT_REPLY    = 0x00  # Direct command, response required
CMD_SYSTEM_NO_REPLY = 0x81  # System command, no response
CMD_DIRECT_NO_REPLY = 0x80  # Direct command, no response

# System commands
SYS_OPEN_WRITE = 0x01
SYS_WRITE      = 0x03
SYS_CLOSE      = 0x04
SYS_DELETE      = 0x06

# Direct commands
DC_START_PROGRAM  = 0x00
DC_GET_DEVICE_INFO = 0x9B  # Actually a system command
DC_PLAY_TONE      = 0x03


class NXTError(Exception):
    """Error communicating with the NXT brick."""
    pass


class NXTConnection:
    """USB connection to a LEGO NXT brick."""

    def __init__(self, dev=None):
        self._dev = dev
        self._handle = None

    @classmethod
    def find(cls):
        """Find and connect to an NXT brick via USB.

        Returns:
            NXTConnection instance.

        Raises:
            NXTError: If no NXT brick is found or USB setup fails.
        """
        try:
            import usb.core
            import usb.util
        except ImportError:
            raise NXTError(
                "pyusb is not installed. Install it with: pip install pyusb\n"
                "You also need libusb: brew install libusb")

        dev = usb.core.find(idVendor=NXT_VENDOR_ID, idProduct=NXT_PRODUCT_ID)
        if dev is None:
            raise NXTError(
                "No NXT brick found.\n"
                "Make sure the NXT is:\n"
                "  - Turned on\n"
                "  - Connected via USB cable\n"
                "  - Not already in use by another program")

        conn = cls(dev)
        conn._setup()
        return conn

    def _setup(self):
        """Configure the USB device for communication."""
        import usb.util

        dev = self._dev

        # Detach kernel driver if needed (macOS / Linux)
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (AttributeError, NotImplementedError):
            pass  # Not all backends support this

        dev.set_configuration()

    def close(self):
        """Release the USB device."""
        if self._dev is not None:
            import usb.util
            usb.util.dispose_resources(self._dev)
            self._dev = None

    def _send(self, data):
        """Send raw bytes to the NXT."""
        self._dev.write(NXT_EP_OUT, data, timeout=5000)

    def _recv(self, size=64, timeout=5000):
        """Receive raw bytes from the NXT."""
        data = self._dev.read(NXT_EP_IN, size, timeout=timeout)
        return bytes(data)

    def _check_status(self, response, cmd_byte):
        """Check the status byte in an NXT response."""
        if len(response) < 3:
            raise NXTError(f"Response too short: {response.hex()}")
        if response[0] != 0x02:  # Reply byte
            raise NXTError(f"Unexpected reply type: 0x{response[0]:02x}")
        if response[1] != cmd_byte:
            raise NXTError(
                f"Reply for wrong command: expected 0x{cmd_byte:02x}, "
                f"got 0x{response[1]:02x}")
        status = response[2]
        if status != 0x00:
            status_messages = {
                0x20: "Pending communication in progress",
                0x40: "Mailbox queue is empty",
                0x81: "No more handles available",
                0x82: "No space",
                0x83: "No more files found",
                0x84: "End of file expected",
                0x85: "End of file",
                0x86: "Not a linear file",
                0x87: "File not found",
                0x88: "Handle already closed",
                0x89: "No linear space",
                0x8A: "Undefined error",
                0x8B: "File is busy",
                0x8C: "No write buffers",
                0x8D: "Append not possible",
                0x8E: "File is full",
                0x8F: "File already exists",
                0x90: "Module not found",
                0x91: "Out of bounds",
                0x92: "Illegal file name",
                0x93: "Illegal handle",
            }
            msg = status_messages.get(status, f"Unknown error 0x{status:02x}")
            raise NXTError(f"NXT error: {msg}")

    def get_device_info(self):
        """Get NXT device info (name, Bluetooth address, signal strength, free flash).

        Returns:
            dict with 'name', 'bt_address', 'signal_strength', 'free_flash'.
        """
        cmd = bytes([CMD_SYSTEM_REPLY, DC_GET_DEVICE_INFO])
        self._send(cmd)
        resp = self._recv(33)
        self._check_status(resp, DC_GET_DEVICE_INFO)

        name = resp[3:18].split(b"\x00")[0].decode("ascii", errors="replace")
        bt_addr = resp[18:25]
        bt_str = ":".join(f"{b:02X}" for b in bt_addr[:6])
        signal = struct.unpack_from("<I", resp, 25)[0]
        free_flash = struct.unpack_from("<I", resp, 29)[0]

        return {
            "name": name,
            "bt_address": bt_str,
            "signal_strength": signal,
            "free_flash": free_flash,
        }

    def delete_file(self, filename):
        """Delete a file from the NXT.

        Args:
            filename: The filename on the NXT (max 19 chars + null).
        """
        fname_bytes = filename.encode("ascii")[:19].ljust(20, b"\x00")
        cmd = bytes([CMD_SYSTEM_REPLY, SYS_DELETE]) + fname_bytes
        self._send(cmd)
        resp = self._recv()
        # Don't error on "file not found" — it's fine if it doesn't exist
        if len(resp) >= 3 and resp[2] == 0x87:
            return  # File not found, that's OK
        self._check_status(resp, SYS_DELETE)

    def upload_file(self, local_path, nxt_filename, progress_callback=None):
        """Upload a file to the NXT brick.

        Args:
            local_path: Path to the local file.
            nxt_filename: Filename to use on the NXT (max 19 chars).
            progress_callback: Optional callable(bytes_sent, total_bytes).
        """
        with open(local_path, "rb") as f:
            data = f.read()
        total_size = len(data)

        # Delete existing file first (ignore errors)
        try:
            self.delete_file(nxt_filename)
        except NXTError:
            pass

        # Open file for writing
        fname_bytes = nxt_filename.encode("ascii")[:19].ljust(20, b"\x00")
        cmd = bytes([CMD_SYSTEM_REPLY, SYS_OPEN_WRITE]) + fname_bytes
        cmd += struct.pack("<I", total_size)
        self._send(cmd)
        resp = self._recv()
        self._check_status(resp, SYS_OPEN_WRITE)
        handle = resp[3]

        # Write data in chunks
        bytes_sent = 0
        try:
            while bytes_sent < total_size:
                chunk_size = min(MAX_WRITE_PAYLOAD, total_size - bytes_sent)
                chunk = data[bytes_sent:bytes_sent + chunk_size]
                cmd = bytes([CMD_SYSTEM_REPLY, SYS_WRITE, handle]) + chunk
                self._send(cmd)
                resp = self._recv()
                self._check_status(resp, SYS_WRITE)
                bytes_sent += chunk_size
                if progress_callback:
                    progress_callback(bytes_sent, total_size)
        finally:
            # Always close the handle
            cmd = bytes([CMD_SYSTEM_REPLY, SYS_CLOSE, handle])
            self._send(cmd)
            resp = self._recv()
            self._check_status(resp, SYS_CLOSE)

    def start_program(self, filename):
        """Start a program on the NXT.

        Args:
            filename: The .rxe filename on the NXT.
        """
        fname_bytes = filename.encode("ascii")[:19].ljust(20, b"\x00")
        cmd = bytes([CMD_DIRECT_REPLY, DC_START_PROGRAM]) + fname_bytes
        self._send(cmd)
        resp = self._recv()
        self._check_status(resp, DC_START_PROGRAM)

    def play_tone(self, frequency, duration_ms):
        """Play a tone on the NXT (for connection testing).

        Args:
            frequency: Tone frequency in Hz (200-14000).
            duration_ms: Duration in milliseconds.
        """
        cmd = bytes([CMD_DIRECT_NO_REPLY, DC_PLAY_TONE])
        cmd += struct.pack("<HH", frequency, duration_ms)
        self._send(cmd)
