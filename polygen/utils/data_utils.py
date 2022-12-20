"""Utils for manipulating obj data, most of the code is from https://github.com/deepmind/deepmind-research/blob/master/polygen/data_utils.py"""
import os
import six
from six.moves import range
from typing import List, Tuple, Dict

import networkx as nx
import numpy as np
import torch

from mpl_toolkits import mplot3d
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from .truncated_normal import TruncatedNormal


MIN_RANGE = -0.5
MAX_RANGE = 0.5


def random_shift(vertices: torch.Tensor, shift_factor: float = 0.25) -> torch.Tensor:
    """Randomly shift vertices in a cube according to some shift factor

    Args:
        vertices: tensor of shape (num_vertices, 3) representing current vertices
        shift_factor: float representing how much vertices should be shifted

    Returns:
        vertices: Shifted vertices
    """

    max_positive_shift = (255 - torch.max(vertices, axis=0)[0]).to(torch.float32)
    positive_condition_tensor = max_positive_shift > 1e-9
    max_positive_shift = torch.where(
        positive_condition_tensor, max_positive_shift, torch.Tensor([1e-9, 1e-9, 1e-9])
    )

    max_negative_shift = torch.min(vertices, axis=0)[0].to(torch.float32)
    negative_condition_tensor = max_negative_shift > 1e-9
    max_negative_shift = torch.where(
        negative_condition_tensor, max_negative_shift, torch.Tensor([1e-9, 1e-9, 1e-9])
    )
    normal_dist = TruncatedNormal(
        loc=torch.zeros((1, 3)),
        scale=shift_factor * 255,
        a=-max_negative_shift,
        b=max_positive_shift,
    )
    shift = normal_dist.sample().to(torch.int32)
    vertices += shift
    return vertices


def read_obj(obj_path: str) -> Tuple[np.ndarray, List]:
    """Utils method to read .obj file

    Args:
        obj_path: Path of .obj file
    Returns:
        flat_vertices_list: flattened vertex coordinates
        flat_triangles: vertex indices representing connectivity
    """
    vertex_list = []
    flat_vertices_list = []
    flat_vertices_indices = {}
    flat_triangles = []

    with open(obj_path) as obj_file:
        for line in obj_file:
            tokens = line.split()
            if not tokens:
                continue
            line_type = tokens[0]
            # We skip lines not starting with v or f.
            if line_type == "v":
                vertex_list.append([float(x) for x in tokens[1:]])
            elif line_type == "f":
                triangle = []
                for i in range(len(tokens) - 1):
                    vertex_name = tokens[i + 1]
                    if vertex_name in flat_vertices_indices:
                        triangle.append(flat_vertices_indices[vertex_name])
                        continue
                    flat_vertex = []
                    for index in six.ensure_str(vertex_name).split("/"):
                        if not index:
                            continue
                        # obj triangle indices are 1 indexed, so subtract 1 here.
                        flat_vertex += vertex_list[int(index) - 1]
                    flat_vertex_index = len(flat_vertices_list)
                    flat_vertices_list.append(flat_vertex)
                    flat_vertices_indices[vertex_name] = flat_vertex_index
                    triangle.append(flat_vertex_index)
                flat_triangles.append(triangle)

    return np.array(flat_vertices_list, dtype=np.float32), flat_triangles


def write_obj(
    vertices: np.ndarray,
    faces: List[List[int]],
    file_path: str,
    transpose: bool = True,
    scale: float = 1.0,
) -> None:
    """Writes vertices and faces to .obj file to represent 3D object

    Args:
        vertices: array of shape (num_vertices, 3) representing vertex indices
        faces: List of vertex indices representing vertex connectivity
        file_path: Where to save .obj file
        transpose: boolean representing whether to change traditional order of (x, y, z)
        scale: Factor by which to scale vertices
    """
    if transpose:
        vertices = vertices[:, [1, 2, 0]]
    vertices *= scale
    if faces is not None:
        if min(min(faces)) == 0:
            f_add = 1
        else:
            f_add = 0
    with open(file_path, "w") as f:
        for v in vertices:
            f.write("v {} {} {}\n".format(v[0], v[1], v[2]))
        for face in faces:
            line = "f"
            for i in face:
                line += " {}".format(i + f_add)
            line += "\n"
            f.write(line)


def quantize_verts(verts: np.ndarray, n_bits: int = 8) -> np.ndarray:
    """Convert floating point vertices to discrete values in [0, 2 ** n_bits - 1]

    Args:
        verts: np array of floating points vertices
        n_bits: number of quantization bits
    Returns:
        quantized_verts: np array representing quantized verts
    """
    range_quantize = 2 ** n_bits - 1
    verts = verts.astype("float32")
    quantized_verts = (verts - MIN_RANGE) * range_quantize / (MAX_RANGE - MIN_RANGE)
    return quantized_verts.astype("int32")


def dequantize_verts(
    verts: np.ndarray, n_bits: int = 8, add_noise: bool = False
) -> np.ndarray:
    """Undoes quantization process and converts from [0, 2 ** n_bits - 1] to floats

    Args:
        verts: quantized representation of verts
        n_bits: number of quantization bits
        add_noise: adds random values from uniform distribution if set to true
    Returns:
        dequantized_verts: np array representing floating point verts
    """
    range_quantize = 2 ** n_bits - 1
    verts = verts.astype("float32")
    dequantized_verts = verts * (max_range - min_range) / range_quantize + min_range
    if add_noise:
        dequantized_verts = np.random.uniform(size=dequantized_verts.shape) * (
            1 / range_quantize
        )
    return dequantized_verts


def face_to_cycles(faces: List[int]) -> List[int]:
    """Find cycles in faces list
    
    Args:
        faces: List of vertex indices representing connectivity
    
    Returns:
        cycle_basis: All cycles in faces graph
    """
    g = nx.Graph()
    for v in range(len(faces) - 1):
        g.add_edge(faces[v], faces[v + 1])
    g.add_edge(faces[-1], faces[0])
    return list(nx.cycle_basis(g))


def flatten_faces(faces: List[List[int]]) -> np.ndarray:
    """Converts from list of faces to flat face array with stopping indices

    Args:
        faces: List of list of vertex indices
    
    Returns:
        flattened_faces: A 1D list of faces with stop tokens indicating when to move to the next face
    """
    if not faces:
        return np.array([0])
    else:
        l = [f + [-1] for f in faces[:-1]]
        l += [faces[-1] + [-2]]
    return np.array([item for sublist in l for item in sublist]) + 2


def unflatten_faces(flat_faces: np.ndarray) -> List[List[int]]:
    """Converts from flat face sequence to a list of separate faces

    Args:
        flat_faces: A 1D list of vertex indices with stopping tokens
    
    Returns:
        faces: A 2D list of face indices where each face is its own list
    """

    def group(seq):
        g = []
        for el in seq:
            if el == 0 or el == -1:
                yield g
                g = []
            else:
                g.append(el - 1)
        yield g

    outputs = list(group(flat_faces - 1))[:-1]
    return [o for o in outputs if len(o) > 2]


def center_vertices(vertices: np.ndarray) -> np.ndarray:
    """Translate vertices so that the bounding box is centered at zero

    Args:
        vertices: np array of shape (num_vertices, 3)
    
    Returns:
        centered_vertices: centered vertices in array of shape (num_vertices, 3)
    """
    vert_min = np.min(vertices, axis=0)
    vert_max = np.max(vertices, axis=0)
    vert_center = 0.5 * (vert_min + vert_max)
    centered_vertices = vertices - vert_center
    return centered_vertices


def normalize_vertices_scale(vertices: np.ndarray) -> np.ndarray:
    """Scale vertices so that the long diagonal of the bounding box is one

    Args:
        vertices: unscaled vertices of shape (num_vertices, 3)
    Returns:
        scaled_vertices: scaled vertices of shape (num_vertices, 3)
    """
    vert_min = np.min(vertices, axis=0)
    vert_max = np.max(vertices, axis=0)
    extents = vert_max - vert_min
    scale = np.sqrt(np.sum(extents ** 2))
    scaled_vertices = vertices / scale
    return scaled_vertices


def quantize_process_mesh(
    vertices: np.ndarray,
    faces: List[List[int]],
    tris: Optional[List[int]] = None,
    quantization_bits: int = 8,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Quantize vertices, remove resulting duplicates and reindex faces

    Args:
        vertices: np array of shape (num_vertices, 3)
        faces: Unflattened faces
        tris: List of triangles
        quantization_bits: number of quantization bits
    
    Returns:
        vertices: processed vertices
        faces: processed faces
        triangles: list of triangles in 3D object
    """
    vertices = quantize_verts(vertices, quantization_bits)
    vertices, inv = np.unique(vertices, axis=0, return_inverse=True)

    # Sort vertices by z then y then x
    sort_inds = np.lexsort(vertices.T)
    vertices = vertices[sort_inds]

    # Re-index faces and tris to re-ordered vertices
    faces = [np.argsort(sort_inds)[inv[f]] for f in faces]
    if tris is not None:
        tris = np.array([np.argsort(sort_inds)[inv[t]] for t in tris])

    # Merging duplicate vertices and re-indexing the faces causes some faces to
    # contain loops (e.g. [2, 3, 5, 2, 4]). Split these faces into distinct
    # sub-faces.

    sub_faces = []
    for f in faces:
        cliques = face_to_cycles(f)
        for c in cliques:
            c_length = len(c)
            # Only append faces with more than two verts
            if c_length > 2:
                d = np.argmin(c)
                # Cyclically permute faces so that the first index is the smallest
                sub_faces.append([c[(d + i) % c_length] for i in range(c_length)])

    faces = sub_faces
    if tris is not None:
        tris = np.array([v for v in tris if len(set(v)) == len(v)])

    # Sort faces by lowest vertex indices. If two faces have the same lowest
    # index then sort by next lowest and so on.
    faces.sort(key=lambda f: tuple(sorted(f)))
    if tris is not None:
        tris = tris.tolist()
        tris.sort(key=lambda f: tuple(sorted(f)))
        tris = np.array(tris)

    # After removing degenerate faces some vertices are now unreferenced
    # Remove these
    vert_connected = np.equal(
        np.arange(num_verts)[:, None], np.hstack(faces)[None]
    ).any(axis=-1)
    vertices = vertices[vert_connected]

    # Re-index faces and tris to re-ordered vertices.
    vert_indices = np.arange(num_verts) - np.cumsum(1 - vert_connected.astype("int"))
    faces = [vert_indices[f].tolist() for f in faces]
    if tris is not None:
        tris = np.array([vert_indices[t].tolist() for t in tris])
    return vertices, faces, tris


def load_process_mesh(
    mesh_obj_path: str, quantization_bits: int = 8
) -> Dict[str, np.ndarray]:
    """Load obj file and process mesh

    Args:
        mesh_obj_path: string representing path to obj file
        quantization_bits: number of quantization bits
    
    Returns:
        mesh: A dictionary that contains the processed vertices and faces
    """
    vertices, faces = read_obj(mesh_obj_path)

    # Transpose so that z-axis is vertical
    vertices = vertices[:, [2, 0, 1]]

    # Translate the vertices so that bounding box is centered at zero
    vertices = center_vertices(vertices)

    # Scale the vertices so that the long diagonal of the bounding box is equal to one
    vertices = normalize_vertices_scale(vertices)

    # Quantize and sort vertices, remove duplicates, sort and re-index faces
    vertices, faces, _ = quantize_process_mesh(
        vertices, faces, quantization_bits=quantization_bits
    )

    # Flatten faces and add 'new face' = 1 and 'stop' = 0 tokens
    faces = flatten_faces(faces)

    return {
        "vertices": vertices,
        "faces": faces,
    }


def plot_meshes(
    mesh_list: List[Dict[str, np.ndarray]],
    ax_lims: float = 0.3,
    fig_size: int = 4,
    el: int = 30,
    rot_start: int = 120,
    vert_size: int = 10,
    vert_alpha: float = 0.75,
    n_cols: int = 4,
) -> None:
    """Plots mesh data using matplotlib
    
    Args:
        mesh_list: List of different 3D objects to plot
        ax_lims: limits on x-axes
        fig_size: How large should the figure be
        el: Elevation of plot
        rot_start: Starting orientation
        vert_size: size of the vertices
        vert_alpha: control for transparency of the vertices
        n_cols: How many plots to be show side by side
    """

    n_plot = len(mesh_list)
    n_cols = np.minimum(n_plot, n_cols)
    n_rows = np.ceil(n_plot / n_cols).astype("int")
    fig = plt.figure(figsize=(fig_size * n_cols, fig_size * n_rows))
    for p_inc, mesh in enumerate(mesh_list):

        for key in [
            "vertices",
            "faces",
            "vertices_conditional",
            "pointcloud",
            "class_name",
        ]:
            if key not in list(mesh.keys()):
                mesh[key] = None

        ax = fig.add_subplot(n_rows, n_cols, p_inc + 1, projection="3d")

        if mesh["faces"] is not None:
            if mesh["vertices_conditional"] is not None:
                face_verts = np.concatenate(
                    [mesh["vertices_conditional"], mesh["vertices"]], axis=0
                )
            else:
                face_verts = mesh["vertices"]
            collection = []
            for f in mesh["faces"]:
                collection.append(face_verts[f])
            plt_mesh = Poly3DCollection(collection)
            plt_mesh.set_edgecolor((0.0, 0.0, 0.0, 0.3))
            plt_mesh.set_facecolor((1, 0, 0, 0.2))
            ax.add_collection3d(plt_mesh)

        if mesh["vertices"] is not None:
            ax.scatter3D(
                mesh["vertices"][:, 0],
                mesh["vertices"][:, 1],
                mesh["vertices"][:, 2],
                lw=0.0,
                s=vert_size,
                c="g",
                alpha=vert_alpha,
            )

        if mesh["vertices_conditional"] is not None:
            ax.scatter3D(
                mesh["vertices_conditional"][:, 0],
                mesh["vertices_conditional"][:, 1],
                mesh["vertices_conditional"][:, 2],
                lw=0.0,
                s=vert_size,
                c="b",
                alpha=vert_alpha,
            )

        if mesh["pointcloud"] is not None:
            ax.scatter3D(
                mesh["pointcloud"][:, 0],
                mesh["pointcloud"][:, 1],
                mesh["pointcloud"][:, 2],
                lw=0.0,
                s=2.5 * vert_size,
                c="b",
                alpha=1.0,
            )

        ax.set_xlim(-ax_lims, ax_lims)
        ax.set_ylim(-ax_lims, ax_lims)
        ax.set_zlim(-ax_lims, ax_lims)

        ax.view_init(el, rot_start)

        display_string = ""
        if mesh["faces"] is not None:
            display_string += "Num. faces: {}\n".format(len(collection))
        if mesh["vertices"] is not None:
            num_verts = mesh["vertices"].shape[0]
            if mesh["vertices_conditional"] is not None:
                num_verts += mesh["vertices_conditional"].shape[0]
            display_string += "Num. verts: {}\n".format(num_verts)
        if mesh["class_name"] is not None:
            display_string += "Synset: {}".format(mesh["class_name"])
        if mesh["pointcloud"] is not None:
            display_string += "Num. pointcloud: {}\n".format(
                mesh["pointcloud"].shape[0]
            )
        ax.text2D(0.05, 0.8, display_string, transform=ax.transAxes)
    plt.subplots_adjust(
        left=0.0, right=1.0, bottom=0.0, top=1.0, wspace=0.025, hspace=0.025
    )
    plt.show()
