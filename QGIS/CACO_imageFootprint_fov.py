"""
Oblique camera field-of-view footprint generator for QGIS.

Author:  Chelsea A. Volpano (cvolpano@gmail.com)
Revised: 2026-11-14 with Claude Opus 5.5 (claude-opus-5-5)

REVISION SUMMARY
----------------
2026-11-14  Added load_nearest_calibration(): pairs each transect date
            (site + camera + date) with the IO and EO files closest in
            date instead of requiring exact filename matches. Footprint
            layers now carry io_file / eo_file / gap-day attributes.
            Removed a stray __main__ block that called an undefined
            function. Fixed CRS comment (EPSG:26919 = UTM 19N).

Computes ground footprint polygons for oblique images given exterior
orientation (position + azimuth/tilt/roll) and interior orientation
(focal length, principal point, Brown-Conrady distortion), read from a
YAML file. Ground intersection can use either a flat plane (z=constant)
or a real DEM raster loaded in QGIS.

YAML SCHEMA
-----------
See the EXAMPLE_YAML string near the bottom of this file for a full
example. Structure:

    intrinsics:              # shared intrinsics (used unless a camera overrides)
      NU: 2448
      NV: 2048
      coU: 1274.19336741503
      coV: 1023.97839825612
      fx: 2575.69765891443
      fy: 2572.95555921878
      d1: -0.216463164783327
      d2: 0.221491907781633
      d3: -0.0596944654518389
      t1: 0.00102622622281805
      t2: 0.00200970852724846

    cameras:
      - id: IMG_0001
        x: 420087.885757392
        y: 4638319.34468419
        z: 21.3497543187298
        azimuth: 73.1995858409559
        tilt: 71.1450595468697
        roll: -6.27932462929759
        # intrinsics: {...}   # optional per-camera override of the shared block above

      - id: IMG_0002
        x: ...
        y: ...
        ...

If your YAML files are one-per-image (as originally pasted) rather than
a combined file, see `load_split_yaml_files()` near the bottom for a
helper that merges a folder of separate extrinsic/intrinsic YAMLs.

USAGE
-----
1. Set YAML_PATH to your combined YAML file (or use load_split_yaml_files).
2. Set GROUND_MODE to "flat" or "dem".
     - "flat": set GROUND_Z (meters, NAVD88).
     - "dem": set DEM_LAYER_NAME to the name of an already-loaded QGIS
       raster layer (Layers panel name), or DEM_PATH to a file path.
3. Set MAX_RANGE (meters) - the cap used when a ray points above the
   horizon or would intersect the ground implausibly far away.
4. Paste into the QGIS Python Console (or run as a script) and execute.

IMPORTANT CAVEATS
------------------
- Horizon-crossing rays: for high-tilt (near-horizontal) oblique cameras,
  part of the frame may point above the horizon and never hit the ground/
  DEM. Those border rays are capped at MAX_RANGE along their horizontal
  direction rather than left unbounded. Points near this cap are
  approximate "how far in that direction" markers, not precise positions.
- DEM mode ray-marches with an adaptive step + refinement search. This is
  approximate (not a closed-form solution) - very fine terrain features
  smaller than the step size could be missed. Adjust DEM_STEP if needed.
- Flat mode assumes a single constant elevation across the whole scene.
"""

import math
import os
import re
from datetime import datetime
from pathlib import Path

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsRasterLayer
)
from PyQt5.QtCore import QVariant

try:
    import yaml
except ImportError:
    raise ImportError(
        "PyYAML is not available in this QGIS Python environment. "
        "Open the OSGeo4W shell (Windows) or your QGIS python, and run: "
        "python -m pip install pyyaml"
    )


# ----------------------------------------------------------------------
# CONFIG - edit these
# ----------------------------------------------------------------------

# YAML_PATH = "C:/Users/cvolpano/coastcam_processing/CACO_orthoRect/CACO_obliqueImage_Footprints/IOEO_c2_01232025.yaml"
# EXT_PATH = "C:/Users/cvolpano/shorescan_processing/QGIS/extrinsics"
# INT_PATH = "C:/Users/cvolpano/shorescan_processing/QGIS/intrinsics"

# NAD83 / UTM zone 19N. Marconi (~70.0 W) falls in zone 19; the camera
# x/y (420088 E, 4638319 N) only land on Cape Cod in zone 19, despite the
# "UTM zone 18" comment inside the EO YAMLs.
CRS = "EPSG:26919"

# --- nearest-date calibration matching (see load_nearest_calibration) ---
TRANSECT_DIR = "C:/Users/cvolp/shorescan_processing/QGIS/CACO03_timestack_20240920_transects"
IO_DIR = None          # None = look for *_IO.yaml inside TRANSECT_DIR
EO_DIR = None          # None = look for *_EO.yaml inside TRANSECT_DIR
CALIB_MODE = "prior"   # "prior" (latest on/before) or "nearest" (either side)
MAX_GAP_DAYS = 60      # warn when the chosen calibration is older/newer than this

GROUND_MODE = "flat"   # "flat" or "dem"

# --- flat mode settings ---
GROUND_Z = 0.0

# --- dem mode settings ---
DEM_LAYER_NAME = None   # e.g. "my_dem" if already loaded in the Layers panel
DEM_PATH = None         # e.g. "/path/to/dem.tif" if not already loaded
DEM_STEP = .250          # meters, initial ray-march step size along the ray
DEM_MAX_MARCH = 2000.0  # meters, safety cap on total ray-march distance

MAX_RANGE = 200.0       # meters - cap for sky-pointing / far-away rays
POINTS_PER_EDGE = 40    # density of sampling around image border


def load_yaml_config(path):
    """Loads the combined YAML schema described in the module docstring."""
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)

    if "cameras" not in cfg:
        raise ValueError("YAML must contain a top-level 'cameras' list.")

    shared_intrinsics = cfg.get("intrinsics", None)
    cameras = cfg["cameras"]

    for cam in cameras:
        if "intrinsics" not in cam:
            if shared_intrinsics is None:
                raise ValueError(
                    f"Camera '{cam.get('id', '?')}' has no intrinsics and no "
                    f"shared 'intrinsics' block was provided in the YAML."
                )
            cam["intrinsics"] = shared_intrinsics

        required_extrinsic = ["x", "y", "z", "azimuth", "tilt", "roll"]
        missing = [k for k in required_extrinsic if k not in cam]
        if missing:
            raise ValueError(f"Camera '{cam.get('id', '?')}' missing fields: {missing}")

        required_intrinsic = ["NU", "NV", "coU", "coV", "fx", "fy", "d1", "d2", "d3", "t1", "t2"]
        missing_k = [k for k in required_intrinsic if k not in cam["intrinsics"]]
        if missing_k:
            raise ValueError(f"Camera '{cam.get('id', '?')}' intrinsics missing fields: {missing_k}")

    return cameras


def load_split_yaml_files(extrinsic_dir, intrinsic_dir, id_from_filename=True, skip_on_missing=False):
    """
    Helper for the case where you have separate per-image YAML files, e.g.
    one extrinsics YAML (x/y/z/azimuth/tilt/roll) and one intrinsics YAML
    (NU/NV/coU/coV/fx/fy/d1/d2/d3/t1/t2) per image, matched by EXACT filename.

    Assumes filenames correspond 1:1 between the two directories, e.g.
    extrinsic_dir/CACO03_c1_20250123.yaml <-> intrinsic_dir/CACO03_c1_20250123.yaml

    Extrinsics and intrinsics are expected to share the same date in their
    filename. If a given extrinsics file has no exact-name match in the
    intrinsics folder, that's treated as a real data problem (not something
    to silently paper over with fuzzy/nearest-date matching) - it usually
    means a missing calibration file, a typo, or a naming convention
    mismatch between the two folders.

    On a mismatch, this prints a diagnostic comparing filenames in both
    folders (useful for spotting things like inconsistent date formats,
    e.g. "20250123" vs "2025-01-23", or a missing calibration for that date)
    before raising.

    Parameters
    ----------
    skip_on_missing : bool
        If False (default), raises on the first missing intrinsics file -
        use this while you're still cleaning up your file set, so problems
        surface immediately.
        If True, skips cameras with no matching intrinsics file (printing a
        warning for each) and continues processing the rest - use this once
        you've confirmed which images are legitimately missing calibration
        and want to process everything else in the meantime.

    Returns a `cameras` list in the same shape load_yaml_config() produces,
    so it can be used as a drop-in replacement.
    """
    cameras = []
    ext_files = sorted(f for f in os.listdir(extrinsic_dir) if f.endswith((".yaml", ".yml")))
    int_files = sorted(f for f in os.listdir(intrinsic_dir) if f.endswith((".yaml", ".yml")))
    int_files_set = set(int_files)

    skipped = []

    for fname in ext_files:
        img_id = os.path.splitext(fname)[0] if id_from_filename else fname

        if fname not in int_files_set:
            _print_match_diagnostic(fname, ext_files, int_files, extrinsic_dir, intrinsic_dir)
            if skip_on_missing:
                skipped.append(fname)
                continue
            else:
                raise FileNotFoundError(
                    f"No matching intrinsics file for '{fname}' in {intrinsic_dir}. "
                    f"See diagnostic above. Pass skip_on_missing=True to "
                    f"load_split_yaml_files() to skip this file and continue "
                    f"processing the rest instead of stopping here."
                )

        with open(os.path.join(extrinsic_dir, fname), "r") as f:
            ext = yaml.safe_load(f)
        with open(os.path.join(intrinsic_dir, fname), "r") as f:
            intr = yaml.safe_load(f)

        cam = dict(ext)
        cam["id"] = img_id
        cam["intrinsics"] = intr
        cameras.append(cam)

    if skipped:
        print(f"\nSkipped {len(skipped)} camera(s) with no matching intrinsics file:")
        for fname in skipped:
            print(f"  - {fname}")

    return cameras


def _print_match_diagnostic(missing_fname, ext_files, int_files, extrinsic_dir, intrinsic_dir):
    """Prints a side-by-side-ish comparison to help spot naming mismatches
    (typos, date format differences, missing calibration dates, etc.)."""
    print(f"\n{'='*70}")
    print(f"MISMATCH: '{missing_fname}' exists in extrinsics but not intrinsics.")
    print(f"{'='*70}")
    print(f"Extrinsics dir ({extrinsic_dir}) has {len(ext_files)} file(s).")
    print(f"Intrinsics dir ({intrinsic_dir}) has {len(int_files)} file(s):")
    for f in int_files:
        print(f"    {f}")

    # Try to help spot a likely near-match, e.g. same prefix but different
    # date formatting, or same camera ID with a different date entirely.
    stem = os.path.splitext(missing_fname)[0]
    parts = stem.split("_")
    camera_prefix = "_".join(parts[:-1]) if len(parts) > 1 else stem

    near_matches = [f for f in int_files if camera_prefix in f]
    if near_matches:
        print(f"\nFile(s) in intrinsics containing '{camera_prefix}' "
              f"(possible date mismatch or near-match):")
        for f in near_matches:
            print(f"    {f}")
    else:
        print(f"\nNo intrinsics files contain '{camera_prefix}' at all - "
              f"this camera may have no calibration file in this folder,"
              f"or the camera-ID portion of the filename doesn't match "
              f"between folders.")
    print(f"{'='*70}\n")


# ----------------------------------------------------------------------
# NEAREST-DATE CALIBRATION MATCHING
# ----------------------------------------------------------------------

# SITE (4 letters + 2 digits) _ camera (c1, c2, ...) _ [anything_] 8-digit date
# Matches e.g. CACO03_c1_20240801_IO, CACO03_c1_timestack_20240920_transect150,
# and CACO03_c1_01232025 (MMDDYYYY, as in the intrinsics/extrinsics folders).
_NAME_RE = re.compile(
    r"(?P<site>[A-Za-z]{4}\d{2})_(?P<cam>[cC]\d+)_(?:.*?_)?(?P<date>\d{8})"
)


def _parse_8digit_date(s):
    """Parse YYYYMMDD, falling back to MMDDYYYY. Returns datetime or None."""
    for fmt in ("%Y%m%d", "%m%d%Y"):
        try:
            d = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if 1990 <= d.year <= 2100:   # rejects e.g. '01232025' read as year 0123
            return d
    return None


def _parse_name(path):
    """Return (site, camera, date) from a filename, or None if no match."""
    m = _NAME_RE.search(Path(path).stem)
    if m is None:
        return None
    date = _parse_8digit_date(m["date"])
    if date is None:
        return None
    return m["site"].upper(), m["cam"].lower(), date


def _index_calibration(folder, tag, dedicated):
    """
    Build {(site, camera): [(date, path), ...]} for one calibration type.

    tag       : "IO" or "EO".
    dedicated : True if `folder` holds only this type (e.g. intrinsics/),
                so files need no _IO/_EO suffix. False for a shared folder,
                where only files whose stem ends in _IO / _EO are used.
    """
    index = {}
    for p in sorted(Path(folder).glob("*.y*ml")):
        stem = p.stem.upper()
        if "TRANSECT" in stem:
            continue
        if not dedicated and not stem.endswith(f"_{tag}"):
            continue
        parsed = _parse_name(p)
        if parsed is None:
            print(f"  skipping {p.name}: no SITE_cX_DATE pattern")
            continue
        site, cam, date = parsed
        index.setdefault((site, cam), []).append((date, p))
    return index


def _pick_closest(candidates, target, mode):
    """
    Choose the calibration closest to `target` from [(date, path), ...].

    mode="prior":   latest calibration on/before target; if none exist,
                    fall back to the earliest one after (with a note).
    mode="nearest": smallest absolute day difference (ties -> earlier).
    Returns (date, path, signed_gap_days) where gap > 0 means the
    calibration is AFTER the transect date.
    """
    if mode == "prior":
        before = [c for c in candidates if c[0] <= target]
        if before:
            d, p = max(before, key=lambda c: c[0])
        else:
            d, p = min(candidates, key=lambda c: c[0])
            print(f"  note: no calibration on/before {target:%Y-%m-%d}; "
                  f"using later file {p.name}")
    elif mode == "nearest":
        d, p = min(candidates, key=lambda c: (abs((c[0] - target).days), c[0]))
    else:
        raise ValueError(f"Unknown mode '{mode}' (use 'prior' or 'nearest').")
    return d, p, (d - target).days


def load_nearest_calibration(transect_dir, io_dir=None, eo_dir=None,
                             mode="prior", max_gap_days=60):
    """
    Build one camera per unique (site, camera, date) found among the
    transect YAMLs in `transect_dir`, pairing each with the IO and EO
    files closest in date for the same site and camera.

    Every transect file sharing a site/camera/date (transect20, 30, ...)
    uses the same camera geometry, so they collapse to one footprint.

    Parameters
    ----------
    transect_dir : str or Path
        Folder with *transect*.yaml files.
    io_dir, eo_dir : str, Path, or None
        Folders with intrinsics / extrinsics. None = use *_IO.yaml /
        *_EO.yaml inside transect_dir. A separate folder is treated as
        holding only that type (no suffix needed).
    mode : {"prior", "nearest"}
        Date rule; see _pick_closest().
    max_gap_days : int or None
        Print a warning when |gap| exceeds this. None disables warnings.

    Returns
    -------
    list of dict
        Same shape as load_yaml_config(), plus io_file, eo_file,
        io_gap_days, eo_gap_days for traceability.
    """
    transect_dir = Path(transect_dir)
    io_dir = Path(io_dir) if io_dir else transect_dir
    eo_dir = Path(eo_dir) if eo_dir else transect_dir

    io_index = _index_calibration(io_dir, "IO", dedicated=io_dir != transect_dir)
    eo_index = _index_calibration(eo_dir, "EO", dedicated=eo_dir != transect_dir)

    # Unique (site, camera, date) keys from the transect files
    targets = set()
    for p in transect_dir.glob("*.y*ml"):
        if "TRANSECT" in p.stem.upper():
            parsed = _parse_name(p)
            if parsed is not None:
                targets.add(parsed)
    if not targets:
        raise FileNotFoundError(f"No *transect*.yaml files found in {transect_dir}")

    cameras = []
    for site, cam_id, t_date in sorted(targets):
        key = (site, cam_id)
        label = f"{site}_{cam_id}_{t_date:%Y%m%d}"
        missing = [tag for tag, idx in (("IO", io_index), ("EO", eo_index))
                   if key not in idx]
        if missing:
            print(f"WARNING: {label}: no {'/'.join(missing)} file for "
                  f"{site} {cam_id}; skipping.")
            continue

        _, io_path, io_gap = _pick_closest(io_index[key], t_date, mode)
        _, eo_path, eo_gap = _pick_closest(eo_index[key], t_date, mode)

        for tag, path, gap in (("IO", io_path, io_gap), ("EO", eo_path, eo_gap)):
            if max_gap_days is not None and abs(gap) > max_gap_days:
                print(f"WARNING: {label}: {tag} {path.name} is {abs(gap)} days "
                      f"{'after' if gap > 0 else 'before'} the transect date.")

        with open(eo_path, "r") as f:
            cam = dict(yaml.safe_load(f))
        with open(io_path, "r") as f:
            cam["intrinsics"] = yaml.safe_load(f)

        cam.update(id=label, io_file=io_path.name, eo_file=eo_path.name,
                   io_gap_days=io_gap, eo_gap_days=eo_gap)
        cameras.append(cam)
        print(f"{label}: IO={io_path.name} ({io_gap:+d} d), "
              f"EO={eo_path.name} ({eo_gap:+d} d)")

    return cameras


# ----------------------------------------------------------------------
# MATH: rotation, distortion, ray casting
# ----------------------------------------------------------------------

def deg2rad(d):
    return d * math.pi / 180.0


def rot_about_axis(axis, angle_rad):
    x, y, z = axis
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    C = 1 - c
    return [
        [x*x*C + c,   x*y*C - z*s, x*z*C + y*s],
        [y*x*C + z*s, y*y*C + c,   y*z*C - x*s],
        [z*x*C - y*s, z*y*C + x*s, z*z*C + c],
    ]


def mat_vec(M, v):
    return [
        M[0][0]*v[0] + M[0][1]*v[1] + M[0][2]*v[2],
        M[1][0]*v[0] + M[1][1]*v[1] + M[1][2]*v[2],
        M[2][0]*v[0] + M[2][1]*v[1] + M[2][2]*v[2],
    ]


def normalize(v):
    n = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    return [v[0]/n, v[1]/n, v[2]/n]


def build_rotation_matrix(azimuth_deg, tilt_deg, roll_deg):
    """
    Camera-to-world rotation matrix.

    Convention:
      - World frame: X=East, Y=North, Z=Up.
      - Camera frame (standard CV convention): Xc=right (image +U), Yc=down
        (image +V), Zc=forward/boresight.
      - Identity pose (azimuth=0, tilt=90, roll=0): camera horizontal,
        pointing due North, level (Xc=East, Yc=Down, Zc=North).
      - azimuth: compass bearing, clockwise from North, about world Up axis.
      - tilt: 0=nadir, 90=horizon. Pivots the boresight about the camera's
        current right axis (Xc).
      - roll: rotation about the boresight (Zc). Positive = counterclockwise
        as seen from behind the camera looking forward.

    Returns 3x3 matrix R such that world_vector = R @ camera_vector.
    """
    East, North, Down = [1, 0, 0], [0, 1, 0], [0, 0, -1]

    R_az = rot_about_axis([0, 0, 1], deg2rad(-azimuth_deg))
    Xc = mat_vec(R_az, East)
    Yc = Down
    Zc = mat_vec(R_az, North)

    phi = deg2rad(90 - tilt_deg)
    R_tilt = rot_about_axis(Xc, -phi)
    Yc = mat_vec(R_tilt, Yc)
    Zc = mat_vec(R_tilt, Zc)

    R_roll = rot_about_axis(Zc, deg2rad(-roll_deg))
    Xc = mat_vec(R_roll, Xc)
    Yc = mat_vec(R_roll, Yc)

    Xc, Yc, Zc = normalize(Xc), normalize(Yc), normalize(Zc)
    return [
        [Xc[0], Yc[0], Zc[0]],
        [Xc[1], Yc[1], Zc[1]],
        [Xc[2], Yc[2], Zc[2]],
    ]


def distort(xn, yn, K):
    r2 = xn*xn + yn*yn
    radial = 1 + K["d1"]*r2 + K["d2"]*r2**2 + K["d3"]*r2**3
    xd = xn*radial + 2*K["t1"]*xn*yn + K["t2"]*(r2 + 2*xn*xn)
    yd = yn*radial + K["t1"]*(r2 + 2*yn*yn) + 2*K["t2"]*xn*yn
    return xd, yd


def pixel_to_undistorted_normalized(u, v, K):
    xn = (u - K["coU"]) / K["fx"]
    yn = (v - K["coV"]) / K["fy"]
    xd_target, yd_target = xn, yn
    for _ in range(20):
        xd, yd = distort(xn, yn, K)
        xn += (xd_target - xd)
        yn += (yd_target - yd)
    return xn, yn


def pixel_ray_world(u, v, K, R):
    xn, yn = pixel_to_undistorted_normalized(u, v, K)
    return normalize(mat_vec(R, [xn, yn, 1.0]))


# ----------------------------------------------------------------------
# GROUND INTERSECTION - flat plane
# ----------------------------------------------------------------------

def ray_ground_point_flat(cam_pos, ray_dir, ground_z, max_range):
    if ray_dir[2] < -1e-9:
        t = (ground_z - cam_pos[2]) / ray_dir[2]
        gx = cam_pos[0] + t * ray_dir[0]
        gy = cam_pos[1] + t * ray_dir[1]
        dist = math.sqrt((gx - cam_pos[0])**2 + (gy - cam_pos[1])**2)
        if dist <= max_range:
            return gx, gy

    horiz_len = math.sqrt(ray_dir[0]**2 + ray_dir[1]**2)
    if horiz_len < 1e-9:
        return None
    ux, uy = ray_dir[0] / horiz_len, ray_dir[1] / horiz_len
    return cam_pos[0] + max_range * ux, cam_pos[1] + max_range * uy


# ----------------------------------------------------------------------
# GROUND INTERSECTION - DEM ray marching
# ----------------------------------------------------------------------

class DemSampler:
    """Wraps a QGIS raster layer for fast point sampling along rays."""

    def __init__(self, layer):
        self.layer = layer
        self.provider = layer.dataProvider()
        self.extent = layer.extent()
        self.nodata = None
        try:
            self.nodata = self.provider.sourceNoDataValue(1)
        except Exception:
            pass

    def sample(self, x, y):
        """Returns elevation at (x, y) in layer CRS, or None if outside
        extent or nodata."""
        if not self.extent.contains(x, y):
            return None
        val, ok = self.provider.sample(QgsPointXY(x, y), 1)
        if not ok or val is None:
            return None
        if self.nodata is not None and val == self.nodata:
            return None
        return val


def get_dem_sampler(layer_name=None, path=None):
    if layer_name:
        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            raise ValueError(f"No loaded layer named '{layer_name}' found.")
        return DemSampler(layers[0])
    elif path:
        layer = QgsRasterLayer(path, "dem_for_footprints")
        if not layer.isValid():
            raise ValueError(f"Could not load raster at '{path}'.")
        QgsProject.instance().addMapLayer(layer)
        return DemSampler(layer)
    else:
        raise ValueError("Must provide either DEM_LAYER_NAME or DEM_PATH for dem mode.")


def ray_ground_point_dem(cam_pos, ray_dir, dem, max_range, max_march, step):
    """
    Ray-marches from cam_pos along ray_dir, looking for the point where the
    ray's height drops below the DEM surface height (i.e. terrain
    intersection). Uses a coarse march followed by a binary-search
    refinement between the last "above terrain" sample and the first
    "below terrain" sample.

    If the ray never comes down to the DEM within max_march (e.g. it's
    pointing into the sky, or the DEM has no data under it), falls back
    to a max_range cap along the ray's horizontal direction, same as the
    flat-ground behavior.
    """
    if ray_dir[2] >= -1e-9:
        # points level or upward -- can't come down to terrain (in a
        # simple monotonic march); go straight to the range-cap fallback
        return _dem_fallback_cap(cam_pos, ray_dir, max_range)

    prev_t = 0.0
    prev_above = True  # at t=0 we're at the camera, which is above terrain by definition
    t = step
    while t <= max_march:
        x = cam_pos[0] + t * ray_dir[0]
        y = cam_pos[1] + t * ray_dir[1]
        z = cam_pos[2] + t * ray_dir[2]

        terrain_z = dem.sample(x, y)
        if terrain_z is None:
            # off the DEM extent or nodata -- treat like we can't resolve
            # this ray against terrain; fall back to range cap
            return _dem_fallback_cap(cam_pos, ray_dir, max_range)

        above = z > terrain_z
        if not above:
            # crossed from above to below terrain between prev_t and t;
            # refine with binary search
            lo, hi = prev_t, t
            for _ in range(25):
                mid = (lo + hi) / 2
                mx = cam_pos[0] + mid * ray_dir[0]
                my = cam_pos[1] + mid * ray_dir[1]
                mz = cam_pos[2] + mid * ray_dir[2]
                mterrain = dem.sample(mx, my)
                if mterrain is None:
                    # shouldn't usually happen mid-refinement; bail to midpoint
                    break
                if mz > mterrain:
                    lo = mid
                else:
                    hi = mid
            final_t = (lo + hi) / 2
            fx = cam_pos[0] + final_t * ray_dir[0]
            fy = cam_pos[1] + final_t * ray_dir[1]
            dist = math.sqrt((fx - cam_pos[0])**2 + (fy - cam_pos[1])**2)
            if dist <= max_range:
                return fx, fy
            else:
                return _dem_fallback_cap(cam_pos, ray_dir, max_range)

        prev_t, prev_above = t, above
        t += step

    # never hit terrain within max_march
    return _dem_fallback_cap(cam_pos, ray_dir, max_range)


def _dem_fallback_cap(cam_pos, ray_dir, max_range):
    horiz_len = math.sqrt(ray_dir[0]**2 + ray_dir[1]**2)
    if horiz_len < 1e-9:
        return None
    ux, uy = ray_dir[0] / horiz_len, ray_dir[1] / horiz_len
    return cam_pos[0] + max_range * ux, cam_pos[1] + max_range * uy


# ----------------------------------------------------------------------
# FOOTPRINT COMPUTATION
# ----------------------------------------------------------------------

def compute_footprint(cam, ground_mode, ground_z, dem, max_range, max_march, dem_step, points_per_edge):
    K = cam["intrinsics"]
    R = build_rotation_matrix(cam["azimuth"], cam["tilt"], cam["roll"])
    cam_pos = [cam["x"], cam["y"], cam["z"]]
    NU, NV = K["NU"], K["NV"]

    border_pts = []
    for i in range(points_per_edge):
        border_pts.append((NU * i / points_per_edge, 0))
    for i in range(points_per_edge):
        border_pts.append((NU, NV * i / points_per_edge))
    for i in range(points_per_edge):
        border_pts.append((NU * (1 - i / points_per_edge), NV))
    for i in range(points_per_edge):
        border_pts.append((0, NV * (1 - i / points_per_edge)))

    footprint = []
    for u, v in border_pts:
        ray = pixel_ray_world(u, v, K, R)
        if ground_mode == "flat":
            pt = ray_ground_point_flat(cam_pos, ray, ground_z, max_range)
        elif ground_mode == "dem":
            pt = ray_ground_point_dem(cam_pos, ray, dem, max_range, max_march, dem_step)
        else:
            raise ValueError(f"Unknown ground_mode: {ground_mode}")
        if pt is not None:
            footprint.append(pt)
    return footprint

# QGIS LAYER CREATION

def create_layers(cameras, ground_mode, ground_z, dem, max_range, max_march, dem_step, points_per_edge, crs):
    poly_layer = QgsVectorLayer(f"Polygon?crs={crs}", "camera_fov_footprints", "memory")
    poly_provider = poly_layer.dataProvider()
    poly_provider.addAttributes([
        QgsField("id", QVariant.String),
        QgsField("azimuth", QVariant.Double),
        QgsField("tilt", QVariant.Double),
        QgsField("roll", QVariant.Double),
        QgsField("io_file", QVariant.String),
        QgsField("eo_file", QVariant.String),
        QgsField("io_gap_d", QVariant.Int),
        QgsField("eo_gap_d", QVariant.Int),
    ])
    poly_layer.updateFields()

    pt_layer = QgsVectorLayer(f"Point?crs={crs}", "camera_positions", "memory")
    pt_provider = pt_layer.dataProvider()
    pt_provider.addAttributes([
        QgsField("id", QVariant.String),
        QgsField("z", QVariant.Double),
        QgsField("azimuth", QVariant.Double),
        QgsField("tilt", QVariant.Double),
        QgsField("roll", QVariant.Double),
    ])
    pt_layer.updateFields()

    poly_feats = []
    pt_feats = []

    for cam in cameras:
        footprint = compute_footprint(
            cam, ground_mode, ground_z, dem, max_range, max_march, dem_step, points_per_edge
        )

        if len(footprint) < 3:
            print(f"WARNING: {cam['id']} produced too few footprint points, skipping.")
            continue

        qgs_pts = [QgsPointXY(x, y) for x, y in footprint]
        qgs_pts.append(qgs_pts[0])
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPolygonXY([qgs_pts]))
        # .get() keeps load_yaml_config() cameras (no match info) working
        f.setAttributes([cam["id"], cam["azimuth"], cam["tilt"], cam["roll"],
                         cam.get("io_file"), cam.get("eo_file"),
                         cam.get("io_gap_days"), cam.get("eo_gap_days")])
        poly_feats.append(f)

        pf = QgsFeature()
        pf.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(cam["x"], cam["y"])))
        pf.setAttributes([cam["id"], cam["z"], cam["azimuth"], cam["tilt"], cam["roll"]])
        pt_feats.append(pf)

    poly_provider.addFeatures(poly_feats)
    pt_provider.addFeatures(pt_feats)
    poly_layer.updateExtents()
    pt_layer.updateExtents()

    QgsProject.instance().addMapLayer(poly_layer)
    QgsProject.instance().addMapLayer(pt_layer)

    print(f"Added {len(poly_feats)} footprint polygon(s) and {len(pt_feats)} camera point(s).")


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

def main():
    # Pair each transect date with its closest-dated IO/EO files:
    cameras = load_nearest_calibration(
        TRANSECT_DIR, io_dir=IO_DIR, eo_dir=EO_DIR,
        mode=CALIB_MODE, max_gap_days=MAX_GAP_DAYS,
    )

    # Alternatives:
    # cameras = load_yaml_config(YAML_PATH)                # one combined YAML
    # cameras = load_split_yaml_files(EXT_PATH, INT_PATH)  # exact-name pairs

    dem = None
    if GROUND_MODE == "dem":
        dem = get_dem_sampler(layer_name=DEM_LAYER_NAME, path=DEM_PATH)

    create_layers(
        cameras=cameras,
        ground_mode=GROUND_MODE,
        ground_z=GROUND_Z,
        dem=dem,
        max_range=MAX_RANGE,
        max_march=DEM_MAX_MARCH,
        dem_step=DEM_STEP,
        points_per_edge=POINTS_PER_EDGE,
        crs=CRS,
    )


main()


# ----------------------------------------------------------------------
# EXAMPLE YAML (for reference / to create your own file)
# ----------------------------------------------------------------------

EXAMPLE_YAML = """
intrinsics:
  NU: 2448
  NV: 2048
  coU: 1274.19336741503
  coV: 1023.97839825612
  fx: 2575.69765891443
  fy: 2572.95555921878
  d1: -0.216463164783327
  d2: 0.221491907781633
  d3: -0.0596944654518389
  t1: 0.00102622622281805
  t2: 0.00200970852724846

cameras:
  - id: IMG_0001
    x: 420087.885757392
    y: 4638319.34468419
    z: 21.3497543187298
    azimuth: 73.1995858409559
    tilt: 71.1450595468697
    roll: -6.27932462929759
"""