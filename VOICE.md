# Willow's voice

Willow talks in a cloned voice. Sophon clones a voice from a short clip — no training, no restart, no new model.

## Record the clip

- 3 to 10 seconds of clean speech from one speaker. One voice only.
- A quiet room. No music, no background voices.
- Natural speech — a sentence or two, the way Willow should sound.
- Save it as a `.wav` file (`.flac` also works). Any sample rate is fine.
- Name the file `willow.wav`.

A phone voice memo works. Just hold the phone close and talk normally.

## Where it goes

Copy `willow.wav` into the model's voices folder:

```
<willow folder>\sophon-realtime\tag\model\voices\willow.wav
```

(If you installed the Flash build instead, use `sophon-realtime\flash\model\voices\willow.wav`.)

New, replaced, and deleted voices take effect on the next request — no restart, no reinstall.

## Select it

Set the voice to `willow`:

- In `talk.html`: the Voice box already says `willow`.
- In the Live test page or any API client: set `"voice": "willow"`.

## Until a clip is provided

Willow uses the built-in voice. Everything else works the same. In `talk.html`, set the Voice box to `chelsie` until your clip is in place. Record the clip whenever — the voice swaps in on the next request after you copy the file.

## Only clone voices you have permission to use

Clone your own voice, or a voice you have permission for. Do not use it to impersonate anyone or to deceive.
