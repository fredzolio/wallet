pipeline {
    agent any                       // mesmo executor de sempre

    tools {
        git 'Default'               // /usr/bin/git já configurado em Manage → Tools
    }

    environment {
        PYTHON_VERSION         = '3.13'
        DOCKER_COMPOSE_PROJECT = 'wallet'

        // secret text/file no Jenkins: wallet-env-file
        ENV_FILE               = credentials('wallet-env-file')

        // UID e GID do processo Jenkins (confirme com `ps -o uid,gid -p $(pgrep -f jenkins.war)`)
        JENKINS_UID            = '115'
        JENKINS_GID            = '121'
    }

    stages {
        stage('Cleanup + Checkout') {
            steps {
                cleanWs()            // apaga o que sobrou do build anterior
                checkout scm
            }
        }

        stage('Configurar ambiente') {
            steps {
                sh """
                    cp \"${ENV_FILE}\" .env

                    docker --version
                    docker compose version

                    # Garante alembic
                    [ -f alembic.ini ] || cp alembic.ini.example alembic.ini
                    [ -d alembic ] || { echo 'Diretório alembic inexistente'; exit 1; }
                """
            }
        }

        stage('Lint & Testes') {
            steps {
                sh '''
                    set -eu
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

        stage('Build & Up') {
            steps {
                // Se o seu compose ainda não usa UID/GID, tudo bem:
                // a etapa de chown no post vai corrigir a posse dos arquivos.
                sh '''
                    docker compose -p ${DOCKER_COMPOSE_PROJECT} build
                    docker compose -p ${DOCKER_COMPOSE_PROJECT} up -d
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
                    [ "$API_UP" -eq 1 ] || { echo "API não subiu"; exit 1; }
                '''
            }
        }
    }

    /* ---------- Pós-build ---------- */
    post {
        always {
            // 1) Derruba containers + named volumes
            sh 'docker compose -p ${DOCKER_COMPOSE_PROJECT} down -v || true'

            // 2) Ajusta OWNER dos arquivos para Jenkins (115:121)
            sh '''
                docker run --rm -u 0:0 \
                  -v "$WORKSPACE":"$WORKSPACE" -w "$WORKSPACE" alpine \
                  chown -R ${JENKINS_UID}:${JENKINS_GID} .
            '''

            // 3) Agora é seguro limpar o workspace
            deleteDir()
        }

        success {
            echo '✅ Pipeline finalizado com sucesso.'
        }

        failure {
            echo '❌ Falhou — veja os logs acima.'
        }
    }
}
