"""
lib_style.py — Umumiy uslub, materiallar, osmon, render sozlamalari.
Behsar uslubidagi "golden hour / teal-gold" 3D illyustratsiya ko'rinishi.
"""
import bpy
import math
from mathutils import Vector

# ----------------------------------------------------------------------------
# PALITRA  (ranglar sRGB 0..1, sahnada to'g'ridan-to'g'ri ishlatiladi)
# ----------------------------------------------------------------------------
PALETTE = {
    "sky_top":      (0.055, 0.170, 0.190),
    "sky_mid":      (0.230, 0.400, 0.360),
    "sky_horizon":  (0.980, 0.760, 0.420),
    "sun":          (1.000, 0.880, 0.620),
    "fog":          (0.560, 0.520, 0.330),
    "ground":       (0.330, 0.300, 0.150),
    "ground_dark":  (0.150, 0.170, 0.095),
    "grass":        (0.290, 0.380, 0.135),
    "trunk":        (0.180, 0.120, 0.075),
    "leaf_a":       (0.130, 0.290, 0.150),
    "leaf_b":       (0.290, 0.430, 0.180),
    "leaf_dry":     (0.360, 0.290, 0.130),
    "fruit":        (0.640, 0.075, 0.090),
    "robe":         (0.900, 0.880, 0.820),
    "turban":       (0.940, 0.930, 0.890),
    "skin":         (0.700, 0.500, 0.360),
    "dirt":         (0.260, 0.190, 0.110),
    "water":        (0.070, 0.240, 0.270),
}


def hexcol(c):
    return Vector(tuple(c)[:3])


# ----------------------------------------------------------------------------
# MATERIAL
# ----------------------------------------------------------------------------
def mat(name, color, rough=0.85, spec=0.25, emit=0.0, noise_scale=0.0,
        noise_amount=0.18, second=None):
    """Oddiy, "flat/painterly" material. Ixtiyoriy ravishda ikki rang
    orasida noise bilan aralashtirish (barg/to'qimalar uchun)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    if emit > 0:
        key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        bsdf.inputs[key].default_value = (*color, 1)
        bsdf.inputs["Emission Strength"].default_value = emit

    if noise_scale > 0 and second is not None:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = noise_scale
        nz.inputs["Detail"].default_value = 4.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.42
        ramp.color_ramp.elements[1].position = 0.62
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = 'MIX'
        mix.inputs["Fac"].default_value = noise_amount
        mix.inputs["Color1"].default_value = (*color, 1)
        mix.inputs["Color2"].default_value = (*second, 1)
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], mix.inputs["Fac"])
        nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])

    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.diffuse_color = (*color, 1)
    return m


# ----------------------------------------------------------------------------
# OSMON / WORLD — ekran bo'ylab vertikal gradient + quyosh nuri
# ----------------------------------------------------------------------------
def setup_world(scene, sun_dir=(0.35, -1.0, 0.22), warmth=1.0, horizon=None, top=None):
    w = bpy.data.worlds.new("SKY")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0

    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Window"], sep.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = 'EASE'
    top_c = top or PALETTE["sky_top"]
    hor_c = horizon or PALETTE["sky_horizon"]
    cr.elements[0].position = 0.30
    cr.elements[0].color = (*top_c, 1)
    cr.elements[1].position = 0.72
    cr.elements[1].color = (*hor_c, 1)
    e = cr.elements.new(0.52)
    e.color = (*PALETTE["sky_mid"], 1)
    e2 = cr.elements.new(0.84)
    e2.color = (*(hexcol(hor_c) * 0.55), 1)

    nt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])

    # quyosh yo'nalishidagi yumshoq yorug'lik dog'i
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = Vector(sun_dir).normalized()
    nt.links.new(geo.outputs["Incoming"], dot.inputs[0])

    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.55
    mr.inputs["From Max"].default_value = 1.0
    nt.links.new(dot.outputs["Value"], mr.inputs["Value"])

    glow = nt.nodes.new("ShaderNodeMixRGB")
    glow.blend_type = 'ADD'
    glow.inputs["Fac"].default_value = 0.55 * warmth
    glow.inputs["Color2"].default_value = (*PALETTE["sun"], 1)
    nt.links.new(ramp.outputs["Color"], glow.inputs["Color1"])
    nt.links.new(mr.outputs["Result"], glow.inputs["Fac"])

    nt.links.new(glow.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return w


# ----------------------------------------------------------------------------
# YORUG'LIK
# ----------------------------------------------------------------------------
def setup_lights(sun_dir=(0.35, -1.0, 0.22), energy=3.4, warm=1.0):
    d = Vector(sun_dir).normalized()
    light_data = bpy.data.lights.new("SUN", type='SUN')
    light_data.energy = energy
    light_data.angle = math.radians(6.0)
    light_data.color = (1.0, 0.86 * warm, 0.66)
    sun = bpy.data.objects.new("SUN", light_data)
    bpy.context.collection.objects.link(sun)
    sun.location = d * 20
    sun.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    return sun


# ----------------------------------------------------------------------------
# RENDER SOZLAMALARI
# ----------------------------------------------------------------------------
def setup_render(scene, res=(720, 1280), samples=4, fps=24, mist=True,
                 view_transform='Standard'):
    r = scene.render
    r.resolution_x, r.resolution_y = res
    r.resolution_percentage = 100
    r.fps = fps
    r.image_settings.file_format = 'PNG'
    r.image_settings.color_mode = 'RGB'
    r.image_settings.compression = 40
    r.film_transparent = False
    r.threads_mode = 'AUTO'

    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 3
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 1
    scene.cycles.transmission_bounces = 1
    scene.cycles.volume_bounces = 0
    scene.cycles.transparent_max_bounces = 4
    scene.cycles.use_fast_gi = True
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False 

    vs = scene.view_settings
    try:
        vs.view_transform = view_transform
    except TypeError:
        vs.view_transform = 'Filmic'
    vs.look = 'None'
    vs.exposure = 0.0

    if mist and scene.world:
        try:
            scene.world.mist_settings.start = 7.0
            scene.world.mist_settings.depth = 30.0
            scene.world.mist_settings.falloff = 'QUADRATIC'
        except AttributeError:
            pass

    # Bloom uchun Glare node (arzon, kadr boshiga ~0.05s)
    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    gl = nt.nodes.new("CompositorNodeGlare")
    gl.glare_type = 'FOG_GLOW'
    gl.quality = 'MEDIUM'
    gl.threshold = 0.85
    gl.size = 7
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], gl.inputs["Image"])
    nt.links.new(gl.outputs["Image"], comp.inputs["Image"])
    return scene


# ----------------------------------------------------------------------------
# YORDAMCHI
# ----------------------------------------------------------------------------
def new_collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def link(obj, coll):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def purge():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def setup_gpu(scene, denoise=True, samples=None):
    """Modal/GPU muhitida Cycles'ni GPU'ga o'tkazish."""
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for t in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
            try:
                prefs.compute_device_type = t
                break
            except Exception:
                continue
        prefs.get_devices()
        gpu_found = False
        for d in prefs.devices:
            d.use = (d.type != 'CPU')
            if d.type != 'CPU':
                gpu_found = True
        if gpu_found:
            scene.cycles.device = 'GPU'
        if denoise:
            scene.cycles.use_denoising = True
            scene.cycles.denoiser = 'OPENIMAGEDENOISE'
            scene.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
        if samples:
            scene.cycles.samples = samples
        return gpu_found
    except Exception as e:
        print("GPU setup failed:", e)
        return False
