# NXT Toolkit

Write, compile, and upload programs to LEGO NXT Mindstorms from modern macOS — no legacy software needed.

NXT Toolkit is a standalone desktop app with a built-in code editor, compiler, and USB uploader. It uses a simple, Python-like language that compiles directly to NXT bytecode (`.rxe` files).

## Quick Start

```bash
pip install -e .
nxt-toolkit
```

Or build a standalone `.app`:

```bash
pip install pyinstaller pyusb
brew install libusb
./build_app.sh        # produces dist/NXT Toolkit.app
```

## The Language

Programs use a small, beginner-friendly DSL. Here's a complete example:

```
# Obstacle Avoider
# Ultrasonic sensor on port 4, motors on B and C

forever:
    if ultrasonic(4) < 30:
        motor(B).off()
        motor(C).off()
        play_tone(880, 200)
        wait(500)

        motor(B).on(-50)
        motor(C).on(-50)
        wait(1000)

        motor(B).on(50)
        motor(C).on(-50)
        wait(600)
    else:
        motor(B).on(75)
        motor(C).on(75)
    end
end
```

### Motors

```
motor(A).on(75)      # port A at 75% power
motor(B).on(-50)     # port B reverse at 50%
motor(C).off()       # stop with brake
motor(A).coast()     # stop without brake
```

Ports: `A`, `B`, `C`. Power range: -100 to 100.

### Sensors

```
touch(1)             # touch sensor on port 1 (returns 0 or 1)
light(2)             # light sensor on port 2 (0–100)
sound(3)             # sound sensor on port 3 (0–100)
ultrasonic(4)        # ultrasonic on port 4 (distance in cm)
```

Ports: `1`, `2`, `3`, `4`.

### Sound & Display

```
play_tone(440, 500)  # 440 Hz for 500 ms
display("Hello!", 1) # show text on line 1 (lines 1–8)
clear_screen()       # clear the NXT display
```

### Control Flow

```
if x > 5:
    motor(A).on(50)
else:
    motor(A).off()
end

repeat 4:
    play_tone(523, 200)
    wait(300)
end

forever:
    motor(B).on(75)
end
```

### Variables

```
x = 10
x = x + 1           # operators: +, -, *, /, %
```

### Functions

```
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

drive(75, 1500)       # call with arguments
turn_right()          # call with no arguments
```

Functions can take parameters or none at all. Note: recursion is not supported (NXT hardware limitation).

### Comments

```
# everything after # is a comment
```

## How It Works

Source code goes through a four-stage pipeline:

1. **Lexer** — tokenizes the source text
2. **Parser** — builds an AST via recursive descent
3. **Code generator** — walks the AST, emits DSTOC entries and NXT bytecode
4. **RXE writer** — packs everything into a valid `.rxe` binary (format version 5.0)

The compiled `.rxe` is uploaded to the NXT over USB using the standard NXT Direct/System Command protocol via `pyusb`.

## Requirements

- Python 3.10+
- [pyusb](https://pypi.org/project/pyusb/) (for NXT communication)
- [libusb](https://libusb.info/) (`brew install libusb`)
- A LEGO NXT Mindstorms brick with USB cable

## Project Structure

```
nxt_toolkit/
  app.py          # tkinter GUI — editor, toolbar, output panel
  compiler.py     # lexer, parser, AST, code generator
  bytecode.py     # NXT opcode constants and instruction encoding
  dataspace.py    # DSTOC builder and dataspace layout
  rxe_writer.py   # binary .rxe file writer
  usb.py          # NXT USB communication (upload, run, device info)
examples/
  hello.nxt       # play a melody and display text
  drive_square.nxt    # drive in a square using repeat loop
  obstacle_avoid.nxt  # ultrasonic obstacle avoidance
build_app.sh      # build a standalone macOS .app with PyInstaller
```

## License

MIT
