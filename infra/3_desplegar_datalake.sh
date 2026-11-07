#!/bin/bash
# =====================================================================
# Despliega el Data Lake de DEV y PRD con plantillas ARM y sube el CSV
# a la zona raw. Ejecutar en Azure Cloud Shell (Bash) desde la carpeta infra/
# después de correr ./2_local_reemplazar_variables.sh
# =====================================================================
set -e

INICIALES="<INICIALES>"
SUBSCRIPTION_ID="<SUSCRIPCION>"
LOCATION="eastus2"
CSV_LOCAL="../data/ComisionEmpleados_V1_202610.csv"

az account set --subscription "$SUBSCRIPTION_ID"

for AMB in dev prd; do
  RG="az-${INICIALES}-${AMB}-de-rg-dataops"
  SA="az${INICIALES}${AMB}dedlslake"
  echo "===================================================="
  echo ">> [$AMB] Grupo de recursos: $RG"
  az group create --name "$RG" --location "$LOCATION" -o none

  echo ">> [$AMB] Desplegando plantilla ARM del Data Lake: $SA"
  az deployment group create \
    --resource-group "$RG" \
    --name "datalake-$AMB" \
    --template-file arm/datalake.json \
    --parameters @arm/datalake.parameters.$AMB.json \
    -o table

  CONN=$(az storage account show-connection-string -g "$RG" -n "$SA" --query connectionString -o tsv)

  echo ">> [$AMB] Subiendo CSV a lake/raw/comisiones/"
  az storage blob upload \
    --connection-string "$CONN" \
    --container-name lake \
    --name "raw/comisiones/$(basename "$CSV_LOCAL")" \
    --file "$CSV_LOCAL" \
    --overwrite -o none
done

echo ""
echo "===================================================="
echo " Listo. Ahora registra en Jenkins (Credentials → Secret text):"
echo "   adls-dev-conn  = cadena de conexión de az${INICIALES}devdedlslake"
echo "   adls-prd-conn  = cadena de conexión de az${INICIALES}prddedlslake"
echo " Para verlas:"
echo "   az storage account show-connection-string -g az-${INICIALES}-dev-de-rg-dataops -n az${INICIALES}devdedlslake -o tsv"
echo "   az storage account show-connection-string -g az-${INICIALES}-prd-de-rg-dataops -n az${INICIALES}prddedlslake -o tsv"
echo "===================================================="
