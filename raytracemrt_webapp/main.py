import asyncio
import numpy as np
from time import perf_counter

from pyodide.ffi.wrappers import add_event_listener
from pyscript.ffi import create_proxy
from pyscript import window, document, PyWorker

from pyscript_3dapp_lib.utils import create_hidden_link, rgb_falsecolors, convertxyz2zxy, get_bytes_from_file, write_csv_web
from pyscript_3dapp_lib.libthree import get_scene, get_camera, get_renderer, get_orbit_ctrl, get_lights, create_grp, create_cube, viz_pts_color, create_sphere, viz_vox_outlines, create_lines

MRT_RES = None
PLY_NAME = None
PLY_PTS = None
PLY_TEMPS = None
MN_TEMP = None
MX_TEMP = None
VIZ_PTS_MODE = 0
GRID_PTS = None
GRID_RAYS = None
GRID_MS_RAYS = None
RAYS_ON = None
height_3dview_ratio = 0.8
#-----------------------------------------------------------
# region: get the renderer and append it to index.html
renderer = get_renderer()
renderer.setSize(window.innerWidth, window.innerHeight*height_3dview_ratio)
bottom_side = document.getElementById('bottomSide')
bottom_side.appendChild(renderer.domElement)
# endregion: get the renderer and append it to index.html
#-----------------------------------------------------------
# region setup scene and cam
# get the camera and scene
camera = get_camera()
# get the scene
scene = get_scene()
# get lights and put in the scene
lights = get_lights()
for light in lights:
    scene.add(light)

# disable the buttons
dl_btn = document.getElementById("mrt-download")
dl_btn.disabled = True

vizpts_btn = document.getElementById("viz_pts")
vizpts_btn.disabled = True

gridid_btn = document.getElementById("grid_id")
gridid_btn.disabled = True

vizrays_btn = document.getElementById("viz_rays")
vizrays_btn.disabled = True

# orbit controls
controls = get_orbit_ctrl(camera, renderer)
# create a spinning cube
init_cube, init_edges = create_cube()
init_edges.name = 'init_edges'
scene.add(init_edges)

def set_cam_orig():
    camera.position.set(1, 1, 4)
    camera.lookAt(0,0,0)

set_cam_orig()

def animate(*args):
    controls.update()
    init_edges.rotation.x += 0.01
    init_edges.rotation.y += 0.01
    renderer.render(scene, camera)
    # Call the animation loop recursively
    window.requestAnimationFrame(animate_proxy)

animate_proxy = create_proxy(animate)
window.requestAnimationFrame(animate_proxy)
# endregion: setup scene and cam
#-----------------------------------------------------------

def change_dialog_text(txt: str):
    text_elem = document.getElementById("dialogText")
    text_elem.innerText = txt

def change_color_bar(mnval: float, mxval: float):
    val_range = mxval - mnval
    interval = val_range/4
    intervals = [mnval, mnval+interval, mnval+(interval*2), mnval+(interval*3), mxval]
    for cnt, i in enumerate(intervals):
        color_label = document.getElementById("fcval" + str(cnt+1))
        color_label.textContent = str(round(i, 1))

def grid_pts_mrt2rows(grid_pts: list[list[float]], mrts: list[float]) -> list[list]:
    """
    convert grid pts and mrts to rows

    Parameters
    ----------
    grid_pts: list[list[float]]
        mrt gridpts
    
    mrts: list[float]
        mrts calculated corresponding to the grid pts

    Returns
    -------
    list[list]
        list[shape(npts, 4)]  
    """
    header_str = ['x', 'y', 'z', 'MRT(degC)']
    rows = [header_str]
    for cnt,grid_pt in enumerate(grid_pts):
        row = [grid_pt[0], grid_pt[1], grid_pt[2], mrts[cnt]]
        rows.append(row)
    return rows

def viz_a_grid_rays(grid_pt: list[float], grid_rays: list[list[float]], rgb: list[float]):
    """
    process and viz rays of a grid point

    Parameters
    ----------
    grid_pt: list[float]
        list[shape(3)] xyz of the point
    
    grid_rays: list[list[float]]
        list[shape(nrays, 3)] intersections rays with bbox

    grid_id: int
        id of the grid to viz

    Returns
    -------
    THREE.LineSegments
        threejs lines that can be visualize
    """
    nrays = len(grid_rays)
    grid_pts = np.repeat([grid_pt], nrays, axis=0)
    grid_rays = np.array(grid_rays)
    grid_rays = convertxyz2zxy(grid_rays)
    lines_xyzs = np.hstack((grid_pts, grid_rays))
    lines_xyzs_flat = lines_xyzs.flatten().tolist()
    threejs_lines = create_lines(lines_xyzs_flat, rgb_color=rgb)
    return threejs_lines
    
async def on_submit(e):
    try:
        # region: get all the parameters
        t1 = perf_counter()
        submit_btn = document.getElementById("stcsv-submit")
        submit_btn.disabled = True
        set_cam_orig()
        init_edges = scene.getObjectByName( "init_edges", True )
        scene.add(init_edges)
        output_p = document.querySelector("#stcsv-output")
        output_p.textContent = 'Calculating ...'
        st_file_input = document.querySelector("#stpts-file-upload")
        grid_file_input = document.querySelector("#grid-file-upload")
        st_file_list = st_file_input.files
        grid_file_list = grid_file_input.files
        nstfiles = len(st_file_list)
        ngfiles = len(grid_file_list)
        # endregion: get all the parameters
        if nstfiles != 0 and ngfiles != 0:
            # region: loading dialog and get extra parameters
            loading_dialog = document.getElementById("loading")
            loading_dialog.showModal()
            st_item = st_file_list.item(0)
            global PLY_NAME
            st_full_name = st_item.name
            st_name = st_full_name.split('.')[0]
            PLY_NAME = st_name
            grid_item = grid_file_list.item(0)
            st_bytes = await get_bytes_from_file(st_item)
            grid_bytes = await get_bytes_from_file(grid_item)
            vdim = float(document.querySelector("#vdim").value)
            nrays = float(document.querySelector("#nray").value)
            # Await for the worker
            worker_config = {
                                "packages": ["plyfile>=1.1.3", "geomie3d==0.0.11", "numpy-stl>=3.2.0",
                                            "./lib/pyscript_3dapp_lib-0.0.2-py3-none-any.whl", 
                                            "./lib/raytrace_mrt_lib-0.0.2-py3-none-any.whl"]
                            }
            worker = PyWorker("./worker.py", type="pyodide", config = worker_config)
            # Await for the worker
            await worker.ready
            worker.sync.change_dialog_text = change_dialog_text
            # endregion: loading dialog and get extra parameters
            # region: calculate the mrt and retrieve information from the calc
            world = create_grp()
            mrt_data = await worker.sync.calc_mrt(st_bytes, grid_bytes, vdim, nrays)
            vx_midpts = list(mrt_data.midpts)
            vx_midpts = list(map(list, vx_midpts))
            nmidpts = len(vx_midpts)
            vx_temps = list(mrt_data.temps)
            cam_pos = mrt_data.cam[0]
            lookat = mrt_data.cam[1]
            global GRID_PTS
            grid_pts = mrt_data.grid
            GRID_PTS = grid_pts
            mrt_ls = mrt_data.mrt
            mrt_ls = np.round(mrt_ls,2).tolist()
            global PLY_PTS
            pts = list(mrt_data.pts)
            PLY_PTS = pts
            global PLY_TEMPS
            pts_temps = list(mrt_data.pts_temp)
            PLY_TEMPS = pts_temps
            global GRID_RAYS
            grid_rays = mrt_data.rays # shape(ngrids, nintx, 3)
            GRID_RAYS = grid_rays
            global GRID_MS_RAYS
            grid_ms_rays = mrt_data.miss_rays # shape(ngrids, nmiss, 3)
            GRID_MS_RAYS = grid_ms_rays
            # endregion: calculate the mrt and retrieve information from the calc
            # region: convert all temps to falsecolor
            mn_vxtemp = min(vx_temps)
            mx_vxtemp = max(vx_temps)
            mn_mrt = min(mrt_ls)
            mx_mrt = max(mrt_ls)
            mn_temp = min([mn_vxtemp, mn_mrt])
            mx_temp = max([mx_vxtemp, mx_mrt])
            global MN_TEMP
            MN_TEMP = mn_temp
            global MX_TEMP
            MX_TEMP = mx_temp
            change_color_bar(mn_temp, mx_temp)
            nvx_verts = 24
            vx_temps2 = np.repeat(vx_temps, nvx_verts)
            vx_colors = rgb_falsecolors(vx_temps2, mn_temp, mx_temp)
            vx_colors = np.reshape(vx_colors, (nmidpts, nvx_verts*3)).tolist()
            # endregion: convert all temps to falsecolor
            # region: viz voxels mrt to falsecolor and viz the points
            outlines = viz_vox_outlines(vx_midpts, vx_colors, vdim)
            world.add(outlines)
            
            mrt_colors = rgb_falsecolors(mrt_ls, mn_temp, mx_temp)
            mrt_colors = np.reshape(mrt_colors, (len(mrt_ls), 3)).tolist()
            for gcnt, grid_pt in enumerate(grid_pts):
                rgb = mrt_colors[gcnt]
                grid_sphere = create_sphere(0.1, 10, 10, r = rgb[0], g = rgb[1], b = rgb[2])
                grid_sphere.position.x = grid_pt[0]
                grid_sphere.position.y = grid_pt[1]
                grid_sphere.position.z = grid_pt[2]
                world.add(grid_sphere)
            # endregion: viz voxels mrt to falsecolor and viz the points
            # region: prepare the 3d scene
            camera.position.set(cam_pos[0], cam_pos[1], cam_pos[2])
            camera.lookAt(lookat)

            scene.remove(init_edges)
            scene.add(world)
            worker.terminate()
            loading_dialog.close()
            # endregion: prepare the 3d scene
            # region: prepare data for downloads and other viz
            global MRT_RES
            csv_rows = grid_pts_mrt2rows(grid_pts, mrt_ls)
            mrt_res = write_csv_web(csv_rows)
            MRT_RES = mrt_res
            t2 = perf_counter()
            dur = int((t2 - t1)/60)
            if dur == 0:
                dur = 'less than a minute'
            output_p.textContent = f"Success! Time Elapsed (mins): {dur}"
            
            dl_btn.disabled = False
            dl_msg = document.querySelector("#mrt-output")
            dl_msg.textContent = 'Refresh to do another projection.'

            vizpts_btn.disabled = False
            gridid_btn.disabled = False
            vizrays_btn.disabled = False
            # endregion: prepare data for downloads and other viz
        else:
            loading_dialog = document.getElementById("loading")
            loading_dialog.showModal()
            change_dialog_text('Please specify PLY and CSV file')
            
    except Exception as e:
        change_dialog_text(e)
        print(e)

def downloadFile(*args):
    create_hidden_link(MRT_RES, f"{PLY_NAME}_mrt_res", 'csv')

def viz_pts(*args):
    global VIZ_PTS_MODE
    if VIZ_PTS_MODE == 0:
        pts_colors = rgb_falsecolors(PLY_TEMPS, MN_TEMP, MX_TEMP)
        three_js_pts = viz_pts_color(PLY_PTS, pts_colors, size=0.05)
        three_js_pts.name = 'three_js_pts'
        scene.add(three_js_pts)
        VIZ_PTS_MODE = 1
    else:
        three_js_pts = scene.getObjectByName( "three_js_pts", True )
        scene.remove(three_js_pts)
        VIZ_PTS_MODE = 0

def viz_rays(*args):
    global RAYS_ON
    grid_pts = GRID_PTS
    rays = GRID_RAYS
    ms_rays = GRID_MS_RAYS
    grid_id = int(document.querySelector("#grid_id").value)
    grid_pt = grid_pts[grid_id-1]
    grid_rays = rays[grid_id-1]
    grid_ms_rays = ms_rays[grid_id-1]
    nms_rays = len(grid_ms_rays)
    if RAYS_ON == None:
        threejs_lines = viz_a_grid_rays(grid_pt, grid_rays, [1,0,0])
        threejs_lines.name = f"grid_rays{grid_id}"
        scene.add(threejs_lines)
        if nms_rays != 0:
            three_js_lines_ms = viz_a_grid_rays(grid_pt, grid_ms_rays, [1,1,1])
            three_js_lines_ms.name = f"grid_ms_rays{grid_id}"
            scene.add(three_js_lines_ms)
        RAYS_ON = grid_id
    else:
        three_js_lines = scene.getObjectByName(f"grid_rays{RAYS_ON}", True)
        three_js_lines_ms = scene.getObjectByName( f"grid_ms_rays{RAYS_ON}", True)
        scene.remove(three_js_lines)
        scene.remove(three_js_lines_ms)
        if grid_id != RAYS_ON:
            threejs_lines = viz_a_grid_rays(grid_pt, grid_rays, [1,0,0])
            threejs_lines.name = f"grid_rays{grid_id}"
            scene.add(threejs_lines)
            if nms_rays != 0:
                three_js_lines_ms = viz_a_grid_rays(grid_pt, grid_ms_rays, [1,1,1])
                three_js_lines_ms.name = f"grid_ms_rays{grid_id}"
                scene.add(three_js_lines_ms)
            RAYS_ON = grid_id
        else:
            RAYS_ON = None

if __name__ == "__main__":
    animate()
    add_event_listener(document.getElementById("stcsv-submit"), "click", lambda e: asyncio.create_task(on_submit(e)))
    add_event_listener(document.getElementById("mrt-download"), "click", downloadFile)
    add_event_listener(document.getElementById("viz_pts"), "click", viz_pts)
    add_event_listener(document.getElementById("viz_rays"), "click", viz_rays)