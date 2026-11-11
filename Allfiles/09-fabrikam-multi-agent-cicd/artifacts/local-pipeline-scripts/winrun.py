"""Run a module/script with subprocess resolving 'az' -> az.cmd on Windows (local emulation only)."""
import runpy, shutil, subprocess, sys
_orig = subprocess.Popen.__init__
def _init(self, args, *a, **k):
    if isinstance(args, (list, tuple)) and args and args[0] == "az":
        args = [shutil.which("az") or "az.cmd", *args[1:]]
    _orig(self, args, *a, **k)
subprocess.Popen.__init__ = _init
mode, target, *rest = sys.argv[1:]
sys.argv = [target, *rest]
sys.path.insert(0, ".")
if mode == "-m":
    runpy.run_module(target, run_name="__main__", alter_sys=True)
else:
    runpy.run_path(target, run_name="__main__")
