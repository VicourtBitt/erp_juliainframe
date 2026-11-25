"""Parsing AI output and rendering contract templates safely."""

import html
import json
import re
from dataclasses import dataclass, field

from jinja2 import TemplateSyntaxError, meta
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup, escape

_env = SandboxedEnvironment(autoescape=True)
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ContractRenderError(Exception):
    pass


@dataclass
class ParsedContract:
    html: str | None
    title: str | None
    fields: list[str] = field(default_factory=list)


def decode_escapes(text: str | None) -> str | None:
    """Turn literal ``\\u00e3`` sequences and HTML entities into real characters."""
    if not text:
        return text
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    return html.unescape(text)


def _block(text: str, lang: str) -> str | None:
    match = re.search(rf"```{lang}[ \t]*\r?\n(.*?)\r?\n?```", text, re.DOTALL)
    return match.group(1).strip() if match else None


def strip_scripts(document: str) -> str:
    return _SCRIPT_RE.sub("", document)


def extract_canvases(text: str) -> ParsedContract:
    """Extract the html / plaintext / json blocks from the model response."""
    raw_html = _block(text, "html")
    # Entities are decoded before stripping so "&lt;script&gt;" can't sneak through.
    document = strip_scripts(decode_escapes(raw_html)) if raw_html else None
    title = decode_escapes(_block(text, "plaintext"))

    declared: list[str] = []
    raw_json = _block(text, "json")
    if raw_json:
        for candidate in (raw_json, decode_escapes(raw_json)):
            try:
                data = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue
            items = data.get("context_fields", []) if isinstance(data, dict) else data
            declared = [str(f) for f in items if isinstance(f, str)] if isinstance(items, list) else []
            break

    fields = merge_fields(declared, document) if document else declared
    return ParsedContract(html=document, title=(title or "").splitlines()[0][:255] if title else None, fields=fields)


def template_variables(document: str) -> list[str]:
    """Variables actually used in the template, in order of first appearance."""
    try:
        undeclared = meta.find_undeclared_variables(_env.parse(document))
    except TemplateSyntaxError as exc:
        raise ContractRenderError(f"Erro de sintaxe no modelo (linha {exc.lineno}): {exc.message}") from exc
    positions = {name: document.find(name) for name in undeclared}
    return sorted(undeclared, key=lambda n: (positions[n] < 0, positions[n]))


def merge_fields(declared: list[str], document: str) -> list[str]:
    """Fields to ask the user for.

    The original app trusted the model's JSON list blindly; any mismatch left
    placeholders unrendered or produced inputs that did nothing. The template
    itself is the source of truth; the declared list is only a fallback when
    the template can't be parsed.
    """
    try:
        used = template_variables(document)
    except ContractRenderError:
        used = [f for f in declared if _IDENTIFIER_RE.match(f)]
    return list(dict.fromkeys(used))


def humanize(field_name: str) -> str:
    return field_name.replace("_", " ").strip().capitalize()


def render_contract(document: str, values: dict, *, highlight_missing: bool = False) -> str:
    """Render the Jinja template in a sandbox; user values are HTML-escaped."""
    try:
        template = _env.from_string(document)
        names = template_variables(document)
    except TemplateSyntaxError as exc:
        raise ContractRenderError(f"Erro de sintaxe no modelo (linha {exc.lineno}): {exc.message}") from exc
    context = {}
    for name in names:
        value = str(values.get(name, "") or "").strip()
        if value:
            context[name] = Markup("<br>").join(escape(line) for line in value.splitlines())
        elif highlight_missing:
            context[name] = Markup(
                '<mark style="background:#fff3cd;padding:0 .2em">[{}]</mark>'
            ).format(humanize(name))
        else:
            context[name] = ""
    try:
        return template.render(context)
    except Exception as exc:  # SecurityError, UndefinedError, TypeError...
        raise ContractRenderError(f"Erro ao renderizar o contrato: {exc}") from exc
