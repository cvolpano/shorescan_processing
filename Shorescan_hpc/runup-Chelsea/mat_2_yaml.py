import argparse
import numpy as np
import scipy.io as sio
import yaml


def mat_to_serializable(obj):
    """Recursively convert MATLAB/numpy objects into plain Python types."""
    # MATLAB struct (scipy loads these as mat_struct objects)
    if isinstance(obj, sio.matlab.mat_struct):
        return {
            field: mat_to_serializable(getattr(obj, field))
            for field in obj._fieldnames
        }

    # numpy arrays
    if isinstance(obj, np.ndarray):
        # Array of structs / cell array
        if obj.dtype == object:
            if obj.size == 1:
                return mat_to_serializable(obj.item())
            return [mat_to_serializable(item) for item in obj.flatten()]

        # Numeric array
        if obj.size == 1:
            return mat_to_serializable(obj.item())
        return obj.tolist()

    # numpy scalar types
    if isinstance(obj, np.generic):
        return obj.item()

    # bytes -> string
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")

    # Already a plain type
    return obj


def load_mat(filepath):
    """Load a .mat file, handling both old-style and v7.3 (HDF5) formats."""
    try:
        data = sio.loadmat(filepath, struct_as_record=False, squeeze_me=True)
        # Drop MATLAB metadata keys
        return {
            k: v for k, v in data.items()
            if not k.startswith("__")
        }
    except NotImplementedError:
        # v7.3 files are HDF5-based; scipy can't read them directly
        return load_mat_v73(filepath)


def load_mat_v73(filepath):
    """Load MATLAB v7.3 (.mat) files using h5py."""
    import h5py

    def h5_to_serializable(obj):
        if isinstance(obj, h5py.Dataset):
            arr = obj[()]
            if isinstance(arr, np.ndarray):
                if arr.size == 1:
                    return mat_to_serializable(arr.item())
                return arr.tolist()
            return mat_to_serializable(arr)
        elif isinstance(obj, h5py.Group):
            return {k: h5_to_serializable(obj[k]) for k in obj.keys()}
        return obj

    result = {}
    with h5py.File(filepath, "r") as f:
        for key in f.keys():
            if key.startswith("#"):
                continue
            result[key] = h5_to_serializable(f[key])
    return result


def convert(mat_path, yaml_path):
    raw_data = load_mat(mat_path)
    clean_data = mat_to_serializable(raw_data)

    with open(yaml_path, "w") as f:
        yaml.dump(clean_data, f, default_flow_style=False, sort_keys=False)

    print(f"Converted '{mat_path}' -> '{yaml_path}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert a .mat file to .yaml")
    parser.add_argument("input", help="Path to input .mat file")
    parser.add_argument("output", nargs="?", help="Path to output .yaml file")
    args = parser.parse_args()

    output_path = args.output or args.input.rsplit(".", 1)[0] + ".yaml"
    convert(args.input, output_path)