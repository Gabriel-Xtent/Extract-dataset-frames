# Extract-dataset-frames

Ferramenta CLI para montar datasets (ex.: YOLO) a partir de vídeos. Tem duas funções:

1. **`extract`** — extrai frames de um vídeo, com amostragem configurável.
2. **`select`** — abre uma janela interativa para escolher manualmente os melhores frames.

## Pastas

```
inputs/        # coloque aqui os vídeos a processar
outputs-raw/   # frames extraídos (uma subpasta por vídeo)
output-final/  # frames escolhidos na seleção manual (seu dataset)
```

As pastas são criadas automaticamente na primeira execução.

## Instalação

```bash
pip install -r requirements.txt
```

> Usa `opencv-python` (wheel `abi3`, compatível com Python 3.7+ incluindo 3.14).
> A **extração** roda sem display; a **seleção** abre uma janela e precisa de
> ambiente gráfico (X11/Wayland).

## Uso

### Extrair frames

```bash
# 1 frame a cada 10, de um vídeo específico
python extract_frames.py extract --video jogo1.mp4 --every 10

# todos os vídeos de inputs/ (1 a cada 30)
python extract_frames.py extract --every 30

# todos os frames (--every 1 é o padrão)
python extract_frames.py extract --video jogo1.mp4
```

Flags do `extract`:

| Flag | Padrão | Descrição |
|------|--------|-----------|
| `--video NOME` | todos | vídeo em `inputs/` a processar |
| `--every N` | `1` | salva 1 frame a cada N (`1` = todos) |
| `--ext jpg\|png` | `jpg` | formato de saída |
| `--quality 1-100` | `95` | qualidade JPEG |

Saída: `outputs-raw/<video>/<video>_<indice>.jpg` (nome rastreável, sem colisão).

### Selecionar os melhores frames

Abre uma **grade de miniaturas** (padrão 3×3 = 9 por página). Clique nas imagens
para marcar; a borda fica **verde** nos marcados e **amarela** no cursor.

```bash
python extract_frames.py select                     # navega todos os frames de outputs-raw/
python extract_frames.py select --video jogo1.mp4   # só os frames desse vídeo
python extract_frames.py select --rows 4            # mais frames por página (imagens menores)
python extract_frames.py select --cols 2 --rows 2   # menos frames por página (imagens maiores)
```

Controles na janela:

| Ação | Como |
|------|------|
| Marcar / desmarcar | **clique** na miniatura, ou `ESPAÇO` no cursor |
| Mover o cursor | setas `← ↑ → ↓` (ou `a` / `d`) |
| Trocar de página | `n` (próxima) / `p` (anterior) |
| Salvar marcados | `s` |
| Sair | `q` / `ESC` (salva os marcados automaticamente) |

Flags: `--cols` (padrão 3), `--rows` (padrão 6), `--width`/`--height` (tamanho máx. da janela em px).

Os frames escolhidos são copiados para `output-final/`, prontos para anotação.
