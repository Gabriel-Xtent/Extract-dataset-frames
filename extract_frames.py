#!/usr/bin/env python3
"""Extrai frames de vídeos e seleciona manualmente os melhores para um dataset YOLO.

Dois subcomandos:

    extract  -> lê vídeos de inputs/ e salva frames amostrados em outputs-raw/
    select   -> abre uma janela interativa para escolher os melhores frames de
                outputs-raw/ e copia os escolhidos para output-final/

Exemplos:
    python extract_frames.py extract --video jogo1.mp4 --every 10
    python extract_frames.py extract                       # todos os vídeos de inputs/
    python extract_frames.py select
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

# Pastas padrão (relativas ao diretório de onde o script é executado).
ROOT = Path.cwd()
INPUTS_DIR = ROOT / "inputs"
RAW_DIR = ROOT / "outputs-raw"
FINAL_DIR = ROOT / "output-final"

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def ensure_dirs() -> None:
    """Cria as pastas de trabalho se ainda não existirem."""
    for d in (INPUTS_DIR, RAW_DIR, FINAL_DIR):
        d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# extract
# --------------------------------------------------------------------------- #
def find_videos(video: str | None) -> list[Path]:
    """Resolve a lista de vídeos a processar a partir da flag --video."""
    if video:
        path = Path(video)
        if not path.is_absolute() and not path.exists():
            path = INPUTS_DIR / video
        if not path.exists():
            print(f"[erro] vídeo não encontrado: {video}", file=sys.stderr)
            return []
        return [path]

    videos = sorted(
        p for p in INPUTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )
    if not videos:
        print(f"[erro] nenhum vídeo encontrado em {INPUTS_DIR}/", file=sys.stderr)
    return videos


def extract_one(video_path: Path, every: int, ext: str, quality: int) -> int:
    """Extrai frames de um vídeo. Retorna a quantidade de frames salvos."""
    stem = video_path.stem
    out_dir = RAW_DIR / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[erro] não consegui abrir o vídeo: {video_path}", file=sys.stderr)
        return 0

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    write_params: list[int] = []
    if ext == "jpg":
        write_params = [cv2.IMWRITE_JPEG_QUALITY, quality]

    print(f"\n→ {video_path.name}  (frames: {total or '?'}, salvando 1 a cada {every})")

    i = saved = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % every == 0:
            fname = f"{stem}_{i:06d}.{ext}"
            cv2.imwrite(str(out_dir / fname), frame, write_params)
            saved += 1
            if saved % 50 == 0:
                print(f"  ... {saved} frames salvos (lido {i})", flush=True)
        i += 1

    cap.release()
    print(f"✓ {video_path.name}: {saved} frames salvos em {out_dir}/  (lidos {i})")
    return saved


def cmd_extract(args: argparse.Namespace) -> int:
    ensure_dirs()
    if args.every < 1:
        print("[erro] --every deve ser >= 1", file=sys.stderr)
        return 2

    videos = find_videos(args.video)
    if not videos:
        return 1

    total_saved = sum(
        extract_one(v, args.every, args.ext, args.quality) for v in videos
    )
    print(f"\nConcluído: {total_saved} frames em {RAW_DIR}/")
    return 0


# --------------------------------------------------------------------------- #
# select
# --------------------------------------------------------------------------- #
def collect_images(video: str | None) -> list[Path]:
    """Lista as imagens de outputs-raw/ (recursivo), opcionalmente de um vídeo."""
    base = RAW_DIR / Path(video).stem if video else RAW_DIR
    if not base.exists():
        print(f"[erro] pasta não encontrada: {base}", file=sys.stderr)
        return []
    return sorted(
        p for p in base.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


HEADER_H = 30
FOOTER_H = 28
LABEL_H = 18
PAD = 14  # espaçamento (margem) em torno de cada miniatura na célula


def load_thumb(path: Path, cache: dict):
    """Lê e cacheia a imagem decodificada (BGR) de um frame."""
    img = cache.get(path)
    if img is None:
        img = cv2.imread(str(path))
        cache[path] = img
    return img


def cell_box(sample_ar: float, cols: int, rows: int, max_w: int, max_h: int):
    """Calcula o tamanho da célula/thumbnail respeitando largura e altura máx."""
    cell_w = max_w // cols
    thumb_w = cell_w - 2 * PAD
    thumb_h = int(thumb_w * sample_ar)
    cell_h = thumb_h + LABEL_H + 2 * PAD
    if HEADER_H + rows * cell_h + FOOTER_H > max_h:
        # limita pela altura disponível
        cell_h = (max_h - HEADER_H - FOOTER_H) // rows
        thumb_h = cell_h - LABEL_H - 2 * PAD
        thumb_w = max(1, int(thumb_h / sample_ar))
        cell_w = thumb_w + 2 * PAD
    return cell_w, cell_h, thumb_w, thumb_h


def build_page(images, page, cols, rows, sel, cursor, max_w, max_h, cache):
    """Monta a grade (contact-sheet) da página atual.

    Retorna (canvas, rects) onde rects é uma lista de (x0, y0, x1, y1, indice
    global) usada para mapear cliques do mouse a frames.
    """
    per = cols * rows
    start = page * per
    items = images[start:start + per]

    # razão de aspecto a partir do primeiro frame legível da página
    ar = 9 / 16
    for p in items:
        im = load_thumb(p, cache)
        if im is not None:
            ar = im.shape[0] / im.shape[1]
            break

    cell_w, cell_h, thumb_w, thumb_h = cell_box(ar, cols, rows, max_w, max_h)
    W, H = cols * cell_w, HEADER_H + rows * cell_h + FOOTER_H
    canvas = np.full((H, W, 3), 30, np.uint8)
    rects = []

    for i, p in enumerate(items):
        gi = start + i
        r, c = divmod(i, cols)
        x0, y0 = c * cell_w, HEADER_H + r * cell_h
        # canto do thumbnail dentro da célula (PAD = espaço entre tiles)
        tx, ty = x0 + PAD, y0 + PAD
        im = load_thumb(p, cache)
        if im is not None:
            th = cv2.resize(im, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
            canvas[ty:ty + thumb_h, tx:tx + thumb_w] = th

        is_sel, is_cur = p in sel, gi == cursor
        if is_sel:
            color, thick = (80, 220, 80), 3
        elif is_cur:
            color, thick = (40, 220, 255), 3
        else:
            color, thick = (90, 90, 90), 1
        # borda em volta da imagem (não da célula) → o espaço entre tiles aparece
        cv2.rectangle(canvas, (tx - 4, ty - 4),
                      (tx + thumb_w + 3, ty + thumb_h + LABEL_H + 3), color, thick)

        name = p.name if len(p.name) <= 24 else p.name[:21] + "..."
        cv2.putText(canvas, name, (tx, ty + thumb_h + LABEL_H - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (230, 230, 230), 1, cv2.LINE_AA)
        if is_sel:
            cv2.putText(canvas, "OK", (tx + thumb_w - 34, ty + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 220, 80), 2, cv2.LINE_AA)
        rects.append((x0, y0, x0 + cell_w, y0 + cell_h, gi))

    pages = (len(images) + per - 1) // per
    cv2.putText(
        canvas,
        f"Pagina {page + 1}/{pages}   selecionados: {len(sel)}   total: {len(images)}",
        (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "clique=marca  setas=move  ESPACO=marca  n/p=pagina  s=salvar e sair  q=sair",
        (8, H - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 220, 255), 1, cv2.LINE_AA,
    )
    return canvas, rects


def copy_selected(selected: set[Path], dest: Path) -> int:
    """Copia os frames selecionados para `dest`. Retorna quantos copiou."""
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(selected):
        shutil.copy2(p, dest / p.name)
        n += 1
    print(f"✓ {n} frames copiados para {dest}/")
    return n


# Códigos de seta retornados por waitKeyEx (variam por plataforma/backend).
LEFT_KEYS = {81, 65361, 2424832}
RIGHT_KEYS = {83, 65363, 2555904}
UP_KEYS = {82, 65362, 2490368}
DOWN_KEYS = {84, 65364, 2621440}


def cmd_select(args: argparse.Namespace) -> int:
    ensure_dirs()
    images = collect_images(args.video)
    if not images:
        print(f"[erro] nenhuma imagem em {RAW_DIR}/. Rode 'extract' primeiro.", file=sys.stderr)
        return 1

    dest = Path(args.out).expanduser() if args.out else FINAL_DIR
    cols, rows = max(1, args.cols), max(1, args.rows)
    per = cols * rows
    selected: set[Path] = set()
    cache: dict = {}
    saved_flag = False
    cursor = 0
    dirty = True
    win = "Selecao de frames - dataset"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

    state = {"rects": []}

    def on_mouse(event, x, y, flags, param):
        nonlocal saved_flag, dirty, cursor
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        for x0, y0, x1, y1, gi in state["rects"]:
            if x0 <= x < x1 and y0 <= y < y1:
                p = images[gi]
                selected.discard(p) if p in selected else selected.add(p)
                cursor = gi
                saved_flag = dirty = False
                dirty = True
                break

    cv2.setMouseCallback(win, on_mouse)
    print(f"{len(images)} frames em grade {cols}x{rows} "
          f"({per}/página). Clique para marcar; teclado para navegar.")

    while True:
        page = cursor // per
        if dirty:
            canvas, rects = build_page(
                images, page, cols, rows, selected, cursor, args.width, args.height, cache)
            state["rects"] = rects
            cv2.imshow(win, canvas)
            dirty = False

        key = cv2.waitKeyEx(20)
        if key == -1:
            # janela fechada no X (getWindowProperty pode lançar no backend Qt)
            try:
                if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
            continue

        last = len(images) - 1
        if key in (ord("q"), 27):  # q ou ESC
            break
        elif key in RIGHT_KEYS or key == ord("d"):
            cursor = min(cursor + 1, last)
        elif key in LEFT_KEYS or key == ord("a"):
            cursor = max(cursor - 1, 0)
        elif key in DOWN_KEYS:
            cursor = min(cursor + cols, last)
        elif key in UP_KEYS:
            cursor = max(cursor - cols, 0)
        elif key in (ord("n"), ord(".")):  # próxima página
            cursor = min(cursor + per, last)
        elif key in (ord("p"), ord(",")):  # página anterior
            cursor = max(cursor - per, 0)
        elif key in (ord(" "), 13):  # espaço/enter: marca o frame sob o cursor
            p = images[cursor]
            selected.discard(p) if p in selected else selected.add(p)
            saved_flag = False
        elif key == ord("s"):  # salva e fecha a janela
            copy_selected(selected, dest)
            saved_flag = True
            break
        dirty = True

    cv2.destroyAllWindows()

    if selected and not saved_flag:
        print("Salvando seleção antes de sair...")
        copy_selected(selected, dest)
    elif not selected:
        print("Nenhum frame selecionado.")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extrai frames de vídeos e seleciona os melhores para um dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("extract", help="extrai frames de vídeos de inputs/ para outputs-raw/")
    e.add_argument("--video", help="nome do vídeo em inputs/ (omitido = todos)")
    e.add_argument("--every", type=int, default=1,
                   help="salva 1 frame a cada N (1 = todos). Padrão: 1")
    e.add_argument("--ext", choices=["jpg", "png"], default="jpg", help="formato de saída")
    e.add_argument("--quality", type=int, default=95, help="qualidade JPEG (1-100)")
    e.set_defaults(func=cmd_extract)

    s = sub.add_parser("select", help="seleciona frames de outputs-raw/ para output-final/")
    s.add_argument("--video", help="limita à subpasta de um vídeo (omitido = todos)")
    s.add_argument("--cols", type=int, default=3, help="colunas da grade. Padrão: 3")
    s.add_argument("--rows", type=int, default=3, help="linhas da grade. Padrão: 3")
    s.add_argument("--width", type=int, default=1700, help="largura máx. da janela (px)")
    s.add_argument("--height", type=int, default=1040, help="altura máx. da janela (px)")
    s.add_argument("--out", help="pasta destino dos frames escolhidos (padrão: output-final/)")
    s.set_defaults(func=cmd_select)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
