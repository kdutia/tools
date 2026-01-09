#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pynput>=1.7.6",
# ]
# ///
"""
Keyboard Rhythm Capture - Global keypress recorder for music production.

Captures keyboard press/release timing globally (even when not focused) and
exports to MIDI, JSON, or CSV for use in DAWs.

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

from pynput import keyboard


@dataclass
class KeyEvent:
    """A single key event with high-resolution timing."""
    event_type: Literal["keydown", "keyup"]
    key_type: Literal["space", "other"]
    time_ms: float
    key_name: str = ""


@dataclass
class RecordingSession:
    """Holds all events from a recording session."""
    events: list[KeyEvent] = field(default_factory=list)
    start_time: float = 0.0
    space_down: bool = False
    other_down: bool = False

    def add_event(self, event_type: str, key_type: str, key_name: str = ""):
        time_ms = (time.perf_counter() - self.start_time) * 1000
        self.events.append(KeyEvent(event_type, key_type, time_ms, key_name))

    def get_notes(self) -> list[dict]:
        """Convert events to note on/off pairs."""
        notes = []
        pending = {"space": None, "other": None}

        for event in self.events:
            if event.event_type == "keydown":
                pending[event.key_type] = event.time_ms
            elif event.event_type == "keyup" and pending[event.key_type] is not None:
                notes.append({
                    "key_type": event.key_type,
                    "start": pending[event.key_type],
                    "end": event.time_ms
                })
                pending[event.key_type] = None

        # Close any still-held notes
        final_time = self.events[-1].time_ms if self.events else 0
        for key_type, start in pending.items():
            if start is not None:
                notes.append({"key_type": key_type, "start": start, "end": final_time})

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
                  velocity: int = 100) -> bytes:
    """Generate a MIDI file from the recording session."""
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
    other_notes = [n for n in notes if n["key_type"] == "other"]
    space_notes = [n for n in notes if n["key_type"] == "space"]

    tempo_track = build_tempo_track()
    other_track = build_track(other_notes, "Other Keys", other_note)
    space_track = build_track(space_notes, "Space Key", space_note)

    tracks = [tempo_track, other_track, space_track]

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
                "key_type": e.key_type,
                "time_ms": round(e.time_ms, 3),
                "key": e.key_name
            }
            for e in session.events
        ]
    }
    filepath.write_text(json.dumps(data, indent=2))


def export_csv(session: RecordingSession, filepath: Path):
    """Export session to CSV format."""
    lines = ["type,key_type,time_ms,key"]
    for e in session.events:
        lines.append(f"{e.event_type},{e.key_type},{e.time_ms:.3f},{e.key_name}")
    filepath.write_text("\n".join(lines))


class RhythmCapture:
    """Global keyboard rhythm capture with terminal UI."""

    def __init__(self):
        self.session = RecordingSession()
        self.is_recording = False
        self.should_exit = False

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

    def on_release(self, key):
        # Check for stop key (Escape)
        if key == keyboard.Key.esc:
            if self.is_recording:
                self.stop_recording()
            else:
                self.should_exit = True
            return False  # Stop listener

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

    def _print_status(self):
        """Print current status."""
        keydowns = [e for e in self.session.events if e.event_type == "keydown"]
        space_count = len([e for e in keydowns if e.key_type == "space"])
        other_count = len([e for e in keydowns if e.key_type == "other"])

        elapsed = (time.perf_counter() - self.session.start_time) if self.session.start_time else 0

        space_indicator = "[SPACE]" if self.session.space_down else "[ space ]"
        other_indicator = "[OTHER]" if self.session.other_down else "[ other ]"

        print(f"\r  {other_indicator} {other_count:3d}  |  {space_indicator} {space_count:3d}  |  {elapsed:6.2f}s  ", end="", flush=True)

    def start_recording(self):
        """Start a new recording session."""
        self.session = RecordingSession()
        self.session.start_time = time.perf_counter()
        self.is_recording = True
        print("\n  Recording started! Press keys to capture rhythm...")
        print("  Press ESC to stop recording.\n")
        self._print_status()

    def stop_recording(self):
        """Stop the current recording."""
        self.is_recording = False

        # Close any held notes
        if self.session.space_down:
            self.session.add_event("keyup", "space")
            self.session.space_down = False
        if self.session.other_down:
            self.session.add_event("keyup", "other")
            self.session.other_down = False

        keydowns = [e for e in self.session.events if e.event_type == "keydown"]
        print(f"\n\n  Recording stopped! Captured {len(keydowns)} key events.")

    def export_files(self, tempo: int = 120, other_note: int = 38,
                     space_note: int = 36, velocity: int = 100):
        """Export the session to all formats."""
        if not self.session.events:
            print("  No events to export!")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"keyboard-rhythm-{timestamp}"

        # Export MIDI
        midi_path = Path(f"{base_name}.mid")
        midi_data = generate_midi(self.session, tempo, other_note, space_note, velocity)
        midi_path.write_bytes(midi_data)
        print(f"  Exported: {midi_path}")

        # Export JSON
        json_path = Path(f"{base_name}.json")
        export_json(self.session, json_path,
                   tempo=tempo, other_note=other_note,
                   space_note=space_note, velocity=velocity)
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
    print("\n" + "=" * 60)
    print("  KEYBOARD RHYTHM CAPTURE")
    print("  Capture global keypresses for music production")
    print("=" * 60)
    print("\n  Space key is tracked separately from all other keys.")
    print("  Timing resolution: ~0.1ms (using time.perf_counter)")
    print("\n  NOTE: On macOS, grant Accessibility permissions if prompted.")
    print("        System Preferences > Privacy & Security > Accessibility")

    capture = RhythmCapture()

    while True:
        print("\n" + "-" * 60)
        print("  Commands:")
        print("    [R] Start recording")
        print("    [E] Export last recording")
        print("    [S] Settings")
        print("    [Q] Quit")
        print("-" * 60)

        choice = input("\n  Enter command: ").strip().lower()

        if choice == 'r':
            capture.start_recording()

            # Start listener - blocks until ESC
            with keyboard.Listener(
                on_press=capture.on_press,
                on_release=capture.on_release
            ) as listener:
                listener.join()

            if capture.should_exit:
                break

        elif choice == 'e':
            if not capture.session.events:
                print("\n  No recording to export. Record something first!")
                continue

            print("\n  Export Settings:")
            tempo = get_int_input("Tempo (BPM)", 120, 20, 300)

            print("\n  Note options: 36=C1(Kick), 38=D1(Snare), 42=F#1(HiHat), 60=C3")
            other_note = get_int_input("Other keys MIDI note", 38, 0, 127)
            space_note = get_int_input("Space key MIDI note", 36, 0, 127)
            velocity = get_int_input("Velocity", 100, 1, 127)

            print()
            capture.export_files(tempo, other_note, space_note, velocity)

        elif choice == 's':
            print("\n  Current settings are configured during export.")
            print("  Default: 120 BPM, Other=D1(38), Space=C1(36), Velocity=100")

        elif choice == 'q':
            print("\n  Goodbye!")
            break

        else:
            print("\n  Unknown command. Please enter R, E, S, or Q.")


if __name__ == "__main__":
    main()
