"""
qc_filter_overlays.py

Author : Chelsea A. Volpano (cvolpano@gmail.com)
Created: 2026-11-10
Model  : Claude Opus 5.5 (claude.ai)

Summary
-------
Interactive good / bad / training sort of Shorescan results. Each runup
overlay in RESULTS_DIR is shown one at a time. Your key press decides where
EVERY file with the same timestamp/camera/transect ("key") goes, in every
folder listed in FOLDERS:

    g or y  good      -> stays in the folder (downstream code keeps reading it)
    b or n  bad       -> moved to <folder>/_rejected
    t       training  -> moved to <folder>/_training, and <key>.png is added
                         to RESULTS_DIR/forTraining.txt
    u       undo the last decision (moves the files back)
    q / Esc quit (rerun later to resume)

Nothing is deleted. Decisions are saved in RESULTS_DIR/qc_filter_log.csv as
you go. Decisions from the older qc_runup_overlays.py (qc_log.csv) are
imported, so overlays you already reviewed are not shown again.

Key matching
------------
The key is cut out of each file name with one regular expression, STEM_RE,
so prefixes and suffixes don't matter:
    overlay_<key>.jpg, <key>_runup.nc, <key>.flipped_grayscale_res.npz, ...
    key = 1730124000.Mon.Oct.28_14_00_00.GMT.2024.CACO03.c1.ras_transect70

Usage (from a terminal, so the window takes key presses)
--------------------------------------------------------
    python qc_filter_overlays.py              # review overlays
    python qc_filter_overlays.py --sync-only  # only re-apply logged decisions
                                              # (e.g. after adding a folder)

Changelog
---------
2026-11-10  First version. Replaces qc_runup_overlays.py for multi-folder
            sorting; that script is kept unchanged.
"""

import argparse
import csv
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt

# ---------------------------------------------------------------- CONFIG ----
RESULTS_DIR = Path(r"F:\results\runup")         # overlay images live here
OVERLAY_PREFIX = "overlay_"
IMG_EXTS = {".png", ".jpg", ".jpeg"}

# Folders whose files are sorted along with each overlay.
# label: (folder, glob pattern). The pattern limits which files are touched.
# TODO: replace the example paths with your folders.
FOLDERS = {
    "runup_nc": (Path(r"F:\results\netcdf"), "*.nc"),
    "segformer_npz": (Path(r"F:\results\grayscale\full"), "*.npz"),
    "timestack": (Path(r"F:\images"), "*.png"),
    "grayscale": (Path(r"F:\results\grayscale\full"), "*.png"),
    "overlays": (RESULTS_DIR, "overlay_*.jpg"),  # sort overlays too
}

# Where each category's files go: None = stay in the folder itself.
# "_rejected" matches the older script, so earlier rejects are already in place.
CATEGORIES = {"good": None, "bad": "_rejected", "training": "_training"}
KEYS = {"y": "good", "g": "good", "b": "bad","n": "bad", "t": "training"}

# epoch . day . mon . time . GMT . year . site . cN . ras_transectNN
STEM_RE = re.compile(r"\d{10}\..+?\.c\d+\.ras_transect\d+")

LOG_PATH = RESULTS_DIR / "qc_filter_log.csv"
OLD_LOG_PATH = RESULTS_DIR / "qc_log.csv"      # from qc_runup_overlays.py
TRAIN_PATH = RESULTS_DIR / "forTraining.txt"
LOG_FIELDS = ["utc_time", "key", "decision", "n_moved"]
# ----------------------------------------------------------------------------


def key_of(name):
    """Timestamp/camera/transect key in a file name, or None."""
    m = STEM_RE.search(name)
    return m.group(0) if m else None


# -- Indexing -----------------------------------------------------------------
# Scan each folder (and its _rejected/_training subfolders) ONCE and store
# {key: [paths]}. Every later lookup is then an O(1) dictionary access
# instead of a new directory scan per overlay, which matters with thousands
# of files on a hard drive.
def build_index():
    index = {}
    subdirs = [s for s in CATEGORIES.values() if s]
    for label, (root, pattern) in FOLDERS.items():
        idx = defaultdict(list)
        for d in [root] + [root / s for s in subdirs]:
            if not d.is_dir():
                continue
            for p in d.glob(pattern):          # not recursive
                k = key_of(p.name)
                if k:
                    idx[k].append(p)
        index[label] = idx
    return index


def place(index, key, category):
    """Move every file for `key`, in every folder, to `category`'s location.

    Files already in the right place are left alone, so calling this twice
    is harmless (idempotent). Returns the number of files moved.
    """
    n = 0
    sub = CATEGORIES[category]
    for label, (root, _) in FOLDERS.items():
        dest = root / sub if sub else root
        new_paths = []
        for p in index[label].get(key, []):
            target = dest / p.name
            if p.parent != dest:
                if target.exists():
                    print(f"  ! {target} exists, {p.name} left in place")
                    target = p
                else:
                    dest.mkdir(exist_ok=True)
                    shutil.move(str(p), str(target))
                    n += 1
            new_paths.append(target)
        if new_paths:
            index[label][key] = new_paths
    return n


def misplaced(index, key, category):
    """Number of files for `key` not yet in `category`'s location."""
    sub = CATEGORIES[category]
    return sum(p.parent != (root / sub if sub else root)
               for label, (root, _) in FOLDERS.items()
               for p in index[label].get(key, []))


# -- Decision log -------------------------------------------------------------
def load_decisions():
    """Latest decision per key: new log on top of the imported old log."""
    dec = {}
    old_map = {"accept": "good", "reject": "bad",
               "reject_training": "training"}
    if OLD_LOG_PATH.exists():
        with OLD_LOG_PATH.open(newline="") as f:
            for r in csv.DictReader(f):
                k = key_of(r["overlay"])
                if k is None:
                    continue
                if r["decision"] in old_map:
                    dec[k] = old_map[r["decision"]]
                else:                          # "undo"
                    dec.pop(k, None)
    if LOG_PATH.exists():
        with LOG_PATH.open(newline="") as f:
            for r in csv.DictReader(f):        # later rows win
                if r["decision"] in CATEGORIES:
                    dec[r["key"]] = r["decision"]
                else:                          # "undo" -> unreviewed
                    dec.pop(r["key"], None)
    return dec


def append_log(key, decision, n_moved):
    """Add one row now, so a crash or quit loses nothing."""
    new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"utc_time": datetime.now(timezone.utc)
                    .isoformat(timespec="seconds"),
                    "key": key, "decision": decision, "n_moved": n_moved})


class TrainingList:
    """forTraining.txt kept in step with 'training' decisions."""

    def __init__(self, decisions):
        self.names = (set(TRAIN_PATH.read_text().split())
                      if TRAIN_PATH.exists() else set())
        self.names |= {f"{k}.png" for k, c in decisions.items()
                       if c == "training"}
        self.write()

    def update(self, key, category):
        name = f"{key}.png"
        before = name in self.names
        if category == "training":
            self.names.add(name)
        else:
            self.names.discard(name)
        if before != (name in self.names):
            self.write()

    def write(self):
        if self.names or TRAIN_PATH.exists():
            TRAIN_PATH.write_text("".join(f"{s}\n" for s in sorted(self.names)))


# -- Interactive review -------------------------------------------------------
class Reviewer:
    """One window; matplotlib calls on_key() for every key press.

    plt.show() runs an event loop. All state (position, undo stack) lives on
    this object, which main() keeps in a variable so it is not
    garbage-collected (matplotlib holds callbacks only weakly).
    """

    def __init__(self, todo, index, decisions, training):
        self.todo, self.index = todo, index
        self.decisions, self.training = decisions, training
        self.i = 0
        self.history = []                      # (i, key, previous decision)
        self.fig, self.ax = plt.subplots(figsize=(13, 7))
        self.ax.set_axis_off()
        self.im = None
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.show()

    def show(self):
        if self.i >= len(self.todo):
            self.ax.set_title("All overlays reviewed. u = undo, q = close.")
            self.fig.canvas.draw_idle()
            return
        key, path = self.todo[self.i]
        img = plt.imread(path)                 # one image in memory at a time
        h, w = img.shape[:2]
        if self.im is None:
            self.im = self.ax.imshow(img, aspect="auto")
        else:                                  # reuse artist: faster redraw
            self.im.set_data(img)
            self.im.set_extent((-0.5, w - 0.5, h - 0.5, -0.5))
            self.ax.set_xlim(-0.5, w - 0.5)
            self.ax.set_ylim(h - 0.5, -0.5)
        counts = "   ".join(f"{lab}: {len(self.index[lab].get(key, []))}"
                            for lab in FOLDERS)
        self.ax.set_title(
            f"[{self.i + 1}/{len(self.todo)}] {key}\nfiles  {counts}\n"
            "g = good   b = bad   t = training   u = undo   q = quit",
            fontsize=9)
        self.fig.canvas.draw_idle()

    def on_key(self, event):
        k = (event.key or "").lower()
        if k in KEYS and self.i < len(self.todo):
            self.decide(KEYS[k])
        elif k == "u":
            self.undo()
        elif k in ("q", "escape"):
            plt.close(self.fig)

    def decide(self, category):
        key, _ = self.todo[self.i]
        prev = self.decisions.get(key)
        n = place(self.index, key, category)
        self.decisions[key] = category
        self.training.update(key, category)
        append_log(key, category, n)
        print(f"{category:8s} {key}  ({n} file(s) moved)")
        self.history.append((self.i, key, prev))
        self.i += 1
        self.show()

    def undo(self):
        if not self.history:
            return
        self.i, key, prev = self.history.pop()
        # Unreviewed files sit in the main folder, same as "good".
        n = place(self.index, key, prev or "good")
        if prev:
            self.decisions[key] = prev
        else:
            self.decisions.pop(key, None)
        self.training.update(key, prev)
        append_log(key, prev or "undo", n)
        print(f"undo     {key}  ({n} file(s) moved back)")
        self.show()


# -- Main ---------------------------------------------------------------------
def sync(index, decisions, ask=True):
    """Apply logged decisions to all folders (e.g. a newly added folder)."""
    todo = {k: c for k, c in decisions.items() if misplaced(index, k, c)}
    if not todo:
        return
    n_files = sum(misplaced(index, k, c) for k, c in todo.items())
    print(f"{n_files} file(s) for {len(todo)} reviewed key(s) are not in "
          f"their category folder: {dict(Counter(todo.values()))}")
    if ask and input("Move them now? [y/N] ").strip().lower() != "y":
        print("Skipped. Rerun with --sync-only to apply later.")
        return
    moved = sum(place(index, k, c) for k, c in todo.items())
    print(f"Moved {moved} file(s).")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--sync-only", action="store_true",
                        help="apply logged decisions to all folders and exit")
    args = parser.parse_args()

    missing = [str(d) for d in [RESULTS_DIR] + [r for r, _ in FOLDERS.values()]
               if not d.is_dir()]
    if missing:
        sys.exit("Folder(s) not found (edit CONFIG):\n  " + "\n  ".join(missing))

    index = build_index()
    decisions = load_decisions()
    training = TrainingList(decisions)
    sync(index, decisions, ask=not args.sync_only)
    if args.sync_only:
        return

    overlays = sorted(p for p in RESULTS_DIR.glob(f"{OVERLAY_PREFIX}*")
                      if p.suffix.lower() in IMG_EXTS)
    keyed = [(key_of(p.name), p) for p in overlays]
    todo = [(k, p) for k, p in keyed if k and k not in decisions]
    print(f"{len(overlays)} overlays, {len(overlays) - len(todo)} already "
          f"reviewed, {len(todo)} to review. Counts so far: "
          f"{dict(Counter(decisions.values()))}")
    for lab in FOLDERS:
        n0 = sum(not index[lab].get(k) for k, _ in todo)
        if n0:
            print(f"  {n0} overlay(s) have no file in '{lab}'.")
    if not todo:
        return

    plt.rcParams["keymap.quit"] = []           # free 'q' for our handler
    plt.rcParams["keymap.grid"] = []           # free 'g' (default: grid)
    plt.rcParams["keymap.grid_minor"] = []     # free 'G'
    reviewer = Reviewer(todo, index, decisions, training)  # noqa: F841
    plt.show()
    print(f"Decisions logged to {LOG_PATH}")


if __name__ == "__main__":
    main()