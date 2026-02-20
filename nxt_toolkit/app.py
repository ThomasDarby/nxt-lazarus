"""NXT Toolkit — tkinter desktop GUI.

Main window with code editor, toolbar, output panel, and NXT connection status.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import tempfile
import traceback

try:
    from .compiler import compile_source, CompileError
except ImportError:
    from nxt_toolkit.compiler import compile_source, CompileError

# Default file extension
FILE_EXT = ".nxt"
RXE_EXT = ".rxe"

# Colors for syntax highlighting
COLORS = {
    "keyword":  "#C678DD",  # purple — flow control
    "builtin":  "#61AFEF",  # blue — motor/sensor/display builtins
    "number":   "#D19A66",  # orange
    "string":   "#98C379",  # green
    "comment":  "#5C6370",  # gray
    "port":     "#E06C75",  # red — A, B, C
}

# Keyword groups for highlighting
FLOW_KEYWORDS = {"if", "else", "end", "repeat", "forever", "def"}
BUILTIN_KEYWORDS = {
    "motor", "touch", "light", "sound", "ultrasonic",
    "on", "off", "coast", "play_tone", "display", "clear_screen", "wait",
}
PORT_KEYWORDS = {"A", "B", "C"}

SYNTAX_HELP = """\
NXT Toolkit — Language Reference

MOTORS
  motor(A).on(75)     Turn motor A on at 75% power
  motor(B).on(-50)    Reverse at 50%
  motor(C).off()      Stop with brake
  motor(A).coast()    Stop without brake (coast)
  Ports: A, B, C. Power: -100 to 100.

SENSORS
  touch(1)            Read touch sensor on port 1 (returns 0 or 1)
  light(2)            Read light sensor on port 2 (0-100)
  sound(3)            Read sound sensor on port 3 (0-100)
  ultrasonic(4)       Read ultrasonic sensor on port 4 (cm)
  Ports: 1, 2, 3, 4.

SOUND
  play_tone(440, 500) Play 440Hz tone for 500ms

DISPLAY
  display("Hi!", 1)   Show text on line 1 (lines 1-8)
  clear_screen()      Clear the display

TIMING
  wait(1000)          Wait 1000 milliseconds (1 second)

VARIABLES
  x = 10              Set a variable
  x = x + 1           Math: +, -, *, /, %

CONTROL FLOW
  if x > 5:           If/else (comparisons: <, >, ==, !=, <=, >=)
      motor(A).on(50)
  else:
      motor(A).off()
  end

  repeat 4:           Repeat N times
      motor(A).on(50)
      wait(1000)
      motor(A).off()
      wait(1000)
  end

  forever:            Loop forever
      motor(A).on(50)
  end

FUNCTIONS
  def turn_right:       Define a function (no parameters)
      motor(B).on(50)
      motor(C).on(-50)
      wait(600)
  end

  def drive(power):     Define with parameters
      motor(B).on(power)
      motor(C).on(power)
  end

  drive(75)             Call a function
  turn_right()          Call with no arguments
  Note: no recursion (NXT hardware limitation).

COMMENTS
  # This is a comment
"""

# Built-in example programs
EXAMPLES = {
    "Hello World": """\
# Hello World
# Play a tone and show a message
clear_screen()
display("Hello!", 1)
display("NXT Toolkit", 3)
play_tone(523, 200)
wait(300)
play_tone(659, 200)
wait(300)
play_tone(784, 400)
wait(2000)
""",
    "Drive Square": """\
# Drive in a Square
# Motors B and C drive forward, then turn
# Repeat 4 times to make a square

repeat 4:
    # Drive forward
    motor(B).on(75)
    motor(C).on(75)
    wait(1500)

    # Stop
    motor(B).off()
    motor(C).off()
    wait(200)

    # Turn right (one motor forward, one back)
    motor(B).on(50)
    motor(C).on(-50)
    wait(800)

    # Stop
    motor(B).off()
    motor(C).off()
    wait(200)
end

# Coast motors when done
motor(B).coast()
motor(C).coast()
""",
    "Obstacle Avoider": """\
# Obstacle Avoider
# Uses ultrasonic sensor on port 4 to detect walls
# Motors B and C for driving

forever:
    if ultrasonic(4) < 30:
        # Too close! Back up and turn
        motor(B).off()
        motor(C).off()
        play_tone(880, 200)
        wait(500)

        # Back up
        motor(B).on(-50)
        motor(C).on(-50)
        wait(1000)

        # Turn right
        motor(B).on(50)
        motor(C).on(-50)
        wait(600)
    else:
        # Coast is clear, drive forward
        motor(B).on(75)
        motor(C).on(75)
    end
end
""",
    "Functions Demo": """\
# Functions Demo
# Define reusable actions for your robot

def drive(power, duration):
    motor(B).on(power)
    motor(C).on(power)
    wait(duration)
    motor(B).off()
    motor(C).off()
end

def turn_right:
    motor(B).on(50)
    motor(C).on(-50)
    wait(600)
    motor(B).off()
    motor(C).off()
end

def beep:
    play_tone(880, 150)
    wait(200)
end

# Drive in a triangle
repeat 3:
    beep()
    drive(75, 1500)
    turn_right()
end
beep()
""",
    "Line Follower": """\
# Simple Line Follower
# Light sensor on port 3
# Motors B and C

forever:
    if light(3) < 40:
        # On the line (dark) — turn left
        motor(B).on(30)
        motor(C).on(70)
    else:
        # Off the line (light) — turn right
        motor(B).on(70)
        motor(C).on(30)
    end
end
""",
}


class NXTToolkitApp:
    """Main application window."""

    def __init__(self, root):
        self.root = root
        self.root.title("NXT Toolkit")
        self.root.geometry("800x650")

        # Track current file
        self._current_file = None
        self._modified = False

        self._build_menu()
        self._build_toolbar()
        self._build_editor()
        self._build_output()
        self._build_statusbar()

        # Apply syntax highlighting after a short delay
        self.root.after(100, self._highlight_all)

        # Bind events
        self.editor.bind("<<Modified>>", self._on_modified)
        self.editor.bind("<KeyRelease>", self._on_key_release)

        # macOS: Cmd shortcuts
        self.root.bind("<Command-n>", lambda e: self._new_file())
        self.root.bind("<Command-o>", lambda e: self._open_file())
        self.root.bind("<Command-s>", lambda e: self._save_file())
        self.root.bind("<Command-S>", lambda e: self._save_as())
        self.root.bind("<Command-r>", lambda e: self._run())

        # Load the hello world example by default
        self.editor.insert("1.0", EXAMPLES["Hello World"])
        self._highlight_all()

    # ── Menu ────────────────────────────────────────────────────────────

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self._new_file, accelerator="Cmd+N")
        file_menu.add_command(label="Open...", command=self._open_file, accelerator="Cmd+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self._save_file, accelerator="Cmd+S")
        file_menu.add_command(label="Save As...", command=self._save_as, accelerator="Cmd+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.root.quit, accelerator="Cmd+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        # Examples menu
        examples_menu = tk.Menu(menubar, tearoff=0)
        for name in EXAMPLES:
            examples_menu.add_command(
                label=name,
                command=lambda n=name: self._load_example(n))
        menubar.add_cascade(label="Examples", menu=examples_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Language Reference", command=self._show_help)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    # ── Toolbar ─────────────────────────────────────────────────────────

    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=(5, 0))

        ttk.Button(toolbar, text="Compile", command=self._compile).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Upload", command=self._upload).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Run", command=self._run).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Button(toolbar, text="Connect NXT", command=self._test_connection).pack(side=tk.LEFT, padx=2)

    # ── Editor ──────────────────────────────────────────────────────────

    def _build_editor(self):
        editor_frame = ttk.Frame(self.root)
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Line numbers
        self.line_numbers = tk.Text(
            editor_frame, width=4, padx=4, takefocus=0,
            border=0, state="disabled",
            bg="#282C34", fg="#5C6370",
            font=("Menlo", 13))
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        # Code editor
        self.editor = tk.Text(
            editor_frame,
            wrap=tk.NONE,
            undo=True,
            font=("Menlo", 13),
            bg="#282C34",
            fg="#ABB2BF",
            insertbackground="#ABB2BF",
            selectbackground="#3E4451",
            selectforeground="#ABB2BF",
            padx=8,
            pady=8,
            tabs="4c",  # 4 character tab stops
        )
        self.editor.pack(fill=tk.BOTH, expand=True)

        # Scrollbar
        scrollbar = ttk.Scrollbar(editor_frame, command=self.editor.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.config(yscrollcommand=scrollbar.set)

        # Configure syntax highlighting tags
        for tag, color in COLORS.items():
            self.editor.tag_configure(tag, foreground=color)

    # ── Output ──────────────────────────────────────────────────────────

    def _build_output(self):
        output_frame = ttk.LabelFrame(self.root, text="Output")
        output_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.output = scrolledtext.ScrolledText(
            output_frame,
            height=8,
            font=("Menlo", 11),
            bg="#1E2127",
            fg="#ABB2BF",
            state="disabled",
        )
        self.output.pack(fill=tk.X, padx=2, pady=2)

        # Tags for colored output
        self.output.tag_configure("error", foreground="#E06C75")
        self.output.tag_configure("success", foreground="#98C379")
        self.output.tag_configure("info", foreground="#61AFEF")

    # ── Status bar ──────────────────────────────────────────────────────

    def _build_statusbar(self):
        self.statusbar = ttk.Label(self.root, text="Ready", anchor=tk.W)
        self.statusbar.pack(fill=tk.X, padx=5, pady=(0, 5))

    def _set_status(self, text):
        self.statusbar.config(text=text)
        self.root.update_idletasks()

    # ── Output helpers ──────────────────────────────────────────────────

    def _log(self, text, tag=None):
        self.output.config(state="normal")
        if tag:
            self.output.insert(tk.END, text + "\n", tag)
        else:
            self.output.insert(tk.END, text + "\n")
        self.output.see(tk.END)
        self.output.config(state="disabled")
        self.root.update_idletasks()

    def _clear_output(self):
        self.output.config(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.config(state="disabled")

    # ── File operations ─────────────────────────────────────────────────

    def _new_file(self):
        self.editor.delete("1.0", tk.END)
        self._current_file = None
        self._modified = False
        self.root.title("NXT Toolkit")

    def _open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("NXT Programs", "*.nxt"), ("All Files", "*.*")],
            defaultextension=FILE_EXT)
        if path:
            with open(path, "r") as f:
                content = f.read()
            self.editor.delete("1.0", tk.END)
            self.editor.insert("1.0", content)
            self._current_file = path
            self._modified = False
            self.root.title(f"NXT Toolkit — {os.path.basename(path)}")
            self._highlight_all()

    def _save_file(self):
        if self._current_file:
            self._write_file(self._current_file)
        else:
            self._save_as()

    def _save_as(self):
        path = filedialog.asksaveasfilename(
            filetypes=[("NXT Programs", "*.nxt"), ("All Files", "*.*")],
            defaultextension=FILE_EXT)
        if path:
            self._write_file(path)
            self._current_file = path
            self.root.title(f"NXT Toolkit — {os.path.basename(path)}")

    def _write_file(self, path):
        content = self.editor.get("1.0", tk.END)
        with open(path, "w") as f:
            f.write(content)
        self._modified = False

    # ── Examples ────────────────────────────────────────────────────────

    def _load_example(self, name):
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", EXAMPLES[name])
        self._current_file = None
        self._modified = False
        self.root.title(f"NXT Toolkit — {name}")
        self._highlight_all()

    # ── Compile / Upload / Run ──────────────────────────────────────────

    def _get_rxe_path(self):
        """Determine the output .rxe path."""
        if self._current_file:
            base = os.path.splitext(self._current_file)[0]
            return base + RXE_EXT
        return os.path.join(tempfile.gettempdir(), "nxt_program.rxe")

    def _get_nxt_filename(self):
        """Determine the filename to use on the NXT."""
        if self._current_file:
            base = os.path.splitext(os.path.basename(self._current_file))[0]
        else:
            base = "program"
        # NXT filenames: max 15 chars + .rxe = 19 chars
        return base[:15] + RXE_EXT

    def _compile(self):
        """Compile the current program."""
        self._clear_output()
        source = self.editor.get("1.0", tk.END)
        rxe_path = self._get_rxe_path()

        self._set_status("Compiling...")
        self._log("Compiling...", "info")

        try:
            compile_source(source, rxe_path)
            size = os.path.getsize(rxe_path)
            self._log(f"Compiled successfully: {rxe_path}", "success")
            self._log(f"Output size: {size} bytes", "info")
            self._set_status(f"Compiled — {size} bytes")
            return rxe_path
        except SyntaxError as e:
            self._log(f"Syntax error: {e}", "error")
            self._set_status("Compile failed")
            return None
        except CompileError as e:
            self._log(f"Compile error: {e}", "error")
            self._set_status("Compile failed")
            return None
        except Exception as e:
            self._log(f"Unexpected error: {e}", "error")
            self._log(traceback.format_exc(), "error")
            self._set_status("Compile failed")
            return None

    def _new_connection(self):
        """Create a fresh NXT USB connection."""
        try:
            from .usb import NXTConnection
        except ImportError:
            from nxt_toolkit.usb import NXTConnection
        return NXTConnection.find()

    def _upload(self):
        """Compile and upload to NXT."""
        rxe_path = self._compile()
        if not rxe_path:
            return

        nxt_filename = self._get_nxt_filename()
        self._set_status("Connecting to NXT...")
        self._log("Connecting to NXT...", "info")

        conn = None
        try:
            conn = self._new_connection()

            def progress(sent, total):
                pct = int(sent / total * 100)
                self._set_status(f"Uploading... {pct}%")

            def upload_log(msg):
                self._log(f"  {msg}", "info")

            self._log(f"Uploading {nxt_filename}...", "info")
            conn.upload_file(rxe_path, nxt_filename, progress_callback=progress,
                             log=upload_log)
            self._log(f"Upload complete: {nxt_filename}", "success")
            self._set_status("Upload complete")
            return nxt_filename
        except Exception as e:
            self._log(f"Upload error: {e}", "error")
            self._set_status("Upload failed")
            return None
        finally:
            if conn:
                conn.close()

    def _run(self):
        """Compile, upload, and start the program."""
        rxe_path = self._compile()
        if not rxe_path:
            return

        nxt_filename = self._get_nxt_filename()
        self._set_status("Connecting to NXT...")
        self._log("Connecting to NXT...", "info")

        conn = None
        try:
            conn = self._new_connection()

            def progress(sent, total):
                pct = int(sent / total * 100)
                self._set_status(f"Uploading... {pct}%")

            def upload_log(msg):
                self._log(f"  {msg}", "info")

            self._log(f"Uploading {nxt_filename}...", "info")
            conn.upload_file(rxe_path, nxt_filename, progress_callback=progress,
                             log=upload_log)
            self._log(f"Upload complete: {nxt_filename}", "success")

            # Brief pause to let the NXT finalize the flash write
            import time
            time.sleep(0.5)

            self._set_status("Starting program...")
            self._log("Starting program on NXT...", "info")
            conn.start_program(nxt_filename)
            self._log("Program started!", "success")
            self._set_status("Running on NXT")
        except Exception as e:
            self._log(f"Run error: {e}", "error")
            self._set_status("Run failed")
        finally:
            if conn:
                conn.close()

    def _test_connection(self):
        """Test NXT USB connection."""
        self._clear_output()
        self._set_status("Searching for NXT...")
        self._log("Searching for NXT brick...", "info")

        conn = None
        try:
            conn = self._new_connection()
            info = conn.get_device_info()
            fw = conn.get_firmware_version()
            self._log(f"Connected to: {info['name']}", "success")
            self._log(f"Firmware: {fw['firmware_version']} (protocol {fw['protocol_version']})", "info")
            self._log(f"Bluetooth: {info['bt_address']}", "info")
            self._log(f"Free flash: {info['free_flash']:,} bytes", "info")

            # Play a tone to confirm
            conn.play_tone(523, 200)
            self._set_status(f"Connected: {info['name']}")
        except Exception as e:
            self._log(f"Connection failed: {e}", "error")
            self._set_status("Not connected")
        finally:
            if conn:
                conn.close()

    # ── Help ────────────────────────────────────────────────────────────

    def _show_help(self):
        win = tk.Toplevel(self.root)
        win.title("NXT Toolkit — Language Reference")
        win.geometry("600x500")

        text = scrolledtext.ScrolledText(
            win, font=("Menlo", 12),
            bg="#282C34", fg="#ABB2BF",
            padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert("1.0", SYNTAX_HELP)
        text.config(state="disabled")

    def _show_about(self):
        messagebox.showinfo(
            "About NXT Toolkit",
            "NXT Toolkit v0.1.0\n\n"
            "Write, compile, and upload programs\n"
            "to LEGO NXT Mindstorms bricks.\n\n"
            "No LEGO software required.")

    # ── Syntax highlighting ─────────────────────────────────────────────

    def _on_modified(self, event=None):
        if self.editor.edit_modified():
            self._modified = True
            self.editor.edit_modified(False)

    def _on_key_release(self, event=None):
        self._highlight_all()
        self._update_line_numbers()

    def _highlight_all(self):
        """Apply syntax highlighting to all text."""
        content = self.editor.get("1.0", tk.END)

        # Remove all tags first
        for tag in COLORS:
            self.editor.tag_remove(tag, "1.0", tk.END)

        for lineno, line in enumerate(content.split("\n"), 1):
            self._highlight_line(lineno, line)

    def _highlight_line(self, lineno, line):
        """Apply syntax highlighting to a single line."""
        # Comments
        comment_pos = line.find("#")
        if comment_pos >= 0:
            start = f"{lineno}.{comment_pos}"
            end = f"{lineno}.end"
            self.editor.tag_add("comment", start, end)
            line = line[:comment_pos]  # Only process non-comment part

        # Process tokens in the line
        import re
        for match in re.finditer(r'[A-Za-z_]\w*|"[^"]*"|\d+', line):
            word = match.group()
            start_col = match.start()
            end_col = match.end()
            start = f"{lineno}.{start_col}"
            end = f"{lineno}.{end_col}"

            if word.startswith('"'):
                self.editor.tag_add("string", start, end)
            elif word in FLOW_KEYWORDS:
                self.editor.tag_add("keyword", start, end)
            elif word in BUILTIN_KEYWORDS:
                self.editor.tag_add("builtin", start, end)
            elif word in PORT_KEYWORDS:
                self.editor.tag_add("port", start, end)
            elif word.isdigit():
                self.editor.tag_add("number", start, end)

    def _update_line_numbers(self):
        """Update the line number gutter."""
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", tk.END)
        content = self.editor.get("1.0", tk.END)
        line_count = content.count("\n")
        line_nums = "\n".join(str(i) for i in range(1, line_count + 1))
        self.line_numbers.insert("1.0", line_nums)
        self.line_numbers.config(state="disabled")


def main():
    root = tk.Tk()

    # macOS-specific tweaks
    if sys.platform == "darwin":
        # Use native menu bar
        root.createcommand("tk::mac::ShowPreferences", lambda: None)

    app = NXTToolkitApp(root)

    # Load file from command line if provided
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        with open(sys.argv[1], "r") as f:
            content = f.read()
        app.editor.delete("1.0", tk.END)
        app.editor.insert("1.0", content)
        app._current_file = sys.argv[1]
        app.root.title(f"NXT Toolkit — {os.path.basename(sys.argv[1])}")
        app._highlight_all()

    root.mainloop()


if __name__ == "__main__":
    main()
