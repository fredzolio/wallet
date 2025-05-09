pipeline {
    agent any
    
    environment {
        PYTHON_VERSION = '3.13'
        DOCKER_COMPOSE_PROJECT = 'wallet'
        ENV_FILE = credentials('wallet-env-file')
        BUILD_SUCCESS = 'false'
    }
    
    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        
        stage('Corrigir Permissões') {
            steps {
                sh 'find ${WORKSPACE} -type d -exec chmod 755 {} \\; || true'
                sh 'find ${WORKSPACE} -type f -exec chmod 644 {} \\; || true'
            }
        }
        
        stage('Prune') {
          steps {
            sh 'docker system prune -f'
          }
        }

        stage('Configurar Ambiente') {
            steps {
                // Copiar arquivo de env para execução local
                sh 'cp ${ENV_FILE} .env'
                
                // Verificar ferramentas instaladas
                sh '''
                    docker --version
                    docker-compose --version
                '''
                
                // Verificar existência de arquivos importantes
                sh '''
                    echo "Verificando arquivos de configuração..."
                    if [ ! -f "alembic.ini" ]; then
                        echo "ERRO: alembic.ini não encontrado!"
                        if [ -f "alembic.ini.example" ]; then
                            echo "Copiando alembic.ini.example para alembic.ini"
                            cp alembic.ini.example alembic.ini
                        else
                            echo "Arquivo alembic.ini.example também não existe!"
                            exit 1
                        fi
                    fi
                    
                    if [ ! -d "alembic" ]; then
                        echo "ERRO: Diretório alembic não encontrado!"
                        exit 1
                    fi
                '''
            }
        }
        
        stage('Linting e Testes') {
            steps {
                sh '''
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
        
        stage('Construir e Iniciar Aplicações') {
            steps {
                // Construir e iniciar todos os serviços com Docker Compose
                sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} build'
                sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} up -d'
                
                // Esperar aplicações inicializarem
                sh 'sleep 10'
                
                // Verificar estado dos containers
                sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} ps'
                
                // Verificar logs da API para diagnosticar problemas
                sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} logs api'
                
                // Verificar se o container da API está rodando
                sh '''
                    API_RUNNING=$(docker-compose -p ${DOCKER_COMPOSE_PROJECT} ps | grep api | grep "Up" | wc -l)
                    if [ $API_RUNNING -eq 0 ]; then
                        echo "ERRO: Container da API não está rodando!"
                        echo "Verificando arquivos dentro do container:"
                        docker-compose -p ${DOCKER_COMPOSE_PROJECT} exec -T db ls -la /var/lib/postgresql/data || true
                        docker-compose -p ${DOCKER_COMPOSE_PROJECT} exec -T api ls -la /app || true
                        docker-compose -p ${DOCKER_COMPOSE_PROJECT} exec -T api cat /alembic.ini || true
                        exit 1
                    fi
                '''
                
                // Marcar que a build foi bem-sucedida
                script {
                    env.BUILD_SUCCESS = 'true'
                }
            }
        }
        
        stage('Finalização') {
            steps {
                script {
                    if (env.BUILD_SUCCESS == 'true') {
                        echo "Pipeline executado com sucesso! Aplicações rodando em Docker."
                    } else {
                        echo "Pipeline falhou. Verificando logs para diagnóstico."
                        sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} logs api || true'
                        sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} down || true'
                    }
                    
                    // Limpar permissões e corrigir arquivos antes de limpar
                    sh 'find ${WORKSPACE} -type d -exec chmod 755 {} \\; || true'
                    sh 'find ${WORKSPACE} -type f -exec chmod 644 {} \\; || true'
                    
                    echo "Aplicações continuam rodando em http://localhost:8000"
                    // Opção alternativa: Desligar aplicações (descomente se preferir parar)
                    // sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} down'
                }
            }
        }
    }
    
    post {
        always {
            cleanWs()
        }
    }
} 