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
def build(plan, shot, outdir, samples=6, preview=None, quality=None, gpu=False,
          res_override=None, denoise=False, frame_start=None, frame_end=None):
    sc = bpy.context.scene
    q = float(quality if quality is not None else plan.get("quality", 1.0))
    SUB = 2 if q >= 0.85 else 1
    fps = plan.get("fps", 24)
    res = tuple(res_override or plan.get("res", [720, 1280]))
    ST.setup_render(sc, res=res, samples=samples, fps=fps)
    if gpu:
        ok = ST.setup_gpu(sc, denoise=True, samples=samples)
        print("GPU:", ok, flush=True)
    if denoise:
        # OIDN — kam sample bilan ham toza natija beradi (CPU'da ishlaydi)
        sc.cycles.use_denoising = True
        sc.cycles.denoiser = 'OPENIMAGEDENOISE'
        sc.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
        print("DENOISE: OIDN", flush=True)

    sun_dir = shot.get("sun_dir", [0.92, 0.42, 0.20])
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

    print("STAGE: env start", flush=True)
    # ---------------- YER / FON ----------------
    NA.make_ground(c_env, size=340, dry=dry,
                   color=tuple(shot.get("ground_color", (0.062, 0.150, 0.038))),
                   color2=tuple(shot.get("ground_color2", (0.125, 0.265, 0.070))))
    try:
        gm = bpy.data.materials.get("ground_Ground")
        bc = gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value
        print("STAGE: ground ok | color=", [round(v, 3) for v in bc[:3]], flush=True)
    except Exception as e:
        print("STAGE: ground ok | debug fail", e, flush=True)
    if not dry:
        NA.make_grass_tufts(c_env, count=int(shot.get("grass", 420) * q),
                            radius=shot.get("grass_radius", 22), seed=seed)
    if shot.get("hills", False):
        NA.make_hills(c_env, count=max(3, int(6 * q)), radius=150, seed=seed + 1)
    NA.make_far_trees(c_env, count=int(shot.get("far_trees", 40) * q), radius=34,
                      seed=seed + 2, dry=dry)
    print("STAGE: far trees ok", flush=True)
    NA.make_clouds(c_env, count=int(shot.get("clouds", 7) * q), seed=seed + 3)
    print("STAGE: clouds ok", flush=True)
    NA.make_sun(c_env, direction=sun_dir, size=shot.get("sun_size", 3.0))
    print("STAGE: sun ok", flush=True)
    if shot.get("skydome", True):
        NA.make_sky_dome(c_env, horizon=shot.get("sky_horizon"),
                         zenith=shot.get("sky_top"), sun_dir=sun_dir)
        print("STAGE: skydome ok", flush=True)
    NA.make_sun_disc(c_cam, tuple(shot.get("sun_dir", [0.90, 0.40, 0.21])))
    print("STAGE: sun disc ok", flush=True)

    # ---------------- DARAXTLAR ----------------
    trees = []
    layout = shot.get("trees")
    if env in ("orchard", "orchard_dry", "dry"):
        if layout is None:
            # kamera -Y tomondan +Y ga qaraydi: daraxtlarni shu yo'nalishda kamar qilib qo'yamiz
            layout = []
            n = max(2, int(shot.get("tree_count", 9) * q))
            for i in range(n):
                t = (i + 0.5) / n
                a = math.pi * (0.08 + 0.84 * t) + rnd.uniform(-0.12, 0.12)   # 0..pi yoy
                d = rnd.uniform(7.5, 17.0)
                x = math.cos(a) * d
                y = 3.5 + math.sin(a) * d * 0.55 + rnd.uniform(0, 2.5)
                layout.append({"pos": [x, y, 0],
                               "h": rnd.uniform(3.0, 4.3),
                               "fruit": 0 if dry else rnd.randint(4, 12),
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

    print("STAGE: trees ok", flush=True)
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

    print("STAGE: actor+fx ok", flush=True)
    # ---------------- KAMERA ----------------
    cam = CAm.make_camera(c_cam, sc)
    dur_f = int(round(shot["dur"] * fps))
    CAm.animate_shot(cam, shot.get("cam", {}), 1, dur_f)

    sc.frame_start = frame_start or 1
    sc.frame_end = frame_end or dur_f
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
        try:
            for ob in bpy.data.objects:
                if ob.type == 'MESH' and ob.data.materials:
                    mm = ob.data.materials[0]
                    bs = mm.node_tree.nodes.get("Principled BSDF")
                    bc = bs.inputs["Base Color"].default_value if bs else (0, 0, 0, 0)
                    print("OBJ", ob.name, mm.name, [round(v, 3) for v in bc[:3]], "at", [round(v,1) for v in ob.location], flush=True)
        except Exception as e:
            print("dbg fail", e, flush=True)
    else:
        bpy.ops.render.render(animation=True)
        print("RENDERED:", outdir, dur_f, "frames")


def _run_guarded(fn):
    import traceback
    try:
        return fn()
    except BaseException as e:
        print("XATO_TURI:", type(e).__name__, flush=True)
        print("XATO_MATNI:", e, flush=True)
        for line in traceback.format_exc().splitlines()[-14:]:
            print("TRACE:", line, flush=True)
        raise


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
    ap.add_argument("--denoise", action="store_true")
    ap.add_argument("--res", default=None, help="masalan 540x960")
    ap.add_argument("--frame-start", type=int, default=None)
    ap.add_argument("--frame-end", type=int, default=None)
    a = ap.parse_args(argv)

    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    shot = plan["shots"][a.shot]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    res_override = None
    if a.res:
        w, h = a.res.lower().split("x")
        res_override = (int(w), int(h))
    build(plan, shot, a.outdir, samples=a.samples, preview=a.preview,
          quality=a.quality, gpu=a.gpu, res_override=res_override, denoise=a.denoise,
          frame_start=a.frame_start, frame_end=a.frame_end)
    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=a.save_blend)


_run_guarded(main)
