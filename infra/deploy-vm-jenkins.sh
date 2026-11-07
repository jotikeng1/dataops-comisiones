#!/bin/bash

# =======================================================
# Script de Despliegue de Laboratorio Azure
# Docker + Jenkins v2.574 (JDK 21) en Puerto 80
# =======================================================

echo "--------------------------------------------------------"
echo "  Despliegue de Laboratorio Azure: Docker + Jenkins v2.574"
echo "--------------------------------------------------------"

# 1. Solicitar iniciales y sanitizar texto
read -p "Ingresa las iniciales del estudiante (ej. jmd): " RAW_INITIALS
INITIALS=$(echo "$RAW_INITIALS" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')

if [ -z "$INITIALS" ]; then
    echo "Error: Debes ingresar al menos una inicial válida."
    exit 1
fi

# 2. Variables de entorno compartidas para el taller
# Nota: Si una región o SKU se agota en Azure, puedes cambiar LOCATION a "eastus2", "centralus" o "southcentralus"
LOCATION="eastus2"
RESOURCE_GROUP="rg-lab-dataops-taller"
VM_NAME="vm-jenkins-$INITIALS"
ADMIN_USER="azureuser"
VM_SIZE="Standard_D2als_v6"         # 2 vCPU, 4GB RAM (AMD EPYC v6)

# 3. Generar contraseña segura de 20 caracteres
ADMIN_PASSWORD=$(tr -dc 'A-Za-z0-9@#%*+=-_' < /dev/urandom | head -c 20)

echo ""
echo "Configuración asignada:"
echo " - Grupo de Recursos (Compartido): $RESOURCE_GROUP"
echo " - Nombre de la VM:               $VM_NAME"
echo " - Región de Azure:               $LOCATION"
echo " - Tamaño de la VM:               $VM_SIZE"
echo ""

# 4. Asegurar la existencia del Grupo de Recursos único y crear la Máquina Virtual
echo "--> [1/4] Verificando/Creando Grupo de Recursos compartido '$RESOURCE_GROUP'..."
az group create --name $RESOURCE_GROUP --location $LOCATION --output table

echo ""
echo "--> [2/4] Creando Máquina Virtual Ubuntu 22.04 ($VM_NAME)..."
az vm create \
  --resource-group $RESOURCE_GROUP \
  --name $VM_NAME \
  --image Ubuntu2204 \
  --size $VM_SIZE \
  --admin-username $ADMIN_USER \
  --admin-password "$ADMIN_PASSWORD" \
  --authentication-type password \
  --public-ip-sku Standard \
  --output table

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Error al crear la Máquina Virtual en la región '$LOCATION' o con el tamaño '$VM_SIZE'."
    echo "Sugerencia: Cambia LOCATION='eastus' o 'centralus' en el script, o prueba con VM_SIZE='Standard_B2ms' o 'Standard_D2s_v3'."
    exit 1
fi

echo ""
echo "--> [3/4] Apertura de puertos en el Network Security Group (22 SSH, 80 Jenkins Web)..."
az vm open-port --resource-group $RESOURCE_GROUP --name $VM_NAME --port 22 --priority 1001 --output table
az vm open-port --resource-group $RESOURCE_GROUP --name $VM_NAME --port 80 --priority 1002 --output table

# 5. Ejecutar script de instalación con Java 21 y Jenkins 2.574
echo ""
echo "--> [4/4] Instalando Java 21, Docker y Jenkins v2.574 (espera ~2 minutos)..."

INSTALL_SCRIPT=$(cat << 'EOF'
export DEBIAN_FRONTEND=noninteractive

# Esperar a que los bloqueos iniciales de APT se liberen
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do sleep 5; done

# 1. Desinstalar dependencias antiguas
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do 
  apt-get remove -y $pkg
done

# 2. Configurar repositorio oficial de Docker e instalar Java 21
apt-get update -qq
apt-get install -y -qq ca-certificates curl openjdk-21-jdk git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -qq
apt-get -y -qq install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3. Configurar usuario y habilitar servicios
groupadd -f docker
usermod -aG docker azureuser
systemctl enable docker.service
systemctl enable containerd.service

# 4. Crear estructura y docker-compose.yml con Jenkins v2.574 y JDK 21
mkdir -p /home/azureuser/jenkins
cat << 'DOCKER_COMPOSE' > /home/azureuser/jenkins/docker-compose.yml
services:
  jenkins:
    container_name: jenkins
    image: jenkins/jenkins:2.574-slim-jdk21
    restart: unless-stopped
    ports:
      - 80:8080
    volumes:
      - jenkins_home:/var/jenkins_home/
volumes:
  jenkins_home:
DOCKER_COMPOSE

chown -R azureuser:azureuser /home/azureuser/jenkins

# 5. Levantar el contenedor
cd /home/azureuser/jenkins
docker compose up -d
EOF
)

az vm run-command invoke \
  --resource-group $RESOURCE_GROUP \
  --name $VM_NAME \
  --command-id RunShellScript \
  --scripts "$INSTALL_SCRIPT" \
  --output table

# 6. Obtener la IP pública
PUBLIC_IP=$(az vm show -d -g $RESOURCE_GROUP -n $VM_NAME --query publicIps -o tsv)

echo ""
echo "=========================================================="
echo " ¡Despliegue Finalizado con Éxito!"
echo "=========================================================="
echo "  CREDENCIALES VM / SSH:"
echo "    - Usuario:     $ADMIN_USER"
echo "    - Contraseña:  $ADMIN_PASSWORD"
echo "    - Conexión:    ssh $ADMIN_USER@$PUBLIC_IP"
echo ""
echo "  ACCESO A JENKINS v2.574 (Puerto 80):"
echo "    - URL Web:     http://$PUBLIC_IP"
echo "    - URL WebHook: http://$PUBLIC_IP/github-webhook/"
echo ""
echo "  OBTENER CLAVE INICIAL DE JENKINS:"
echo "    ssh $ADMIN_USER@$PUBLIC_IP 'sudo docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword'"
echo ""
echo "  LIMPIAR AMBIENTE (Elimina TODO el taller con un solo comando):"
echo "    az group delete --name $RESOURCE_GROUP --yes --no-wait"
echo ""
echo "  LIMPIAR SOLO ESTA VM (Opcional por estudiante):"
echo "    az vm delete -g $RESOURCE_GROUP -n $VM_NAME --yes"
echo "=========================================================="