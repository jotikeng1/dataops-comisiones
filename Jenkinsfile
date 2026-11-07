// =====================================================================
// Pipeline CI/CD - Comisiones DataOps
// CI : validar herramientas → construir imagen → pruebas automáticas
// CD : desplegar en DEV → quality gate (aprobación automática) → PRD
// =====================================================================
pipeline {
    agent { label 'azure_agent' }

    parameters {
        string(name: 'PERIODO', defaultValue: '202610',
               description: 'Periodo AAAAMM del archivo de comisiones a procesar')
    }

    environment {
        COMPOSE_PROJECT_NAME = 'reporte_comisiones'
        STORAGE_MODE         = 'azure'
        SMTP_ENABLED         = 'true'
    }

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timestamps()
        disableConcurrentBuilds()   // evita que dos builds usen el mismo proyecto compose a la vez
    }

    stages {
        stage('1. Preparar Entorno') {
            steps {
                echo "> Rama: ${env.GIT_BRANCH} | Periodo: ${params.PERIODO}"
                sh 'docker --version'
                sh 'docker compose version'
            }
        }

        stage('2. Construir Imagen Docker') {
            steps {
                sh 'docker compose build --no-cache'
            }
        }

        stage('3. Pruebas Automáticas (CI)') {
            steps {
                sh 'mkdir -p reports'
                sh '''docker compose run --rm --user "$(id -u):$(id -g)" app \
                      python -m pytest -v tests --junitxml=/reports/pytest.xml'''
            }
            post {
                always { junit allowEmptyResults: true, testResults: 'reports/pytest.xml' }
            }
        }

        stage('4. Desplegar en DEV') {
            steps {
                withCredentials([
                    string(credentialsId: 'pg-password',   variable: 'PG_PASSWORD'),
                    string(credentialsId: 'adls-dev-conn', variable: 'AZURE_STORAGE_CONNECTION_STRING')
                ]) {
                    sh 'AMBIENTE=dev PERIODO=$PERIODO docker compose run --rm app python main.py'
                }
            }
        }

        stage('5. Quality Gate DEV (aprobación automática)') {
            steps {
                withCredentials([
                    string(credentialsId: 'adls-dev-conn', variable: 'AZURE_STORAGE_CONNECTION_STRING')
                ]) {
                    // Si la verificación falla (exit 1), el pipeline se detiene y PRD no se toca
                    sh 'AMBIENTE=dev docker compose run --rm app python main.py --verificar --periodo $PERIODO'
                }
                echo '> Calidad DEV aprobada automáticamente. Se promueve a PRD.'
            }
        }

        stage('6. Desplegar en PRD') {
            when { expression { env.GIT_BRANCH?.endsWith('main') } }
            steps {
                withCredentials([
                    string(credentialsId: 'pg-password',   variable: 'PG_PASSWORD'),
                    string(credentialsId: 'adls-prd-conn', variable: 'AZURE_STORAGE_CONNECTION_STRING')
                ]) {
                    sh 'AMBIENTE=prd PERIODO=$PERIODO docker compose run --rm app python main.py'
                    sh 'AMBIENTE=prd docker compose run --rm app python main.py --verificar --periodo $PERIODO'
                }
            }
        }
    }

    post {
        always {
            echo '> Limpieza de recursos y contenedores'
            sh 'docker compose down --volumes --remove-orphans || true'
        }
        success { echo 'Pipeline OK: datos procesados, verificados y publicados en el Data Lake.' }
        failure { echo 'Pipeline FALLIDO: revisa la etapa en rojo. PRD no fue modificado.' }
    }
}
