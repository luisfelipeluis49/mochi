# Proposta: contratos v0.5 (nova visão de produto)

**De:** Tasnim (apps/web) · **Para:** Matheus (contratos), Luís (gateway), Kauê (intelligence)
**Status:** proposta. Nada aqui vale até o time aprovar. As telas já funcionam com isto **só no modo falso** (`?mock=1`). Com o backend real, elas continuam funcionando com a v0.4 de hoje.

A nova visão (slides de novembro de 2026) pede coisas que o AGENTS.md v0.4 ainda não tem. Abaixo está o mínimo para as telas mostrarem a visão nova, mudando o contrato o menos possível.

## 1. Dois modos novos: `choosing` e `practice`

| Onde | Hoje (v0.4) | Proposta (v0.5) |
|---|---|---|
| Session `mode` | `together`, `activity` | `together`, `activity`, **`choosing`**, **`practice`** |

- **`choosing`:** alguém disse "Oi, Mochi!" e o Mochi pergunta "O que vocês querem fazer hoje?". A tela do Mochi mostra *Praticar · Companhia · Jogar*.
- **`practice`:** o modo Praticar (uma pessoa conversa com o Mochi).
- Os nomes na tela ficam: `practice` = Praticar, `together` = Companhia, `activity` = Jogar.
- **Quem muda o modo:** o backend, pelo `session.state.changed` que já existe. A escolha é falada, não tocada.

## 2. Um motivo novo de fala: `practice_partner`

| Onde | Hoje | Proposta |
|---|---|---|
| Speak `reason` | `asks_mochi`, `activity_host` | + **`practice_partner`** |

No modo Praticar o Mochi fala o tempo todo como parceiro de conversa. A tela mostra o rostinho e o que ele diz.

## 3. Um evento novo: `session.summary.created`

O resumo do slide "Mochi Mobile". Enviado **só para o celular daquela pessoa**, quando a sessão para.

```json
{ "summary_id": "sum_001", "user_id": "sophie", "target_language": "pt-BR",
  "speaking_minutes": 24,
  "strengths": ["Descrever objetos"],
  "to_review": ["Pretérito: fui, comprei"],
  "new_expressions": ["apesar de", "na verdade"],
  "next_step": "Descreva e Adivinhe: histórias",
  "created_at": "2026-11-19T16:30:00.000Z" }
```

| Evento | Payload | Enviado para |
|---|---|---|
| `session.summary.created` | SessionSummary (acima) | o celular daquele usuário, e só ele |

- Listas vazias são permitidas, e a tela esconde a parte vazia. `next_step` pode ser `null`.
- **O celular agora é a página de análise** (progresso, última sessão, sessões, palavras). Por isso, **ao conectar**, o servidor precisa reenviar para aquele celular **todos os resumos antigos** e **todas as palavras salvas** da pessoa. Sem isso, os números de progresso começam do zero quando a página recarrega. Usa os eventos que já existem; só muda a regra do "ao conectar".
- Os números do progresso (palavras novas, usadas com ajuda, lembradas no jogo, minutos) são **contados na tela** a partir das palavras e dos resumos. Não precisam de campo novo.
- **Quem gera:** sugestão: Kauê (intelligence), a partir das frases e das palavras salvas; Luís publica.

## 3b. Um evento novo: `conversation.report.created` (página "Minhas conversas")

A análise de **uma conversa real** de **uma pessoa** (reunião de trabalho, ligação, conversa com amigo). Mostrada na página `/me?user=…`. Enviada **só para aquela pessoa**, quando a sessão para.

```json
{ "report_id": "rep_001", "user_id": "tasnim", "target_language": "en",
  "title": "Weekly sync with the team", "context": "meeting",
  "started_at": "2026-11-20T13:00:00.000Z", "ended_at": "2026-11-20T13:30:00.000Z", "speaking_minutes": 20,
  "my_sentences": [ { "at": "2026-11-20T13:04:00.000Z", "text": "I finish the slides yesterday.",
                      "better": "I finished the slides yesterday.", "topic": "Past tense" } ],
  "mistakes": [ { "kind": "grammar", "topic": "Past tense",
                  "said": "I finish the slides yesterday.", "better": "I finished the slides yesterday.", "count": 1 } ],
  "unknown_words": [ { "expression": "deadline", "meaning": "prazo", "said_instead": "prazo", "times": 1 } ],
  "strengths": ["Explaining your work"],
  "focus_next": ["Past tense: sent, received, finished"] }
```

- **Cada gravação é uma conversa.** A pessoa aperta **Gravar conversa** no celular (`POST /api/sessions/demo/start`) e **Parar e salvar** (`/stop`). Um relatório é criado para aquele intervalo, com `started_at` e `ended_at`. Uma hora depois, outra gravação vira outro relatório.
- **Só as frases da própria pessoa:** o campo `my_sentences` traz, em ordem, o que **ela** disse: `{ "at", "text", "better", "topic" }`. `better` é a frase corrigida (ou `null`); `topic` é o grupo do erro (ou `null` quando é só uma palavra que faltou). **O que a outra pessoa disse nunca vai para a página dela.** Isso depende de saber de quem é cada frase: o Pi já reconhece as vozes (seção 3c).
- `kind`: `grammar`, `word_choice` ou `false_friend`. `context`: `meeting`, `conversation` ou `practice`.
- **Quem gera:** a parte de inteligência (Kauê). Isso **inclui correção de gramática**, que o AGENTS.md v0.4 deixa fora do MVP (seção 8): é uma decisão do time.
- **Precisa saber quem falou:** só as frases **daquela pessoa** entram no relatório dela. Depende da decisão de "quem disse o quê".
- **Reenviar ao conectar:** a página só mostra progresso se o backend reenviar todos os relatórios antigos daquela pessoa quando ela abre a página.
- **Privacidade:** em reuniões há outras pessoas. O Mochi só ouve entre Iniciar e Parar, e a página lembra de avisar os outros.

## 3c. Um evento novo: `speaker.changed` (quem está falando agora)

O Pi do Matheus **já reconhece as vozes** (`hardware/pi-bridge/mochi_device/speakers.py`) e já manda o nome para o backend em `POST /api/devices/home_pi_01/status` (`"speaker": "Tasnim"`, AGENTS.md 6.6). A tela do próprio aparelho (`face.html`) já mostra esse nome no canto.

Para o Mochi do **web app** mostrar o mesmo (tela do Mochi e telão), o gateway só precisa **repassar** esse valor quando ele muda:

```json
{ "type": "speaker.changed", "payload": { "name": "Tasnim", "user_id": "tasnim" } }
```

- `name`: o nome com que a voz foi aprendida. `null` quando ninguém conhecido está falando.
- `user_id`: o id do usuário, quando o gateway souber ligar o nome ao id (ex.: minúsculas: "Tasnim" → "tasnim").
- **Enviado para:** todas as conexões.
- **Quem faz:** Luís (gateway). Nada muda no Pi.
- **Bônus:** com isso, o backend também sabe **de quem é cada frase**. É o que falta para os relatórios de "Minhas conversas" serem de cada pessoa.

## 4. Dica com até 3 opções, sem mudar campo

O slide do modo Companhia mostra "me queimei · tomei muito sol". Proposta: **convenção, sem campo novo.** `expression` pode ter até 3 opções separadas por ` · ` (espaço, ponto do meio, espaço). As telas mostram uma por linha.

Se o time preferir um campo próprio (por exemplo `alternatives: string[]`), eu adapto. É uma mudança pequena nas telas.

## 5. Jogo: o Mochi é o anfitrião (sem mudar o contrato)

- O backend percebe o palpite certo pela voz, manda `activity.state.changed` com `ROUND_RESULT`, e manda um `agent.speak.requested` com `reason: "activity_host"` (ex.: "Correct! Sophie, your turn to describe.").
- O toque na tela do Mochi continua como **reserva**: segundo toque = acertou, segurar = pulou.
- O jogo começa **por voz** ("Bora jogar!"): o backend inicia a rodada sozinho. O botão "Iniciar um jogo" saiu do celular.
- Na demo nova, **Ana descreve e Sophie adivinha**, e depois elas trocam (o backend troca `describer_user_id` e `guesser_user_id` a cada rodada).

## 6. Pessoas da demo: Ben vira Sophie

`participants: ["ana", "sophie"]`. Ana aprende inglês; Sophie aprende português (`comfortable_languages: ["en"]`, `target_language: "pt-BR"`). Os testes e as frases de exemplo do Kauê precisam trocar Ben por Sophie.

## Fora desta proposta, mas precisa de decisão

- **"Quem disse o quê"** (prioridade 1 no slide do MVP): hoje o AGENTS.md diz que uma frase chega **sem quem falou**, porque é um microfone só. A visão nova precisa saber quem falou. Isso é do backend e do áudio (Luís, Kauê e Matheus), não das telas: as telas já recebem `target_user_id` pronto.
- **Mochi AR e Mochi Watch:** fora do MVP (estão em "depois" e "mais tarde" no slide). Não fiz nada para eles.

## O que preciso de cada um

- **Matheus:** aprovar ou mudar os itens 1 a 4 e colocar no `packages/contracts`.
- **Luís:** dizer se consegue mandar `choosing` e `practice` e o novo evento de resumo, e o resultado do jogo pela voz.
- **Kauê:** dizer se consegue gerar o resumo (tempo de fala, ponto forte, para revisar, expressões novas, próximo passo).
