import io
from pyscript import sync
from plyfile import PlyData
import numpy as np

def heavy_compute():
    res = np.array([1234, 5678, 91011])
    return res

sync.heavy_compute = heavy_compute

def read_ply(ply_bytes: bytes):
    ply_bytes = ply_bytes.to_py()
    bstream = io.BytesIO(ply_bytes)
    plydata = PlyData.read(bstream)
    vertices = plydata['vertex'].data.tolist()
    xyzs_ls = np.array(vertices)
    return xyzs_ls

sync.read_ply = read_ply