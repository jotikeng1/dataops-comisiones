#!/bin/bash

# Archivo de variables
VARIABLES_FILE="1_local_variables.txt"

if [ ! -f "$VARIABLES_FILE" ]; then
  echo ">> No se encontró el archivo $VARIABLES_FILE"
  exit 1
fi

# Leer archivo y limpiar saltos de línea y retorno de carro
while IFS='=' read -r key value; do
  # Eliminar espacios en blanco, saltos de línea y retorno de carro
  clean_key=$(echo "$key" | tr -d '\r' | xargs)
  clean_value=$(echo "$value" | tr -d '\r' | xargs)
  
  case "$clean_key" in
    INICIALES) INICIALES="$clean_value" ;;
    SUSCRIPCION) SUSCRIPCION="$clean_value" ;;
    PAT) PAT="$clean_value" ;;
    DEVOPS) DEVOPS="$clean_value" ;;
    TENANT) TENANT="$clean_value" ;;
  esac
done < "$VARIABLES_FILE"

# Ruta del script y su carpeta
SCRIPT_PATH="$(realpath "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
SCRIPT_NAME="$(basename "$0")"

echo "📁 Ejecutando en directorio: $SCRIPT_DIR"

# Buscar archivos .sh, .json, .tfvars y *backend.tf, excluyendo este script
find "$SCRIPT_DIR" \( -name "*.sh" -o -name "*.json" -o -name "*.yml" -o -name "*backend.tf" \) ! -name "$SCRIPT_NAME" -type f | while read -r file; do
  echo ">>> Reemplazando variables en: $file"
  sed -i'' -e "s|<INICIALES>|$INICIALES|g" \
           -e "s|<SUSCRIPCION>|$SUSCRIPCION|g" \
           -e "s|<PAT>|$PAT|g" \
           -e "s|<DEVOPS>|$DEVOPS|g" \
           -e "s|<TENANT>|$TENANT|g" "$file"
done

echo ">> Reemplazo completado en archivos dentro de '$SCRIPT_DIR'"
