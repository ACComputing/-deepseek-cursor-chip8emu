#!/usr/bin/env python3.14

"""
Chip8emu by a.c
Version 1.0

From-scratch Chip-8 emulator in pure Python with tkinter GUI.
- 4 KB memory, 64x32 monochrome disaplay
- Font sprites stored at 0x050
- ROMs loaded at 0x200 with clean state reset
- Remappable 16-key hex keypad
- mGBA-inspired dark theme
"""

import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from tkinter import DoubleVar, IntVar, StringVar
import random
import time
import sys
import os


# mGBA-inspired UI palette
UI_BG = "#1f232a"
UI_PANEL = "#2a3038"
UI_TEXT = "#d9dee7"
UI_ACCENT = "#6aa0ff"
SCREEN_BG = "#0f1410"
SCREEN_ON = "#8fe08f"

# ---------------------------
# Chip‑8 Core Implementation
# ---------------------------
class Chip8:
    def __init__(self):
        # Memory (4K)
        self.memory = [0] * 4096
        # Registers
        self.V = [0] * 16          # 16 general purpose registers
        self.I = 0                 # Index register
        self.pc = 0x200            # Program counter (start at 0x200)
        self.sp = 0                # Stack pointer
        self.stack = [0] * 16      # 16‑level stack
        # Timers
        self.delay_timer = 0
        self.sound_timer = 0
        # Display (64x32 pixels, 1‑bit per pixel)
        self.display = [[0 for _ in range(64)] for _ in range(32)]
        # Keypad state (16 keys, 0=up, 1=down)
        self.keys = [0] * 16
        # Flags
        self.draw_flag = False     # Indicates display needs updating
        self.waiting_key = False   # For FX0A opcode (wait for key press)
        self.waiting_register = None

        # Load fontset at 0x050 (standard Chip-8 convention)
        self.font_base = 0x050
        fontset = [
            0xF0, 0x90, 0x90, 0x90, 0xF0,  # 0
            0x20, 0x60, 0x20, 0x20, 0x70,  # 1
            0xF0, 0x10, 0xF0, 0x80, 0xF0,  # 2
            0xF0, 0x10, 0xF0, 0x10, 0xF0,  # 3
            0x90, 0x90, 0xF0, 0x10, 0x10,  # 4
            0xF0, 0x80, 0xF0, 0x10, 0xF0,  # 5
            0xF0, 0x80, 0xF0, 0x90, 0xF0,  # 6
            0xF0, 0x10, 0x20, 0x40, 0x40,  # 7
            0xF0, 0x90, 0xF0, 0x90, 0xF0,  # 8
            0xF0, 0x90, 0xF0, 0x10, 0xF0,  # 9
            0xF0, 0x90, 0xF0, 0x90, 0x90,  # A
            0xE0, 0x90, 0xE0, 0x90, 0xE0,  # B
            0xF0, 0x80, 0x80, 0x80, 0xF0,  # C
            0xE0, 0x90, 0x90, 0x90, 0xE0,  # D
            0xF0, 0x80, 0xF0, 0x80, 0xF0,  # E
            0xF0, 0x80, 0xF0, 0x80, 0x80   # F
        ]
        for i, byte in enumerate(fontset):
            self.memory[self.font_base + i] = byte

    def load_rom(self, rom_path):
        """Load a Chip‑8 ROM into memory starting at 0x200."""
        # Reset runtime state first so ROM bytes written below are not wiped.
        self.reset_state()

        # Clear prior ROM area to avoid stale bytes past EOF from old loads.
        for i in range(0x200, len(self.memory)):
            self.memory[i] = 0

        with open(rom_path, 'rb') as f:
            data = f.read()
        for i, byte in enumerate(data):
            self.memory[0x200 + i] = byte
        self.pc = 0x200

    def reset_state(self):
        """Reset CPU state (registers, timers, display) without clearing ROM."""
        self.V = [0] * 16
        self.I = 0
        self.sp = 0
        self.stack = [0] * 16
        self.delay_timer = 0
        self.sound_timer = 0
        self.display = [[0 for _ in range(64)] for _ in range(32)]
        self.keys = [0] * 16
        self.draw_flag = True
        self.waiting_key = False
        self.waiting_register = None

    def save_state(self):
        """Capture a full emulator snapshot for quick save/load."""
        return {
            "memory": self.memory.copy(),
            "V": self.V.copy(),
            "I": self.I,
            "pc": self.pc,
            "sp": self.sp,
            "stack": self.stack.copy(),
            "delay_timer": self.delay_timer,
            "sound_timer": self.sound_timer,
            "display": [row.copy() for row in self.display],
            "keys": self.keys.copy(),
            "draw_flag": self.draw_flag,
            "waiting_key": self.waiting_key,
            "waiting_register": self.waiting_register,
        }

    def load_state(self, state):
        """Restore emulator state from a snapshot dict."""
        self.memory = state["memory"].copy()
        self.V = state["V"].copy()
        self.I = state["I"]
        self.pc = state["pc"]
        self.sp = state["sp"]
        self.stack = state["stack"].copy()
        self.delay_timer = state["delay_timer"]
        self.sound_timer = state["sound_timer"]
        self.display = [row.copy() for row in state["display"]]
        self.keys = state["keys"].copy()
        self.draw_flag = state["draw_flag"]
        self.waiting_key = state["waiting_key"]
        self.waiting_register = state["waiting_register"]

    def emulate_cycle(self):
        """Execute one Chip‑8 instruction."""
        if self.waiting_key:
            # Wait for a key press (FX0A)
            for i, pressed in enumerate(self.keys):
                if pressed:
                    self.V[self.waiting_register] = i
                    self.waiting_key = False
                    self.waiting_register = None
                    self.pc += 2  # Move to next instruction
                    break
            return

        # Fetch opcode (big‑endian)
        opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        self.pc += 2

        # Decode and execute
        x = (opcode & 0x0F00) >> 8
        y = (opcode & 0x00F0) >> 4
        n = opcode & 0x000F
        nn = opcode & 0x00FF
        nnn = opcode & 0x0FFF

        # 0x0nnn: SYS addr (ignored on modern systems)
        if opcode == 0x00E0:
            # Clear screen
            self.display = [[0 for _ in range(64)] for _ in range(32)]
            self.draw_flag = True
        elif opcode == 0x00EE:
            # Return from subroutine
            if self.sp <= 0:
                raise RuntimeError("Stack underflow")
            self.sp -= 1
            self.pc = self.stack[self.sp]
        elif (opcode & 0xF000) == 0x1000:
            # 1nnn: Jump to address nnn
            self.pc = nnn
        elif (opcode & 0xF000) == 0x2000:
            # 2nnn: Call subroutine at nnn
            if self.sp >= 16:
                raise RuntimeError("Stack overflow")
            self.stack[self.sp] = self.pc
            self.sp += 1
            self.pc = nnn
        elif (opcode & 0xF000) == 0x3000:
            # 3xkk: Skip next if Vx == kk
            if self.V[x] == nn:
                self.pc += 2
        elif (opcode & 0xF000) == 0x4000:
            # 4xkk: Skip next if Vx != kk
            if self.V[x] != nn:
                self.pc += 2
        elif (opcode & 0xF000) == 0x5000:
            # 5xy0: Skip next if Vx == Vy
            if self.V[x] == self.V[y]:
                self.pc += 2
        elif (opcode & 0xF000) == 0x6000:
            # 6xkk: Set Vx = kk
            self.V[x] = nn
        elif (opcode & 0xF000) == 0x7000:
            # 7xkk: Add kk to Vx
            self.V[x] = (self.V[x] + nn) & 0xFF
        elif (opcode & 0xF000) == 0x8000:
            # Arithmetic and logic operations
            if n == 0x0:
                # 8xy0: Set Vx = Vy
                self.V[x] = self.V[y]
            elif n == 0x1:
                # 8xy1: Vx |= Vy
                self.V[x] |= self.V[y]
            elif n == 0x2:
                # 8xy2: Vx &= Vy
                self.V[x] &= self.V[y]
            elif n == 0x3:
                # 8xy3: Vx ^= Vy
                self.V[x] ^= self.V[y]
            elif n == 0x4:
                # 8xy4: Vx += Vy (set VF = carry)
                result = self.V[x] + self.V[y]
                self.V[0xF] = 1 if result > 0xFF else 0
                self.V[x] = result & 0xFF
            elif n == 0x5:
                # 8xy5: Vx -= Vy (set VF = not borrow)
                self.V[0xF] = 1 if self.V[x] >= self.V[y] else 0
                self.V[x] = (self.V[x] - self.V[y]) & 0xFF
            elif n == 0x6:
                # 8xy6: Vx >>= 1 (set VF = LSB)
                self.V[0xF] = self.V[x] & 1
                self.V[x] >>= 1
            elif n == 0x7:
                # 8xy7: Vx = Vy - Vx (set VF = not borrow)
                self.V[0xF] = 1 if self.V[y] >= self.V[x] else 0
                self.V[x] = (self.V[y] - self.V[x]) & 0xFF
            elif n == 0xE:
                # 8xyE: Vx <<= 1 (set VF = MSB)
                self.V[0xF] = (self.V[x] >> 7) & 1
                self.V[x] = (self.V[x] << 1) & 0xFF
        elif (opcode & 0xF000) == 0x9000:
            # 9xy0: Skip next if Vx != Vy
            if self.V[x] != self.V[y]:
                self.pc += 2
        elif (opcode & 0xF000) == 0xA000:
            # Annn: Set I = nnn
            self.I = nnn
        elif (opcode & 0xF000) == 0xB000:
            # Bnnn: Jump to nnn + V0
            self.pc = nnn + self.V[0]
        elif (opcode & 0xF000) == 0xC000:
            # Cxkk: Vx = random & kk
            self.V[x] = random.randint(0, 255) & nn
        elif (opcode & 0xF000) == 0xD000:
            # Dxyn: Draw sprite at (Vx, Vy) with height n
            x_pos = self.V[x] % 64
            y_pos = self.V[y] % 32
            self.V[0xF] = 0
            for row in range(n):
                if y_pos + row >= 32:
                    break
                sprite_byte = self.memory[self.I + row]
                for col in range(8):
                    if x_pos + col >= 64:
                        break
                    pixel = (sprite_byte >> (7 - col)) & 1
                    if pixel:
                        if self.display[y_pos + row][x_pos + col] == 1:
                            self.V[0xF] = 1  # Collision
                        self.display[y_pos + row][x_pos + col] ^= 1
            self.draw_flag = True
        elif (opcode & 0xF000) == 0xE000:
            # Ex9E: Skip if key pressed
            if (opcode & 0x00FF) == 0x9E:
                if self.keys[self.V[x]]:
                    self.pc += 2
            # ExA1: Skip if key not pressed
            elif (opcode & 0x00FF) == 0xA1:
                if not self.keys[self.V[x]]:
                    self.pc += 2
        elif (opcode & 0xF000) == 0xF000:
            # Fx07: Set Vx = delay_timer
            if nn == 0x07:
                self.V[x] = self.delay_timer
            # Fx0A: Wait for a key press (store in Vx)
            elif nn == 0x0A:
                self.waiting_key = True
                self.waiting_register = x
                self.pc -= 2  # Re‑fetch this instruction until key pressed
            # Fx15: Set delay_timer = Vx
            elif nn == 0x15:
                self.delay_timer = self.V[x]
            # Fx18: Set sound_timer = Vx
            elif nn == 0x18:
                self.sound_timer = self.V[x]
            # Fx1E: Add Vx to I
            elif nn == 0x1E:
                self.I = (self.I + self.V[x]) & 0xFFFF
            # Fx29: Set I = sprite address for digit Vx
            elif nn == 0x29:
                self.I = self.font_base + (self.V[x] * 5)
            # Fx33: Store BCD of Vx at I, I+1, I+2
            elif nn == 0x33:
                value = self.V[x]
                self.memory[self.I] = value // 100
                self.memory[self.I + 1] = (value // 10) % 10
                self.memory[self.I + 2] = value % 10
            # Fx55: Store V0..Vx in memory starting at I
            elif nn == 0x55:
                for i in range(x + 1):
                    self.memory[self.I + i] = self.V[i]
                # Some implementations advance I; we follow original spec (I unchanged)
            # Fx65: Load V0..Vx from memory starting at I
            elif nn == 0x65:
                for i in range(x + 1):
                    self.V[i] = self.memory[self.I + i]
                # I unchanged

# ---------------------------
# GUI with tkinter
# ---------------------------
class ACHoldingChip8:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Chip8emu by a.c")
        self.window.geometry("800x500")
        self.window.resizable(True, True)
        self.window.configure(bg=UI_BG)

        # Chip‑8 core
        self.chip8 = Chip8()

        # Display scaling (original: 64x32, we'll scale by factor)
        self.display_scale = DoubleVar(value=8)   # 8 -> 512x256 canvas
        self.display_canvas = None
        self.display_width = 64
        self.display_height = 32

        # Volume control (0-100) – for beep simulation
        self.volume = IntVar(value=50)
        self.speed_multiplier = DoubleVar(value=1.0)
        self._saved_state = None

        # Key mapping (Chip‑8 hex keypad → keyboard keys)
        # Default mapping: 1 2 3 C → 1 2 3 4
        #                4 5 6 D → Q W E R
        #                7 8 9 E → A S D F
        #                A 0 B F → Z X C V
        self.key_map = {
            '1': 0x1, '2': 0x2, '3': 0x3, '4': 0xC,
            'q': 0x4, 'w': 0x5, 'e': 0x6, 'r': 0xD,
            'a': 0x7, 's': 0x8, 'd': 0x9, 'f': 0xE,
            'z': 0xA, 'x': 0x0, 'c': 0xB, 'v': 0xF
        }
        # Reverse mapping for UI
        self.key_map_rev = {v: k for k, v in self.key_map.items()}

        self.setup_gui()

        # Timing model:
        # - CPU executes ~540 instructions/sec (9 cycles per 60 Hz frame)
        # - Timers decrement at exactly 60 Hz, independent of CPU cycle rate
        self.running = True
        self.frame_interval_ms = 1000 // 60
        self.cycles_per_frame = 9
        self.timer_interval = 1.0 / 60.0
        self._last_timer_tick = time.perf_counter()
        self._beep_active = False
        self.window.after(0, self.emulation_loop)

        # Key bindings
        self.bind_keys()

        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_gui(self):
        self.setup_style()

        # Menu bar
        menubar = tk.Menu(self.window)
        self.window.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open ROM...", command=self.open_rom)
        file_menu.add_command(label="Save State", command=self.save_state)
        file_menu.add_command(label="Load State", command=self.load_state)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # Controls menu
        controls_menu = tk.Menu(menubar, tearoff=False)
        controls_menu.add_command(label="Settings", command=self.show_controls)
        controls_menu.add_command(label="Debug Registers", command=self.show_registers)
        menubar.add_cascade(label="Controls", menu=controls_menu)

        # About menu
        about_menu = tk.Menu(menubar, tearoff=False)
        about_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="About", menu=about_menu)

        # Main frame
        main_frame = tk.Frame(self.window, bg=UI_BG)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Canvas for display (will be created later)
        self.create_display_canvas()

        # Status bar (optional)
        self.status_var = tk.StringVar()
        self.status_var.set("No ROM loaded")
        status_bar = tk.Label(
            self.window,
            textvariable=self.status_var,
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W,
            bg=UI_PANEL,
            fg=UI_TEXT,
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def setup_style(self):
        style = ttk.Style(self.window)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=UI_BG)
        style.configure("TLabel", background=UI_BG, foreground=UI_TEXT)
        style.configure("TLabelFrame", background=UI_BG, foreground=UI_TEXT)
        style.configure("TLabelFrame.Label", background=UI_BG, foreground=UI_TEXT)
        style.configure("TButton", background=UI_PANEL, foreground=UI_TEXT)
        style.configure(
            "TScale",
            background=UI_BG,
            troughcolor=UI_PANEL,
        )
        style.configure("TEntry", fieldbackground=UI_PANEL, foreground=UI_TEXT)

    def create_display_canvas(self):
        if self.display_canvas:
            self.display_canvas.destroy()
        scale = self.display_scale.get()
        width = int(self.display_width * scale)
        height = int(self.display_height * scale)
        self.display_canvas = tk.Canvas(
            self.window,
            width=width,
            height=height,
            bg=SCREEN_BG,
            highlightthickness=2,
            highlightbackground=UI_PANEL,
        )
        self.display_canvas.pack(pady=10, expand=True, fill=tk.BOTH)

    def draw_display(self):
        """Redraw the canvas from the Chip‑8 display buffer."""
        if not self.display_canvas:
            return
        scale = self.display_scale.get()
        width = self.display_width
        height = self.display_height
        self.display_canvas.delete("all")
        for y in range(height):
            for x in range(width):
                if self.chip8.display[y][x]:
                    x1 = x * scale
                    y1 = y * scale
                    x2 = x1 + scale
                    y2 = y1 + scale
                    self.display_canvas.create_rectangle(x1, y1, x2, y2, fill=SCREEN_ON, outline="")

    def emulation_loop(self):
        """Main emulation loop: execute instructions, handle timers, redraw."""
        if not self.running:
            return

        # Execute ~540 instructions per second (9 * 60 Hz), scaled by speed multiplier
        cycles = max(1, int(self.cycles_per_frame * self.speed_multiplier.get()))
        for _ in range(cycles):
            self.chip8.emulate_cycle()

        # Timers are hardware-timed at 60 Hz (independent of CPU instruction rate)
        now = time.perf_counter()
        elapsed = now - self._last_timer_tick
        if elapsed >= self.timer_interval:
            ticks = int(elapsed / self.timer_interval)
            self._last_timer_tick += ticks * self.timer_interval
            for _ in range(ticks):
                if self.chip8.delay_timer > 0:
                    self.chip8.delay_timer -= 1
                if self.chip8.sound_timer > 0:
                    self.chip8.sound_timer -= 1

        # Keep tone active as long as sound_timer > 0
        if self.chip8.sound_timer > 0 and not self._beep_active:
            self.start_beep()
        elif self.chip8.sound_timer == 0 and self._beep_active:
            self.stop_beep()

        # Redraw if needed
        if self.chip8.draw_flag:
            self.draw_display()
            self.chip8.draw_flag = False

        # Schedule next cycle
        self.window.after(self.frame_interval_ms, self.emulation_loop)

    def start_beep(self):
        """Start continuous tone while sound_timer > 0."""
        if self.volume.get() <= 0:
            return
        self._beep_active = True
        try:
            import winsound
            # Loop a system alias asynchronously until stop_beep() is called.
            winsound.PlaySound(
                "SystemAsterisk",
                winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_LOOP
            )
        except Exception:
            # Fallback: one bell pulse when tone starts.
            sys.stdout.write("\a")
            sys.stdout.flush()

    def stop_beep(self):
        """Stop continuous tone."""
        if not self._beep_active:
            return
        self._beep_active = False
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_ASYNC)
        except Exception:
            pass

    def open_rom(self):
        file_path = filedialog.askopenfilename(
            title="Open Chip‑8 ROM",
            filetypes=[("Chip‑8 ROMs", "*.ch8 *.rom *.bin"), ("All files", "*.*")]
        )
        if file_path:
            try:
                self.chip8.load_rom(file_path)
                self.status_var.set(f"Loaded: {os.path.basename(file_path)}")
                self.chip8.draw_flag = True   # Force redraw
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load ROM:\n{e}")

    def save_state(self):
        self._saved_state = self.chip8.save_state()
        self.status_var.set("State saved")

    def load_state(self):
        if not self._saved_state:
            messagebox.showinfo("Load State", "No saved state yet.")
            return
        self.chip8.load_state(self._saved_state)
        self.chip8.draw_flag = True
        self.status_var.set("State loaded")

    def show_controls(self):
        """Window for settings: display scaling, volume, key mapping."""
        ctrl_win = tk.Toplevel(self.window)
        ctrl_win.title("Controls")
        ctrl_win.geometry("400x400")
        ctrl_win.resizable(False, False)
        ctrl_win.configure(bg=UI_BG)

        # Display scaling
        scale_frame = ttk.LabelFrame(ctrl_win, text="Display Scaling")
        scale_frame.pack(fill=tk.X, padx=10, pady=5)
        scale_slider = ttk.Scale(scale_frame, from_=2, to=16, variable=self.display_scale, orient=tk.HORIZONTAL)
        scale_slider.pack(fill=tk.X, padx=10, pady=5)
        scale_label = ttk.Label(scale_frame, textvariable=self.display_scale)
        scale_label.pack()
        # Update canvas when scale changes
        def update_scale(*args):
            self.create_display_canvas()
            self.draw_display()
        self.display_scale.trace_add("write", update_scale)

        # Volume
        vol_frame = ttk.LabelFrame(ctrl_win, text="Volume")
        vol_frame.pack(fill=tk.X, padx=10, pady=5)
        vol_slider = ttk.Scale(vol_frame, from_=0, to=100, variable=self.volume, orient=tk.HORIZONTAL)
        vol_slider.pack(fill=tk.X, padx=10, pady=5)
        vol_label = ttk.Label(vol_frame, textvariable=self.volume)
        vol_label.pack()

        # Speed multiplier
        speed_frame = ttk.LabelFrame(ctrl_win, text="Speed Multiplier")
        speed_frame.pack(fill=tk.X, padx=10, pady=5)
        speed_slider = ttk.Scale(speed_frame, from_=0.25, to=4.0, variable=self.speed_multiplier, orient=tk.HORIZONTAL)
        speed_slider.pack(fill=tk.X, padx=10, pady=5)
        speed_label = ttk.Label(speed_frame, textvariable=self.speed_multiplier)
        speed_label.pack()

        # Key mapping
        key_frame = ttk.LabelFrame(ctrl_win, text="Key Mapping (Chip‑8 → Keyboard)")
        key_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Create a table for all 16 keys
        rows = 4
        cols = 4
        for chip_key in range(16):
            row = chip_key // cols
            col = chip_key % cols
            current_key = self.key_map_rev.get(chip_key, "?")
            label = ttk.Label(key_frame, text=f"Key {chip_key:X}:")
            entry = ttk.Entry(key_frame, width=5)
            entry.insert(0, current_key)
            label.grid(row=row*2, column=col, padx=5, pady=2, sticky=tk.W)
            entry.grid(row=row*2+1, column=col, padx=5, pady=2)
            # Store entry for later retrieval
            setattr(ctrl_win, f"key_entry_{chip_key}", entry)

        def save_key_mapping():
            new_map = {}
            for chip_key in range(16):
                entry = getattr(ctrl_win, f"key_entry_{chip_key}")
                key = entry.get().strip().lower()
                if key:
                    new_map[key] = chip_key
            if len(new_map) == 16:
                self.key_map = new_map
                self.key_map_rev = {v: k for k, v in new_map.items()}
                self.bind_keys()   # Re‑bind keys
                messagebox.showinfo("Success", "Key mapping saved.")
            else:
                messagebox.showerror("Error", "Please assign all 16 keys (duplicates or missing).")

        save_btn = ttk.Button(ctrl_win, text="Save", command=save_key_mapping)
        save_btn.pack(pady=10)

    def show_registers(self):
        """Debug register viewer for development."""
        dbg_win = tk.Toplevel(self.window)
        dbg_win.title("Debug Registers")
        dbg_win.geometry("360x320")
        dbg_win.resizable(False, False)
        dbg_win.configure(bg=UI_BG)

        lines = [f"V{i:X}: {self.chip8.V[i]:02X}" for i in range(16)]
        reg_text = "  ".join(lines[0:4]) + "\n" + "  ".join(lines[4:8]) + "\n" + "  ".join(lines[8:12]) + "\n" + "  ".join(lines[12:16])
        summary = (
            f"{reg_text}\n\n"
            f"I: {self.chip8.I:04X}\n"
            f"PC: {self.chip8.pc:04X}\n"
            f"SP: {self.chip8.sp:02X}\n"
            f"DT: {self.chip8.delay_timer:02X}\n"
            f"ST: {self.chip8.sound_timer:02X}"
        )
        lbl = tk.Label(dbg_win, text=summary, justify=tk.LEFT, font=("Courier", 11), bg=UI_BG, fg=UI_TEXT)
        lbl.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def bind_keys(self):
        """Bind keyboard events using the current key map."""
        # Unbind previous keys
        if hasattr(self, "_bound_keys"):
            for key in self._bound_keys:
                self.window.unbind(f"<KeyPress-{key}>")
                self.window.unbind(f"<KeyRelease-{key}>")

        self._bound_keys = list(self.key_map.keys())

        # Bind new keys
        for key, chip_key in self.key_map.items():
            self.window.bind(f"<KeyPress-{key}>", lambda e, k=chip_key: self.key_press(k))
            self.window.bind(f"<KeyRelease-{key}>", lambda e, k=chip_key: self.key_release(k))

    def key_press(self, chip_key):
        self.chip8.keys[chip_key] = 1

    def key_release(self, chip_key):
        self.chip8.keys[chip_key] = 0

    def show_about(self):
        about_win = tk.Toplevel(self.window)
        about_win.title("About Chip8emu by a.c")
        about_win.geometry("300x200")
        about_win.resizable(False, False)
        about_win.configure(bg=UI_BG)

        title = tk.Label(
            about_win,
            text="Chip8emu by a.c\nChip‑8 Emulator",
            font=("Arial", 14, "bold"),
            bg=UI_BG,
            fg=UI_TEXT,
        )
        title.pack(pady=10)

        version = tk.Label(about_win, text="Version 1.0", bg=UI_BG, fg=UI_TEXT)
        version.pack()

        credits = tk.Label(
            about_win,
            text="© 2026 a.c\nChip‑8 core written from scratch.\nUsing tkinter for GUI.",
            bg=UI_BG,
            fg=UI_TEXT,
        )
        credits.pack(pady=10)

        close_btn = ttk.Button(about_win, text="Close", command=about_win.destroy)
        close_btn.pack(pady=5)

    def on_close(self):
        self.running = False
        self.stop_beep()
        self.window.destroy()

    def run(self):
        self.window.mainloop()


if __name__ == "__main__":
    emu = ACHoldingChip8()
    emu.run()
