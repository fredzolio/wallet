pipeline {
    agent any
    
    environment {
        PYTHON_VERSION = '3.13'
        DOCKER_COMPOSE_PROJECT = 'wallet'
        ENV_FILE = credentials('wallet-env-file')
    }
    
    stages {
        stage('Checkout') {
            steps {
                checkout scm
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
            }
        }
        
        stage('Linting e Verificação de Código') {
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
                '''
            }
        }
        
        stage('Testes') {
            steps {
                sh '''
                    . .venv/bin/activate
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
                sh 'sleep 30'
                
                // Verificar estado dos containers
                sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} ps'
            }
        }
        
        stage('Executar Migrations') {
            steps {
                sh '''
                    # Executar migrations no banco de dados
                    docker-compose -p ${DOCKER_COMPOSE_PROJECT} exec -T api alembic upgrade head
                '''
            }
        }
        
        stage('Testes de Integração') {
            steps {
                sh '''
                    # Executar testes de integração contra serviços em execução
                    . .venv/bin/activate
                    # Aqui você pode adicionar testes de integração ou verificações
                    curl -s http://localhost:8000/api/v1/health | grep "status.*ok"
                '''
            }
        }
        
        stage('Validar Métricas') {
            steps {
                sh '''
                    # Verificar se Prometheus está recebendo métricas
                    curl -s http://localhost:9090/api/v1/targets | grep "state.*up"
                    
                    # Verificar se Grafana está disponível
                    curl -s http://localhost:3000/api/health | grep "database.*ok"
                '''
            }
        }
    }
    
    post {
        success {
            echo "Pipeline executado com sucesso! Aplicações rodando em Docker."
        }
        failure {
            echo "Pipeline falhou. Verifique os logs para mais detalhes."
            
            // Em caso de falha, tenta parar os containers
            sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} down || true'
        }
        cleanup {
            // Opção 1: Manter aplicações rodando
            echo "Aplicações continuam rodando em http://localhost:8000"
            
            // Opção 2: Desligar aplicações (descomente se preferir parar)
            // sh 'docker-compose -p ${DOCKER_COMPOSE_PROJECT} down'
            
            // Limpar workspace
            cleanWs()
        }
    }
} 