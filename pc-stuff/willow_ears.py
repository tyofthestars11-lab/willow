"""Willow's ears and voice for the Command Center: continuous, natural voice-to-voice.
Hears you with Whisper small.en on the GPU; speaks with Kokoro (a natural neural voice), pyttsx3 only as backup.
Everything you say goes to her, and DLAM stays on. Say "stop listening" to pause; say "Willow" to wake her."""
import os, queue, subprocess, sys, threading, time

VOICE = "af_heart"  # Kokoro voice: try af_bella, af_nicole, bf_emma
HERE = os.path.dirname(os.path.abspath(__file__))

SPEAKING = threading.Event()
TTS = ("import sys, pyttsx3\n"
       "e = pyttsx3.init()\n"
       "e.setProperty('rate', 175)\n"
       "e.say(sys.argv[1])\n"
       "e.runAndWait()\n")
VOICE_Q = queue.Queue()
JUNK = {"", "you", "thank you", "thanks for watching", "bye", "uh", "um", "hmm"}


def start(respond, say, w):
    def voice_worker():
        # One voice at a time. Kokoro loads once and plays through your speakers.
        kokoro = None
        try:
            import sounddevice as sd
            from kokoro_onnx import Kokoro
            kokoro = Kokoro(os.path.join(HERE, "kokoro-v1.0.onnx"), os.path.join(HERE, "voices-v1.0.bin"))
        except Exception as e:
            print(f"Kokoro voice not loaded ({e}); using the old voice.")
        while True:
            text = VOICE_Q.get()
            SPEAKING.set()
            try:
                if kokoro:
                    samples, rate = kokoro.create(text, voice=VOICE, speed=1.0, lang="en-us")
                    sd.play(samples, rate)
                    sd.wait()
                else:
                    subprocess.run([sys.executable, "-c", TTS, text], timeout=120,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception as e:
                print(f"voice error: {e}")
            time.sleep(0.4)
            if VOICE_Q.empty():
                SPEAKING.clear()

    def speak_quiet(text):
        if text:
            SPEAKING.set()
            VOICE_Q.put(str(text)[:600])

    threading.Thread(target=voice_worker, daemon=True).start()
    w.speak_orig = speak_quiet
    w.speak = speak_quiet
    w.VOICE_ON = True
    w.DLAM_FILE.write_text("on", encoding="utf-8")  # continuous DLAM

    def loop():
        try:
            import willow as wv
            wv.WHISPER_MODEL = "small.en"  # sharper ears than base.en
            ear = wv.Willow()
            ear.stream.start()
            ear.calibrate()
        except Exception as e:
            say(f"My ears didn't start: {e}", "Guard")
            return
        say("Ears on, always listening. DLAM locked on. Just talk.", "Action")
        paused = False
        while True:
            if SPEAKING.is_set():
                ear.drain()
                time.sleep(0.1)
                continue
            heard = ear.hear()
            if SPEAKING.is_set() or heard.lower().strip(" .!?,") in JUNK:
                continue
            woke, rest = ear.strip_wake(heard)
            low = heard.lower()
            if "stop listening" in low:
                paused = True
                say("Paused. Say Willow when you need me.")
                continue
            if paused:
                if not woke:
                    continue
                paused = False
            if not w.dlam_on():
                w.DLAM_FILE.write_text("on", encoding="utf-8")
            msg = rest if woke else heard
            if msg.lower().strip(" .!?,") in ("", "hey", "hi"):
                say("Yes?")
                continue
            respond(msg)

    threading.Thread(target=loop, daemon=True).start()
