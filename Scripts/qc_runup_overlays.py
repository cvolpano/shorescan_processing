"""
qc_runup_overlays.py

Author : Chelsea A. Volpano (cvolpano@gmail.com)
Created: 2026-11-03
Model  : Claude Opus 5.5 (claude.ai)

Summary
-------
Interactive QA/QC of Shorescan modeled runup. Shows each runup-on-timestack
overlay in RESULTS_DIR one at a time and waits for a key:

    y  accept      n  reject      u  undo last      q / Esc  quit
    t  training: add <stem>.png to RESULTS_DIR/forTraining.txt (once) AND
       reject (netCDF moved to _rejected), then advance. u undoes both.

A rejected overlay's matching runup netCDF(s) are MOVED (not deleted) to
RUNUP_DIR/_rejected, so read_transect_nc.ipynb no longer picks them up and a
mistake can be undone. Every keypress is appended to RESULTS_DIR/qc_log.csv,
so you can quit at any time and rerun to resume where you stopped.

File matching (shared stem, different prefix/suffix):
    overlay_<stem>.jpg   <->   <stem>_runup.nc
    e.g. stem = 1727778600.Tue.Oct.01_10_30_00.GMT.2024.CACO03.c1.ras_transect20

Run from a terminal (not Jupyter) so matplotlib opens a normal window:
    python qc_runup_overlays.py

Changelog
---------
2026-11-03  First version.
2026-11-03  Fix: key presses ignored (Reviewer was garbage-collected).
2026-11-03  Added 't' key: logs <stem>.png to forTraining.txt.
2026-11-03  't' now always rejects too and advances; undo reverses both.
"""

import csv
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt

# ---------------------------------------------------------------- CONFIG ----
RESULTS_DIR = Path(r"D:\usgs\results\runup")      # overlay images
RUNUP_DIR = Path(r"D:\usgs\results\netcdf")          # TODO: set to your runup netCDF folder
# In WSL these would be Path("/mnt/d/usgs/results") etc.

OVERLAY_PREFIX, OVERLAY_SUFFIX = "overlay_", ""
NC_PREFIX, NC_SUFFIX = "", "_runup"

IMG_EXTS = {".png", ".jpg", ".jpeg"}
LOG_NAME = "qc_log.csv"
REJECT_SUBDIR = "_rejected"
LOG_FIELDS = ["utc_time", "overlay", "decision", "files"]
TRAIN_NAME = "forTraining.txt"              # one <stem>.png per line
# ----------------------------------------------------------------------------


def stem_of(path, prefix, suffix):
    """Shared stem of a file name, or None if it lacks the prefix/suffix.

    Path.stem drops only the final extension (.jpg / .nc), so the dots inside
    the Shorescan names are kept.
    """
    s = path.stem
    if not (s.startswith(prefix) and s.endswith(suffix)):
        return None
    return s[len(prefix):len(s) - len(suffix)]


def index_netcdfs(runup_dir):
    """Map stem -> list of netCDF paths.

    Building this dict once makes each later lookup O(1), instead of
    re-scanning the folder for every overlay. glob() is not recursive, so
    files already in _rejected are ignored.
    """
    idx = defaultdict(list)
    for p in runup_dir.glob("*.nc"):
        key = stem_of(p, NC_PREFIX, NC_SUFFIX)
        if key is not None:
            idx[key].append(p)
    return idx


def latest_decisions(log_path):
    """Last logged decision per overlay ('accept', 'reject' or 'undo')."""
    if not log_path.exists():
        return {}
    with log_path.open(newline="") as f:
        # Later rows overwrite earlier ones, so the newest decision wins.
        return {r["overlay"]: r["decision"] for r in csv.DictReader(f)}


def append_log(log_path, overlay, decision, files):
    """Append one row; written immediately so a crash loses nothing."""
    new = not log_path.exists()
    with log_path.open("a", newline="") as f:
        w = csv.DictWriter(f, LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "utc_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "overlay": overlay,
            "decision": decision,
            "files": ";".join(files),
        })


def move_files(paths, dest_dir):
    """Move files into dest_dir; skip (with a warning) if the name exists."""
    dest_dir.mkdir(exist_ok=True)
    moved = []
    for p in paths:
        dst = dest_dir / p.name
        if dst.exists():
            print(f"  ! {dst.name} already in {dest_dir.name}, left in place")
            continue
        shutil.move(str(p), str(dst))
        moved.append(dst)
    return moved


class Reviewer:
    """One matplotlib window; key presses drive the review.

    matplotlib is event driven: plt.show() runs a loop that waits for events
    (key presses) and calls on_key() for each. All state (current index,
    undo history) lives on this object between calls.
    """

    def __init__(self, todo, nc_index, log_path):
        self.todo, self.nc_index, self.log_path = todo, nc_index, log_path
        self.reject_dir = RUNUP_DIR / REJECT_SUBDIR
        self.i = 0
        self.history = []                      # (overlay name, moved paths)
        # Training list: load names already in the file into a set so each
        # 't' press is an O(1) duplicate check, not a re-read of the file.
        self.train_path = RESULTS_DIR / TRAIN_NAME
        self.train_set = (set(self.train_path.read_text().split())
                          if self.train_path.exists() else set())
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
        stem, path = self.todo[self.i]
        img = plt.imread(path)                 # only one image in memory
        h, w = img.shape[:2]
        if self.im is None:
            self.im = self.ax.imshow(img, aspect="auto")
        else:
            # Reusing the image artist is faster than clearing and redrawing
            # the axes for every overlay.
            self.im.set_data(img)
            self.im.set_extent((-0.5, w - 0.5, h - 0.5, -0.5))
            self.ax.set_xlim(-0.5, w - 0.5)
            self.ax.set_ylim(h - 0.5, -0.5)
        n_nc = len(self.nc_index.get(stem, []))
        nc_note = f"{n_nc} netCDF" if n_nc else "NO matching netCDF"
        # self.ax.set_title(
        #     f"[{self.i + 1}/{len(self.todo)}] {path.name}\n{nc_note}   |   "
        #     "y = accept   n = reject   u = undo   q = quit", fontsize=9)
        # ^ Replaced 2026-11-03: title now lists the 't' key and shows
        #   whether this image is already in forTraining.txt.
        train_note = ("   |   [in forTraining]"
                      if f"{stem}.png" in self.train_set else "")
        self.ax.set_title(
            f"[{self.i + 1}/{len(self.todo)}] {path.name}\n{nc_note}"
            f"{train_note}   |   y = accept   n = reject   t = training   "
            "u = undo   q = quit", fontsize=9)
        self.fig.canvas.draw_idle()

    def on_key(self, event):
        key = (event.key or "").lower()
        if key in ("y", "n") and self.i < len(self.todo):
            self.decide(key == "y")
        elif key == "u":
            self.undo()
        elif key == "t" and self.i < len(self.todo):
            self.mark_training()
        elif key in ("q", "escape"):
            plt.close(self.fig)

    def decide(self, accept, train_name=None):
        """Accept or reject the current overlay, then advance.

        train_name: set by 't' when this reject also added a line to
        forTraining.txt, so undo can take that line back out.
        """
        stem, path = self.todo[self.i]
        moved = [] if accept else move_files(
            self.nc_index.get(stem, []), self.reject_dir)
        # append_log(self.log_path, path.name, "accept" if accept else "reject",
        #            [p.name for p in moved])
        # ^ Replaced 2026-11-03: 't' rejects are logged as "reject_training".
        decision = ("accept" if accept else
                    "reject_training" if train_name else "reject")
        append_log(self.log_path, path.name, decision, [p.name for p in moved])
        if not accept:
            print(f"{decision} {path.name}: moved {len(moved)} file(s)")
        # self.history.append((path.name, moved))
        # ^ Replaced 2026-11-03: history also stores the training name.
        self.history.append((path.name, moved, train_name))
        self.i += 1
        self.show()

    def mark_training(self):
        """Add <stem>.png to forTraining.txt (once), then REJECT and advance.

        Changed 2026-11-03: training images are always rejects, so 't' now
        also moves the netCDF to _rejected and goes to the next image.
        """
        stem, _ = self.todo[self.i]
        name = f"{stem}.png"
        # if name in self.train_set:
        #     print(f"already in {TRAIN_NAME}: {name}")
        #     return
        # ^ Replaced 2026-11-03: a name already listed must still be
        #   rejected, so skip only the write, not the whole step.
        added = name not in self.train_set
        if added:
            with self.train_path.open("a") as f:   # append: written now
                f.write(name + "\n")
            self.train_set.add(name)
            print(f"added to {TRAIN_NAME}: {name}")
        else:
            print(f"already in {TRAIN_NAME}: {name}")
        # self.show()                            # refresh title marker
        # ^ Replaced 2026-11-03: decide() advances and redraws.
        self.decide(False, train_name=name if added else None)

    def undo(self):
        """Undo the last decision made this session."""
        if not self.history:
            return
        # name, moved = self.history.pop()
        # ^ Replaced 2026-11-03: history entries now have 3 fields.
        name, moved, train_name = self.history.pop()
        for dst in moved:
            shutil.move(str(dst), str(RUNUP_DIR / dst.name))
        if train_name:
            # Rewrite the list without this name (the file is small, so
            # rewriting it whole is simpler and safe).
            self.train_set.discard(train_name)
            lines = self.train_path.read_text().split()
            self.train_path.write_text(
                "".join(f"{s}\n" for s in lines if s != train_name))
            print(f"removed from {TRAIN_NAME}: {train_name}")
        append_log(self.log_path, name, "undo", [p.name for p in moved])
        print(f"undid {name}: restored {len(moved)} file(s)")
        self.i -= 1
        self.show()


def main():
    # matplotlib binds 'q' to close-window by default; free it for our handler.
    plt.rcParams["keymap.quit"] = []

    for d in (RESULTS_DIR, RUNUP_DIR):
        if not d.is_dir():
            sys.exit(f"Folder not found: {d}  (edit CONFIG at top of script)")

    log_path = RESULTS_DIR / LOG_NAME
    done = {k for k, v in latest_decisions(log_path).items() if v != "undo"}

    overlays = sorted(p for p in RESULTS_DIR.iterdir()
                      if p.suffix.lower() in IMG_EXTS)
    keyed = [(stem_of(p, OVERLAY_PREFIX, OVERLAY_SUFFIX), p) for p in overlays]
    todo = [(k, p) for k, p in keyed if k is not None and p.name not in done]
    n_bad = sum(k is None for k, _ in keyed)

    nc_index = index_netcdfs(RUNUP_DIR)
    n_no_nc = sum(k not in nc_index for k, _ in todo)

    print(f"{len(overlays)} images, {len(done)} already reviewed, "
          f"{len(todo)} to review.")
    if n_bad:
        print(f"  {n_bad} image(s) skipped: name doesn't start with "
              f"'{OVERLAY_PREFIX}'.")
    if n_no_nc:
        print(f"  {n_no_nc} overlay(s) have no matching netCDF in {RUNUP_DIR}.")
    if not todo:
        return

    # Reviewer(todo, nc_index, log_path)
    # ^ Fixed 2026-11-03: with no variable holding the Reviewer, Python
    #   garbage-collected it. matplotlib keeps only weak references to
    #   callbacks, so the key handler silently disappeared and key presses
    #   did nothing.
    reviewer = Reviewer(todo, nc_index, log_path)  # noqa: F841 (keep alive)
    plt.show()
    print(f"Decisions logged to {log_path}")


if __name__ == "__main__":
    main()
