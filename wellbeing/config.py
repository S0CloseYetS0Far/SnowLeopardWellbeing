"""Numbers you can tweak to change how everything behaves.

Distances are screen pixels, times are seconds, and y points down.
"""

# --- jumping ---------------------------------------------------------------
GRAVITY = 2600.0              # px/s^2 pulling every picture down to the floor
JUMP_HEIGHT = (0.25, 0.9)     # a jump climbs this share of the free height above the floor
JUMP_SIDEWAYS = (100.0, 550.0)  # sideways speed of a jump, px/s
KEEP_DIRECTION = 0.65         # chance that a jump goes the same way as the last one
CROUCH_TIME = (0.12, 0.45)    # time spent squashed on the floor before jumping again
LANDING_SLIDE = 0.35          # share of sideways speed kept when landing
FLOOR_FRICTION = 8.0          # how quickly a landing slide stops, 1/s
WALL_BOUNCE = 0.8             # share of sideways speed kept when bouncing off a wall
CEILING_BOUNCE = 0.4          # share of upward speed kept when hitting the top
MAX_THROW_SPEED = 3500.0      # px/s, for pictures flung with the mouse
MAX_STEP = 1 / 120            # physics sub-step, for stability
MAX_FRAME_TIME = 0.1          # a stalled frame never advances time by more than this

# --- squash and stretch ------------------------------------------------------
# The shape is one number: > 0 is taller and thinner (stretched), < 0 is
# shorter and wider (compacted). Width x height always keeps the same area.
STRETCH_PER_SPEED = 1 / 7000  # stretch per px/s of vertical speed while flying
MAX_STRETCH = 0.5             # at most +50 % height
MAX_SQUASH = 0.45             # at most -45 % height
CROUCH_SQUASH = (0.12, 0.30)  # squash while crouching; deeper before a bigger jump
LANDING_SQUASH = 0.0012       # squash kick per px/s of landing speed
LAUNCH_STRETCH = 2.5          # stretch kick when leaving the floor
WALL_SQUASH = 0.004           # sideways squeeze kick per px/s when hitting a wall
SPRING_STIFFNESS = 260.0      # how fast the shape snaps back
SPRING_DAMPING = 14.5         # lower means more jelly wobble

# --- picture windows ---------------------------------------------------------
PICTURE_SIZE = (0.14, 0.23)   # longest side of a picture window, as a share of screen height
FPS = 60                      # animation frames per second
PICTURES_DELAY_MS = 400       # the pictures start right after the video does
SPAWN_INTERVAL_MS = 70        # gap between pictures popping up at the start
RESPAWN_PER_CLOSE = 1         # pictures that open each time you close one
POP_TIME = 0.22               # a new picture pops open over this long
CLOSE_TIME = 0.14             # a closed picture shrinks away over this long
TITLE_BAR_HEIGHT = 24         # the little title strip on each picture
CLOSE_BUTTON_WIDTH = 34

# --- video window ---------------------------------------------------------
VIDEO_MAX_WIDTH = 0.55        # largest share of the screen width the video may take
VIDEO_MAX_HEIGHT = 0.78       # largest share of the screen height the video may take
VIDEO_VOLUME = 1.0            # 0.0 - 1.0
