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
    "ground":       (0.062, 0.105, 0.042),
    "ground_dark":  (0.045, 0.080, 0.035),
    "grass":        (0.120, 0.215, 0.060),
    "trunk":        (0.115, 0.072, 0.042),
    "leaf_a":       (0.038, 0.135, 0.062),
    "leaf_b":       (0.155, 0.310, 0.105),
    "leaf_dry":     (0.300, 0.235, 0.095),
    "fruit":        (0.520, 0.038, 0.052),
    "robe":         (0.720, 0.690, 0.610),
    "turban":       (0.880, 0.865, 0.800),
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
def setup_world(scene, sun_dir=(0.92, 0.42, 0.20), warmth=1.0, horizon=None, top=None,
                strength=1.25, sun_elev=12.0, sun_rot=24.0, dust=1.1):
    """Nishita fizik osmon: teal -> amber gradient + quyosh halqasi. Cycles CPU'da barqaror."""
    import math
    w = bpy.data.worlds.new("SKY")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = 'NISHITA'
        sky.sun_disc = True
        sky.sun_elevation = math.radians(sun_elev)
        sky.sun_rotation = math.radians(sun_rot)
        sky.sun_intensity = 1.8
        sky.altitude = 120.0
        sky.air_density = 1.1
        sky.dust_density = dust
        sky.ozone_density = 2.0
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    except (AttributeError, TypeError) as e:
        print("SKY fallback:", e, flush=True)
        bg.inputs["Color"].default_value = (0.34, 0.42, 0.46, 1)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    print("WORLD: nishita", flush=True)
    return w


# ----------------------------------------------------------------------------
# YORUG'LIK
# ----------------------------------------------------------------------------
def setup_lights(sun_dir=(0.90, 0.40, 0.21), energy=4.5, warm=1.0):
    d = Vector(sun_dir).normalized()
    ld = bpy.data.lights.new("SUN", type='SUN')
    ld.energy = energy
    ld.use_shadow = True
    ld.angle = math.radians(1.5)
    ld.color = (1.0, 0.78 * warm, 0.50)
    sun = bpy.data.objects.new("SUN", ld)
    bpy.context.collection.objects.link(sun)
    sun.location = d * 20
    sun.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()

    # sovuq to'ldiruvchi (osmondan aks) — soyalarni o'lik qora bo'lishdan saqlaydi
    ld2 = bpy.data.lights.new("FILL", type='AREA')
    ld2.energy = 45.0
    ld2.size = 14.0
    ld2.color = (0.55, 0.75, 0.85)
    fill = bpy.data.objects.new("FILL", ld2)
    bpy.context.collection.objects.link(fill)
    fill.location = (-d.x * 12, -d.y * 12, 10)
    fill.rotation_euler = (Vector((0, 0, 0)) - fill.location).to_track_quat('-Z', 'Y').to_euler()
    fill.visible_camera = False          # kameraga ko'rinmasin!
    fill.visible_glossy = False
    sun.visible_camera = False
    return sun


# ----------------------------------------------------------------------------
# RENDER SOZLAMALARI
# ----------------------------------------------------------------------------
def setup_render(scene, res=(720, 1280), samples=4, fps=24, mist=True,
                 view_transform='Standard', exposure=0.05):
    # ENG MUHIM: EEVEE GPU kontekst talab qiladi va headless runner'da crash bo'ladi.
    scene.render.engine = 'CYCLES'
    try:
        scene.cycles.device = 'CPU'
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.02
    except AttributeError:
        pass
    r = scene.render
    print("ENGINE:", r.engine, "| device:", scene.cycles.device if hasattr(scene,'cycles') else '?', flush=True)
    r.resolution_x, r.resolution_y = res
    r.resolution_percentage = 100
    r.fps = fps
    r.image_settings.file_format = 'PNG'
    r.image_settings.color_mode = 'RGB'
    r.image_settings.compression = 40
    r.film_transparent = False
    r.threads_mode = 'AUTO'
    try:
        r.compositor_device = 'CPU'      # GPU kontekst (libEGL) kerak bo'lmasin
    except (AttributeError, TypeError):
        pass

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
    r.use_persistent_data = True     # BVH kadrlar orasida saqlanadi — 2-3x tez

    vs = scene.view_settings
    try:
        vs.view_transform = view_transform
    except TypeError:
        vs.view_transform = 'Filmic'
    for look in ('None',):
        try:
            vs.look = look
            break
        except TypeError:
            continue
    vs.exposure = exposure

    if mist and scene.world:
        try:
            scene.world.mist_settings.start = 7.0
            scene.world.mist_settings.depth = 30.0
            scene.world.mist_settings.falloff = 'QUADRATIC'
        except AttributeError:
            pass

    # GPU kontekst talab qiladigan kompozitor o'chirilgan: glow/vignette ffmpeg'da.
    scene.render.use_compositing = False
    scene.use_nodes = False
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
