#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pynput>=1.7.6",
# ]
# ///
"""
Keyboard & Mouse Rhythm Capture - Global input recorder for music production.

Captures keyboard press/release timing and mouse/trackpad gestures globally
(even when not focused) and exports to MIDI, JSON, or CSV for use in DAWs.

Supported inputs:
    - Keyboard: Space key and all other keys (tracked separately)
    - Mouse: Left click, right click, scroll up/down

Usage:
    uv run capture.py

Requirements:
    - macOS: Grant Accessibility permissions in System Preferences > Privacy & Security
"""

import time
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Literal

from pynput import keyboard, mouse


@dataclass
class InputEvent:
    """A single input event with high-resolution timing."""
    event_type: Literal["keydown", "keyup", "click", "scroll"]
    input_type: Literal["space", "other", "left_click", "right_click", "scroll_up", "scroll_down"]
    time_ms: float
    key_name: str = ""


# Alias for backwards compatibility
KeyEvent = InputEvent


@dataclass
class RecordingSession:
    """Holds all events from a recording session."""
    events: list[InputEvent] = field(default_factory=list)
    start_time: float = 0.0
    # Keyboard state
    space_down: bool = False
    other_down: bool = False
    # Mouse button state
    left_click_down: bool = False
    right_click_down: bool = False

    def add_event(self, event_type: str, input_type: str, key_name: str = ""):
        time_ms = (time.perf_counter() - self.start_time) * 1000
        self.events.append(InputEvent(event_type, input_type, time_ms, key_name))

    def get_notes(self) -> list[dict]:
        """Convert events to note on/off pairs."""
        notes = []
        # Track pending note-on events for sustained inputs (keys and clicks)
        pending = {"space": None, "other": None, "left_click": None, "right_click": None}

        for event in self.events:
            if event.event_type == "keydown":
                pending[event.input_type] = event.time_ms
            elif event.event_type == "keyup" and pending.get(event.input_type) is not None:
                notes.append({
                    "input_type": event.input_type,
                    "start": pending[event.input_type],
                    "end": event.time_ms
                })
                pending[event.input_type] = None
            elif event.event_type == "click":
                # Click events (mouse button press/release)
                if event.input_type in pending:
                    if pending[event.input_type] is None:
                        # Button pressed
                        pending[event.input_type] = event.time_ms
                    else:
                        # Button released
                        notes.append({
                            "input_type": event.input_type,
                            "start": pending[event.input_type],
                            "end": event.time_ms
                        })
                        pending[event.input_type] = None
            elif event.event_type == "scroll":
                # Scroll events are instantaneous - create short notes
                notes.append({
                    "input_type": event.input_type,
                    "start": event.time_ms,
                    "end": event.time_ms + 50  # 50ms duration for scroll ticks
                })

        # Close any still-held notes
        final_time = self.events[-1].time_ms if self.events else 0
        for input_type, start in pending.items():
            if start is not None:
                notes.append({"input_type": input_type, "start": start, "end": final_time})

        return sorted(notes, key=lambda n: n["start"])


def encode_vlq(value: int) -> bytes:
    """Encode integer as MIDI variable-length quantity."""
    result = []
    result.append(value & 0x7F)
    value >>= 7
    while value > 0:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(result))


def generate_midi(session: RecordingSession, tempo: int = 120,
                  other_note: int = 38, space_note: int = 36,
                  velocity: int = 100,
                  left_click_note: int = 40, right_click_note: int = 41,
                  scroll_up_note: int = 42, scroll_down_note: int = 44) -> bytes:
    """Generate a MIDI file from the recording session.

    Default note mappings (General MIDI drum kit):
        - Space key: 36 (C1 - Bass Drum)
        - Other keys: 38 (D1 - Snare)
        - Left click: 40 (E1 - Electric Snare)
        - Right click: 41 (F1 - Low Floor Tom)
        - Scroll up: 42 (F#1 - Closed Hi-Hat)
        - Scroll down: 44 (G#1 - Pedal Hi-Hat)
    """
    TICKS_PER_BEAT = 480
    MS_PER_BEAT = 60000 / tempo

    def ms_to_ticks(ms: float) -> int:
        return round((ms / MS_PER_BEAT) * TICKS_PER_BEAT)

    def build_track(track_notes: list[dict], track_name: str, note_num: int) -> bytes:
        data = bytearray()

        # Track name meta event
        name_bytes = track_name.encode('utf-8')
        data.extend(b'\x00\xff\x03')
        data.append(len(name_bytes))
        data.extend(name_bytes)

        # Build MIDI events
        midi_events = []
        for note in track_notes:
            midi_events.append({"time": ms_to_ticks(note["start"]), "type": "on"})
            midi_events.append({"time": ms_to_ticks(note["end"]), "type": "off"})

        midi_events.sort(key=lambda e: e["time"])

        # Convert to delta times
        last_time = 0
        for event in midi_events:
            delta = event["time"] - last_time
            data.extend(encode_vlq(delta))

            if event["type"] == "on":
                data.extend(bytes([0x90, note_num, velocity]))  # Note on
            else:
                data.extend(bytes([0x80, note_num, 0]))  # Note off

            last_time = event["time"]

        # End of track
        data.extend(b'\x00\xff\x2f\x00')
        return bytes(data)

    def build_tempo_track() -> bytes:
        data = bytearray()

        # Track name
        name = b'Tempo'
        data.extend(b'\x00\xff\x03')
        data.append(len(name))
        data.extend(name)

        # Tempo meta event
        us_per_beat = round(60_000_000 / tempo)
        data.extend(b'\x00\xff\x51\x03')
        data.extend(struct.pack('>I', us_per_beat)[1:])  # 3 bytes, big endian

        # Time signature 4/4
        data.extend(b'\x00\xff\x58\x04\x04\x02\x18\x08')

        # End of track
        data.extend(b'\x00\xff\x2f\x00')
        return bytes(data)

    notes = session.get_notes()
    # Keyboard events
    other_notes = [n for n in notes if n["input_type"] == "other"]
    space_notes = [n for n in notes if n["input_type"] == "space"]
    # Mouse events
    left_click_notes = [n for n in notes if n["input_type"] == "left_click"]
    right_click_notes = [n for n in notes if n["input_type"] == "right_click"]
    scroll_up_notes = [n for n in notes if n["input_type"] == "scroll_up"]
    scroll_down_notes = [n for n in notes if n["input_type"] == "scroll_down"]

    tempo_track = build_tempo_track()
    other_track = build_track(other_notes, "Other Keys", other_note)
    space_track = build_track(space_notes, "Space Key", space_note)
    left_click_track = build_track(left_click_notes, "Left Click", left_click_note)
    right_click_track = build_track(right_click_notes, "Right Click", right_click_note)
    scroll_up_track = build_track(scroll_up_notes, "Scroll Up", scroll_up_note)
    scroll_down_track = build_track(scroll_down_notes, "Scroll Down", scroll_down_note)

    tracks = [tempo_track, other_track, space_track,
              left_click_track, right_click_track, scroll_up_track, scroll_down_track]

    # MIDI header
    header = bytearray(b'MThd')
    header.extend(struct.pack('>I', 6))  # Header length
    header.extend(struct.pack('>H', 1))  # Format 1
    header.extend(struct.pack('>H', len(tracks)))  # Number of tracks
    header.extend(struct.pack('>H', TICKS_PER_BEAT))  # Ticks per beat

    # Track chunks
    midi_data = bytearray(header)
    for track in tracks:
        midi_data.extend(b'MTrk')
        midi_data.extend(struct.pack('>I', len(track)))
        midi_data.extend(track)

    return bytes(midi_data)


def export_json(session: RecordingSession, filepath: Path, **settings):
    """Export session to JSON format."""
    data = {
        "recorded_at": datetime.now().isoformat(),
        "settings": settings,
        "events": [
            {
                "type": e.event_type,
                "input_type": e.input_type,
                "time_ms": round(e.time_ms, 3),
                "key": e.key_name
            }
            for e in session.events
        ]
    }
    filepath.write_text(json.dumps(data, indent=2))


def export_csv(session: RecordingSession, filepath: Path):
    """Export session to CSV format."""
    lines = ["type,input_type,time_ms,key"]
    for e in session.events:
        lines.append(f"{e.event_type},{e.input_type},{e.time_ms:.3f},{e.key_name}")
    filepath.write_text("\n".join(lines))


class RhythmCapture:
    """Global keyboard and mouse rhythm capture with terminal UI."""

    # Triple-tap ESC settings
    ESC_TAP_COUNT = 3
    ESC_TAP_WINDOW = 1.0  # seconds

    def __init__(self):
        self.session = RecordingSession()
        self.is_recording = False
        self.should_exit = False
        self.esc_tap_times: list[float] = []
        # Mouse listeners
        self.mouse_listener = None

    def on_press(self, key):
        if not self.is_recording:
            return

        try:
            key_name = key.char if hasattr(key, 'char') and key.char else str(key)
        except AttributeError:
            key_name = str(key)

        is_space = key == keyboard.Key.space
        key_type = "space" if is_space else "other"

        # Ignore key repeat
        if is_space and self.session.space_down:
            return
        if not is_space and self.session.other_down:
            return

        if is_space:
            self.session.space_down = True
        else:
            self.session.other_down = True

        self.session.add_event("keydown", key_type, key_name)
        self._print_status()

    def _check_esc_triple_tap(self) -> bool:
        """Check if ESC was triple-tapped within the time window."""
        now = time.perf_counter()
        self.esc_tap_times.append(now)

        # Keep only taps within the window
        self.esc_tap_times = [t for t in self.esc_tap_times if now - t <= self.ESC_TAP_WINDOW]

        if len(self.esc_tap_times) >= self.ESC_TAP_COUNT:
            self.esc_tap_times.clear()
            return True
        return False

    def on_release(self, key):
        # Check for triple-tap ESC to stop
        if key == keyboard.Key.esc:
            if self._check_esc_triple_tap():
                if self.is_recording:
                    self.stop_recording()
                else:
                    self.should_exit = True
                return False  # Stop listener
            return  # Continue listening

        if not self.is_recording:
            return

        try:
            key_name = key.char if hasattr(key, 'char') and key.char else str(key)
        except AttributeError:
            key_name = str(key)

        is_space = key == keyboard.Key.space
        key_type = "space" if is_space else "other"

        if is_space:
            if not self.session.space_down:
                return
            self.session.space_down = False
        else:
            if not self.session.other_down:
                return
            self.session.other_down = False

        self.session.add_event("keyup", key_type, key_name)
        self._print_status()

    def on_click(self, x, y, button, pressed):
        """Handle mouse click events."""
        if not self.is_recording:
            return

        # Determine click type
        if button == mouse.Button.left:
            input_type = "left_click"
            if pressed:
                if self.session.left_click_down:
                    return  # Ignore repeat
                self.session.left_click_down = True
            else:
                if not self.session.left_click_down:
                    return
                self.session.left_click_down = False
        elif button == mouse.Button.right:
            input_type = "right_click"
            if pressed:
                if self.session.right_click_down:
                    return  # Ignore repeat
                self.session.right_click_down = True
            else:
                if not self.session.right_click_down:
                    return
                self.session.right_click_down = False
        else:
            return  # Ignore middle click and other buttons

        self.session.add_event("click", input_type, f"{button.name}")
        self._print_status()

    def on_scroll(self, x, y, dx, dy):
        """Handle mouse scroll events."""
        if not self.is_recording:
            return

        # Vertical scroll
        if dy > 0:
            input_type = "scroll_up"
        elif dy < 0:
            input_type = "scroll_down"
        else:
            return  # No vertical scroll

        self.session.add_event("scroll", input_type, f"dy={dy}")
        self._print_status()

    def _print_status(self):
        """Print current status."""
        # Count keyboard events
        keydowns = [e for e in self.session.events if e.event_type == "keydown"]
        space_count = len([e for e in keydowns if e.input_type == "space"])
        other_count = len([e for e in keydowns if e.input_type == "other"])

        # Count mouse events
        click_events = [e for e in self.session.events if e.event_type == "click"]
        left_click_count = len([e for e in click_events if e.input_type == "left_click"]) // 2  # pairs
        right_click_count = len([e for e in click_events if e.input_type == "right_click"]) // 2

        scroll_events = [e for e in self.session.events if e.event_type == "scroll"]
        scroll_up_count = len([e for e in scroll_events if e.input_type == "scroll_up"])
        scroll_down_count = len([e for e in scroll_events if e.input_type == "scroll_down"])

        elapsed = (time.perf_counter() - self.session.start_time) if self.session.start_time else 0

        # Keyboard indicators
        space_indicator = "[SPACE]" if self.session.space_down else "[space]"
        other_indicator = "[OTHER]" if self.session.other_down else "[other]"

        # Mouse indicators
        lclick_indicator = "[LCLK]" if self.session.left_click_down else "[lclk]"
        rclick_indicator = "[RCLK]" if self.session.right_click_down else "[rclk]"

        # Build status line
        status = (
            f"\r  {other_indicator}{other_count:3d} {space_indicator}{space_count:3d} | "
            f"{lclick_indicator}{left_click_count:3d} {rclick_indicator}{right_click_count:3d} | "
            f"scroll:{scroll_up_count:2d}up/{scroll_down_count:2d}dn | "
            f"{elapsed:6.2f}s  "
        )
        print(status, end="", flush=True)

    def start_recording(self):
        """Start a new recording session."""
        self.session = RecordingSession()
        self.session.start_time = time.perf_counter()
        self.is_recording = True
        print("\n  Recording started! Use keyboard and mouse to capture rhythm...")
        print("  Tracked: keys, left/right clicks, scroll up/down")
        print("  Triple-tap ESC to stop recording.\n")
        self._print_status()

    def stop_recording(self):
        """Stop the current recording."""
        self.is_recording = False

        # Close any held keyboard keys
        if self.session.space_down:
            self.session.add_event("keyup", "space")
            self.session.space_down = False
        if self.session.other_down:
            self.session.add_event("keyup", "other")
            self.session.other_down = False

        # Close any held mouse buttons
        if self.session.left_click_down:
            self.session.add_event("click", "left_click")
            self.session.left_click_down = False
        if self.session.right_click_down:
            self.session.add_event("click", "right_click")
            self.session.right_click_down = False

        # Count events by type
        keydowns = [e for e in self.session.events if e.event_type == "keydown"]
        clicks = [e for e in self.session.events if e.event_type == "click"]
        scrolls = [e for e in self.session.events if e.event_type == "scroll"]
        total = len(keydowns) + len(clicks) // 2 + len(scrolls)
        print(f"\n\n  Recording stopped! Captured {total} events "
              f"({len(keydowns)} keys, {len(clicks)//2} clicks, {len(scrolls)} scrolls).")

    def export_files(self, tempo: int = 120, other_note: int = 38,
                     space_note: int = 36, velocity: int = 100,
                     left_click_note: int = 40, right_click_note: int = 41,
                     scroll_up_note: int = 42, scroll_down_note: int = 44):
        """Export the session to all formats."""
        if not self.session.events:
            print("  No events to export!")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"input-rhythm-{timestamp}"

        # Export MIDI
        midi_path = Path(f"{base_name}.mid")
        midi_data = generate_midi(
            self.session, tempo, other_note, space_note, velocity,
            left_click_note, right_click_note, scroll_up_note, scroll_down_note
        )
        midi_path.write_bytes(midi_data)
        print(f"  Exported: {midi_path}")

        # Export JSON
        json_path = Path(f"{base_name}.json")
        export_json(self.session, json_path,
                   tempo=tempo, other_note=other_note,
                   space_note=space_note, velocity=velocity,
                   left_click_note=left_click_note, right_click_note=right_click_note,
                   scroll_up_note=scroll_up_note, scroll_down_note=scroll_down_note)
        print(f"  Exported: {json_path}")

        # Export CSV
        csv_path = Path(f"{base_name}.csv")
        export_csv(self.session, csv_path)
        print(f"  Exported: {csv_path}")

        return midi_path


def get_int_input(prompt: str, default: int, min_val: int, max_val: int) -> int:
    """Get integer input with validation."""
    while True:
        try:
            value = input(f"  {prompt} [{default}]: ").strip()
            if not value:
                return default
            value = int(value)
            if min_val <= value <= max_val:
                return value
            print(f"    Please enter a value between {min_val} and {max_val}")
        except ValueError:
            print("    Please enter a valid number")


def main():
    print("\n" + "=" * 70)
    print("  KEYBOARD & MOUSE RHYTHM CAPTURE")
    print("  Capture global input events for music production")
    print("=" * 70)
    print("\n  Tracked inputs:")
    print("    - Keyboard: Space key (separate track) + all other keys")
    print("    - Mouse: Left click, right click, scroll up/down")
    print("  Timing resolution: ~0.1ms (using time.perf_counter)")
    print("\n  NOTE: On macOS, grant Accessibility permissions if prompted.")
    print("        System Preferences > Privacy & Security > Accessibility")

    capture = RhythmCapture()

    while True:
        print("\n" + "-" * 70)
        print("  Commands:")
        print("    [R] Start recording")
        print("    [E] Export last recording")
        print("    [S] Settings")
        print("    [Q] Quit")
        print("-" * 70)

        choice = input("\n  Enter command: ").strip().lower()

        if choice == 'r':
            capture.start_recording()

            # Start both keyboard and mouse listeners
            keyboard_listener = keyboard.Listener(
                on_press=capture.on_press,
                on_release=capture.on_release
            )
            mouse_listener = mouse.Listener(
                on_click=capture.on_click,
                on_scroll=capture.on_scroll
            )

            keyboard_listener.start()
            mouse_listener.start()

            # Wait for keyboard listener to stop (triple-tap ESC)
            keyboard_listener.join()

            # Stop mouse listener when keyboard listener stops
            mouse_listener.stop()

            if capture.should_exit:
                break

        elif choice == 'e':
            if not capture.session.events:
                print("\n  No recording to export. Record something first!")
                continue

            print("\n  Export Settings:")
            tempo = get_int_input("Tempo (BPM)", 120, 20, 300)

            print("\n  Keyboard MIDI notes (36=C1/Kick, 38=D1/Snare, 42=F#1/HiHat):")
            other_note = get_int_input("Other keys MIDI note", 38, 0, 127)
            space_note = get_int_input("Space key MIDI note", 36, 0, 127)

            print("\n  Mouse MIDI notes (40=E1, 41=F1, 42=F#1, 44=G#1):")
            left_click_note = get_int_input("Left click MIDI note", 40, 0, 127)
            right_click_note = get_int_input("Right click MIDI note", 41, 0, 127)
            scroll_up_note = get_int_input("Scroll up MIDI note", 42, 0, 127)
            scroll_down_note = get_int_input("Scroll down MIDI note", 44, 0, 127)

            velocity = get_int_input("\nVelocity", 100, 1, 127)

            print()
            capture.export_files(tempo, other_note, space_note, velocity,
                               left_click_note, right_click_note,
                               scroll_up_note, scroll_down_note)

        elif choice == 's':
            print("\n  Current settings are configured during export.")
            print("  Defaults:")
            print("    - Tempo: 120 BPM, Velocity: 100")
            print("    - Keyboard: Other=38(D1/Snare), Space=36(C1/Kick)")
            print("    - Mouse: LClick=40(E1), RClick=41(F1), ScrollUp=42(F#1), ScrollDn=44(G#1)")

        elif choice == 'q':
            print("\n  Goodbye!")
            break

        else:
            print("\n  Unknown command. Please enter R, E, S, or Q.")


if __name__ == "__main__":
    main()
