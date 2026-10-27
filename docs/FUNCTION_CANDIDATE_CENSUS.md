# Inventário inicial de candidatos ARM/Thumb

`tools/summarize_arm_function_candidates.py` percorre somente o segmento `.text` declarado pelo ExHeader e conta locais que coincidem com padrões comuns de prólogo: ARM `PUSH/STMDB SP!`, ARM `SUB SP, #imm`, Thumb `PUSH` e Thumb `SUB SP, #imm`.

## O que este passo prova

- O ExHeader e o `.code` passam pelo preflight estrutural existente.
- Os padrões são contados apenas dentro da faixa lógica de `.text`, usando o layout de segmentos validado.
- O modo padrão imprime apenas contagens agregadas; não imprime endereços, bytes de instrução, mnemônicos de ocorrências individuais nem pseudocódigo.
- O relatório de endereços detalhados é opcional e o script recusa gerá-lo dentro da árvore do repositório.

## O que ele não prova

Isto **não descobre limites de função nem prova que um candidato é código executável**. A região `.text` pode conter pools de literais, tabelas ou dados alinhados; os padrões também podem ocorrer por coincidência em dados. As contagens ARM e Thumb são heurísticas independentes e podem se sobrepor. Não se deve selecionar uma função apenas com base nestas ocorrências.

## Execução local

Para imprimir apenas a contagem:

```sh
python tools/summarize_arm_function_candidates.py \
  --target ultra-sun \
  --exheader /caminho-privado/exheader.bin \
  --code /caminho-privado/code.bin
```

Para salvar endereços candidatos em um relatório **privado**, fora do repositório:

```sh
python tools/summarize_arm_function_candidates.py \
  --target ultra-sun \
  --exheader /caminho-privado/exheader.bin \
  --code /caminho-privado/code.bin \
  --private-report /caminho-privado/candidates.json
```

Use apenas arquivos de jogo que você possui e está autorizado a analisar. Não faça upload de relatório privado, ROM, ExHeader, `.code`, ELF ou desassemblagem para commits, issues, logs públicos ou artifacts. A próxima etapa exige confirmar manualmente um candidato no Ghidra/REA, determinar estado e limites, analisar fluxo de controle e efeitos e validar a tradução por um oráculo independente. Até isso acontecer, nenhum candidato deve ser tratado como função real recompilada.