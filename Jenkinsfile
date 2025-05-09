pipeline {
    agent any

    /* ---------- Ferramentas ---------- */
    tools { git 'Default' }

    environment {
        DOCKER_COMPOSE_PROJECT = 'wallet'
        ENV_FILE               = credentials('wallet-env-file')
        JENKINS_UID            = '115'   // confirme com ps -o uid
        JENKINS_GID            = '121'   // confirme com ps -o gid
    }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
    }

    stages {
        stage('Prep workspace + Checkout') {
            steps {
                // Conserta dono de execuções anteriores
                sh '''
                    docker run --rm -u 0:0 \
                      -v "$WORKSPACE":"$WORKSPACE" -w "$WORKSPACE" alpine \
                      chown -R ${JENKINS_UID}:${JENKINS_GID} . || true
                '''
                // NÃO deleteDir: se a stack anterior estiver rodando,
                // o workspace está em uso. Basta garantir permissões.
                checkout scm
            }
        }

        stage('Configurar ambiente') {
            steps {
                sh '''
                    rm -rf .env                    # <-- NOVO
                    cp "${ENV_FILE}" .env          # secret → workspace
                    chmod 600 .env                 # opcional

                    docker compose version
                    [ -f alembic.ini ] || cp alembic.ini.example alembic.ini
                    [ -d alembic ]   || { echo "Diretório alembic inexistente"; exit 1; }
                    
                    # Cria diretórios para Nginx e Certbot
                    mkdir -p nginx/conf certbot/conf certbot/www
                    
                    # Verifica domínio DuckDNS no .env
                    grep -q "DUCKDNS_DOMAIN" .env || { echo "DUCKDNS_DOMAIN não configurado no .env"; exit 1; }
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

        stage('Configurar HTTPS') {
            steps {
                sh '''
                    # Atualiza os arquivos de configuração com o domínio DuckDNS real
                    DUCKDNS_DOMAIN=$(grep DUCKDNS_DOMAIN .env | cut -d= -f2)
                    
                    # Substitui domínio nos arquivos de configuração
                    sed -i "s/apiwallet.duckdns.org/$DUCKDNS_DOMAIN/g" nginx/conf/app.conf
                    sed -i "s/apiwallet.duckdns.org/$DUCKDNS_DOMAIN/g" init-letsencrypt.sh
                    
                    # Configura e-mail para Let's Encrypt
                    EMAIL=$(grep ACME_EMAIL .env | cut -d= -f2)
                    if [ ! -z "$EMAIL" ]; then
                        sed -i "s/seu-email@exemplo.com/$EMAIL/g" init-letsencrypt.sh
                    fi
                    
                    # Torna o script executável
                    chmod +x init-letsencrypt.sh
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

        stage('Inicializar certificados') {
            steps {
                sh '''
                    # Executa o script para inicializar os certificados
                    # Use -y para aceitar automaticamente a sobreposição de certificados existentes
                    echo "y" | ./init-letsencrypt.sh
                '''
            }
        }

        stage('Smoke') {
            steps {
                sh '''
                    API_UP=$(docker compose -p ${DOCKER_COMPOSE_PROJECT} ps | grep api | grep Up | wc -l)
                    [ "$API_UP" -eq 1 ] || { echo "API não subiu"; exit 1; }
                    
                    NGINX_UP=$(docker compose -p ${DOCKER_COMPOSE_PROJECT} ps | grep nginx | grep Up | wc -l)
                    [ "$NGINX_UP" -eq 1 ] || { echo "Nginx não subiu"; exit 1; }
                '''
            }
        }
    }

    /* ---------- Pós-build ---------- */
    post {
        failure {
            echo '❌ Falhou – derrubando stack e limpando workspace.'

            // Derruba stack e remove volumes só em falha
            sh 'docker compose -p ${DOCKER_COMPOSE_PROJECT} down -v || true'

            // Ajusta permissão e APAGA o workspace (agora nada está montado)
            sh '''
                docker run --rm -u 0:0 \
                  -v "$WORKSPACE":"$WORKSPACE" -w "$WORKSPACE" alpine \
                  chown -R ${JENKINS_UID}:${JENKINS_GID} . || true
            '''
            deleteDir()
        }

        success {
            echo '🟢 Build ok – stack continua rodando em background.'
            sh '''
                docker run --rm -u 0:0 \
                  -v "$WORKSPACE":"$WORKSPACE" -w "$WORKSPACE" alpine \
                  chown -R ${JENKINS_UID}:${JENKINS_GID} . || true
            '''
        }
    }
}
