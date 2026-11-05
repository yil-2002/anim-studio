"""
build_scene.py — Bitta "shot" (kadr) uchun to'liq 3D sahna quradi va render qiladi.

Ishlatish:
  blender -b -P build_scene.py -- --plan scenes/demo.json --shot 0 --outdir build/shot00
  blender -b -P build_scene.py -- --plan scenes/demo.json --shot 0 --outdir build/prev --preview 40
"""
import bpy
import sys
import os
import json
import math
import random
import argparse
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lib_style as ST
import lib_nature as NA
import lib_character as CH
import lib_camera as CAm
import lib_fx as FX


# ----------------------------------------------------------------------------
def build(plan, shot, outdir, samples=6, preview=None, quality=None, gpu=False):
    sc = bpy.context.scene
    q = float(quality if quality is not None else plan.get("quality", 1.0))
    SUB = 2 if q >= 0.85 else 1
    fps = plan.get("fps", 24)
    res = tuple(plan.get("res", [720, 1280]))
    ST.setup_render(sc, res=res, samples=samples, fps=fps)
    if gpu:
        ok = ST.setup_gpu(sc, denoise=True, samples=samples)
        print("GPU:", ok, flush=True)

    sun_dir = shot.get("sun_dir", [0.35, -1.0, 0.24])
    ST.setup_world(sc, sun_dir=sun_dir,
                   horizon=shot.get("sky_horizon"),
                   top=shot.get("sky_top"))
    ST.setup_lights(sun_dir=sun_dir, energy=shot.get("sun_energy", 3.2))

    c_env = ST.new_collection("ENV")
    c_act = ST.new_collection("ACTOR")
    c_fx = ST.new_collection("FX")
    c_cam = ST.new_collection("CAMERA")

    env = shot.get("env", "orchard")
    dry = shot.get("dry", env in ("orchard_dry", "dry"))
    seed = shot.get("seed", 1)
    rnd = random.Random(seed)

    # ---------------- YER / FON ----------------
    NA.make_ground(c_env, size=90, dry=dry)
    if not dry:
        NA.make_grass_tufts(c_env, count=int(shot.get("grass", 240) * q),
                            radius=shot.get("grass_radius", 15), seed=seed)
    NA.make_hills(c_env, count=max(3, int(6 * q)), radius=46, seed=seed + 1)
    NA.make_far_trees(c_env, count=int(shot.get("far_trees", 26) * q), radius=32,
                      seed=seed + 2, dry=dry)
    NA.make_clouds(c_env, count=int(shot.get("clouds", 7) * q), seed=seed + 3)
    NA.make_sun(c_env, direction=sun_dir, size=shot.get("sun_size", 6.0))

    # ---------------- DARAXTLAR ----------------
    trees = []
    layout = shot.get("trees")
    if env in ("orchard", "orchard_dry", "dry"):
        if layout is None:
            layout = []
            n = max(2, int(shot.get("tree_count", 8) * q))
            for i in range(n):
                a = rnd.uniform(0, math.tau)
                d = rnd.uniform(4.5, 14.0)
                layout.append({"pos": [math.cos(a) * d, math.sin(a) * d + 4.0, 0],
                               "h": rnd.uniform(2.9, 4.0),
                               "fruit": 0 if dry else rnd.randint(3, 9),
                               "dry": dry})
    for i, t in enumerate(layout):
        tr = NA.make_tree(c_env, name=f"T{i}", loc=t.get("pos", [0, 0, 0]),
                          height=t.get("h", 3.4),
                          canopy=t.get("canopy", 1.0),
                          fruit=t.get("fruit", 0),
                          dry=t.get("dry", dry),
                          seed=seed * 100 + i, subdiv=SUB)
        NA.add_wind(tr, strength=t.get("wind", 0.030), seed=i)
        trees.append(tr)

    # ---------------- ODAM ----------------
    man = None
    act = shot.get("actor")
    if act:
        man = CH.build_man(c_act, height=act.get("height", 1.78))
        pos = Vector(act.get("pos", [0, 0, 0]))
        man["root"].location = pos
        yaw = math.radians(act.get("yaw", 0))
        man["root"].rotation_euler = (0, 0, yaw)
        dur_f = int(shot["dur"] * fps)
        pose = act.get("pose", "idle")
        if pose == "walk":
            start = pos
            d = Vector(act.get("walk_to", [0, 3.5, 0])) 
            CH.anim_walk(man, start=start, end=pos + d, f0=1, f1=dur_f,
                         steps=act.get("steps", 3))
        elif pose == "kneel":
            CH.anim_kneel(man, 1, dur_f)
            CH.anim_idle(man, 1, dur_f)
        elif pose == "reach":
            CH.anim_reach(man, 1, dur_f, side=act.get("hand", "L"))
        else:
            CH.anim_idle(man, 1, dur_f)

    # ---------------- FX ----------------
    if shot.get("dust", True):
        FX.dust_motes(c_fx, count=max(8, int(shot.get("dust_count", 55) * q)),
                      area=(12, 12, 6), center=(0, 0, 1.6), seed=seed + 9)
    if shot.get("leaves", False):
        FX.falling_leaves(c_fx, count=shot.get("leaf_count", 12), seed=seed + 11)

    # ---------------- KAMERA ----------------
    cam = CAm.make_camera(c_cam, sc)
    dur_f = int(round(shot["dur"] * fps))
    CAm.animate_shot(cam, shot.get("cam", {}), 1, dur_f)

    sc.frame_start = 1
    sc.frame_end = dur_f
    sc.frame_current = 1

    # ---------------- RENDER SOZLAMALARI ----------------
    sc.render.filepath = os.path.join(outdir, "f_")
    os.makedirs(outdir, exist_ok=True)

    with open(os.path.join(outdir, "shot_meta.json"), "w") as f:
        json.dump({"dur": shot["dur"], "fps": fps, "frames": dur_f,
                   "res": res, "text": shot.get("text", "")}, f, ensure_ascii=False)

    if preview is not None:
        sc.frame_set(int(preview))
        sc.render.filepath = os.path.join(outdir, f"preview_{int(preview):04d}.png")
        bpy.ops.render.render(write_still=True)
        print("PREVIEW:", sc.render.filepath)
    else:
        bpy.ops.render.render(animation=True)
        print("RENDERED:", outdir, dur_f, "frames")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--shot", type=int, default=0)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--samples", type=int, default=6)
    ap.add_argument("--preview", type=int, default=None)
    ap.add_argument("--save-blend", default=None)
    ap.add_argument("--quality", type=float, default=None)
    ap.add_argument("--gpu", action="store_true")
    a = ap.parse_args(argv)

    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    shot = plan["shots"][a.shot]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    build(plan, shot, a.outdir, samples=a.samples, preview=a.preview,
          quality=a.quality, gpu=a.gpu)
    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=a.save_blend)


main()
