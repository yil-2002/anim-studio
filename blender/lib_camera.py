"""
lib_camera.py — Kamera va uning harakatlari (push-in, pull-out, pan, orbit, tilt).
Referens videodagi "sekin yaqinlashish" effekti shu yerda.
"""
import bpy
import math
from mathutils import Vector, Euler


SHOTS = {
    # nomi:          (distance, height, focal, target_height)
    "wide":         (12.0, 2.6, 30.0, 1.9),
    "medium":       (6.2, 1.6, 45.0, 1.15),
    "close":        (2.6, 1.55, 70.0, 1.35),
    "closeup":      (1.7, 1.5, 85.0, 1.45),
    "low":          (7.0, 0.45, 30.0, 1.4),
    "high":         (13.0, 7.5, 40.0, 0.8),
    "detail":       (1.3, 0.0, 90.0, 0.6),
    "establishing": (17.0, 3.2, 26.0, 1.6),
}


def make_camera(coll, scene):
    cam_data = bpy.data.cameras.new("CAM")
    cam_data.sensor_fit = 'VERTICAL'
    cam_data.sensor_height = 24.0
    cam_data.clip_start = 0.05
    cam_data.clip_end = 400.0
    cam = bpy.data.objects.new("CAM", cam_data)
    coll.objects.link(cam)
    scene.camera = cam
    return cam


def _look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def place_camera(cam, shot=None):
    """shot = {"type": "wide", "move": "push_in", "target": [x,y,z], "azimuth": deg}"""
    shot = shot or {}
    t = shot.get("type", "wide")
    dist, h, focal, tz = SHOTS.get(t, SHOTS["wide"])
    dist *= shot.get("dist_scale", 1.0)
    focal *= shot.get("focal_scale", 1.0)

    target = Vector(shot.get("target", [0, 0, tz]))
    if shot.get("target") and len(shot["target"]) == 3 and shot["target"][2] == 0:
        target.z = tz
    az = math.radians(shot.get("azimuth", 90.0))   # 90 = old tomondan (-Y)
    cam.data.lens = focal
    cam.location = target + Vector((math.cos(az) * dist, -math.sin(az) * dist, h))
    _look_at(cam, target)
    return target, dist


def animate_shot(cam, shot, f0, f1):
    """Kamera harakati: sekin push-in / pull-out / pan / orbit / tilt — juda muhim."""
    shot = shot or {}
    move = shot.get("move", "push_in")
    amt = shot.get("amount", 1.0)
    target, dist = place_camera(cam, shot)
    base_loc = cam.location.copy()
    base_rot = cam.rotation_euler.copy()
    fwd = (target - base_loc).normalized()
    right = fwd.cross(Vector((0, 0, 1))).normalized()

    if move == "static":
        return

    steps = 6
    for i in range(steps + 1):
        f = int(f0 + (f1 - f0) * i / steps)
        k = i / steps
        loc = base_loc.copy()
        tgt = target.copy()
        if move == "push_in":
            loc = base_loc + fwd * (dist * 0.14 * amt * k)
        elif move == "pull_out":
            loc = base_loc - fwd * (dist * 0.14 * amt * (1 - k))
        elif move == "pan_lr":
            loc = base_loc + right * (dist * 0.16 * amt * (k - 0.5)) + fwd * (dist * 0.05 * k)
        elif move == "pan_rl":
            loc = base_loc - right * (dist * 0.16 * amt * (k - 0.5)) + fwd * (dist * 0.05 * k)
        elif move == "orbit":
            a = math.radians(shot.get("orbit_deg", 14)) * (k - 0.5)
            rel = base_loc - target
            rl = Vector((rel.x * math.cos(a) - rel.y * math.sin(a),
                         rel.x * math.sin(a) + rel.y * math.cos(a), rel.z))
            loc = target + rl
        elif move == "tilt_up":
            tgt = target + Vector((0, 0, 1.4 * amt * k))
            loc = base_loc + fwd * (dist * 0.04 * k)
        elif move == "handheld":
            amp = 0.012 * amt
            loc = base_loc + right * amp * math.sin(i * 2.1) + Vector((0, 0, amp * math.sin(i * 3.3)))
        cam.location = loc
        _look_at(cam, tgt)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)

    # yumshoq interpolatsiya
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.easing = 'EASE_IN_OUT'
