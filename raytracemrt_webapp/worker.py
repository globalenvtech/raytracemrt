import io
import csv

import geomie3d
import numpy as np

from raytrace_mrt_lib import separate_rays, gen_rays
from pyscript_3dapp_lib.utils import read_csv_web, convertxyz2zxy, read_ply_web, get_cam_place_from_xyzs
from pyscript import sync

def process_grid_data(csv_rows: list[list]) -> list[list]:
    """
    read csv file for webapp

    Parameters
    ----------
    csv_rows: list[list]
        list[shape(nrows, ncolumns)].

    Returns
    -------
    list[list]
        list[shape(ngrid_pts, 3)]
    """
    pts = csv_rows[1:]
    pts_arr = np.array(pts)
    pts_arr = pts_arr.astype(float).tolist()
    return pts_arr
    
def process_plydata(plydata: np.ndarray) -> dict:
    """
    separate the plydata into xyzs and temperatures

    Parameters
    ----------
    plydata: np.ndarray
        np.ndarray[shape(n_pts, n_attributes)] 

    Returns
    -------
    dict
        A dictionary containing:
            - "xyzs": np.ndarray[(n_pts, 3)].
            - "temps": np.ndarray[(n_pts)].
    """
    temps = plydata[:, 3]
    vertices = plydata[:, 0:3]
    return {'xyzs': vertices, 'temps': temps}

def calc_mrt(ply_bytes: bytes, grid_bytes: bytes, vdim: float, nrays: int) -> dict:
    """
    calc mrt

    Parameters
    ----------
    ply_bytes: bytes
        JS bytes from the file specified. Need to be converted to python with .to_py() function.

    grid_bytes: bytes
        JS bytes from the file specified. Need to be converted to python with .to_py() function.

    vdim: float
        dimesion of a voxel in meters.

    nrays: int
        number of rays to cast per grid point.
        
    Returns
    -------
    flatten_mesh_xyzs : np.ndarray
        np.ndarray[shape(ntri * 3 * 3)]
    """
    #------------------------------------------------------------------
    # region: read ply file
    sync.change_dialog_text('Reading PLY file ...')
    plydata = read_ply_web(ply_bytes)
    plydata = process_plydata(plydata)
    ply_xyzs = plydata['xyzs']
    ply_temps = plydata['temps']
    # endregion: read ply file
    #------------------------------------------------------------------
    # region: convert ply pts to voxels
    sync.change_dialog_text('Convert PLY pts to voxels ...')
    vxres_dict = geomie3d.modify.xyzs2voxs(ply_xyzs, vdim, vdim, vdim)
    #convert the voxels to bboxes
    vxs = vxres_dict['voxels']
    vx_dim = vxres_dict['voxel_dim']
    ijks = vxs.keys()
    nijk = len(ijks)
    midpts = []
    avg_temps = []
    atts = []
    xdims = np.array([vx_dim[0]])
    xdims = np.repeat(xdims, nijk)
    ydims = np.array([vx_dim[1]])
    ydims = np.repeat(ydims, nijk)
    zdims = np.array([vx_dim[2]])
    zdims = np.repeat(zdims, nijk)
    sync.change_dialog_text('Convert voxels to bounding boxes ...')
    for ijk in ijks:
        vx = vxs[ijk]
        midpt = vx['midpt']
        midpt = list(map(float, midpt))
        idxs = vx['idx']
        sel_temps = np.take(ply_temps, idxs)
        avg_temp = float(np.mean(sel_temps))
        att = {'idx': vx['idx'], 'ijk': ijk, 'midpt':midpt, 'temperature': avg_temp}
        avg_temps.append(avg_temp)
        midpts.append(midpt)
        atts.append(att)
    bbx_ls = geomie3d.create.bboxes_frm_midpts(midpts, xdims, ydims, zdims, attributes_list = atts)
    # endregion: read ply file
    #------------------------------------------------------------------
    # region: read csv file and convert them into rays for projection
    sync.change_dialog_text('Reading CSV file and generating rays ...')
    csv_rows = read_csv_web(grid_bytes)
    grid_pts = process_grid_data(csv_rows)
    ngrids = len(grid_pts)
    rays = gen_rays(grid_pts, nrays)

    aloop = 1000000#30
    nbbox = len(bbx_ls)
    ndir = len(rays)
    ttl = ndir*nbbox
    nparallel = int(ttl/aloop)
    
    if nparallel != 0:
        rays_ls = separate_rays(rays, nparallel)
    else:
        rays_ls = [rays]
    # endregion: read csv file and convert them into rays for projection
    #------------------------------------------------------------------
    # region: project the rays onto the bboxes
    sync.change_dialog_text('Projecting ray onto bboxes ...')
    ttl_k = int(ttl/1000)
    proj_rays = []
    ms_rays = []
    rcnt = 0
    for rays1 in rays_ls:
        rcnt += len(rays1)
        percentage = int((rcnt*nbbox)/ttl * 100)
        hrs, mrs, hbs, mbs = geomie3d.calculate.rays_bboxes_intersect(rays1, bbx_ls)
        nhr = len(hrs)
        nmr = len(mrs)
        msg = f"Projecting {ndir} ray onto {nbbox} Voxels ... \n{percentage}% of {ttl_k}k calculations completed"
        msg += f"\n{nhr} rays intersection, {nmr} rays did not hit any voxels"
        sync.change_dialog_text(msg)
        proj_rays.extend(hrs)
        ms_rays.extend(mrs)
    # endregion: project the rays onto the bboxes
    #------------------------------------------------------------------
    # region: process the raytracing results
    grid_temps = []
    for _ in range(ngrids):
        grid_temps.append([])

    grid_intxs = []
    for _ in range(ngrids):
        grid_intxs.append([])

    grid_ms_rays = []
    for _ in range(ngrids):
        grid_ms_rays.append([])
    
    for proj_ray in proj_rays:
        grid_id = proj_ray.attributes['grid_id']
        intx_att = proj_ray.attributes['rays_bboxes_intersection']
        hit_bbxs = intx_att['hit_bbox']
        if len(hit_bbxs) == 1:
            if 'temperature' in hit_bbxs[0].attributes:
                intxs = intx_att['intersection']
                temp = hit_bbxs[0].attributes['temperature']
                grid_temps[grid_id].append(temp)
                grid_intxs[grid_id].extend(intxs)
        else:
            ijks = [hb.attributes['ijk'] for hb in hit_bbxs]
            unq = np.unique(ijks, axis=0)
            if len(unq) == 1:
                intxs = intx_att['intersection']
                temp = hit_bbxs[0].attributes['temperature']
                grid_temps[grid_id].append(temp)
                grid_intxs[grid_id].extend(intxs)
            else:
                print('not sure what is happening please debug')

    for ms_ray in ms_rays:
        grid_id = ms_ray.attributes['grid_id']
        orig = ms_ray.origin
        dirx = ms_ray.dirx
        mv_xyzs = geomie3d.calculate.move_xyzs([orig], [dirx], [5])
        grid_ms_rays[grid_id].extend(mv_xyzs)

    mrt_ls = []
    for gcnt,gt in enumerate(grid_temps):
        if len(gt) != 0:
            avg = sum(gt)/len(gt)
            mrt_ls.append(avg)
        else:
            print(f"grid pt {gcnt} do not see any temperatures")
            mrt_ls.append(-999)

    # endregion: process the raytracing results
    #------------------------------------------------------------------
    # region: prepare data to return to main script
    cam_place = get_cam_place_from_xyzs(midpts, zoom_out_val = 5)
    cam_place_zxy = convertxyz2zxy(cam_place) 
    midpts_zxy = convertxyz2zxy(midpts)
    grid_pts_zxy = convertxyz2zxy(grid_pts)
    ply_zxy = convertxyz2zxy(ply_xyzs)
    ply_zxy = ply_zxy.flatten()
    # grid_intxs_zxy = convertxyz2zxy(grid_intxs)
    return {'midpts': midpts_zxy, 'temps': avg_temps, 'mrt': mrt_ls, 'cam': cam_place_zxy, 'grid': grid_pts_zxy, 'pts': ply_zxy, 
            'pts_temp': ply_temps, 'rays': grid_intxs, 'miss_rays': grid_ms_rays}
    # endregion: prepare data to return to main script
    #------------------------------------------------------------------

sync.calc_mrt = calc_mrt