import io
import math
import time
import asyncio

# from js import document, Uint8Array, File, URL

from pyodide.ffi.wrappers import add_event_listener
from pyodide.ffi import create_proxy
from pyscript import window, document, PyWorker

from libthree import get_scene, get_camera, get_renderer
from libthree import get_controls, get_lights
from libthree import generate_cubes, get_stats

from plyfile import PlyData

async def get_bytes_from_file(item) -> bytes:
    array_buf = await item.arrayBuffer()
    return array_buf.to_bytes()

async def read_ply_file(item) -> PlyData:
    array_buf = await item.arrayBuffer()
    array_bytes = array_buf.to_bytes()
    bstream = io.BytesIO(array_bytes)
    # plydata = PlyData.read(bstream)
    print('right before plyread')
    plydata = await asyncio.to_thread(PlyData.read, bstream)
    return plydata

async def on_pts_submit(e):
    try:
        output_p = document.querySelector("#pts-output")
        output_p.textContent = 'Reading ...'
        loading_dialog = document.getElementById("loading")
        loading_dialog.showModal()
        worker = PyWorker("./worker.py", type="pyodide", config = { "packages": ["plyfile>=1.1.3"] })
        print("before ready")
        # Await for the worker
        await worker.ready
        print("after ready")
        file_input = document.querySelector("#pts-file-upload")
        file_list = file_input.files
        item = file_list.item(0)
        my_bytes: bytes = await get_bytes_from_file(item)
        plydata = await worker.sync.read_ply(my_bytes)
        # print(len(plydata))
        output_p.textContent = 'Success'
        worker.terminate()
        loading_dialog.close()
        
    except Exception as e:
        print(e)
        
scene = get_scene()
camera = get_camera()
renderer = get_renderer()
controls = get_controls(camera, renderer)
lights = get_lights()
# stats = get_stats()
cubes = []

def init():
    for cube in generate_cubes(scale=1000):
        scene.add(cube)
        cubes.append(cube)
        if len(cubes) == 50000:
            break

    for light in lights:
        scene.add(light)

def animate(now):
    # stats.begin()
    controls.update()
    camera.position.x += math.sin(now * 0.0001)
    camera.position.z += math.cos(now * 0.0001)
    light_back_green, light_back_white = lights
    light_back_green.position.x = camera.position.x
    light_back_green.position.y = camera.position.y
    light_back_green.position.z = camera.position.z
    light_back_white.position.x = camera.position.x
    light_back_white.position.y = camera.position.y
    light_back_white.position.z = camera.position.z
    camera.lookAt(scene.position)
    renderer.render(scene, camera)
    # stats.end()
    window.requestAnimationFrame(animate_js)

animate_js = create_proxy(animate)

if __name__ == "__main__":
    init()
    animate(time.time())
    add_event_listener(document.getElementById("pts-submit"), "click", lambda e: asyncio.create_task(on_pts_submit(e)) )
