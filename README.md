### Game

Este repositório contém um jogo de plataforma 2D procedural em pixel art construído com Python e Pygame.

#### Dependências
- Python 3.11+
- [Pygame](https://www.pygame.org/) (`pip install pygame`)

#### Como jogar
```bash
python main.py
```

**Controles**
- `←` / `→` ou `A` / `D`: mover
- `↑`, `W` ou `Espaço`: pular (com salto duplo quando o power-up estiver ativo)
- `R`: encerrar a corrida atual e voltar ao menu

**Recursos**
- Fases geradas proceduralmente com novas rotas a cada execução
- Power-ups colecionáveis (salto duplo, turbo, escudo e ímã) que ampliam a jogabilidade
- Cristais para pontuar e ranking persistente salvo em `scores.json`
- Sistema de HUD e efeitos visuais em pixel art com paralaxe e tiles detalhados

Após finalizar uma corrida, digite seu nome para registrar a pontuação no ranking permanente.
