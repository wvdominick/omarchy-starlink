import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "wvdominick.starlink"

  readonly property var panelItem: panelLoader.item
  readonly property var minute: panelItem && panelItem.minute ? panelItem.minute : null
  readonly property var status: panelItem ? panelItem.status : null
  readonly property bool ok: panelItem ? panelItem.ok !== false : true
  readonly property string chipText: Model.barLine(status, minute, ok)
  readonly property string barTooltip: panelItem ? panelItem.barTooltip : "Starlink"
  readonly property color barColor: panelItem ? panelItem.barColor : (bar ? bar.barForeground : Color.foreground)
  readonly property color warnColor: panelItem ? panelItem.warnColor : "#e6b84d"
  readonly property color goodColor: "#5fd68a"
  readonly property string pingQuality: Model.pingQuality(
    status && status.pingMs !== undefined ? status.pingMs : (minute ? minute.pingMs : null),
    status,
    ok,
    minute ? minute.pingSuccess : null
  )
  readonly property color chipColor: pingQuality === "ok" ? goodColor
    : pingQuality === "warn" ? warnColor
    : pingQuality === "bad" ? Color.urgent
    : Qt.darker(barColor, 1.45)

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  function refresh() {
    if (panelLoader.item && panelLoader.item.refresh) panelLoader.item.refresh()
  }

  function togglePanel() {
    if (panelLoader.item && panelLoader.item.toggle) panelLoader.item.toggle()
  }

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() {
    if (panelLoader.item && panelLoader.item.openFromHotkey) panelLoader.item.openFromHotkey()
  }

  function close() {
    if (panelLoader.item && panelLoader.item.close) panelLoader.item.close()
  }

  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  function triggerPress(mouseButton) {
    if (!panelLoader.item) return
    if (mouseButton === Qt.MiddleButton) {
      root.refresh()
      return
    }
    if (mouseButton === Qt.RightButton) {
      panelLoader.item.notifyStatus()
      return
    }
    root.togglePanel()
  }

  function injectPanelAndRefresh() {
    injectPanel()
    root.refresh()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  readonly property real openPanelIndicatorWidth: root.vertical ? 0 : comboRow.implicitWidth

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanelAndRefresh)
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "starlink"
    labelVisible: false
    hasVisualContent: true
    tooltipText: root.barTooltip
    foreground: root.chipColor
    active: root.opened
    useActiveColor: false
    horizontalMargin: 8
    fixedWidth: root.vertical ? -1 : (comboRow.implicitWidth + scaledHorizontalMargin * 2)
    fixedHeight: root.vertical ? Style.bar.statusSlot : -1
    onPressed: function(b) { root.triggerPress(b) }

    StarlinkLogo {
      visible: root.vertical
      anchors.centerIn: parent
      pixelSize: Style.bar.iconCanvas
      color: root.chipColor
    }

    Row {
      id: comboRow
      visible: !root.vertical
      height: parent.height
      z: 1
      anchors.verticalCenter: parent.verticalCenter
      anchors.horizontalCenter: parent.horizontalCenter
      spacing: Style.space(6)

      StarlinkLogo {
        anchors.verticalCenter: parent.verticalCenter
        pixelSize: Style.bar.iconCanvas
        color: root.chipColor
      }

      Text {
        anchors.verticalCenter: parent.verticalCenter
        text: root.chipText
        color: root.chipColor
        font.family: button.fontFamily
        font.pixelSize: Style.font.body
        font.bold: root.pingQuality === "ok"
        renderType: Text.NativeRendering

        Behavior on color {
          ColorAnimation { duration: 180 }
        }
      }
    }
  }
}
