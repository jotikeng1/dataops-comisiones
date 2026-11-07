# Permite importar los módulos de app/ tanto en local como dentro del contenedor
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for ruta in (RAIZ / "app", RAIZ):
    if (ruta / "etl.py").exists():
        sys.path.insert(0, str(ruta))
