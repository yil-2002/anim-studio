"""
lib_nature.py — Procedural tabiat: yer, anor daraxti, o't, tepaliklar, bulut, quyosh.
Hammasi kod bilan quriladi — hech qanday tashqi model fayl kerak emas.
"""
import bpy
import bmesh
import math
import random
from mathutils import Vector, noise
from lib_style import mat, PALETTE


# ============================================================================
# GEOMETRIYA YORDAMCHILARI
# ============================================================================
def _obj_from_bm(bm, name, collection, material=None, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    if material:
        ob.data.materials.append(material)
    return ob


def _bmesh_ico(radius=1.0, subdiv=2):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    return bm


def blob(radius, subdiv=2, irregular=0.30, seed=0, squash=(1, 1, 1)):
    """Noto'g'ri shakldagi 'klaster' — barg to'pi, bulut, tosh uchun."""
    rnd = random.Random(seed)
    bm = _bmesh_ico(radius, subdiv)
    off = Vector((rnd.uniform(-50, 50), rnd.uniform(-50, 50), rnd.uniform(-50, 50)))
    for v in bm.verts:
        n = v.co.normalized()
        d = noise.noise(v.co * 1.7 + off)
        v.co += n * (d * irregular * radius)
        v.co.x *= squash[0]
        v.co.y *= squash[1]
        v.co.z *= squash[2]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def _merge_bm(dst, src, offset=(0, 0, 0), scale=1.0):
    """src bmesh'ni dst ga ko'chirib qo'shadi (xotira tejash uchun birlashtirish)."""
    off = Vector(offset)
    vmap = {}
    for v in src.verts:
        vmap[v] = dst.verts.new(v.co * scale + off)
    dst.verts.index_update()
    for f in src.faces:
        try:
            dst.faces.new([vmap[v] for v in f.verts])
        except ValueError:
            pass
    src.free()

def _taper_segment(bm, p0, p1, r0, r1, segs=8):
    """Ikki nuqta orasida konus / silindr ko'rinishidagi bo'g'in."""
    p0 = Vector(p0)
    p1 = Vector(p1)
    axis = (p1 - p0)
    L = axis.length
    if L < 1e-6:
        return
    axis = axis / L
    up = Vector((0, 0, 1))
    if abs(axis.dot(up)) > 0.99:
        up = Vector((1, 0, 0))
    side = axis.cross(up).normalized()
    side2 = axis.cross(side).normalized()

    ring0, ring1 = [], []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        d = side * math.cos(a) + side2 * math.sin(a)
        ring0.append(bm.verts.new(p0 + d * r0))
        ring1.append(bm.verts.new(p1 + d * r1))
    for i in range(segs):
        j = (i + 1) % segs
        bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i]))
    # qopqoqlar
    if r1 > 1e-4:
        bm.faces.new(ring1)
    if r0 > 1e-4:
        bm.faces.new(list(reversed(ring0)))


# ============================================================================
# YER
# ============================================================================
def make_ground(coll, name="Ground", size=90, dry=False, color=None):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=40, y_segments=40, size=size / 2)
    for v in bm.verts:
        d = math.hypot(v.co.x, v.co.y)
        v.co.z = noise.noise(Vector((v.co.x * 0.06, v.co.y * 0.06, 0.3))) * 0.55
        if dry:
            v.co.z += noise.noise(Vector((v.co.x * 0.5, v.co.y * 0.5, 2.0))) * 0.05
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    c1 = color or (PALETTE["dirt"] if dry else PALETTE["ground"])
    c2 = (0.395, 0.345, 0.170) if not dry else (0.330, 0.255, 0.150)
    m = mat(f"ground_{name}", c1, rough=0.95, spec=0.06,
            noise_scale=0.55, noise_amount=0.30, second=c2)
    return _obj_from_bm(bm, name, coll, m)


def make_grass_tufts(coll, count=260, radius=16, height=0.30, color=None, seed=1):
    """Yer usti o'tlari — mayda uchburchak 'tutam'lar."""
    rnd = random.Random(seed)
    bm = bmesh.new()
    for _ in range(count):
        a = rnd.uniform(0, math.tau)
        r = radius * math.sqrt(rnd.random())
        x, y = math.cos(a) * r, math.sin(a) * r
        z = noise.noise(Vector((x * 0.06, y * 0.06, 0.3))) * 0.55
        h = height * rnd.uniform(0.6, 1.5)
        w = h * 0.10
        n_blades = rnd.randint(2, 3)
        for b in range(n_blades):
            ox = rnd.uniform(-0.09, 0.09)
            oy = rnd.uniform(-0.09, 0.09)
            tilt = Vector((rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), 0))
            v0 = bm.verts.new((x + ox - w, y + oy, z))
            v1 = bm.verts.new((x + ox + w, y + oy, z))
            v2 = bm.verts.new((x + ox + tilt.x, y + oy + tilt.y, z + h))
            bm.faces.new((v0, v1, v2))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    m = mat("grass", color or PALETTE["grass"], rough=0.9, spec=0.1)
    ob = _obj_from_bm(bm, "Grass", coll, m, smooth=False)
    ob.visible_shadow = False
    return ob


# ============================================================================
# DARAXT
# ============================================================================
def make_tree(coll, name="Tree", loc=(0, 0, 0), height=3.2, canopy=1.0,
              fruit=0, dry=False, seed=0, spread=0.55, subdiv=2):
    """
    Anor daraxti: qayrilgan tanasi, 3-5 shox, bir necha barg to'pi, mevalar.
    Qaytaradi: dict(obj=..., canopy_objs=[...], fruit_objs=[...])
    """
    rnd = random.Random(seed)
    objs = []
    bm_trunk = bmesh.new()

    # --- tana (2-3 bo'g'in, yengil qayrilgan) ---
    base = Vector(loc)
    p = base.copy()
    trunk_h = height * 0.42
    rad = height * 0.055
    lean = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), 0)) * height * 0.07
    n_seg = 3
    for i in range(n_seg):
        t = (i + 1) / n_seg
        nxt = base + Vector((0, 0, trunk_h * t)) + lean * (t ** 1.6)
        nxt.x += math.sin(t * 3 + seed) * height * 0.02
        _taper_segment(bm_trunk, p, nxt, rad * (1 - 0.28 * i), rad * (1 - 0.28 * (i + 1)), 8)
        # ildiz/shox chiqishlar
        p = nxt

    tips = [p.copy()]
    # --- shoxlar ---
    n_branch = rnd.randint(3, 5)
    for b in range(n_branch):
        a = math.tau * b / n_branch + rnd.uniform(-0.4, 0.4)
        L = height * rnd.uniform(0.30, 0.46) * spread / 0.55
        r0 = rad * 0.55
        r1 = rad * 0.18
        mid = p + Vector((math.cos(a) * L * 0.45, math.sin(a) * L * 0.45, L * 0.42))
        end = p + Vector((math.cos(a) * L, math.sin(a) * L, L * 0.78))
        _taper_segment(bm_trunk, p, mid, r0, r0 * 0.7, 7)
        _taper_segment(bm_trunk, mid, end, r0 * 0.7, r1, 7)
        tips.append(end)
        # ikkinchi darajali shoxcha
        if rnd.random() < 0.7:
            a2 = a + rnd.uniform(-0.9, 0.9)
            L2 = L * rnd.uniform(0.35, 0.6)
            end2 = end + Vector((math.cos(a2) * L2, math.sin(a2) * L2, L2 * 0.55))
            _taper_segment(bm_trunk, end, end2, r1, r1 * 0.5, 6)
            tips.append(end2)

    bmesh.ops.recalc_face_normals(bm_trunk, faces=bm_trunk.faces)
    m_trunk = mat("trunk", PALETTE["trunk"], rough=0.95, spec=0.05,
                  noise_scale=8.0, noise_amount=0.45, second=(0.32, 0.24, 0.15))
    trunk = _obj_from_bm(bm_trunk, name + "_trunk", coll, m_trunk)
    objs.append(trunk)

    # --- barg to'plari ---
    if dry:
        leaf_col, leaf_col2 = PALETTE["leaf_dry"], (0.50, 0.40, 0.18)
        n_clusters = max(4, len(tips))
    else:
        leaf_col, leaf_col2 = PALETTE["leaf_a"], PALETTE["leaf_b"]
        n_clusters = int(len(tips) * 1.9) + 3

    m_leaf = mat(f"leaf_{name}", leaf_col, rough=0.75, spec=0.15,
                 noise_scale=6.0, noise_amount=0.7, second=leaf_col2)

    canopy_bm = bmesh.new()
    canopy_centers = []
    for i in range(n_clusters):
        if i < len(tips):
            c = tips[i]
        else:
            c = p + Vector((rnd.uniform(-1, 1) * canopy * 0.7,
                            rnd.uniform(-1, 1) * canopy * 0.7,
                            rnd.uniform(0, 1) * canopy * 0.5))
        r = canopy * rnd.uniform(0.42, 0.78) * (height * 0.19)
        bsub = 2 if subdiv >= 2 else 1
        bm = blob(r, subdiv=bsub, irregular=0.55, seed=seed * 31 + i,
                  squash=(1.15, 1.1, 0.78))
        pos = c + Vector((rnd.uniform(-0.34, 0.34), rnd.uniform(-0.34, 0.34),
                          rnd.uniform(-0.26, 0.30)))
        _merge_bm(canopy_bm, bm, offset=pos - Vector(loc))
        canopy_centers.append(pos)
    bmesh.ops.recalc_face_normals(canopy_bm, faces=canopy_bm.faces)
    canopy_obj = _obj_from_bm(canopy_bm, f"{name}_canopy", coll, m_leaf)
    canopy_obj.location = Vector(loc)
    objs.append(canopy_obj)
    canopy_objs = [canopy_obj]

    # --- mevalar ---
    fruit_objs = []
    if fruit > 0:
        m_fruit = mat("fruit", PALETTE["fruit"], rough=0.35, spec=0.6)
        fr = height * 0.045
        fbm = bmesh.new()
        for i in range(fruit):
            c = rnd.choice(tips) if tips else p
            ang = rnd.uniform(0, math.tau)
            rr = canopy * (0.55 + rnd.random() * 0.55) * height * 0.19
            pos = c + Vector((math.cos(ang) * rr, math.sin(ang) * rr,
                              rnd.uniform(-0.55, 0.15) * canopy))
            sb = bmesh.new()
            bmesh.ops.create_uvsphere(sb, u_segments=14, v_segments=9, radius=fr)
            _merge_bm(fbm, sb, offset=pos - Vector(loc))
        bmesh.ops.recalc_face_normals(fbm, faces=fbm.faces)
        fobj = _obj_from_bm(fbm, f"{name}_fruit", coll, m_fruit)
        fobj.location = Vector(loc)
        objs.append(fobj)
        fruit_objs = [fobj]

    return {"objs": objs, "trunk": trunk, "canopy": canopy_objs, "fruit": fruit_objs}


def add_wind(tree, strength=0.035, seed=0):
    """Barglarga 'shamol' — driver orqali, keyframe kerak emas (arzon)."""
    for i, ob in enumerate(tree["canopy"]):
        ph = 1.3 * i + seed
        fc = ob.driver_add("rotation_euler", 1)
        fc.driver.expression = f"{strength:.4f}*sin(frame*0.09+{ph:.2f})"
        fc2 = ob.driver_add("rotation_euler", 0)
        fc2.driver.expression = f"{strength*0.6:.4f}*sin(frame*0.07+{ph*1.7:.2f})"


# ============================================================================
# FON: tepaliklar, uzoq daraxtlar, bulutlar, quyosh diski
# ============================================================================
def make_hills(coll, count=5, radius=72, seed=5):
    rnd = random.Random(seed)
    m = mat("hill", (0.10, 0.155, 0.140), rough=1.0, spec=0.0, emit=0.25)
    out = []
    for i in range(count):
        a = math.pi * (0.08 + 0.84 * i / max(1, count - 1))
        d = radius * rnd.uniform(0.75, 1.05)
        bm = blob(1.0, subdiv=2, irregular=0.10, seed=i, squash=(1, 1, 1))
        ob = _obj_from_bm(bm, f"hill{i}", coll, m)
        ob.location = (math.cos(a) * d, math.sin(a) * d, -11 + rnd.uniform(-1, 1))
        ob.scale = (rnd.uniform(20, 30), rnd.uniform(14, 20), rnd.uniform(9, 14))
        out.append(ob)
    return out


def make_far_trees(coll, count=26, radius=30, seed=9, dry=False):
    rnd = random.Random(seed)
    m = mat("far_leaf", (0.16, 0.26, 0.16) if not dry else (0.34, 0.28, 0.16),
            rough=0.9, spec=0.05, emit=0.2)
    mtr = mat("far_trunk", PALETTE["trunk"], rough=1.0, spec=0.02, emit=0.1)
    out = []
    for i in range(count):
        a = rnd.uniform(0, math.tau)
        d = radius * rnd.uniform(0.55, 1.0)
        h = rnd.uniform(2.4, 4.2)
        x, y = math.cos(a) * d, math.sin(a) * d
        bm = bmesh.new()
        _taper_segment(bm, (0, 0, 0), (0, 0, h * 0.50), 0.16, 0.10, 6)
        ob = _obj_from_bm(bm, f"ft{i}", coll, mtr)
        ob.location = (x, y, 0)
        bm2 = blob(h * 0.27, subdiv=2, irregular=0.45, seed=i, squash=(1.15, 1.1, 0.95))
        ob2 = _obj_from_bm(bm2, f"fl{i}", coll, m)
        ob2.location = (x, y, h * 0.68)
        out += [ob, ob2]
    return out


def make_clouds(coll, count=7, seed=3, height=16, radius=40):
    rnd = random.Random(seed)
    m = mat("cloud", (0.98, 0.86, 0.66), rough=1.0, spec=0.0, emit=1.6)
    out = []
    for i in range(count):
        a = math.pi * rnd.uniform(0.05, 0.95)
        d = radius * rnd.uniform(0.7, 1.15)
        bm = blob(1.0, subdiv=2, irregular=0.22, seed=100 + i, squash=(1.9, 1.0, 0.42))
        ob = _obj_from_bm(bm, f"cloud{i}", coll, m)
        ob.location = (math.cos(a) * d, math.sin(a) * d, height + rnd.uniform(-3, 5))
        s = rnd.uniform(2.5, 6.0)
        ob.scale = (s, s, s * 0.7)
        out.append(ob)
    return out


def make_sun(coll, direction=(0.35, -1.0, 0.22), distance=70, size=5.0):
    """Yorqin quyosh diski — Glare (bloom) bilan birga chiroyli nur beradi."""
    d = Vector(direction).normalized()
    m = bpy.data.materials.new("sun_disc")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.92, 0.72, 1)
    em.inputs["Strength"].default_value = 22.0
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=size)
    ob = _obj_from_bm(bm, "SunDisc", coll, m)
    ob.location = d * distance
    ob.visible_shadow = False
    return ob


def make_water(coll, y=8, width=60, length=60, z=-0.35):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1)
    m = bpy.data.materials.new("water")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*PALETTE["water"], 1)
    bsdf.inputs["Roughness"].default_value = 0.06
    bsdf.inputs["Metallic"].default_value = 0.85
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    ob = _obj_from_bm(bm, "Water", coll, m, smooth=True)
    ob.location = (0, y, z)
    ob.scale = (width / 2, length / 2, 1)
    return ob


def make_sky_dome(coll, radius=220, horizon=(1.00, 0.60, 0.26),
                  zenith=(0.016, 0.080, 0.110), mid=(0.055, 0.190, 0.215),
                  strength=0.75, sun_dir=(0.35, -1.0, 0.24)):
    """Osmon gumbazi: haqiqiy geometriya + emission gradient.
    World node'lariga bog'liq emas — har qanday kamerada bir xil chiqadi."""
    import bmesh
    from mathutils import Vector as _V

    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=radius)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    me = bpy.data.meshes.new("skydome")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("SkyDome", me)
    coll.objects.link(ob)
    # MUHIM: gumbaz faqat KAMERAGA ko'rinadi — yorug'lik manbai emas (aks holda render osilib qoladi)
    ob.visible_shadow = False
    ob.visible_diffuse = False
    ob.visible_glossy = False
    ob.visible_transmission = False
    ob.visible_volume_scatter = False

    m = bpy.data.materials.new("skydome_mat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength

    tc = nt.nodes.new("ShaderNodeTexCoord")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -0.02
    mr.inputs["From Max"].default_value = 0.42
    mr.clamp = True
    sepxyz = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sepxyz.inputs["Vector"])
    nt.links.new(sepxyz.outputs["Z"], mr.inputs["Value"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = 'EASE'
    cr.elements[0].position = 0.0
    cr.elements[0].color = (*horizon, 1)
    cr.elements[1].position = 1.0
    cr.elements[1].color = (*zenith, 1)
    for pos, col in ((0.14, (0.98, 0.47, 0.17)),
                     (0.36, (0.30, 0.34, 0.26)),
                     (0.60, mid)):
        e = cr.elements.new(pos)
        e.color = (*col, 1)
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])

    # quyosh halqasi
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = _V(sun_dir).normalized()
    nt.links.new(geo.outputs["Incoming"], dot.inputs[0])
    mr2 = nt.nodes.new("ShaderNodeMapRange")
    mr2.inputs["From Min"].default_value = 0.90
    mr2.inputs["From Max"].default_value = 1.0
    mr2.clamp = True
    nt.links.new(dot.outputs["Value"], mr2.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = 'ADD'
    mix.inputs["Color2"].default_value = (1.0, 0.70, 0.34, 1)
    nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(mr2.outputs["Result"], mix.inputs["Fac"])

    nt.links.new(mix.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    me.materials.append(m)
    ob.location = (0, 0, 0)
    return ob
