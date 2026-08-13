import sys
import qxui

# ---

state = qxui.State({"counter": 0, "status": "hi"})
app = qxui.App(state)

# ---

app.component("CounterCard", """

  <Item background.color="111827" padding="16" radius="12" gap="8">
    <Text color="38bdf8" font.pixelSize="24">{label}: {counter}</Text>
    <Text color="94a3b8">{subtitle}</Text>
    <children />
  </Item>

""", props={"label": "shared counter", "subtitle": "..."}
)

# ---

main_ui = """
<Item layout="column" id="outermost" padding="20" gap="16">
  <Item direction="row" dragRegion="true" background.color="0f172a" height="40" radius="8" paddingX="12" align="center">
    <Text color="white" font.weight="Font.DemiBold" flex="1">main window</Text>
    <Button background.color="ef4444" color="white" radius="6" width="32" height="28" onClick="close">x</Button>
  </Item>

  <CounterCard>
    <Text color="22c55e" font.pixelSize="12">{status}</Text>
  </CounterCard>

  <Item direction="row" gap="12">
    <Button flex="1" background.color="38bdf8" color="black" radius="8" onClick="inc">increment</Button>
    <Button flex="1" background.color="1e293b" color="white" radius="8" onClick="spawnPopup">open popup window</Button>
  </Item>
</Item>
"""

popup_ui = """
<Item layout="column" padding="20" gap="16">
  <Text color="white" font.pixelSize="18" font.weight="Font.DemiBold">popup</Text>
  <CounterCard label="popup counter" subtitle="im a popup. pop! pop! pop! pop!" />

  <Item direction="row" gap="12">
    <Button flex="1" background.color="22c55e" color="black" radius="8" onClick="inc">increment</Button>
    <Button flex="1" background.color="ef4444" color="white" radius="8" onClick="close">close</Button>
  </Item>
</Item>
"""

# ---

@app.action("inc")
def inc(ctx):
    ctx.update_state({"counter": ctx.state["counter"] + 1, "status": f"incremented"})

@app.action("spawnPopup")
def spawn_popup(ctx):
    app.create_window(
        source     = popup_ui,
        title      = "popup window",
        size       = (480, 200),
        background = "#1e293b",
        frameless  = False,
    )
    ctx.update_state({"status": "spawned window"})

# ---

def main():
    app.create_window(
        source     = main_ui,
        title      = "main window",
        size       = (550, 260),
        background = "#0b1020",
        frameless  = True,
    )
    sys.exit(app.run())

if __name__ == "__main__":
    main()
