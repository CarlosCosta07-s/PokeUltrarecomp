# Contrato de função candidata

Este guia descreve `tools/check_function_contract.py`, que confronta um **contrato declarado pelo mantenedor** com o relatório local de `tools/inspect_3ds_code_range.py` (`instructions`, `control_flow`, `dataflow`). Ele não lê arquivos do jogo, não executa código e **nunca declara uma função validada**: um oráculo independente continua obrigatório antes de qualquer emissão de C.

## O que é e o que não é

- O contrato é uma *afirmação* do mantenedor sobre um trecho já escolhido e com estado ARM/Thumb confirmado. A ferramenta não infere contratos nem descobre funções.
- O resultado `consistent-with-observed-static-effects` significa apenas que nenhuma violação foi **provada** pelos efeitos estáticos observados. Não é validação, equivalência nem autorização para gerar C.
- O que depende de caminho, de valores de pilha/memória, de callees ou da ABI real vai para `needs_proof` ou `unverifiable`, nunca para "ok".
- O contrato e o relatório podem conter dados derivados do código do jogo. Mantenha-os locais, fora do Git; `--output` recusa caminhos dentro do repositório.

## Formato (`schema_version` 1)

Todas as chaves são obrigatórias; chaves desconhecidas são rejeitadas. O exemplo abaixo é **sintético**.

```json
{
  "schema_version": 1,
  "contract_id": "synthetic-001",
  "target_id": "ultra-sun",
  "state": "thumb",
  "entry_address": "0x00100000",
  "inputs":   {"registers": [],     "flags": []},
  "outputs":  {"registers": ["r0"], "flags": []},
  "clobbers": {"registers": [],     "flags": ["n", "z"]},
  "preserved": ["r4"],
  "stack_delta_on_return": 0,
  "memory": "stack-only",
  "calls": "none",
  "oracle": {"kind": "differential-planned", "reference": "descrição da referência independente"}
}
```

| Campo | Significado |
| --- | --- |
| `target_id`, `state`, `entry_address` | Devem coincidir com o alvo, o estado e o início explícito do relatório; senão o resultado é `not-validatable`. |
| `inputs` | Registradores/flags que a função pode ler do chamador. |
| `outputs`, `clobbers` | Registradores/flags que ela pode escrever (resultado ou destruição declarada). Não podem se sobrepor. |
| `preserved` | Registradores que devem sair com o valor de entrada. Não podem ser `outputs`/`clobbers`. |
| `stack_delta_on_return` | Variação líquida de SP em bytes (múltiplo de 4) no primeiro retorno. |
| `memory` | `none`, `stack-only` ou `may-access`. |
| `calls` | `none` ou `allowed` (callees assumidos como preservadores de SP e dos registradores `preserved`). |
| `oracle` | `kind` e `reference` não vazios: obriga a nomear a comparação independente futura. Não registra resultado. |

`pc` não pode aparecer em listas; `sp`, `lr` e `pc` têm leitura implícita, e `sp`/`pc` escrita implícita (a variação de SP é verificada por `stack_delta_on_return`).

## Uso

```
python3 tools/check_function_contract.py --contract contrato.json --report relatorio.json [--output resultado.json]
```

Códigos de saída: `0` consistente com os efeitos observados; `1` violações; `2` erro de entrada ou `not-validatable`.

## Veredito

- **`not-validatable`** (falha fechada): identidade divergente (alvo, estado, entrada) ou efeitos desconhecidos/parciais. Chamadas (`BL`, `BLX`) são tratadas pelo campo `calls`, não bloqueiam o veredito.
- **`contract-violations`**: `undeclared-register-write`, `undeclared-input-read`, `undeclared-flag-write`, `undeclared-flag-input`, `memory-access-observed`, `call-observed`, `stack-delta-mismatch`.
- **`needs_proof`**: `preserved-register-written` (a restauração não é provada) e `stack-only-unproven` (endereços não resolvidos).
- **`unverifiable`**: `no-return-observed`, `indirect-transfer-unresolved`, `stack-delta-unverifiable` (desvios tornam a variação dependente de caminho).

## Limites

A análise não é sensível a caminho nem a ordem: uma leitura só é sinalizada se o registrador/flag nunca for escrito no trecho. Preservação de registradores, endereços de memória, comportamento de callees e ABI real exigem o oráculo independente, que este passo apenas obriga a nomear. A variação de SP só é calculada em trechos sem desvios e assume que chamadas permitidas preservam SP.
