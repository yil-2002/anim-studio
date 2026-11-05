"""
lib_fx.py — Muhit effektlari: havoda uchayotgan chang/zarra, quyosh nurlari,
tushayotgan barglar. Referens videoning "sehrli" hissini beradi.
"""
import bpy
import bmesh
import math
import random
from mathutils import Vector


def dust_motes(coll, count=70, area=(14, 14, 6), center=(0, 0, 2.0), seed=4,
               color=(1.0, 0.86, 0.58), strength=3.0, size=0.011):
    rnd = random.Random(seed)
    m = bpy.data.materials.new("dust")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])

    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=size)
    me = bpy.data.meshes.new("dustmesh")
    bm.to_mesh(me); bm.free()
    me.materials.append(m)

    objs = []
    for i in range(count):
        ob = bpy.data.objects.new(f"dust{i}", me)
        coll.objects.link(ob)
        ob.visible_shadow = False
        sx = rnd.uniform(-area[0] / 2, area[0] / 2)
        sy = rnd.uniform(-area[1] / 2, area[1] / 2)
        sz = rnd.uniform(0.2, area[2])
        ob.location = (center[0] + sx, center[1] + sy, center[2] + sz * 0.35)
        sc = rnd.uniform(0.5, 2.2)
        ob.scale = (sc, sc, sc)
        for axis in (0, 1, 2):
            fc = ob.driver_add("location", axis)
            amp = rnd.uniform(0.15, 0.55)
            spd = rnd.uniform(0.02, 0.07)
            ph = rnd.uniform(0, 6.28)
            base = ob.location[axis]
            fc.driver.expression = f"{base:.3f}+{amp:.3f}*sin(frame*{spd:.4f}+{ph:.2f})"
        objs.append(ob)
    return objs


def falling_leaves(coll, count=14, area=(8, 8), z0=4.0, seed=7,
                   color=(0.42, 0.34, 0.14)):
    rnd = random.Random(seed)
    m = bpy.data.materials.new("leaf_fx")
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = 0.8

    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.055)
    me = bpy.data.meshes.new("leafmesh"); bm.to_mesh(me); bm.free()
    me.materials.append(m)

    objs = []
    for i in range(count):
        ob = bpy.data.objects.new(f"leaf{i}", me)
        coll.objects.link(ob)
        x = rnd.uniform(-area[0] / 2, area[0] / 2)
        y = rnd.uniform(-area[1] / 2, area[1] / 2)
        ob.location = (x, y, z0)
        ob.rotation_euler = (rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3))
        span = rnd.uniform(90, 200)
        ph = rnd.uniform(0, span)
        # pastga tushish + yon tebranish + aylanish
        for axis in (0, 1, 2):
            fc = ob.driver_add("location", axis)
            base = ob.location[axis]
            if axis == 2:
                fc.driver.expression = f"{z0:.2f}-mod(frame+{ph:.1f},{span:.1f})*{z0/span:.4f}"
            else:
                fc.driver.expression = (
                    f"{base:.3f}+0.5*sin(mod(frame+{ph:.1f},{span:.1f})*0.06+{base:.2f})")
        for axis, amt, spd in ((0, 0.9, 0.03), (1, 0.7, 0.045), (2, 0.5, 0.025)):
            fc = ob.driver_add("rotation_euler", axis)
            fc.driver.expression = f"{amt:.2f}*sin(frame*{spd:.3f}+{ph:.1f})"
        objs.append(ob)
    return objs


def light_shaft(coll, location=(0, 4, 6), rotation=(0, 0, 0), scale=(3.5, 3.5, 9.0),
                opacity=0.10, color=(1.0, 0.86, 0.6)):
    """Quyosh nurining yumshoq ustuni (additive)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16,
                          radius1=0.35, radius2=1.0, depth=2.0)
    me = bpy.data.meshes.new("shaft"); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new("LightShaft", me)
    coll.objects.link(ob)
    ob.location = location
    ob.rotation_euler = rotation
    ob.scale = scale
    ob.visible_shadow = False

    m = bpy.data.materials.new("shaft_mat")
    m.use_nodes = True
    m.blend_method = 'BLEND'
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = 1.2
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    mx.inputs[0].default_value = 1.0 - opacity
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    me.materials.append(m)
    return ob
