"""
lib_character.py — Uslublashtirilgan 3D odam (oq jellya + salla), oddiy skelet.
Past-poly, illyustrativ ko'rinish. Yurish / turish / tiz cho'kish / qo'l uzatish.
"""
import bpy
import bmesh
import math
import random
from mathutils import Vector, Euler
from lib_style import mat, PALETTE


def _lathe(profile, segments=20, name="lathe"):
    """(z, r) profillarni Z o'qi atrofida aylantirib mesh yasaydi."""
    bm = bmesh.new()
    rings = []
    for (z, r) in profile:
        ring = []
        for i in range(segments):
            a = 2 * math.pi * i / segments
            ring.append(bm.verts.new((math.cos(a) * r, math.sin(a) * r, z)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
    # pastki qopqoq
    bm.faces.new(list(reversed(rings[0])))
    if profile[-1][1] > 0.01:
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def _add_mesh(bm, name, coll, material, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.data.materials.append(material)
    return ob


def _sphere(name, coll, material, radius, location, segments=18, rings=12, scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    ob = _add_mesh(bm, name, coll, material)
    ob.location = location
    ob.scale = scale
    return ob


def build_man(coll, name="Man", height=1.78, robe_color=None, turban_color=None):
    """
    Oq jellyali, sallali odam. Qaytaradi: {root, armature, parts, bones}
    height — real balandlik (m).
    """
    s = height / 1.80  # 1.80 bazaviy model
    m_robe = mat("robe", robe_color or PALETTE["robe"], rough=0.92, spec=0.10,
                 noise_scale=3.0, noise_amount=0.35, second=(0.72, 0.70, 0.62))
    m_turban = mat("turban", turban_color or PALETTE["turban"], rough=0.88, spec=0.14,
                   noise_scale=4.0, noise_amount=0.30, second=(0.80, 0.78, 0.72))
    m_skin = mat("skin", PALETTE["skin"], rough=0.65, spec=0.25)
    m_sash = mat("sash", (0.55, 0.42, 0.26), rough=0.9, spec=0.1)

    parts = {}

    # --- jellya (tana) ---
    profile = [
        (0.00, 0.335), (0.04, 0.345), (0.10, 0.330), (0.35, 0.300),
        (0.75, 0.270), (1.05, 0.262), (1.25, 0.292), (1.38, 0.255),
        (1.45, 0.135), (1.47, 0.105),
    ]
    profile = [(z * s, r * s) for z, r in profile]
    robe = _add_mesh(_lathe(profile, 24), name + "_robe", coll, m_robe)
    parts["robe"] = robe

    # --- belbog' ---
    belt = _sphere(name + "_belt", coll, m_sash, 0.268 * s, (0, 0, 1.02 * s),
                   segments=20, rings=8, scale=(1.0, 1.0, 0.16))
    parts["belt"] = belt

    # --- bo'yin + bosh ---
    neck = _sphere(name + "_neck", coll, m_skin, 0.075 * s, (0, 0, 1.47 * s),
                   segments=12, rings=8, scale=(1, 1, 1.3))
    parts["neck"] = neck
    head = _sphere(name + "_head", coll, m_skin, 0.108 * s, (0, 0, 1.585 * s),
                   segments=20, rings=14, scale=(0.95, 1.0, 1.12))
    parts["head"] = head

    # --- YUZ (ko'z, qosh, burun, lab, soqol) — front = +Y ---
    m_dark = mat("face_dark", (0.085, 0.062, 0.052), rough=0.55, spec=0.3)
    m_eye = mat("eye_white", (0.94, 0.93, 0.90), rough=0.35, spec=0.5)
    m_pupil = mat("pupil", (0.045, 0.035, 0.030), rough=0.25, spec=0.6)
    m_beard = mat("beard", (0.115, 0.098, 0.088), rough=0.95, spec=0.05)
    fy = 0.093 * s          # yuz tekisligi (+Y = modelning oldi)
    hz = 1.585 * s          # bosh markazi balandligi
    for side, sx in (("L", 1), ("R", -1)):
        eye = _sphere(f"{name}_eye{side}", coll, m_eye, 0.0225 * s,
                      (sx * 0.040 * s, fy, hz + 0.012 * s), segments=12, rings=10,
                      scale=(1.0, 0.55, 0.85))
        parts[f"eye{side}"] = eye
        pup = _sphere(f"{name}_pupil{side}", coll, m_pupil, 0.0115 * s,
                      (sx * 0.040 * s, fy + 0.012 * s, hz + 0.012 * s), segments=10, rings=8,
                      scale=(1.0, 0.5, 1.0))
        parts[f"pupil{side}"] = pup
        brow = _sphere(f"{name}_brow{side}", coll, m_dark, 0.020 * s,
                       (sx * 0.042 * s, fy - 0.004 * s, hz + 0.043 * s), segments=10, rings=6,
                       scale=(1.25, 0.45, 0.30))
        brow.rotation_euler = Euler((0, math.radians(sx * -8), 0))
        parts[f"brow{side}"] = brow
    nose = _sphere(f"{name}_nose", coll, m_skin, 0.020 * s,
                   (0, fy + 0.008 * s, hz - 0.010 * s), segments=10, rings=8,
                   scale=(0.8, 1.0, 1.1))
    parts["nose"] = nose
    mouth = _sphere(f"{name}_mouth", coll, m_dark, 0.019 * s,
                    (0, fy + 0.004 * s, hz - 0.043 * s), segments=10, rings=6,
                    scale=(1.5, 0.4, 0.55))
    parts["mouth"] = mouth
    beard = _sphere(f"{name}_beard", coll, m_beard, 0.086 * s,
                    (0, 0.062 * s, hz - 0.072 * s), segments=16, rings=12,
                    scale=(1.02, 0.80, 1.05))
    parts["beard"] = beard
    # bosh kiyim ostidagi soch chizig'i
    hair = _sphere(f"{name}_hair", coll, m_beard, 0.104 * s,
                   (0, -0.010 * s, hz + 0.030 * s), segments=16, rings=10,
                   scale=(1.0, 1.0, 0.62))
    parts["hair"] = hair

    # --- salla ---
    turban = _sphere(name + "_turban", coll, m_turban, 0.148 * s, (0, 0, 1.685 * s),
                     segments=20, rings=12, scale=(1.0, 1.0, 0.82))
    parts["turban"] = turban
    # salla o'rami (halqa)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=20,
                          radius1=0.152 * s, radius2=0.148 * s, depth=0.035 * s)
    band = _add_mesh(bm, name + "_turban_band", coll, m_turban)
    band.location = (0, 0, 1.625 * s)
    parts["turban_band"] = band
    # yelka ustidagi mato (yelka yopinchig'i)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, cap_tris=False, segments=22,
                          radius1=0.30 * s, radius2=0.13 * s, depth=0.30 * s)
    mantle = _add_mesh(bm, name + "_mantle", coll, m_robe)
    mantle.location = (0, 0, 1.33 * s)
    parts["mantle"] = mantle

    # --- qo'llar ---
    for side, sx in (("L", 1), ("R", -1)):
        bm = bmesh.new()
        # yeng
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=12,
                              radius1=0.085 * s, radius2=0.055 * s, depth=0.50 * s)
        upper = _add_mesh(bm, f"{name}_sleeve{side}", coll, m_robe)
        upper.location = (sx * 0.275 * s, 0, 1.15 * s)
        upper.rotation_euler = Euler((0, math.radians(sx * -6), 0))
        parts[f"sleeve{side}"] = upper

        hand = _sphere(f"{name}_hand{side}", coll, m_skin, 0.052 * s,
                       (sx * 0.30 * s, 0, 0.88 * s), segments=10, rings=8,
                       scale=(1, 0.9, 1.2))
        parts[f"hand{side}"] = hand

    # --- oyoq uchlari (jellya ostidan) ---
    for side, sx in (("L", 1), ("R", -1)):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        foot = _add_mesh(bm, f"{name}_foot{side}", coll, m_sash, smooth=False)
        foot.scale = (0.075 * s, 0.13 * s, 0.035 * s)
        foot.location = (sx * 0.10 * s, 0.05 * s, 0.025 * s)
        parts[f"foot{side}"] = foot

    # ---------------- SKELET ----------------
    arm_data = bpy.data.armatures.new(name + "_arm")
    arm = bpy.data.objects.new(name + "_rig", arm_data)
    coll.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones

    def bone(nm, head_v, tail_v, parent=None):
        b = eb.new(nm)
        b.head = Vector(head_v)
        b.tail = Vector(tail_v)
        if parent:
            b.parent = parent
        return b

    b_root = bone("root", (0, 0, 0), (0, 0, 0.10 * s))
    b_hips = bone("hips", (0, 0, 0.85 * s), (0, 0, 0.98 * s), b_root)
    b_spine = bone("spine", (0, 0, 0.98 * s), (0, 0, 1.42 * s), b_hips)
    b_head = bone("head", (0, 0, 1.42 * s), (0, 0, 1.80 * s), b_spine)
    b_armL = bone("arm.L", (0.275 * s, 0, 1.36 * s), (0.30 * s, 0, 0.86 * s), b_spine)
    b_armR = bone("arm.R", (-0.275 * s, 0, 1.36 * s), (-0.30 * s, 0, 0.86 * s), b_spine)
    bpy.ops.object.mode_set(mode='OBJECT')

    # --- bog'lash (rigid weighting) ---
    mapping = {
        "hips": ["robe", "footL", "footR"],
        "spine": ["belt", "mantle"],
        "head": ["head", "neck", "turban", "turban_band", "eyeL", "eyeR", "pupilL",
                 "pupilR", "browL", "browR", "nose", "mouth", "beard", "hair"],
        "arm.L": ["sleeveL", "handL"],
        "arm.R": ["sleeveR", "handR"],
    }
    for bone_name, part_names in mapping.items():
        for pn in part_names:
            ob = parts.get(pn)
            if not ob:
                continue
            vg = ob.vertex_groups.get(bone_name) or ob.vertex_groups.new(name=bone_name)
            vg.add(range(len(ob.data.vertices)), 1.0, 'REPLACE')
            md = ob.modifiers.new("Armature", 'ARMATURE')
            md.object = arm
            ob.parent = arm

    root = bpy.data.objects.new(name + "_root", None)
    coll.objects.link(root)
    arm.parent = root

    # muhim: edit-mode bone'lari emas, POSE bone'lari kerak
    pb = {n: arm.pose.bones[n] for n in ("hips", "spine", "head", "arm.L", "arm.R")}
    return {"root": root, "rig": arm, "parts": parts, "bones": pb}


# ============================================================================
# POZALAR / ANIMATSIYA
# ============================================================================
def kb(pb, frame, rot=None, loc=None):
    if rot is not None:
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = Euler(rot)
        pb.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        pb.location = Vector(loc)
        pb.keyframe_insert("location", frame=frame)


def anim_idle(man, f0=1, f1=96, breath=0.012):
    """Tinch turish: yengil nafas, bosh va tana tebranishi."""
    b = man["bones"]
    for f, k in ((f0, 0), ((f0 + f1) // 2, 1), (f1, 0)):
        x = math.sin(k * math.pi)
        kb(b["spine"], f, rot=(x * breath, 0, x * 0.006))
        kb(b["head"], f, rot=(x * breath * 0.6, 0, x * 0.05))
        kb(b["arm.L"], f, rot=(x * 0.05, 0, 0))
        kb(b["arm.R"], f, rot=(-x * 0.05, 0, 0))


def anim_walk(man, start=(0, -3, 0), end=(0, 3, 0), f0=1, f1=120, steps=4):
    """Joyida yurish: tana tebranishi, qo'l siltanishi, oldinga siljish."""
    b = man["bones"]
    rig = man["rig"]
    root = man["root"]
    root.location = Vector(start)
    root.keyframe_insert("location", frame=f0)
    root.location = Vector(end)
    root.keyframe_insert("location", frame=f1)
    # yo'nalish bo'ylab burilish
    d = Vector(end) - Vector(start)
    yaw = math.atan2(-d.x, d.y) if d.length > 1e-5 else 0.0
    root.rotation_euler = Euler((0, 0, yaw))
    root.keyframe_insert("rotation_euler", frame=f0)

    n = max(8, int((f1 - f0) / max(1, steps)))
    for i in range(steps * 2 + 1):
        f = f0 + (f1 - f0) * i / (steps * 2)
        ph = math.sin(i * math.pi / 2)
        kb(b["hips"], int(f), rot=(0, ph * 0.05, ph * 0.03))
        kb(b["spine"], int(f), rot=(ph * 0.02, 0, -ph * 0.02))
        kb(b["arm.L"], int(f), rot=(ph * 0.38, 0, 0))
        kb(b["arm.R"], int(f), rot=(-ph * 0.38, 0, 0))
        kb(b["head"], int(f), rot=(0, 0, -ph * 0.03))


def anim_kneel(man, f0=1, f1=60):
    """Tiz cho'kish (masalan duo qilayotganda)."""
    b = man["bones"]
    kb(b["hips"], f0, loc=(0, 0, -0.30), rot=(0.35, 0, 0))
    kb(b["spine"], f0, rot=(-0.28, 0, 0))
    kb(b["head"], f0, rot=(-0.10, 0, 0))
    kb(b["arm.L"], f0, rot=(0.55, 0, 0))
    kb(b["arm.R"], f0, rot=(0.55, 0, 0))
    kb(b["head"], f1, rot=(-0.22, 0, 0))


def anim_reach(man, f0=1, f1=48, side="L"):
    """Qo'l uzatish (meva uzish)."""
    b = man["bones"]
    kb(b["arm." + side], f0, rot=(0, 0, 0))
    kb(b["arm." + side], f0 + (f1 - f0) // 2, rot=(-1.25, 0, 0))
    kb(b["arm." + side], f1, rot=(-0.30, 0, 0))
    kb(b["spine"], f0 + (f1 - f0) // 2, rot=(-0.08, 0, 0))
    kb(b["head"], f0 + (f1 - f0) // 2, rot=(-0.25, 0, 0))


def set_shadow_catch(obj):
    obj.is_shadow_catcher = True
