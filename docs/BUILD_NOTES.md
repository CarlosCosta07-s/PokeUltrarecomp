# Notas de build e testes reproduzíveis

Este documento é o registro canônico dos testes locais. Nenhum teste de build da porta foi executado por PokeUltrarecomp na auditoria inicial. Não preencher resultados por suposição.

## Regras

- Fixar commit completo de cada ferramenta e registrar o repositório de origem.
- Registrar versão exata de compilador, sistema operacional, SDK e dependências.
- Guardar logs completos localmente quando contiverem caminhos, hashes de entrada ou outras informações privadas; compartilhar somente uma cópia redigida.
- Não anexar ROMs, dumps, firmware, chaves, executáveis de jogo, recursos extraídos nem saídas derivadas.
- Se um teste exige entrada proprietária, mantê-la local e fora de Git/CI. Preferir casos sintéticos.
- Não classificar compilar uma ferramenta como prova de execução do jogo.
- Para cada falha, registrar comando, código de saída, etapa da falha e tentativa mínima de reprodução.
- Não registrar um teste como aprovado só porque o processo terminou sem crash; declarar a asserção que foi observada.

## Modelo de registro

Copie o modelo abaixo para uma issue ou nota nova ao executar um teste.

~~~text
Identificador do teste:
Data e hora:
Responsável:
Objetivo:
Repositório e commit completo:
Caminho/documentação de referência:
Sistema operacional e versão:
Windows build:
WSL/distribuição/kernel (se aplicável):
Arquitetura CPU:
Rust/C/C++/MSVC/MinGW version:
CMake/Ninja/Make/Python/Node versions:
Dependências e suas versões/commits:
Ferramentas instaladas e origem:
Entradas: sintéticas / próprias-localmente / nenhuma
Confirmação de que entradas e saídas proprietárias não foram publicadas:
Comando exato:
Diretório de trabalho:
Resultado esperado:
Resultado observado:
Código de saída:
Testes/asserções executados:
Log local (caminho privado):
Resumo público redigido:
Hashes de artefatos não proprietários (se relevante):
Erros ou advertências:
Tentativas de reprodução:
Classificação: PASS / FAIL / INCONCLUSIVE / NOT RUN
Critério de aceitação satisfeito:
Limitações:
Próximo passo:
~~~

## Primeiro registro: auditoria inicial

- Identificador: DOC-AUDIT-001
- Data: 2026-10-24
- Objetivo: inspecionar os repositórios de referência e preparar documentação do projeto.
- Ambiente local de compilação: não aplicável.
- Builds/testes de jogo: **não executados**.
- Resultado: leitura documental e verificação de caminhos públicos; os autores relatam resultados descritos em [AUDIT.md](AUDIT.md), mas eles não foram reproduzidos por este repositório.
- Limitações: estados e licenças podem mudar; commits de referência e os arquivos consultados devem ser revistos antes de qualquer incorporação.


## Teste de referência 001 — parser sintético de overrides

- Especificação: [REFERENCE_TEST_001.md](REFERENCE_TEST_001.md).
- Ferramenta: [3dsrecomp](https://github.com/fearkov/3dsrecomp), commit c3f21f94ba50d688025febc8974ff348d471b587.
- Fonte dos testes: [src/overrides.rs](https://github.com/fearkov/3dsrecomp/blob/c3f21f94ba50d688025febc8974ff348d471b587/src/overrides.rs).
- Comando: cargo test --locked --lib overrides::tests -- --nocapture.
- Ambiente pretendido: runner Windows, Rust 1.95.0.
- Entradas de jogo: nenhuma; os testes constroem strings sintéticas.
- Estado: **aguardando inspeção do resultado do GitHub Actions**.
- Interpretação: aprovado significa apenas que dois testes de parser passam no commit fixado; não demonstra recompilação ARM nem execução de Ultra Sun/Ultra Moon.


### Observação de execução remota

O workflow está publicado e os commits que alteraram os caminhos monitorados estão na branch principal. A integração GitHub disponível nesta sessão não forneceu resultados de runs disparados por push; o endpoint acessível de runs está limitado a eventos de pull request. O ambiente de execução local também não tem Rust/Cargo instalado. Portanto, não há evidência confirmada de PASS ou FAIL nesta etapa. O resultado continua NOT VERIFIED; verifique a página Actions do repositório antes de mudar esse estado.
