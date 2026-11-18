"""Diagnostica el uso de almacenamiento de Mi Clipper sin borrar archivos.

Uso desde la raíz del proyecto:
    python tools/diagnostico_almacenamiento.py

El script es de solo lectura. No modifica ni elimina archivos.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def format_size(size_bytes: int) -> str:
    """Convierte bytes a una unidad fácil de leer."""
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.2f} {unit}"
        value /= 1024
    return f"{value:,.2f} TB"


def folder_size(path: Path) -> int:
    """Calcula el tamaño de una carpeta sin detenerse por archivos inaccesibles."""
    total = 0

    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0

    if not path.is_dir():
        return 0

    for current_root, _, filenames in os.walk(path, onerror=lambda _error: None):
        for filename in filenames:
            file_path = Path(current_root) / filename
            try:
                if not file_path.is_symlink():
                    total += file_path.stat().st_size
            except OSError:
                continue

    return total


def get_pip_cache_path() -> Path | None:
    """Obtiene la ubicación de la caché de pip, si pip puede consultarla."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "cache", "dir"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        cache_path = result.stdout.strip()
        return Path(cache_path).expanduser() if cache_path else None
    except (OSError, subprocess.SubprocessError):
        return None


def get_huggingface_cache_path() -> Path:
    """Resuelve la caché usada normalmente por Hugging Face Hub."""
    explicit_cache = (
        os.environ.get("HF_HUB_CACHE")
        or os.environ.get("HUGGINGFACE_HUB_CACHE")
    )
    if explicit_cache:
        return Path(explicit_cache).expanduser()

    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home).expanduser() / "hub"

    return Path.home() / ".cache" / "huggingface" / "hub"


def collect_locations() -> list[tuple[str, Path]]:
    """Reúne ubicaciones relevantes y evita medir dos veces la misma ruta."""
    locations: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add(label: str, path: Path | None) -> None:
        if path is None:
            return
        try:
            normalized = str(path.expanduser().resolve(strict=False)).casefold()
        except OSError:
            normalized = str(path).casefold()
        if normalized not in seen:
            seen.add(normalized)
            locations.append((label, path.expanduser()))

    add("Temporales de Mi Clipper", Path(tempfile.gettempdir()) / "clipper_trabajo")
    add("Caché de modelos Whisper (Hugging Face)", get_huggingface_cache_path())
    add("Caché de pip", get_pip_cache_path())

    for folder_name in (".venv", "venv", "env"):
        add(f"Entorno Python: {folder_name}", PROJECT_ROOT / folder_name)

    for folder_name in ("salida", "guardados", "outputs", "temp", "tmp", "cache", ".cache"):
        add(f"Carpeta local: {folder_name}", PROJECT_ROOT / folder_name)

    return locations


def report_disk_space() -> None:
    """Muestra el espacio total, usado y libre de la unidad del proyecto."""
    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
    except OSError as error:
        print(f"No pude consultar el espacio de la unidad: {error}")
        return

    used = usage.total - usage.free
    print("\nESPACIO DE LA UNIDAD DEL PROYECTO")
    print(f"  Total:    {format_size(usage.total)}")
    print(f"  Usado:    {format_size(used)}")
    print(f"  Libre:    {format_size(usage.free)}")


def report_locations() -> None:
    """Muestra el tamaño de las carpetas que suelen ocupar espacio."""
    print("\nCARPETAS Y CACHÉS")
    print("-" * 78)

    total_found = 0
    for label, path in collect_locations():
        if not path.exists():
            print(f"[No existe] {label}")
            print(f"            {path}")
            continue

        size = folder_size(path)
        total_found += size
        print(f"{format_size(size):>12}  {label}")
        print(f"             {path}")

        if "Hugging Face" in label and path.is_dir():
            try:
                model_folders = sorted(
                    (child for child in path.iterdir() if child.is_dir()),
                    key=lambda child: folder_size(child),
                    reverse=True,
                )
            except OSError:
                model_folders = []

            for model_folder in model_folders[:10]:
                model_size = folder_size(model_folder)
                print(f"               - {format_size(model_size):>10}  {model_folder.name}")

    print("-" * 78)
    print(f"Tamaño combinado de las ubicaciones encontradas: {format_size(total_found)}")


def main() -> None:
    print("=" * 78)
    print("MI CLIPPER PERSONAL - DIAGNÓSTICO DE ALMACENAMIENTO")
    print("=" * 78)
    print(f"Proyecto: {PROJECT_ROOT}")
    print("Modo: solo lectura. No se elimina ni modifica ningún archivo.")

    report_disk_space()
    report_locations()

    print("\nRECOMENDACIONES")
    print("  1. Si 'Temporales de Mi Clipper' tiene archivos, cierra la aplicación.")
    print("     Después puedes borrar únicamente esa carpeta; se crea de nuevo al procesar.")
    print("  2. La caché de Whisper evita descargar el modelo en cada ejecución.")
    print("     No la borres salvo que aceptes volver a descargar los modelos.")
    print("  3. La caché de pip se puede limpiar manualmente con:")
    print("     python -m pip cache purge")
    print("  4. No borres el entorno .venv/venv si no estás preparado para reinstalar")
    print("     las dependencias con pip install -r requirements.txt.")
    print("\nDiagnóstico terminado. No se cambió ningún archivo.")


if __name__ == "__main__":
    main()
