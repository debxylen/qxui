import re
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------------------------------------

IMPORTS = """import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls
"""

WINDOW_DEFAULTS = {
    "type":       "Window",
    "id":         "root",
    "visible":    True,
    "width":      1280,
    "height":     800,
    "title":      "",
    "background": "#000000",
}

NAMED_COLORS = {
    "white":  "#ffffff", "black": "#000000",
    "red":    "#ef4444", "green": "#22c55e", "blue": "#3b82f6",
    "yellow": "#eab308", "gray":  "#9ca3af", "slate": "#64748b",
}

LITERAL_PRES = ("parent.", "root.", "Font.", "Text.", "Qt.")

# ---------------------------------------------------------------------------------------------------------

@dataclass
class QMLSpec:
    type:     str
    props:    dict = field(default_factory=dict)
    slots:    dict = field(default_factory=dict)
    children: list = field(default_factory=list)

@dataclass
class StyleRule:
    selectors:    list
    declarations: dict
    order:        int

class Literal:
    def __init__(self, value):
        self.value = value

# ---------------------------------------------------------------------------------------------------------

class Rule:
    def __init__(self, action, tag=None, attr=None, value=None, match=None):
        self.action = action
        self.tag    = tag
        self.attr   = attr
        self.value  = value
        self.match  = match

    def accepts(self, node, context):
        if self.tag != None:
            tags = self.tag if isinstance(self.tag, tuple) else (self.tag,)
            if node.tag not in tags: return False

        if self.attr != None:
            key, expected = self.attr, self.value
            if key not in node.attrib or (expected != None and node.attrib[key] != expected): return False

        return self.match == None or self.match(node, context)

    def apply(self, generator, node, context):
        return self.action(generator, node, context)

class Profile:
    def __init__(self):
        self.rules = []

    def rule(self, action, *, tag=None, attr=None, value=None, match=None):
        self.rules.append(Rule(action, tag, (attr if attr else None), value, match))
        return self

    def emit_node(self, generator, node, context):
        for rule in self.rules:
            if not rule.accepts(node, context): continue
            emitted = rule.apply(generator, node, context)
            if emitted != None: return emitted

# ---------------------------------------------------------------------------------------------------------

class StyleSheet:
    def __init__(self, source=None):
        self.rules = []
        self.parse(source or "")

    def parse(self, source):
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)

        for order, match in enumerate(re.finditer(r"([^{}]+)\{([^{}]*)\}", source)):
            selectors    = [s.strip() for s in match.group(1).split(",") if s.strip()]
            declarations = {}

            for declaration in match.group(2).split(";"):
                if ":" not in declaration: continue
                key, value = declaration.split(":", 1)
                declarations[key.strip()] = value.strip()

            if selectors and declarations:
                self.rules.append(StyleRule(selectors, declarations, order))

    @staticmethod
    def simple(node, selector):
        if selector.startswith("#"): return node.attrib.get("id") == selector[1:]

        classes = set(node.attrib.get("class", "").split())
        if selector.startswith("."): return selector[1:] in classes

        if "." in selector:
            tag, cls = selector.split(".", 1)
            return node.tag == tag and cls in classes

        return node.tag == selector or selector == "*"

    def matches(self, node, ancestors, selector):
        direct = ">" in selector
        parts  = [part for part in re.split(r"\s*>\s*|\s+", selector) if part]

        if not parts or not self.simple(node, parts[-1]): return False

        current = list(reversed(ancestors))
        if direct and len(parts) == 2: return bool(current) and self.simple(current[0], parts[0])

        for part in reversed(parts[:-1]):
            found = False
            while current:
                if self.simple(current.pop(0), part):
                    found = True
                    break

            if not found: return False
        return True

    def apply(self, node, ancestors=()):
        result = {}
        ranked = []

        for rule in self.rules:
            for selector in rule.selectors:
                if not self.matches(node, ancestors, selector): continue
                spec = 0

                for p in selector.split():
                    if p.startswith("#"): spec += 100
                    elif "." in p: spec += 10
                    else: spec += 1

                ranked.append((spec, rule.order, rule.declarations))
                break

        for _, _, declarations in sorted(ranked):
            result.update(declarations)

        return result

# ---------------------------------------------------------------------------------------------------------

class QMLGenerator:
    def __init__(self, profiles=None, components=None):
        self.profiles   = list(profiles or [])
        self.components = dict(components or {})

    @staticmethod
    def indent(n: int) -> str: return " " * 4 * n

    @staticmethod
    def color(v: str) -> str:
        if v.startswith("{") or "(" in v: return v
        if v in NAMED_COLORS: return NAMED_COLORS[v]
        if v.startswith("#"): return v
        if all(ch in "0123456789abcdefABCDEF" for ch in v): return "#" + v
        return v

    @staticmethod
    def try_int(v: str, default = 0):
        return int(v) if v.lstrip("-").isdigit() else default

    @staticmethod
    def stringify(value) -> str:
        return json.dumps(str(value))

    def id(self, prefix="q") -> str:
        self.__next_id += 1
        return f"{prefix}{self.__next_id}"

    def niceify_value(self, value: str) -> str:
        if isinstance(value, Literal):                     return value.value
        if isinstance(value, (int, float)):                return str(value)
        if value in ("true", "false", "null"):             return value
        if re.fullmatch(r"-?\d+(\.\d+)?", value):          return value
        if value.startswith("{") and value.endswith("}"):  return self.parse_expr(value)
        if any(value.startswith(p) for p in LITERAL_PRES): return value
        return self.stringify(value)

    # -----------------------------------------------------------------------------------------------------

    def props(self, node, styles=None) -> dict:
        numeric = {
            "radius", "gap", "width", "height", "padding", "paddingX", "paddingY", "flex",
            "margin", "marginX", "marginY", "marginTop", "marginBottom", "marginRight", "marginLeft",
        }
        merged = dict(styles or {})
        merged.update(node.attrib)

        return {
            key: (
                self.try_int(value, value) if key in numeric else
                self.color(value)          if key in {"color", "background.color"}
                else value
            )
            for key, value in merged.items()
        }

    def parse_expr(self, value: str) -> str:
        if value.startswith("{") and value.endswith("}") and not value[1:-1].startswith("{"):
            inner = value[1:-1].strip()
            if re.fullmatch(r"[A-Za-z_][\w.]*", inner):
                key = inner[6:] if inner.startswith("state.") else inner
                return f'(backend !== null && backend.state !== undefined && backend.state.{key} !== undefined ? backend.state.{key} : "")'

            keywords = {"true", "false", "null", "undefined", "backend", "Font", "Qt", "Math", "Number", "String"}
            def repl_ident(m):
                w = m.group(0)
                if w in keywords or w.startswith(("'", '"')): return w
                if w.startswith("state."): return f"backend.state.{w[6:]}"
                if w.startswith("backend."): return w
                return f"backend.state.{w}"

            parts = []
            pos = 0
            for m in re.finditer(r"('[^']*'|\"[^\"]*\"|\b[A-Za-z_][\w.]*\b)", inner):
                parts.append(inner[pos:m.start()])
                tok = m.group(0)
                parts.append(tok if tok.startswith(("'", '"')) else repl_ident(m))
                pos = m.end()
            parts.append(inner[pos:])
            return f"({''.join(parts)})"

        parts = []
        pos = 0

        for match in re.finditer(r"{\s*([A-Za-z_][\w.]*)\s*}", value):
            raw = value[pos:match.start()]
            key = match.group(1)

            if raw: parts.append(self.stringify(raw))
            if key.startswith("state."): key = key[6:]

            parts.append(f'(backend !== null && backend.state !== undefined && backend.state.{key} !== undefined ? backend.state.{key} : "")')
            pos = match.end()

        tail = value[pos:]
        if tail: parts.append(self.stringify(tail))
        if not parts: return self.stringify(value)

        return " + ".join(parts)

    def expand_node(self, node):
        tag    = node.tag.split("}", 1)[-1]
        attrib = { k.split("}", 1)[-1]: v for k, v in node.attrib.items() }

        if tag == "_":
            if len(node) == 1: return self.expand_node(node[0])
            new_node = ET.Element("Item")

            for child in node:
                expanded = self.expand_node(child)
                if expanded.tag == "_": new_node.extend(list(expanded))
                else: new_node.append(expanded)

            return new_node

        if tag in self.components:
            source, default_props = self.components[tag]
            props = {**default_props, **attrib}

            children = []
            for child in list(node):
                expanded = self.expand_node(child)
                if expanded.tag == "_": children.extend(list(expanded))
                else: children.append(expanded)

            expanded_src = source
            for k, v in props.items():
                expanded_src = expanded_src.replace(f"{{{k}}}", str(v))

            compo_root = ET.fromstring(expanded_src)
            for k, v in props.items():
                if f"{{{k}}}" not in source and k not in compo_root.attrib:
                    compo_root.attrib[k] = str(v)

            slot_found = False
            for elem in compo_root.iter():
                elem.tag = elem.tag.split("}", 1)[-1]

                if elem.tag.lower() in ("slot", "children"):
                    elem.tag = "Item"
                    elem.extend(children)
                    slot_found = True
                    break

            if not slot_found and children:
                compo_root.extend(children)

            return compo_root

        new_node      = ET.Element(tag, attrib)
        new_node.text = node.text
        new_node.tail = node.tail

        for child in node:
            expanded = self.expand_node(child)
            if expanded.tag == "_": new_node.extend(list(expanded))
            else: new_node.append(expanded)

        return new_node

    # -----------------------------------------------------------------------------------------------------

    def build_spec(self, node, parent_layout=None, is_root=False, ancestors=()):
        styles  = self.stylesheet.apply(node, ancestors)
        context = {
            "parent_layout": parent_layout,
            "is_root":       is_root,
            "styles":        styles,
            "ancestors":     ancestors,
        }

        for profile in self.profiles:
            emitted = profile.emit_node(self, node, context)
            if emitted != None: return emitted

        raw_props = {}
        for key, value in node.attrib.items():
            if key == "id": raw_props[key] = Literal(value)
            else: raw_props[key] = self.niceify_value(value)

        emitted = QMLSpec(node.tag, raw_props)
        if node.text and node.text.strip():
            emitted.props["text"] = Literal(self.parse_expr(node.text.strip()))

        emitted.children = [self.build_spec(child, None, False, ancestors + (node,)) for child in node]
        return emitted

    def emit_spec(self, spec: QMLSpec, indent) -> list[str]:
        ind   = self.indent(indent)
        lines = [f"{ind}{spec.type} {{"]

        indent += 1
        ind     = self.indent(indent)

        for key, value in spec.props.items():
            rendered = value.value if isinstance(value, Literal) else self.niceify_value(value)
            lines.append(f"{ind}{key}: {rendered}")

        for slot, value in spec.slots.items():
            slot_lines    = self.emit_spec(value, indent)
            slot_lines[0] = f"{ind}{slot}: " + slot_lines[0].lstrip()
            lines.extend(slot_lines)

        for child in spec.children:
            lines.extend(self.emit_spec(child, indent))

        lines.append(f"{self.indent(indent - 1)}}}")
        return lines

    # -----------------------------------------------------------------------------------------------------

    def generate_app(self, app: dict) -> str:
        self.__next_id = 0

        window = {**WINDOW_DEFAULTS, **dict(app.get("window") or {})}
        self.stylesheet = StyleSheet(app.get("styles", ""))

        header = [IMPORTS.rstrip(), "", f'{window["type"]} {{', f'    id: {window["id"]}']
        for key, value in window.items():
            if key in {"type", "id"}: continue
            qkey     = {"background": "color"}.get(key, key)
            rendered = ("true" if value else "false") if isinstance(value, bool) else self.niceify_value(str(value))
            header.append(f"    {qkey}: {rendered}")

        root = self.expand_node(ET.fromstring(app["ui"]))
        spec = self.build_spec(root, parent_layout=None, is_root=True)

        out = [*header, *self.emit_spec(spec, indent=1), "}"]
        return "\n".join(out) + "\n"
