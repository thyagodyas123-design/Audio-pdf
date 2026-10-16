"""Tradução local (Argos Translate / CTranslate2). Baixa o modelo do par na primeira vez."""
import threading
from collections.abc import Callable

MAX_BLOCK = 1500  # caracteres por chamada; parágrafos nunca são cortados no meio


def _blocks(text: str, limit: int = MAX_BLOCK) -> list[str]:
    out, cur = [], ""
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if cur and len(cur) + len(para) + 2 > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


class ArgosTranslator:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    @staticmethod
    def _has(src: str, tgt: str) -> bool:
        import argostranslate.translate as tr

        langs = {l.code: l for l in tr.get_installed_languages()}
        return src in langs and tgt in langs and langs[src].get_translation(langs[tgt]) is not None

    def _ensure(self, src: str, tgt: str) -> None:
        if self._has(src, tgt):
            return
        import argostranslate.package as pkg

        pkg.update_package_index()
        avail = pkg.get_available_packages()
        wanted = [(src, tgt)] if any(p.from_code == src and p.to_code == tgt for p in avail) \
            else [(src, "en"), ("en", tgt)]  # pivô via inglês
        for a, b in wanted:
            p = next((p for p in avail if p.from_code == a and p.to_code == b), None)
            if p is None:
                raise RuntimeError(f"par de idiomas sem modelo: {a}->{b}")
            pkg.install_from_path(p.download())
        if not self._has(src, tgt):
            raise RuntimeError(f"par de idiomas indisponível: {src}->{tgt}")

    def translate(self, text: str, src: str, tgt: str,
                  on_progress: Callable[[float], None] | None = None) -> str:
        if src == tgt or not text.strip():
            return text
        import argostranslate.translate as tr

        with self._lock:
            self._ensure(src, tgt)
            blocks = _blocks(text)
            out = []
            for i, b in enumerate(blocks):
                out.append(tr.translate(b, src, tgt))
                if on_progress:
                    on_progress((i + 1) / len(blocks))
        return "\n\n".join(out)
