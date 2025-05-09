# Changelog

## Unreleased (2025-05-08)

### Features

* adiciona suporte a geração automática de changelog (2451384)
* first version (03a3efb)

### Code Refactoring

* simplifica a leitura e geração do changelog, atualiza o template e melhora o tratamento de erros na função de geração (429ad01)
* atualiza Dockerfile para incluir o Git, adiciona suporte ao python-semantic-release no pyproject.toml e implementa geração de changelog com fallback para GitAnalyzer (af71a30)

### Chores

* adiciona app/data ao .gitignore para evitar controle de versão (8aea807)
* remove app/data do controle de versão (fb73655)

