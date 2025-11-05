# Neon Mask: Plataforma Procedural Estilo Tomb of the Mask

Este projeto entrega um plataforma 2D totalmente procedural com estética neon inspirada em **Tomb of the Mask**, desenvolvido em Python com **Pygame**. A engine foi retrabalhada para oferecer mosaicos dinâmicos, iluminação, partículas aditivas e ranking persistente.

## Dependências
- Python 3.11+
- [Pygame](https://www.pygame.org/) (`pip install pygame`)

## Como executar
```bash
python main.py
```

## Controles
- `←` / `→` ou `A` / `D`: mover
- `Z`, `Espaço` ou `W`: salto
- `X` ou `Shift`: dash aéreo quando o power-up estiver ativo
- `Esc`: fechar o jogo ou cancelar a inserção do nome após o game over

## Destaques do jogo
- **Engine neon aprimorada**: tiles conectivos renderizados com atlas procedural (mais de mil variações) e fundo animado com faixas luminosas.
- **Personagem com trilha de luz**: movimentação fluida com salto fantasma, rajada, dobra temporal e outros power-ups.
- **Obstáculos reativos**: feixes a laser, campos energizados e cavernas geradas dinamicamente.
- **Colecionáveis magnéticos**: cristais que alimentam combos crescentes com feedback flutuante.
- **Ranking permanente**: após o game over digite um nome para salvar sua pontuação em `scores.json`.

A estética neon usa sprites e partículas totalmente geradas por código, mantendo a vibe vertical de Tomb of the Mask em uma experiência de plataforma lateral.
