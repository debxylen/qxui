# QXUI

An XML-based reactive-declarative native UI framework built on Qt/QML.

```bash
pip install qxui # or: pip install git+https://github.com/debxylen/qxui
```

### why

when it comes to cross platform native UI, most of the options are either way too imperative, or not easy enough to use.
thus most things end up being web wrapped in tauri/electron anyway, or become clunky UIs that also need a lot more time to write.

QML is great: declarative, reactive, and all, but it's quite verbose to write, and nowhere close to the html/webdev-like experience.

qxui aims to cover up some shortcomings by wrapping the same Qt/QML backend in a nice and direct XML syntax with easy layout, closer to the web;
and cuts down the amount of boilerplate to be written, by providing easy multi-window app and state management.

### how it works

- **compiler**: raw-translates declarative XML UI into QML
- **profiles**: extends capabilities by acting as a layout engine, along with basic styling, etc
- **runtime**: provides a nice api to manage and create apps/windows, reactive states, actions, etc

### quick example

```xml
<!-- ui.xml -->
<Item padding="24" gap="16" background.color="#0f172a">
    <Text color="white" font.weight="Font.Bold" font.pixelSize="20">
        Clicks: {clicks}
    </Text>

    <Button onClick="increment"> increment </Button>
</Item>
```

```python
from qxui import App, State

with open("ui.xml", "r", encoding="utf-8") as f:
    ui = f.read()

state = State({"clicks": 0})
app = App(state)

@app.action("increment")
def click_handler(ctx):
    ctx.set_state("clicks", ctx.state["clicks"] + 1)

app.create_window(ui, title="cool app", size=(400, 300))
app.run()
```

more at [examples](examples/); more to be added

### schema

the standard XML schema can be linked by adding these attributes to your root:

```xml
<_ xmlns="urn:qxui:schema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="urn:qxui:schema https://raw.githubusercontent.com/debxylen/qxui/main/schema.xsd">

    ...

</_>
```

### license

[LGPL v3.0](LICENSE)
