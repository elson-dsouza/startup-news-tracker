from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules


def load_plugins() -> None:
    package_dir = Path(__file__).resolve().parent
    for module_info in iter_modules([str(package_dir)]):
        if module_info.name == "__init__":
            continue
        import_module(f"{__name__}.{module_info.name}")
