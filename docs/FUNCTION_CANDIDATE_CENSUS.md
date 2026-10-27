# Inventário inicial de candidatos ARM/Thumb

`tools/summarize_arm_function_candidates.py` percorre somente o segmento `.text` declarado pelo ExHeader e conta locais que coincidem com padrões comuns de prólogo: ARM `PUSH/STMDB SP!`, ARM `SUB SP, #imm`, Thumb `PUSH` e Thumb `SUB SP, #imm`.

## O que este passo prova

- O ExHeader e o `.code` passam pelo preflight estrutural existente.
- Os padrões são contados apenas dentro da faixa lógica de `.text`, usando o layout de segmentos validado.
- O modo padrão imprime apenas contagens agregadas; não imprime endereços, bytes de instrução, mnemônicos de ocorrências individuais nem pseudocódigo. Com `--decode-summary`, Capstone também conta os candidatos cuja leitura linear limitada chega a um retorno comum em até 512 bytes/96 instruções. O filtro para em desvios incondicionais e resume retornos `BX LR`, `MOV PC, LR`, `POP {..., PC}` e `LDM SP!, {..., PC}`.
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

Para incluir a triagem limitada com Capstone no resumo agregado:

```sh
python -m pip install -r tools/requirements-analysis.txt
python tools/summarize_arm_function_candidates.py --decode-summary --target ultra-sun --exheader /caminho-privado/exheader.bin --code /caminho-privado/code.bin
```

O contador de retornos é apenas uma pista adicional: a leitura é linear, não segue o grafo de controle, pode atravessar dados e não prova que o retorno é alcançável. Nem o total bruto nem o total que chega a um retorno representam quantidade de funções confirmadas.

Para salvar endereços candidatos em um relatório **privado**, fora do repositório:

```sh
python tools/summarize_arm_function_candidates.py \
  --target ultra-sun \
  --exheader /caminho-privado/exheader.bin \
  --code /caminho-privado/code.bin \
  --private-report /caminho-privado/candidates.json
```

Use apenas arquivos de jogo que você possui e está autorizado a analisar. Não faça upload de relatório privado, ROM, ExHeader, `.code`, ELF ou desassemblagem para commits, issues, logs públicos ou artifacts. A próxima etapa exige confirmar manualmente um candidato no Ghidra/REA, determinar estado e limites, analisar fluxo de controle e efeitos e validar a tradução por um oráculo independente. Até isso acontecer, nenhum candidato deve ser tratado como função real recompilada.