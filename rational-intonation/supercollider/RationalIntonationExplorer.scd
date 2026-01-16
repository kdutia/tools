/*
    RATIONAL INTONATION EXPLORER - SuperCollider Version
    =====================================================

    A tool for exploring just intonation and rational frequency relationships,
    inspired by the work of Catherine Lamb and Kali Malone.

    QUICK START:
    1. Boot the server: s.boot;
    2. Evaluate this entire file (Cmd+Enter or Ctrl+Enter on the whole file)
    3. Use the functions below to explore

    MICHIGAN XVI FADERBANK:
    - Connect your Michigan XVI via USB before booting SuperCollider
    - MIDI is automatically initialized when you evaluate this file
    - See "MIDI MAPPING" section below for fader assignments

    If you need to manually connect:
        MIDIClient.init;
        MIDIIn.connectAll;
*/

(
// ============================================================================
// CONFIGURATION
// ============================================================================

~config = (
    rootFreq: 440,           // Root frequency in Hz (A4)
    masterAmp: 0.3,          // Master amplitude (0.0 - 1.0)
    fadeTime: 0.1,           // Fade in/out time in seconds
    numVoices: 16,           // Maximum simultaneous voices
    outBus: 0,               // Output bus (stereo)
);

// ============================================================================
// JUST INTONATION SCALES & MODES
// ============================================================================

// Ratio definitions as [numerator, denominator] pairs
~scales = (
    // 5-Limit Just Major Scale
    justMajor: [
        [1,1], [9,8], [5,4], [4,3], [3,2], [5,3], [15,8], [2,1]
    ],

    // 5-Limit Just Minor Scale
    justMinor: [
        [1,1], [9,8], [6,5], [4,3], [3,2], [8,5], [9,5], [2,1]
    ],

    // 7-Limit Dorian Mode (septimal intervals - Catherine Lamb territory)
    dorian7: [
        [1,1], [8,7], [7,6], [4,3], [3,2], [8,5], [7,4], [2,1]
    ],

    // 7-Limit Lydian Mode
    lydian7: [
        [1,1], [9,8], [5,4], [7,5], [3,2], [5,3], [15,8], [2,1]
    ],

    // 11-Limit Neutral Mode (undecimal intervals)
    neutral11: [
        [1,1], [12,11], [11,9], [4,3], [11,8], [3,2], [11,6], [2,1]
    ],

    // 13-Limit Extended Mode (tridecimal intervals)
    extended13: [
        [1,1], [13,12], [9,8], [13,10], [4,3], [13,9], [13,8], [2,1]
    ],

    // Harmonic Series (partials 1-16)
    harmonicSeries: [
        [1,1], [2,1], [3,1], [4,1], [5,1], [6,1], [7,1], [8,1],
        [9,1], [10,1], [11,1], [12,1], [13,1], [14,1], [15,1], [16,1]
    ],

    // Undertone Series (subharmonics - characteristic of Catherine Lamb)
    undertoneSeries: [
        [1,1], [1,2], [1,3], [1,4], [1,5], [1,6], [1,7], [1,8],
        [1,9], [1,10], [1,11], [1,12], [1,13], [1,14], [1,15], [1,16]
    ],
);

// Interval names for common ratios
~intervalNames = Dictionary[
    "1/1" -> "unison",
    "2/1" -> "octave",
    "3/2" -> "perfect fifth",
    "4/3" -> "perfect fourth",
    "5/4" -> "major third",
    "6/5" -> "minor third",
    "5/3" -> "major sixth",
    "8/5" -> "minor sixth",
    "9/8" -> "major whole tone",
    "10/9" -> "minor whole tone",
    "15/8" -> "major seventh",
    "16/15" -> "minor second",
    "7/4" -> "harmonic seventh",
    "7/6" -> "septimal minor third",
    "8/7" -> "septimal whole tone",
    "7/5" -> "septimal tritone",
    "9/5" -> "minor seventh",
    "11/8" -> "undecimal tritone",
    "11/9" -> "neutral third",
    "11/6" -> "neutral seventh",
    "12/11" -> "undecimal second",
    "13/8" -> "tridecimal neutral sixth",
    "13/12" -> "tridecimal second",
    "13/10" -> "tridecimal minor third",
    "13/9" -> "tridecimal diminished fifth",
];

// ============================================================================
// SYNTH DEFINITIONS
// ============================================================================

SynthDef(\intone, {
    arg out=0, freq=440, amp=0.3, pan=0, fadeTime=0.1, gate=1;
    var sig, env;

    // Pure sine tone - the foundation of exploring ratios
    sig = SinOsc.ar(freq);

    // Amplitude envelope with configurable fade
    env = EnvGen.kr(
        Env.asr(fadeTime, 1, fadeTime, \sin),
        gate,
        doneAction: 2
    );

    // Output with panning
    sig = sig * env * amp;
    sig = Pan2.ar(sig, pan);

    Out.ar(out, sig);
}).add;

// Alternative synth with subtle harmonics (warmer tone)
SynthDef(\intoneWarm, {
    arg out=0, freq=440, amp=0.3, pan=0, fadeTime=0.1, gate=1;
    var sig, env;

    // Fundamental plus quiet overtones
    sig = SinOsc.ar(freq) +
          (SinOsc.ar(freq * 2) * 0.1) +
          (SinOsc.ar(freq * 3) * 0.05);

    env = EnvGen.kr(
        Env.asr(fadeTime, 1, fadeTime, \sin),
        gate,
        doneAction: 2
    );

    sig = sig * env * amp * 0.7; // Compensate for added harmonics
    sig = Pan2.ar(sig, pan);

    Out.ar(out, sig);
}).add;

// Difference tone generator (important for Catherine Lamb's practice)
SynthDef(\differenceTone, {
    arg out=0, freq1=440, freq2=660, amp=0.3, pan=0, fadeTime=0.1, gate=1;
    var sig, env, diff;

    // The two source tones
    sig = SinOsc.ar(freq1) + SinOsc.ar(freq2);

    // Difference tone (psychoacoustic phenomenon made audible)
    diff = SinOsc.ar((freq2 - freq1).abs) * 0.5;

    sig = sig + diff;

    env = EnvGen.kr(
        Env.asr(fadeTime, 1, fadeTime, \sin),
        gate,
        doneAction: 2
    );

    sig = sig * env * amp * 0.5;
    sig = Pan2.ar(sig, pan);

    Out.ar(out, sig);
}).add;

"SynthDefs loaded.".postln;

// ============================================================================
// VOICE MANAGEMENT
// ============================================================================

~voices = Dictionary.new;  // Active synths indexed by frequency
~voiceAmps = Dictionary.new;  // Per-voice amplitudes
~voicePans = Dictionary.new;  // Per-voice panning

// Play a single frequency
~playFreq = { |freq, amp=nil, pan=0, synthType=\intone|
    var actualAmp = amp ?? { ~config.masterAmp };

    // Don't duplicate if already playing
    if(~voices[freq].isNil) {
        ~voices[freq] = Synth(synthType, [
            \freq, freq,
            \amp, actualAmp,
            \pan, pan,
            \fadeTime, ~config.fadeTime,
            \out, ~config.outBus
        ]);
        ~voiceAmps[freq] = actualAmp;
        ~voicePans[freq] = pan;
        "Playing: % Hz (amp: %, pan: %)".format(freq.round(0.01), actualAmp, pan).postln;
    };
};

// Stop a single frequency
~stopFreq = { |freq|
    if(~voices[freq].notNil) {
        ~voices[freq].set(\gate, 0);
        ~voices.removeAt(freq);
        ~voiceAmps.removeAt(freq);
        ~voicePans.removeAt(freq);
        "Stopped: % Hz".format(freq.round(0.01)).postln;
    };
};

// Stop all voices
~stopAll = {
    ~voices.keysValuesDo { |freq, synth|
        synth.set(\gate, 0);
    };
    ~voices.clear;
    ~voiceAmps.clear;
    ~voicePans.clear;
    "All voices stopped.".postln;
};

// Toggle a frequency on/off
~toggleFreq = { |freq, amp=nil, pan=0|
    if(~voices[freq].notNil) {
        ~stopFreq.(freq);
    } {
        ~playFreq.(freq, amp, pan);
    };
};

// ============================================================================
// RATIO & SCALE FUNCTIONS
// ============================================================================

// Calculate frequency from ratio
~ratioToFreq = { |ratio, rootFreq=nil|
    var root = rootFreq ?? { ~config.rootFreq };
    if(ratio.isArray) {
        root * ratio[0] / ratio[1];
    } {
        root * ratio;  // Assume decimal ratio
    };
};

// Play a ratio relative to root
~playRatio = { |num, denom=1, amp=nil, pan=0|
    var freq = ~config.rootFreq * num / denom;
    ~playFreq.(freq, amp, pan);
    "Ratio %/% = % Hz".format(num, denom, freq.round(0.01)).postln;
};

// Play an entire scale/mode
~playScale = { |scaleName, amp=nil, spacing=0|
    var scale = ~scales[scaleName];
    var delay = 0;

    if(scale.isNil) {
        "Unknown scale: %. Available: %".format(scaleName, ~scales.keys).postln;
    } {
        "Playing scale: %".format(scaleName).postln;
        scale.do { |ratio, i|
            var freq = ~ratioToFreq.(ratio);
            var pan = i.linlin(0, scale.size-1, -0.8, 0.8);  // Spread across stereo

            if(spacing > 0) {
                // Arpeggiate with delay
                SystemClock.sched(delay, {
                    ~playFreq.(freq, amp, pan);
                    nil;
                });
                delay = delay + spacing;
            } {
                // Play all at once
                ~playFreq.(freq, amp, pan);
            };
        };
    };
};

// Display scale information
~showScale = { |scaleName|
    var scale = ~scales[scaleName];

    if(scale.isNil) {
        "Unknown scale: %. Available: %".format(scaleName, ~scales.keys).postln;
    } {
        "\n=== % ===".format(scaleName.asString.toUpper).postln;
        scale.do { |ratio, i|
            var freq = ~ratioToFreq.(ratio);
            var ratioStr = "%/%".format(ratio[0], ratio[1]);
            var name = ~intervalNames[ratioStr] ?? "—";
            "  %: % = % Hz (%)".format(
                (i+1).asString.padLeft(2),
                ratioStr.padRight(6),
                freq.round(0.01).asString.padRight(10),
                name
            ).postln;
        };
        "".postln;
    };
};

// List all available scales
~listScales = {
    "\n=== AVAILABLE SCALES ===".postln;
    ~scales.keys.asArray.sort.do { |name|
        "  - %".format(name).postln;
    };
    "\nUse: ~showScale.(\\scaleName) for details".postln;
    "Use: ~playScale.(\\scaleName) to play".postln;
    "".postln;
};

// ============================================================================
// FREE EXPLORATION MODE (m*A + n*B combinations)
// ============================================================================

~freeExplore = { |ratio, maxCoeff=5|
    var rootFreq = ~config.rootFreq;
    var intervalFreq = rootFreq * ratio;
    var combinations = List.new;

    "\n=== FREE EXPLORATION MODE ===".postln;
    "Root (A): % Hz".format(rootFreq).postln;
    "Interval (B): % Hz (ratio: %)".format(intervalFreq.round(0.01), ratio).postln;
    "Generating m*A + n*B combinations (m,n = 0 to %)...".format(maxCoeff).postln;
    "\n".postln;

    // Generate all combinations
    (0..maxCoeff).do { |m|
        (0..maxCoeff).do { |n|
            if((m > 0) || (n > 0)) {  // Skip 0*A + 0*B
                var freq = (m * rootFreq) + (n * intervalFreq);
                combinations.add([m, n, freq]);
            };
        };
    };

    // Sort by frequency and display
    combinations.sort { |a, b| a[2] < b[2] };
    combinations.do { |combo, i|
        var m = combo[0], n = combo[1], freq = combo[2];
        "  %: %*A + %*B = % Hz".format(
            (i+1).asString.padLeft(2),
            m, n,
            freq.round(0.01)
        ).postln;
    };

    // Store for later use
    ~currentCombinations = combinations;

    "\nUse ~playCombination.(index) to play a specific combination".postln;
    "Use ~playAllCombinations.() to play all".postln;
    "".postln;
};

~playCombination = { |index, amp=nil|
    if(~currentCombinations.notNil && (index > 0) && (index <= ~currentCombinations.size)) {
        var combo = ~currentCombinations[index - 1];
        var freq = combo[2];
        ~playFreq.(freq, amp);
    } {
        "Invalid index. Run ~freeExplore first.".postln;
    };
};

~playAllCombinations = { |amp=nil, spacing=0|
    if(~currentCombinations.notNil) {
        var delay = 0;
        ~currentCombinations.do { |combo, i|
            var freq = combo[2];
            var pan = i.linlin(0, ~currentCombinations.size-1, -0.8, 0.8);

            if(spacing > 0) {
                SystemClock.sched(delay, {
                    ~playFreq.(freq, amp, pan);
                    nil;
                });
                delay = delay + spacing;
            } {
                ~playFreq.(freq, amp, pan);
            };
        };
    } {
        "Run ~freeExplore first.".postln;
    };
};

// ============================================================================
// DIFFERENCE TONES
// ============================================================================

~playDifferenceTone = { |ratio1, ratio2, amp=nil|
    var freq1 = ~config.rootFreq * ratio1;
    var freq2 = ~config.rootFreq * ratio2;
    var diffFreq = (freq2 - freq1).abs;

    "\n=== DIFFERENCE TONE ===".postln;
    "Freq 1: % Hz (ratio %)".format(freq1.round(0.01), ratio1).postln;
    "Freq 2: % Hz (ratio %)".format(freq2.round(0.01), ratio2).postln;
    "Difference: % Hz".format(diffFreq.round(0.01)).postln;
    "".postln;

    Synth(\differenceTone, [
        \freq1, freq1,
        \freq2, freq2,
        \amp, amp ?? { ~config.masterAmp },
        \fadeTime, ~config.fadeTime,
        \out, ~config.outBus
    ]);
};

// ============================================================================
// MICHIGAN XVI MIDI FADERBANK SUPPORT
// ============================================================================

/*
    MIDI MAPPING (Michigan XVI / 16-channel faderbank):

    Fader 1  (CC 0):  Master Amplitude (0.0 - 1.0)
    Fader 2  (CC 1):  Root Frequency (logarithmic: 20 - 2000 Hz)
    Fader 3  (CC 2):  Fade Time (0 - 5 seconds)
    Fader 4  (CC 3):  Voice 1 Amplitude
    Fader 5  (CC 4):  Voice 2 Amplitude
    Fader 6  (CC 5):  Voice 3 Amplitude
    Fader 7  (CC 6):  Voice 4 Amplitude
    Fader 8  (CC 7):  Voice 5 Amplitude
    Fader 9  (CC 8):  Voice 6 Amplitude
    Fader 10 (CC 9):  Voice 7 Amplitude
    Fader 11 (CC 10): Voice 8 Amplitude
    Fader 12 (CC 11): Voice 1 Pan
    Fader 13 (CC 12): Voice 2 Pan
    Fader 14 (CC 13): Voice 3 Pan
    Fader 15 (CC 14): Voice 4 Pan
    Fader 16 (CC 15): Voice 5 Pan

    The Michigan XVI typically sends CC 0-15.
    Some units may use CC 32-47 - adjust ~midiCCOffset if needed.
*/

~midiCCOffset = 32;  // Michigan XVI uses CC 32-47 (change to 0 if yours uses CC 0-15)
~midiChannel = nil; // nil = all channels, or set 0-15 for specific channel

~initMIDI = {
    MIDIClient.init;
    MIDIIn.connectAll;

    // Store voice references for MIDI control
    ~midiVoices = Array.newClear(8);
    ~midiVoiceFreqs = Array.newClear(8);

    // CC responder
    MIDIdef.cc(\faderbank, { |val, num, chan, src|
        var cc = num - ~midiCCOffset;
        var normalized = val / 127;

        case
        // Fader 1: Master Amplitude
        { cc == 0 } {
            ~config.masterAmp = normalized;
            "Master Amp: %".format(normalized.round(0.01)).postln;
            // Update all playing voices
            ~voices.keysValuesDo { |freq, synth|
                synth.set(\amp, ~voiceAmps[freq] * normalized);
            };
        }

        // Fader 2: Root Frequency (logarithmic scaling)
        { cc == 1 } {
            var freq = normalized.linexp(0, 1, 20, 2000);
            ~config.rootFreq = freq;
            "Root Freq: % Hz".format(freq.round(0.1)).postln;
        }

        // Fader 3: Fade Time
        { cc == 2 } {
            ~config.fadeTime = normalized * 5;  // 0-5 seconds
            "Fade Time: % sec".format((normalized * 5).round(0.01)).postln;
        }

        // Faders 4-11: Voice Amplitudes
        { (cc >= 3) && (cc <= 10) } {
            var voiceIdx = cc - 3;
            if(~midiVoices[voiceIdx].notNil) {
                ~midiVoices[voiceIdx].set(\amp, normalized * ~config.masterAmp);
                "Voice % Amp: %".format(voiceIdx + 1, normalized.round(0.01)).postln;
            };
        }

        // Faders 12-16: Voice Pans
        { (cc >= 11) && (cc <= 15) } {
            var voiceIdx = cc - 11;
            var pan = normalized.linlin(0, 1, -1, 1);
            if(~midiVoices[voiceIdx].notNil) {
                ~midiVoices[voiceIdx].set(\pan, pan);
                "Voice % Pan: %".format(voiceIdx + 1, pan.round(0.01)).postln;
            };
        };

    }, (0..15) + ~midiCCOffset, ~midiChannel);

    // Note on - trigger voices from scale
    MIDIdef.noteOn(\noteOn, { |vel, num, chan, src|
        var octave = (num / 12).floor - 5;  // MIDI note to octave offset
        var degree = num % 12;
        var scale = ~currentScale ?? { ~scales.justMajor };
        var idx = degree.min(scale.size - 1);
        var ratio = scale[idx];
        var freq = ~ratioToFreq.(ratio) * (2 ** octave);
        var amp = vel / 127 * ~config.masterAmp;

        // Find empty voice slot
        8.do { |i|
            if(~midiVoices[i].isNil) {
                ~midiVoices[i] = Synth(\intone, [
                    \freq, freq,
                    \amp, amp,
                    \fadeTime, ~config.fadeTime,
                    \out, ~config.outBus
                ]);
                ~midiVoiceFreqs[i] = num;  // Store MIDI note for release
                "MIDI Voice %: % Hz".format(i + 1, freq.round(0.01)).postln;
                i = 8;  // Break
            };
        };
    });

    // Note off - release voices
    MIDIdef.noteOff(\noteOff, { |vel, num, chan, src|
        8.do { |i|
            if(~midiVoiceFreqs[i] == num) {
                ~midiVoices[i].set(\gate, 0);
                ~midiVoices[i] = nil;
                ~midiVoiceFreqs[i] = nil;
            };
        };
    });

    "\n=== MIDI INITIALIZED ===".postln;
    "Michigan XVI faderbank ready.".postln;
    "Connected MIDI devices:".postln;
    MIDIClient.sources.do { |src, i|
        "  %: % - %".format(i, src.device, src.name).postln;
    };
    "".postln;
};

// ============================================================================
// CONVENIENCE FUNCTIONS
// ============================================================================

// Set root frequency
~root = { |freq|
    ~config.rootFreq = freq;
    "Root frequency set to % Hz".format(freq).postln;
};

// Set master amplitude
~amp = { |amp|
    ~config.masterAmp = amp;
    "Master amplitude set to %".format(amp).postln;
};

// Set fade time
~fade = { |time|
    ~config.fadeTime = time;
    "Fade time set to % seconds".format(time).postln;
};

// Quick interval playing
~fifth = { ~playRatio.(3, 2) };
~fourth = { ~playRatio.(4, 3) };
~majorThird = { ~playRatio.(5, 4) };
~minorThird = { ~playRatio.(6, 5) };
~seventh = { ~playRatio.(7, 4) };  // Harmonic seventh
~octave = { ~playRatio.(2, 1) };

// Store current scale for MIDI
~currentScale = ~scales.justMajor;

~setScale = { |scaleName|
    if(~scales[scaleName].notNil) {
        ~currentScale = ~scales[scaleName];
        "Current scale set to %".format(scaleName).postln;
    } {
        "Unknown scale. Use ~listScales.() to see options.".postln;
    };
};

// ============================================================================
// HELP & DOCUMENTATION
// ============================================================================

~help = {
    "
=============================================================================
                    RATIONAL INTONATION EXPLORER
                         SuperCollider Version
=============================================================================

BASIC USAGE:
  ~root.(440)              Set root frequency to 440 Hz
  ~amp.(0.3)               Set master amplitude
  ~fade.(0.1)              Set fade time in seconds

PLAYING TONES:
  ~playFreq.(440)          Play a specific frequency
  ~stopFreq.(440)          Stop a specific frequency
  ~toggleFreq.(440)        Toggle frequency on/off
  ~stopAll.()              Stop all playing tones

  ~playRatio.(3, 2)        Play a ratio (3/2 = perfect fifth)
  ~fifth.()                Quick: play perfect fifth
  ~fourth.()               Quick: play perfect fourth
  ~majorThird.()           Quick: play major third
  ~seventh.()              Quick: play harmonic seventh

SCALES & MODES:
  ~listScales.()           Show all available scales
  ~showScale.(\\justMajor) Display scale intervals
  ~playScale.(\\justMajor) Play entire scale simultaneously
  ~playScale.(\\dorian7, spacing: 0.2)  Arpeggiate with 0.2s between notes
  ~setScale.(\\justMajor)  Set scale for MIDI keyboard mapping

  Available scales:
    \\justMajor      5-limit just major
    \\justMinor      5-limit just minor
    \\dorian7        7-limit dorian (septimal)
    \\lydian7        7-limit lydian
    \\neutral11      11-limit neutral
    \\extended13     13-limit extended
    \\harmonicSeries Partials 1-16
    \\undertoneSeries Subharmonics 1-16

FREE EXPLORATION:
  ~freeExplore.(1.5)       Generate m*A + n*B combinations for ratio 1.5
  ~playCombination.(1)     Play specific combination from list
  ~playAllCombinations.()  Play all combinations

DIFFERENCE TONES:
  ~playDifferenceTone.(1, 1.5)  Play two tones and their difference tone

MIDI (Michigan XVI):
  ~initMIDI.()             Initialize MIDI (usually automatic)

  Fader mapping:
    1: Master amplitude
    2: Root frequency (log scale)
    3: Fade time
    4-11: Voice amplitudes
    12-16: Voice pans

=============================================================================
".postln;
};

// ============================================================================
// INITIALIZATION
// ============================================================================

// Wait for server and initialize
s.waitForBoot {
    // Initialize MIDI automatically
    ~initMIDI.();

    "\n".postln;
    "=============================================================".postln;
    "  RATIONAL INTONATION EXPLORER READY".postln;
    "  Type ~help.() for usage instructions".postln;
    "=============================================================".postln;
    "\n".postln;
};
)

// ============================================================================
// EXAMPLE SESSIONS
// ============================================================================

/*
// --- Basic exploration ---

~root.(220);           // Set root to A3 (220 Hz)
~playRatio.(1, 1);     // Play root
~playRatio.(3, 2);     // Add perfect fifth
~playRatio.(5, 4);     // Add major third
~stopAll.();

// --- Explore 7-limit intervals (Catherine Lamb style) ---

~showScale.(\dorian7);
~playScale.(\dorian7, spacing: 0.3);  // Arpeggiate slowly
~stopAll.();

// --- Free exploration with 3/2 ratio ---

~freeExplore.(3/2, 3);  // All m*A + n*B where m,n go 0-3
~playAllCombinations.(spacing: 0.1);
~stopAll.();

// --- Difference tones ---

~playDifferenceTone.(1, 5/4);  // Root + major third + difference tone
~stopAll.();

// --- Using the warm synth ---

~playFreq.(440, synthType: \intoneWarm);
~playFreq.(660, synthType: \intoneWarm);
~stopAll.();
*/
