"""Transformă Markdown în HTML. Formulele ($...$ și $$...$$) sunt randate în browser cu KaTeX,
diagramele ```mermaid``` cu Mermaid (inclus local)."""
import html
import re

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

_CLOZE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.S)


def _cloze_rule(state: StateInline, silent: bool) -> bool:
    """{{c1::text}} sau {{c1::text::indiciu}} → text subliniat discret."""
    if not state.src.startswith("{{c", state.pos):
        return False
    m = _CLOZE.match(state.src, state.pos)
    if not m:
        return False
    if not silent:
        token = state.push("cloze", "span", 0)
        token.content = m.group(2)
        token.meta = {"n": m.group(1)}
    state.pos = m.end()
    return True


def _cloze_plugin(md: MarkdownIt) -> None:
    md.inline.ruler.before("emphasis", "cloze", _cloze_rule)
    md.add_render_rule("cloze", lambda self, tokens, idx, options, env:
                       f'<span class="cloze" data-c="{html.escape(tokens[idx].meta["n"])}">'
                       f'{html.escape(tokens[idx].content)}</span>')


def _mermaid_plugin(md: MarkdownIt) -> None:
    default_fence = md.renderer.rules.get("fence")

    def fence(self, tokens, idx, options, env):
        token = tokens[idx]
        if token.info.strip().split(" ")[0].lower() == "mermaid":
            return f'<div class="mermaid">{html.escape(token.content)}</div>\n'
        return default_fence(tokens, idx, options, env)

    md.add_render_rule("fence", fence)


# html=False: HTML brut din notițe (de exemplu din text generat de AI) nu ajunge în pagină.
_md = (
    MarkdownIt("commonmark", {"html": False, "typographer": False})
    .enable(["table", "strikethrough"])
    .use(dollarmath_plugin, double_inline=True)
    .use(tasklists_plugin)
    .use(footnote_plugin)
    .use(anchors_plugin, min_level=1, max_level=4)
    .use(_cloze_plugin)
    .use(_mermaid_plugin)
)


def render(text: str) -> str:
    return _md.render(text)


def parse(text: str):
    """Tokenii markdown-it (cu id-urile ancorelor deja calculate)."""
    return _md.parse(text)
