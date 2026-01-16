# Rational Intonation Explorer - SuperCollider

A SuperCollider implementation of the rational intonation explorer for working with just intonation systems.

## Quick Start

1. Connect your Michigan XVI via USB
2. Open SuperCollider
3. Boot the server: `s.boot;`
4. Open and evaluate `RationalIntonationExplorer.scd` (Cmd+Enter / Ctrl+Enter on whole file)

## Michigan XVI Connection

### macOS
The Michigan XVI should appear automatically. If not:
```supercollider
MIDIClient.init;
MIDIClient.sources;  // Check if XVI is listed
MIDIIn.connectAll;
```

### Linux
You may need to check your ALSA/JACK MIDI setup:
```bash
aconnect -l  # List MIDI devices
```

In SuperCollider:
```supercollider
MIDIClient.init;
MIDIClient.sources;
```

If the XVI doesn't appear, ensure you have permissions for `/dev/midi*` devices (add yourself to the `audio` group).

### Windows
The XVI should appear via MME/DirectMusic. Run `MIDIClient.init;` and check sources.

## Michigan XVI Fader Mapping

| Fader | CC  | Function            | Range           |
|-------|-----|---------------------|-----------------|
| 1     | 0   | Master Amplitude    | 0.0 - 1.0       |
| 2     | 1   | Root Frequency      | 20 - 2000 Hz    |
| 3     | 2   | Fade Time           | 0 - 5 seconds   |
| 4-11  | 3-10| Voice Amplitudes    | 0.0 - 1.0       |
| 12-16 | 11-15| Voice Pans         | L (-1) to R (+1)|

If your XVI uses CC 32-47 instead of 0-15, change in the code:
```supercollider
~midiCCOffset = 32;
```

## Basic Usage

```supercollider
// Set root and play intervals
~root.(220);           // A3
~playRatio.(3, 2);     // Perfect fifth
~playRatio.(5, 4);     // Major third
~stopAll.();

// Play a just intonation scale
~playScale.(\justMajor);
~playScale.(\dorian7, spacing: 0.2);  // Arpeggiate

// Free exploration
~freeExplore.(3/2);    // Generate m*A + n*B combinations
```

## Available Scales

- `\justMajor` - 5-limit just major
- `\justMinor` - 5-limit just minor
- `\dorian7` - 7-limit dorian (septimal intervals)
- `\lydian7` - 7-limit lydian
- `\neutral11` - 11-limit neutral (undecimal)
- `\extended13` - 13-limit extended (tridecimal)
- `\harmonicSeries` - Partials 1-16
- `\undertoneSeries` - Subharmonics 1-16

Type `~help.()` in SuperCollider for full documentation.
