"""Relatório de downloads das releases do CCA, para medir o alcance.

O GitHub conta cada download de arquivo anexado a uma release. Cada versão tem
dois zips iguais: `CCA-<versão>.zip` (baixado pela página, por gente nova) e
`CCA-<versão>-atualizacao.zip` (baixado pelo atualizador do app, por quem já
usa). Os números são de downloads, não de pessoas: quem baixa duas vezes conta
duas, e a consulta de versão nova do app não conta."""

import json
import sys
import urllib.request

import updater


def summarize(data):
    """[(versão, publicada, baixados, atualizacoes)] da mais nova para a mais
    velha, mais os totais (baixados, atualizacoes)."""
    rows = []
    for rel in data if isinstance(data, list) else []:
        if rel.get("draft"):
            continue
        manual = auto = 0
        for asset in rel.get("assets") or []:
            count = int(asset.get("download_count") or 0)
            if asset.get("name", "").endswith(updater.UPDATE_SUFFIX):
                auto += count
            elif asset.get("name", "").endswith(".zip"):
                manual += count
        rows.append((rel.get("tag_name", "?"), (rel.get("published_at") or "")[:10], manual, auto))
    rows.sort(key=lambda r: updater.parse_version(r[0]), reverse=True)
    return rows, (sum(r[2] for r in rows), sum(r[3] for r in rows))


def report(data):
    rows, (manual, auto) = summarize(data)
    if not rows:
        return "Nenhuma release publicada ainda."
    lines = ["Versão | Publicada | Baixados pela página | Atualizações pelo app"]
    for version, date, m, a in rows:
        lines.append(f"{version} | {date} | {m} | {a}")
    lines.append(f"Total | | {manual} | {auto}")
    lines.append(f"Downloads no total: {manual + auto}.")
    return "\n".join(lines)


def main():
    try:
        data = json.loads(updater.http_get(updater.API).decode("utf-8"))
    except Exception as exc:
        print(f"Não consegui consultar o GitHub: {exc}")
        return 1
    print(report(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
