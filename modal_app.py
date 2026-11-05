"""
modal_app.py — GPU'da render + ffmpeg montaj + Telegram'ga yetkazish.

Buyruqlar:
  modal run modal_app.py::probe                       # GPU/Blender tekshiruvi
  modal run modal_app.py::render --shot 0             # bitta kadrni render qilish
  modal run modal_app.py::render_all                  # butun planni render qilish
  modal run modal_app.py::compose                     # videoni yig'ish va TG'ga yuborish
"""
import modal
import json
import os

APP_NAME = "anim-studio"
BLENDER_VER = "4.3.2"
VOL = modal.Volume.from_name("anim-studio-vol", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "curl", "xz-utils", "ffmpeg", "fonts-dejavu-core", "fontconfig",
        "libx11-6", "libxi6", "libxxf86vm1", "libxfixes3", "libxrender1",
        "libgl1", "libegl1", "libsm6", "libice6", "libglib2.0-0",
    )
    .run_commands(
        f"curl -fsSL https://download.blender.org/release/Blender4.3/"
        f"blender-{BLENDER_VER}-linux-x64.tar.xz -o /tmp/b.tar.xz",
        "tar -xf /tmp/b.tar.xz -C /opt && mv /opt/blender-*-linux-x64 /opt/blender"
        " && rm /tmp/b.tar.xz && /opt/blender/blender --version",
    )
    .env({"PATH": "/opt/blender:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin"})
    .add_local_dir("/home/user/anim/blender", remote_path="/work/blender")
    .add_local_dir("/home/user/anim/scenes", remote_path="/work/scenes")
    .add_local_file("/home/user/anim/assets/fonts/DejaVuSans-Bold.ttf",
                    remote_path="/work/fonts/DejaVuSans-Bold.ttf")
)

app = modal.App(APP_NAME)


# ---------------------------------------------------------------- PROBE
@app.function(image=image, gpu="A10G", timeout=900)
def probe():
    import subprocess
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                          "--format=csv,noheader"], capture_output=True, text=True)
    print("GPU:", out.stdout.strip() or out.stderr.strip())
    v = subprocess.run(["/opt/blender/blender", "--version"], capture_output=True, text=True)
    print(v.stdout.split("\n")[0])
    # kichik GPU render sinovi
    test = '''
import bpy, time, sys
sys.path.insert(0, "/work/blender")
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_monkey_add()
bpy.ops.object.light_add(type="SUN")
bpy.ops.object.camera_add(location=(0,-5,0), rotation=(1.5708,0,0))
sc.camera = bpy.context.object
sc.render.resolution_x, sc.render.resolution_y = 720, 1280
sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
try:
    prefs.compute_device_type = "OPTIX"
except Exception:
    prefs.compute_device_type = "CUDA"
prefs.get_devices()
for d in prefs.devices:
    d.use = (d.type != "CPU")
sc.cycles.device = "GPU"
sc.cycles.samples = 32
sc.cycles.use_denoising = True
sc.render.filepath = "/tmp/t.png"
t = time.time()
bpy.ops.render.render(write_still=True)
print("RENDER_SECONDS", round(time.time()-t, 2))
print("DEVICE", prefs.compute_device_type)
'''
    open("/tmp/t.py", "w").write(test)
    r = subprocess.run(["/opt/blender/blender", "-b", "-P", "/tmp/t.py"],
                       capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        if "RENDER_SECONDS" in line or "DEVICE" in line or "Error" in line:
            print(line)


# ---------------------------------------------------------------- RENDER
@app.function(image=image, gpu="A10G", timeout=7200, cpu=8, memory=16384,
              volumes={"/vol": VOL})
def render_shot(plan: dict, idx: int, samples: int = 48, quality: float = 1.0,
                slug: str = "demo"):
    import subprocess, time
    os.makedirs("/work", exist_ok=True)
    with open("/work/plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False)
    outdir = f"/vol/projects/{slug}/shot{idx:02d}"
    os.makedirs(outdir, exist_ok=True)
    cmd = ["/opt/blender/blender", "-b", "-P", "/work/blender/build_scene.py", "--",
           "--plan", "/work/plan.json", "--shot", str(idx), "--outdir", outdir,
           "--samples", str(samples), "--quality", str(quality), "--gpu"]
    t = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    dur = round(time.time() - t, 1)
    err = (r.stdout + r.stderr)[-1500:]
    n = len([f for f in os.listdir(outdir) if f.endswith(".png")])
    VOL.commit()
    print(f"shot{idx}: {n} kadr, {dur}s")
    if n == 0:
        print(err)
    return {"shot": idx, "frames": n, "seconds": dur, "log": err if n == 0 else ""}


@app.function(image=image, gpu="A10G", timeout=7200, cpu=8, memory=16384,
              volumes={"/vol": VOL})
def render_all(plan: dict, samples: int = 48, quality: float = 1.0, slug: str = "demo"):
    import subprocess, time
    with open("/work/plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False)
    results = []
    for idx, shot in enumerate(plan["shots"]):
        outdir = f"/vol/projects/{slug}/shot{idx:02d}"
        os.makedirs(outdir, exist_ok=True)
        cmd = ["/opt/blender/blender", "-b", "-P", "/work/blender/build_scene.py", "--",
               "--plan", "/work/plan.json", "--shot", str(idx), "--outdir", outdir,
               "--samples", str(samples), "--quality", str(quality), "--gpu"]
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        n = len([f for f in os.listdir(outdir) if f.endswith(".png")])
        results.append({"shot": idx, "frames": n, "seconds": round(time.time() - t, 1)})
        print(results[-1])
        VOL.commit()
    return results


@app.local_entrypoint()
def probe_main():
    probe.remote()


if __name__ == "__main__":
    pass
