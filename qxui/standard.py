from xml.etree.ElementTree import Element
from .core import QMLGenerator, Profile, QMLSpec, Literal

class StandardProfile(Profile):
    def __init__(self):
        super().__init__()
        self.rule(self.emit_text,    tag=("Text", "Label"))
        self.rule(self.emit_button,  tag=("Button", "ToolButton"))
        self.rule(self.emit_input,   tag=("TextField", "TextInput", "TextArea"))
        self.rule(self.emit_control, tag=("CheckBox", "RadioButton"))
        self.rule(self.emit_scroll,  attr="overflow", value="scroll")
        self.rule(self.emit_scroll,  attr="overflow", value="auto")
        self.rule(self.emit_managed, match=self.needs_mgmt)

    # -----------------------------------------------------------------------------------------------------

    @staticmethod
    def needs_mgmt(node, context):
        managed_attrs = {
            "direction", "layout", "gap", "padding", "paddingX", "paddingY",
            "flex", "margin", "marginX", "marginY", "width", "height",
            "dragRegion", "overflow", "justify", "items",
        }
        return (
            bool(managed_attrs & node.attrib.keys())
            or any(key in node.attrib for key in ("color", "background.color"))
            or "background.color" in context.get("styles", {})
        )

    # -----------------------------------------------------------------------------------------------------

    @staticmethod
    def add_font(target, node, context):
        family = node.attrib.get("font.family") or context["styles"].get("font.family")
        if family != None: target["font.family"] = family

    def add_layout(self, qprops, context, props):
        parent = context["parent_layout"]

        if parent in ("row", "scroll-row"): qprops["Layout.minimumWidth"] = Literal("0")
        elif parent:                        qprops["Layout.fillWidth"]    = Literal("true")

        if parent in ("row", "root-col", "fill-col"):
            qprops["Layout.fillHeight"] = Literal("true")

        if props.get("flex") != None:
            if parent in ("row", "scroll-row"):
                qprops["Layout.fillWidth"]      = Literal("true")
                qprops["Layout.preferredWidth"] = props["flex"]

            elif parent.startswith("scroll"):
                qprops.pop("Layout.fillHeight", None)
                qprops["Layout.preferredHeight"] = Literal("implicitHeight")
                qprops["Layout.maximumHeight"]   = Literal("implicitHeight")

            else:
                qprops["Layout.fillHeight"]      = Literal("true")
                qprops["Layout.preferredHeight"] = props["flex"]

        if isinstance(props.get("width"), int) and parent in ("row", "scroll-row"):
            qprops.pop("Layout.fillWidth", None)
            qprops["Layout.preferredWidth"] = props["width"]

        elif props.get("width") in ("full", "parent.width"):
            qprops["Layout.fillWidth"] = Literal("true")

        if isinstance(props.get("height"), int) and parent not in ("row", "scroll-row"):
            qprops.pop("Layout.fillHeight", None)
            qprops["Layout.preferredHeight"] = props["height"]

    # -----------------------------------------------------------------------------------------------------

    def emit_text(self, generator: QMLGenerator, node: Element, context):
        props  = generator.props(node, context["styles"])
        qprops = {
            "text":           Literal(generator.parse_expr((node.text or "").strip())),
            "color":          props.get("color", context["styles"].get("color", "#ffffff")),
            "font.pixelSize": props.get("font.pixelSize", 14),
        }

        self.add_font(qprops, node, context)
        if "font.weight" in props: qprops["font.weight"] = Literal(props["font.weight"])

        self.add_layout(qprops, context, props)
        return QMLSpec("Text", qprops)

    # -----------------------------------------------------------------------------------------------------

    def emit_button(self, generator: QMLGenerator, node: Element, context):
        props  = generator.props(node, context["styles"])
        qprops = {"text": Literal(generator.parse_expr((node.text or "").strip()))}

        if node.attrib.get("onClick"):
            qprops["onClicked"] = Literal("backend.dispatch(%s)" % generator.stringify(node.attrib["onClick"]))

        self.add_layout(qprops, context, props)

        content = QMLSpec("Text", {
            "text":                Literal("parent.text"),
            "color":               props.get("color", context["styles"].get("color", "#ffffff")),
            "font.pixelSize":      props.get("font.pixelSize", 14),
            "horizontalAlignment": Literal("Text.AlignHCenter"),
            "verticalAlignment":   Literal("Text.AlignVCenter"),
        })

        self.add_font(content.props, node, context)
        if "font.weight" in props: content.props["font.weight"] = Literal(props["font.weight"])

        background = QMLSpec("Rectangle", {
            "color":  props.get("background.color", "#45475a"),
            "radius": props.get("radius", 8),
        })
        return QMLSpec("Button", qprops, slots={"contentItem": content, "background": background})

    # -----------------------------------------------------------------------------------------------------

    def emit_input(self, generator: QMLGenerator, node: Element, context):
        props  = generator.props(node, context["styles"])
        qprops = {}

        value       = node.attrib.get("text", node.attrib.get("value"))
        placeholder = node.attrib.get("placeholder", node.attrib.get("placeholderText"))

        if value != None:       qprops["text"]            = Literal(generator.stringify(value))
        if placeholder != None: qprops["placeholderText"] = Literal(generator.stringify(placeholder))

        qprops["color"] = props.get("color", context["styles"].get("color", "#ffffff"))
        self.add_font(qprops, node, context)
        self.add_layout(qprops, context, props)

        slots = {}
        if "color" in props or "radius" in props:
            slots["background"] = QMLSpec("Rectangle", {
                "color":  props.get("background.color", "transparent"),
                "radius": props.get("radius", 0),
            })
        return QMLSpec(node.tag, qprops, slots=slots)

    # -----------------------------------------------------------------------------------------------------

    def emit_control(self, generator: QMLGenerator, node: Element, context):
        props  = generator.props(node, context["styles"])
        qprops = {}

        for key in ("text", "checked"):
            if key in node.attrib: qprops[key] = Literal(generator.stringify(node.attrib[key]))

        self.add_layout(qprops, context, props)

        slots = {}
        if "color" in props:
            slots["contentItem"] = QMLSpec("Text", {
                "text":              Literal("parent.text"),
                "color":             props["color"],
                "verticalAlignment": Literal("Text.AlignVCenter"),
            })
            self.add_font(slots["contentItem"].props, node, context)

        return QMLSpec(node.tag, qprops, slots=slots)

    # -----------------------------------------------------------------------------------------------------

    def emit_scroll(self, generator: QMLGenerator, node: Element, context):
        return self.gen_container(generator, node, context, "ScrollView")

    def emit_managed(self, generator: QMLGenerator, node: Element, context):
        return self.gen_container(generator, node, context)

    def gen_container(self, generator: QMLGenerator, node: Element, context, tag=None):
        props    = generator.props(node, context["styles"])
        children = list(node)
        tag      = tag or node.tag

        qprops = {}
        if context["is_root"]:  qprops["anchors.fill"] = Literal("parent")
        if tag == "ScrollView": qprops["contentWidth"] = Literal("availableWidth")

        self.add_layout(qprops, context, props)

        width, height = props.get("width"), props.get("height")
        if width in ("full", "parent.width"):   qprops["width"]  = Literal("parent.width")
        elif isinstance(width, int):            qprops["width"]  = width

        if height in ("full", "parent.height"): qprops["height"] = Literal("parent.height")
        elif isinstance(height, int):           qprops["height"] = height

        direction = node.attrib.get("direction", node.attrib.get("layout"))
        layout    = QMLSpec("RowLayout" if direction == "row" else "ColumnLayout")
        layout_id = generator.id("layout")

        layout.props["id"]           = Literal(layout_id)
        layout.props["spacing"]      = props.get("gap", 16 if tag == "ScrollView" else 0)
        layout.props["anchors.fill"] = Literal("parent")

        padding = props.get("padding", 0)
        layout.props["anchors.leftMargin"]   = props.get("paddingX", padding)
        layout.props["anchors.rightMargin"]  = props.get("paddingX", padding)
        layout.props["anchors.topMargin"]    = props.get("paddingY", padding)
        layout.props["anchors.bottomMargin"] = props.get("paddingY", padding)

        child_is_container = lambda child: bool(child.attrib.get("direction") or list(child))
        child_layout = (
            "scroll-row" if tag == "ScrollView" and direction == "row" else
            "scroll-col" if tag == "ScrollView" else
            "row"        if direction == "row" else
            "root-col"   if context["is_root"] else
            "fill-col"   if len(children) == 1 and child_is_container(children[0]) else
            "col"
        )

        layout.children = [
            generator.build_spec(child, child_layout, ancestors=context["ancestors"] + (node,))
            for child in children
        ]

        qprops["implicitWidth"]  = Literal(f"{layout_id}.implicitWidth + {padding * 2}")
        qprops["implicitHeight"] = Literal(f"{layout_id}.implicitHeight + {padding * 2}")

        spec_children = [layout]
        if props.get("dragRegion") in (True, "true", "1"):
            drag = QMLSpec("MouseArea", {
                "z":                -1,
                "anchors.fill":     Literal("parent"),
                "acceptedButtons":  Literal("Qt.LeftButton"),
                "onPressed":        Literal("root.startSystemMove()"),
            })
            spec_children.insert(0, drag)

        spec = QMLSpec(tag, qprops, children=spec_children)
        if "background.color" in props:
            qprops = {"color": props["background.color"], "radius": props.get("radius", 0), **qprops}
            spec   = QMLSpec("Rectangle", qprops, children=spec_children)

        return spec
