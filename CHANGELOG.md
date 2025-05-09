# Changelog

## Unreleased (2025-05-09)

### Features

* adiciona suporte a geração automática de changelog (2451384)
* first version (03a3efb)

### Code Refactoring

* atualiza a geração do changelog para usar markdown e remove dependências obsoletas (01adf8f)
* simplifica a leitura e geração do changelog, atualiza o template e melhora o tratamento de erros na função de geração (429ad01)
* atualiza Dockerfile para incluir o Git, adiciona suporte ao python-semantic-release no pyproject.toml e implementa geração de changelog com fallback para GitAnalyzer (af71a30)

### Chores

* corrige a instalação de dependências no CI para usar modo editável (300a57d)
* simplifica a instalação de dependências no CI removendo a opção de instalação em modo editável (caf86c6)
* adiciona app/data ao .gitignore para evitar controle de versão (8aea807)
* remove app/data do controle de versão (fb73655)

