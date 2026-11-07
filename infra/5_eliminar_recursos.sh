#!/bin/bash
# Elimina los Data Lakes del proyecto (ejecutar al terminar, para no gastar crédito)
INICIALES="<INICIALES>"
for AMB in dev prd; do
  az group delete --name "az-${INICIALES}-${AMB}-de-rg-dataops" --yes --no-wait
done
# La VM de Jenkins se elimina aparte, SOLO tu VM (el grupo del taller puede ser compartido):
#   az vm delete -g rg-lab-dataops-taller -n vm-jenkins-${INICIALES} --yes
echo "Eliminación enviada (asíncrona)."
