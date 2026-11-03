# SnowLeopardWellbeing

A desktop toy. The snow leopard video starts playing straight away, and every
snow leopard picture pops up in a little window of its own and jumps around
the screen: it stretches tall as it leaps, gets pulled back down by gravity,
lands compacted, crouches, and jumps again. Every picture moves on its own,
with its own timing and direction.

Close one and another opens. The video window refuses to close while any
picture is open, and since closing a picture opens another, it never closes.
It keeps going until you stop the script.

## Run it

Double-click **`run.bat`**. The first run creates a Python environment in
`.venv` and installs PySide6 (Qt for Python), which takes about a minute.
After that it starts at once.

Or from a terminal in this folder:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m wellbeing
```

Made for Windows 10/11 with Python 3.10 or newer.

## Stop it

- **Ctrl+Shift+Q**, from any window
- **Ctrl+C** in the console window that `run.bat` opened
- or close that console window. Its taskbar button stays reachable, because
  the pictures never cover the taskbar.

## What you can do

| You do                       | What happens                                                       |
| ---------------------------- | ------------------------------------------------------------------ |
| Click a picture's ✕          | It closes, and a different picture pops up somewhere else          |
| Alt+F4                       | Closes the picture you clicked last; another pops up               |
| Press on a picture and drag  | You grab it; let go to throw it                                    |
| Click a picture              | It comes to the front                                              |
| Close the video window       | Refused: it shakes and tells you how many leopards are still out there |
| Minimize or pause the video  | It comes back / keeps playing                                      |

## Options

```bat
run.bat --mute               :: no sound
run.bat --duration 30        :: stop by itself after 30 seconds
run.bat --pictures D:\cats   :: another folder of pictures
run.bat --video clip.mp4     :: another video
```

The same options work with `python -m wellbeing`. Gravity, jump heights,
how far the pictures stretch and squash, their sizes, and how many open per
close (`RESPAWN_PER_CLOSE`) are in [`wellbeing/config.py`](wellbeing/config.py).

## How it works

| File | Job |
| --- | --- |
| [`wellbeing/physics.py`](wellbeing/physics.py) | Each picture's body: gravity, crouch and jump, wall bounces, and a spring that drives the squash and stretch. Width × height keeps the same area. Plain Python, no Qt. |
| [`wellbeing/picture.py`](wellbeing/picture.py) | Draws one picture as a little window (title strip, ✕), stretched to its body's shape. |
| [`wellbeing/overlay.py`](wellbeing/overlay.py) | One transparent, always-on-top layer over the screen that every picture is drawn on. Turns clicks into close / grab / throw. |
| [`wellbeing/swarm.py`](wellbeing/swarm.py) | Opens all the pictures, runs the 60 fps clock, and opens a new picture whenever one is closed. |
| [`wellbeing/video_window.py`](wellbeing/video_window.py) | Plays and loops the video, resumes it if paused, restores it if minimized, and refuses to close while pictures are open. |
| [`wellbeing/killswitch.py`](wellbeing/killswitch.py) | The Ctrl+Shift+Q system-wide hotkey. |
| [`wellbeing/app.py`](wellbeing/app.py) | Options, and wiring everything together. |

**Why one layer instead of 53 real windows.** Moving and resizing a real
window costs Windows about a millisecond each time. Squash and stretch means
resizing every picture every frame, so 53 real windows only managed 8.5
frames a second. Drawing all the pictures on one see-through layer runs at
about 59 frames a second. Clicks on the see-through parts fall through to
whatever is underneath, so the rest of the desktop still works between the
leopards.

The media: 53 pictures in [`snowleopard/`](snowleopard) and the video
`Download (1).mp4`.

## Tests

```bat
.venv\Scripts\python -m unittest
```

The tests run Qt offscreen, so nothing pops up on screen. They cover the
physics, finding the media, closing and respawning, the video lock, and
the kill switch.
