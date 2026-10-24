# Referência de teste 001 — parser sintético de overrides

**Estado inicial:** selecionado; execução pelo GitHub Actions ainda não confirmada neste registro.

## Objetivo

Reproduzir um teste de unidade público do [3dsrecomp](https://github.com/fearkov/3dsrecomp) que analisa marcadores de overrides em pequenos trechos sintéticos de código C. Esse teste não precisa de ROM, dump, firmware, chave, recurso extraído, compilação de jogo nem runtime 3DS.

## Fonte fixada

- Repositório: https://github.com/fearkov/3dsrecomp
- Commit de origem: [c3f21f94ba50d688025febc8974ff348d471b587](https://github.com/fearkov/3dsrecomp/commit/c3f21f94ba50d688025febc8974ff348d471b587)
- Arquivo de teste: [src/overrides.rs](https://github.com/fearkov/3dsrecomp/blob/c3f21f94ba50d688025febc8974ff348d471b587/src/overrides.rs)
- Manifesto e versões travadas: [Cargo.toml](https://github.com/fearkov/3dsrecomp/blob/c3f21f94ba50d688025febc8974ff348d471b587/Cargo.toml) e [Cargo.lock](https://github.com/fearkov/3dsrecomp/blob/c3f21f94ba50d688025febc8974ff348d471b587/Cargo.lock)
- Componente testado: parser de marcadores RECOMP_OVERRIDE e RECOMP_OVERRIDE_IN.

O código upstream contém um teste positivo que garante que marcadores em comentários e strings sejam ignorados e que marcadores válidos gerem endereços/nomes esperados. Outro teste verifica a rejeição de marcadores malformados e de endereços duplicados. São assertions de parser sobre strings sintéticas.

## Execução planejada

A automação está em [.github/workflows/reference-test-001.yml](../.github/workflows/reference-test-001.yml) e roda em um runner Windows hospedado pelo GitHub. O código de referência é consultado em um commit fixo no workspace temporário do runner; nenhum código do 3dsrecomp é incorporado ao histórico do PokeUltrarecomp.

O comando usado é:

~~~powershell
cargo test --locked --lib overrides::tests -- --nocapture
~~~

Toolchain fixada: Rust 1.95.0. O lockfile determina as versões exatas de crates e da dependência Git declarada pelo projeto. Nenhum input de jogo deve ser fornecido à tarefa.

## Critérios de aceitação

O teste só pode ser registrado como aprovado quando um run do GitHub Actions para este workflow:
1. terminar com código de saída zero;
2. listar e aprovar os dois testes da seção overrides::tests;
3. usar exatamente o commit de referência acima e Rust 1.95.0;
4. não baixar, solicitar ou acessar conteúdo de jogo.

Uma falha de rede, compilador ou dependência deve ser registrada como falha de infraestrutura, não como evidência de defeito no parser. Um teste aprovado prova apenas aquele comportamento de parser em fixtures sintéticas. **Não prova que código ARM foi recompilado, que Ultra Sun/Ultra Moon inicializam, nem que exista runtime ou porta nativa para Windows.**

## Licença e limites

O teste é executado diretamente na fonte pública de referência sem copiar arquivos para o PokeUltrarecomp. O Cargo.toml desse commit declara MIT, mas a consulta documental anterior não encontrou um arquivo LICENSE no caminho padrão desse repositório. Assim, a automação serve para estudar e executar o teste upstream; não autoriza copiar nem redistribuir o código. Antes de qualquer incorporação, confirme a licença aplicável e as atribuições com base na origem completa.

## Resultado registrado

- Data da definição: 2026-10-24.
- Execução local: não realizada.
- Resultado do GitHub Actions: pendente de verificação.
- Classificação atual: NOT RUN / NOT VERIFIED.
- Próximo passo após um run aprovado: registrar seu URL/commit e escolher uma segunda prova de conceito que valide um componente host próprio com fixtures sintéticas, após resolver os bloqueios de licença e procedência.
