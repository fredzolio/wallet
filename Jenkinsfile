// Jenkinsfile (versão corrigida)
pipeline {
    agent any

    /* -------------- Ferramentas ---------------- */
    tools {
        // Em: Manage Jenkins → Global Tool Configuration → Git
        git 'Default'
    }

    /* -------------- Variáveis de ambiente ------ */
    environment {
        PYTHON_VERSION          = '3.13'
        DOCKER_COMPOSE_PROJECT  = 'wallet'
        ENV_FILE                = credentials('wallet-env-file')   // secret file
        JENKINS_UID             = '115'   // uid do processo Jenkins (ps -o uid)
        JENKINS_GID             = '121'   // gid do processo Jenkins (ps -o gid)
    }

    /* -------------- Opções do pipeline --------- */
    options {
        // Começa SEMPRE com workspace vazio (evita arquivos órfãos)
        skipDefaultCheckout()
        disableConcurrentBuilds()
    }

    /* -------------- Stages --------------------- */
    stages {

        stage('Prep workspace') {
            steps {
                deleteDir()          // limpa RESTOS antes do checkout
                checkout scm
            }
        }

        stage('Configurar ambiente') {
            steps {
                sh """
                    cp \"${ENV_FILE}\" .env

                    echo 'Versões:'
                    docker --version
                    docker compose version

                    # garante alembic.ini
                    [ -f alembic.ini ] || cp alembic.ini.example alembic.ini
                    [ -d alembic ] || { echo 'Diretório alembic inexistente'; exit 1; }
                """
            }
        }

        stage('Lint & Test') {
            steps {
                sh '''
                    set -e
                    curl -LsSf https://astral.sh/uv/install.sh | sh
                    export PATH="$HOME/.local/bin:$PATH"
                    uv add ruff mypy
                    uv sync
                    uv venv .venv
                    . .venv/bin/activate
                    uv run ruff check .
                    uv run mypy app
                    uv run pytest app/tests -v
                '''
            }
        }

        stage('Build & Up (docker compose)') {
            steps {
                sh '''
                    # Se seus Dockerfiles/compose aceitarem UID/GID, já passa aqui
                    export UID=${JENKINS_UID}
                    export GID=${JENKINS_GID}

                    docker compose -p ${DOCKER_COMPOSE_PROJECT} build
                    docker compose -p ${DOCKER_COMPOSE_PROJECT} up -d

                    echo '⏳ Aguardando containers subirem…'
                    sleep 10
                    docker compose -p ${DOCKER_COMPOSE_PROJECT} ps
                    docker compose -p ${DOCKER_COMPOSE_PROJECT} logs --no-color api
                '''
            }
        }

        stage('Smoke check') {
            steps {
                sh '''
                    API_UP=$(docker compose -p ${DOCKER_COMPOSE_PROJECT} ps | grep api | grep Up | wc -l)
                    if [ "$API_UP" -eq 0 ]; then
                        echo 'API não subiu – exibindo logs:'
                        docker compose -p ${DOCKER_COMPOSE_PROJECT} logs --no-color api || true
                        exit 1
                    fi
                '''
            }
        }
    }

    /* -------------- Pós-build ------------------ */
    post {
        always {
            // derruba stack e remove volumes - não deixa nada preso
            sh 'docker compose -p ${DOCKER_COMPOSE_PROJECT} down -v || true'

            // remove containers órfãos (mas não faz system prune global)
            sh 'docker container prune -f || true'

            // workspace agora só tem arquivos com uid 115 → pode apagar
            deleteDir()
        }

        success {
            echo '✅ Pipeline executado com sucesso.'
        }

        failure {
            echo '❌ Pipeline falhou – verifique os logs acima.'
        }
    }
}
