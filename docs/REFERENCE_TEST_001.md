# Referência de teste 001 — parser sintético de overrides

## Objetivo

Executar localmente dois testes unitários públicos do [3dsrecomp](https://github.com/fearkov/3dsrecomp), referentes a marcadores de substituição de funções. Os casos de teste usam strings sintéticas; não exigem ROM, dump, firmware, chaves ou recursos extraídos.

## Fonte fixada

- Repositório: https://github.com/fearkov/3dsrecomp
- Commit: [c3f21f94ba50d688025febc8974ff348d471b587](https://github.com/fearkov/3dsrecomp/commit/c3f21f94ba50d688025febc8974ff348d471b587)
- Testes: [src/overrides.rs](https://github.com/fearkov/3dsrecomp/blob/c3f21f94ba50d688025febc8974ff348d471b587/src/overrides.rs)
- Lockfile de dependências: [Cargo.lock](https://github.com/fearkov/3dsrecomp/blob/c3f21f94ba50d688025febc8974ff348d471b587/Cargo.lock)
- Testes selecionados: **marks_are_found_outside_comments** e **bad_marks_are_reported**.

O primeiro verifica que marcadores em comentários/strings são ignorados e que exemplos válidos produzem endereços/nomes esperados. O segundo verifica a rejeição de sintaxe inválida e endereços duplicados.

## Método sem GitHub Actions

Use [tools/run_reference_test_001.ps1](../tools/run_reference_test_001.ps1) em um computador Windows com Git e Rust/Cargo instalados. Este teste compila e executa código de terceiros e dependências baixadas; o script exige opt-in explícito. Prefira Windows Sandbox ou uma VM descartável, use uma conta sem privilégios administrativos e não exponha arquivos pessoais/credenciais nesse ambiente. O script não é uma sandbox por si só. O script:

1. cria um diretório temporário isolado;
2. faz um fetch raso do commit de referência e verifica o SHA exato;
3. confirma que os dois testes esperados existem na fonte;
4. direciona o cache de Cargo e os artefatos de build para o diretório temporário;
5. executa apenas os testes de overrides;
6. grava um log local em %TEMP%\PokeUltrarecomp-reference-test-001.log;
7. limpa o checkout e os artefatos temporários ao sair, inclusive em caso de falha, salvo uso explícito de -KeepWorkspace.

O script não altera a configuração global do Git nem pede credenciais. O fetch é do código-fonte público da ferramenta; dependências Rust podem ser baixadas durante o teste. Os diretórios temporários são removidos para limitar o uso de armazenamento. O log é mantido no diretório temporário; revise e redija caminhos locais antes de compartilhá-lo.

## Pré-requisitos

- Git disponível no PATH.
- Rust/Cargo 1.88.0 ou mais recente, conforme o rust-version declarado pelo pacote fixado.
- Acesso à rede para obter o commit e as dependências.
- Espaço temporário para o checkout e a compilação.

Não instale toolchains nem dependências com privilégios elevados. Use fontes oficiais e, se a instalação de Rust for necessária, siga as instruções oficiais: https://www.rust-lang.org/tools/install.

## Comando

Abra PowerShell na pasta de trabalho do projeto e execute:

    .\tools\run_reference_test_001.ps1 -AcceptThirdPartyCode

Para capturar a saída numa cópia adicional do log:

    .\tools\run_reference_test_001.ps1 2>&1 | Tee-Object "$env:TEMP\PokeUltrarecomp-reference-test-001-console.log"

O script escreve seu próprio log resumido. A segunda opção cria um segundo log, que deve ser removido depois de não ser mais necessário.

## Critérios de aceitação

Registre PASS somente se:
1. o script confirmar o commit exato;
2. Cargo terminar com código zero;
3. os dois testes de overrides forem listados e aprovados;
4. não forem usadas entradas de jogo.

Se uma dependência/rede/toolchain falhar, classifique a execução como falha de ambiente, sem inferir que o parser está defeituoso. Um PASS prova apenas os dois testes sintéticos do parser. Não prova recompilação ARM, inicialização de Ultra Sun/Ultra Moon nem runtime próprio para Windows.

## Licença e limite de reutilização

O script não copia arquivos para o repositório PokeUltrarecomp. O Cargo.toml da revisão consultada declara MIT, mas não foi encontrado um arquivo LICENSE no caminho padrão do 3dsrecomp. Executar um teste para pesquisa não é aprovação para copiar ou redistribuir código. Qualquer incorporação continua bloqueada até que a licença aplicável e a procedência estejam esclarecidas.

## Resultado atual

- Data da preparação: 2026-10-24.
- Execução no ambiente desta sessão: **não realizada**, pois não há rustc nem cargo instalados.
- Resultado no computador do mantenedor: pendente.
- Estado: NOT RUN / NOT VERIFIED.
- Evidência exigida: log local revisado e anotação com data, versões de Git/Rust/Cargo, SHA de referência, código de saída e resultado dos dois testes. Não publique logs que revelem caminhos privados.
