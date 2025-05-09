pipeline {
    agent any

    /* ------------- Ferramentas ------------- */
    tools {
        git 'Default'                       // /usr/bin/git registrado em "Manage → Tools"
    }

    /* ------------- Variáveis --------------- */
    environment {
        DOCKER_COMPOSE_PROJECT = 'wallet'
        ENV_FILE               = credentials('wallet-env-file')

        // uid/gid do processo Jenkins (confirme com `ps -o uid,gid -p $(pgrep -f jenkins.war)`)
        JENKINS_UID = '115'
        JENKINS_GID = '121'
    }

    /* ------------- Opções ------------------ */
    options {
        skipDefaultCheckout(true)           // <-- DESLIGA o checkout implícito
        disableConcurrentBuilds()
    }

    stages {

        /* PREP: conserta dono do workspace e faz checkout */
        stage('Prep workspace + Checkout') {
            steps {
                /* Se o build anterior deixou arquivos root:root, conserta-os */
                sh '''
                    docker run --rm -u 0:0 \
                      -v "$WORKSPACE":"$WORKSPACE" -w "$WORKSPACE" alpine \
                      sh -c "chown -R ${JENKINS_UID}:${JENKINS_GID} . || true"
                '''

                deleteDir()        // agora o Jenkins pode apagar tudo

                checkout scm       // checkout sob controle do seu pipeline
            }
        }

        /* ---------- demais estágios (sem mudanças) --------- */
        stage('Configurar ambiente') {
            steps {
                sh '''
                    cp "${ENV_FILE}" .env
                    docker compose version
                    [ -f alembic.ini ] || cp alembic.ini.example alembic.ini
                    [ -d alembic ] || { echo "Sem diretório alembic"; exit 1; }
                '''
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
                sh '''
                    docker compose -p ${DOCKER_COMPOSE_PROJECT} build
                    docker compose -p ${DOCKER_COMPOSE_PROJECT} up -d
                    sleep 10
                    docker compose -p ${DOCKER_COMPOSE_PROJECT} ps
                '''
            }
        }

        stage('Smoke') {
            steps {
                sh '''
                    API_UP=$(docker compose -p ${DOCKER_COMPOSE_PROJECT} ps | grep api | grep Up | wc -l)
                    [ "$API_UP" -eq 1 ] || { echo "API não subiu"; exit 1; }
                '''
            }
        }
    }

    /* ------------- Pós-build --------------- */
    post {
        always {
            sh 'docker compose -p ${DOCKER_COMPOSE_PROJECT} down -v || true'

            /* Garante que tudo volte a ser 115:121 antes de apagar */
            sh '''
                docker run --rm -u 0:0 \
                  -v "$WORKSPACE":"$WORKSPACE" -w "$WORKSPACE" alpine \
                  chown -R ${JENKINS_UID}:${JENKINS_GID} . || true
            '''

            deleteDir()
        }

        success { echo '✅ Pipeline finalizado com sucesso.' }
        failure { echo '❌ Pipeline falhou — veja os logs acima.' }
    }
}
