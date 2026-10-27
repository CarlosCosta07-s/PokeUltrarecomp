# Inventário inicial de candidatos ARM/Thumb

`tools/summarize_arm_function_candidates.py` percorre somente o segmento `.text` declarado pelo ExHeader e conta locais que coincidem com padrões comuns de prólogo: ARM `PUSH/STMDB SP!`, ARM `SUB SP, #imm`, Thumb `PUSH` e Thumb `SUB SP, #imm`.

## O que este passo prova

- O ExHeader e o `.code` passam pelo preflight estrutural existente.
- Os padrões são contados apenas dentro da faixa lógica de `.text`, usando o layout de segmentos validado.
- O modo padrão imprime apenas contagens agregadas; não imprime endereços, bytes de instrução, mnemônicos de ocorrências individuais nem pseudocódigo. Com `--decode-summary`, Capstone também conta os candidatos cuja leitura linear limitada chega a um retorno comum em até 512 bytes/96 instruções. O filtro para em desvios incondicionais e resume retornos `BX LR`, `MOV PC, LR`, `POP {..., PC}` e `LDM SP!, {..., PC}`.
- O relatório de endereços detalhados é opcional e o script recusa gerá-lo dentro da árvore do repositório.

## Triagem privada do Ghidra contra o tradutor ARM atual

O tradutor ARM A32 agora inclui formas simples de `Operand2` em registrador sem deslocamento: `MOV/MVN`, lógica sem S-bit, aritmética e comparações `ADD/SUB/ADDS/SUBS/CMN/CMP), além de lógica com flags `MOVS/MVNS/ANDS/ORRS/EORS/BICS` e `TST/TEQ`. O banco continua limitado a `r0-r3`; os shifts imediatos `LSL/LSR/ASR/ROR/RRX` agora são modelados com as regras de carry de entrada/saída pertinentes; shifts especificados por registrador e outros formatos de memória permanecem bloqueados. Candidatos com `LDR/STR` de palavra, `LDRB/STRB` de byte, `LDRH/STRH` halfword e `LDRSB/LDRSH` signed pré-indexados imediatos são triados com o modelo de região de memória delimitada (halfwords alinhados a 2 bytes neste modelo). `LDRSB` e `LDRSH` fazem extensão de sinal de forma explícita usando operações unsigned portáveis; as stores signed e modos post-indexados/writeback continuam recusados. Isso só valida geração/sintaxe e fixtures sintéticas, não semântica contra o jogo. Para lógica com S-bit e shift zero, o C gerado atualiza N/Z e preserva C/V, conforme testado em fixtures sintéticas. A nova matriz diferencial sintética passou em 192/192 casos contra o modelo NZCV separado do projeto; isso valida a POC sintética, não código do jogo.


O workflow remoto também importa um ELF de análise temporário no Ghidra e retém em armazenamento temporário os corpos pequenos que a análise automática identifica como candidatos A32 contínuos, sem chamadas diretas detectadas e terminados em `BX LR`. A seleção é deliberadamente restrita (8–64 bytes) e serve apenas como uma primeira triagem.

Para cada candidato, `screen_private_ghidra_candidates` tenta a tradução com o subconjunto A32 existente. Os candidatos aceitos são reunidos em amostras de C e passam por uma verificação de sintaxe do compilador host (`-fsyntax-only`). Para as sequências rejeitadas, o relatório público conta apenas famílias fixas de causa, como instrução fora do modelo atual, forma de flags não suportada ou registrador fora do subconjunto. Os endereços, palavras de instrução, C gerado e mensagens completas do compilador ficam em armazenamento temporário privado e são descartados.

Esses números orientam a próxima implementação de instruções, mas não identificam uma função pronta para ser reutilizada. As fronteiras do Ghidra podem ser heurísticas; o teste de sintaxe não é uma comparação semântica com ARM, e a triagem não verifica ABI, memória, fluxo completo, estado compartilhado nem equivalência funcional. A análise da ROM real só publica contagens agregadas e mnemônicos gerais.

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