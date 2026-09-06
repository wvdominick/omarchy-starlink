import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "wvdominick.starlink"
  ipcTarget: "wvdominick.starlink"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root
  property bool openedFromHotkey: false

  property bool ok: true
  property string error: ""
  property string host: ""
  property string fetchedAt: ""
  property var status: null
  property var minute: null
  property var day: null
  property var history: null
  property var map: null
  property int sparkEpoch: 0
  property bool pluginUpdateAvailable: false
  property bool pluginUpdating: false
  property string pluginUpdateError: ""

  readonly property string backendScript: {
    var path = String(Qt.resolvedUrl("."))
    path = path.replace(/^file:\/\//, "")
    try { path = decodeURIComponent(path) } catch (e) {}
    if (path.length && path.charAt(0) !== "/") path = "/" + path
    return path + "fetch.py"
  }
  readonly property string dishHost: String(setting("dishHost", "192.168.100.1:9200") || "192.168.100.1:9200")
  readonly property int refreshSec: Math.max(2, parseInt(setting("refreshIntervalSec", 5), 10) || 5)
  readonly property color foreground: barForeground
  readonly property color dim: Qt.darker(foreground, 1.4)
  readonly property color warnColor: "#e6b84d"
  readonly property color urgent: Color.urgent
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property string tone: Model.tone(status, ok)
  readonly property string barTooltip: Model.tooltip(status, ok, error, host, minute, day)
  readonly property color goodColor: "#5fd68a"
  readonly property color barColor: tone === "ok" ? goodColor
    : tone === "warn" ? warnColor
    : tone === "bad" ? urgent
    : dim
  readonly property var dayBuckets: day && day.buckets ? day.buckets : []
  readonly property var mapSnr: map && map.snr ? map.snr : []
  readonly property int mapRows: map && map.rows ? map.rows : 0
  readonly property int mapCols: map && map.cols ? map.cols : 0

  function open() {
    openedFromHotkey = false
    setCenterHoverRevealSuppressed(false)
    root.controller.show()
    root.refresh()
    root.refreshDetails()
  }

  function openFromHotkey() {
    openedFromHotkey = true
    root.controller.show()
    root.refresh()
    root.refreshDetails()
    Qt.callLater(function() {
      if (root.opened) setCenterHoverRevealSuppressed(true)
    })
  }

  function close() {
    setCenterHoverRevealSuppressed(false)
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.openFromHotkey()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function setCenterHoverRevealSuppressed(value) {
    if (root.bar && "centerHoverRevealSuppressed" in root.bar)
      root.bar.centerHoverRevealSuppressed = value
  }

  function refresh() {
    if (statusProc.running) return
    statusProc.command = ["/usr/bin/python3", root.backendScript, "status", "--host", root.dishHost]
    statusProc.running = true
  }

  function refreshDetails() {
    if (detailProc.running) return
    detailProc.command = ["/usr/bin/python3", root.backendScript, "details", "--host", root.dishHost]
    detailProc.running = true
  }

  function paintSky() {
    if (skyMap) skyMap.requestPaint()
  }

  function applyReport(text) {
    var parsed = Model.parseReport(text)
    if (parsed.host) root.host = parsed.host
    if (parsed.fetchedAt) root.fetchedAt = parsed.fetchedAt
    if (parsed.status) root.status = parsed.status
    if (parsed.minute) {
      root.minute = parsed.minute
      root.sparkEpoch = root.sparkEpoch + 1
    }
    if (parsed.day) root.day = parsed.day
    if (parsed.history) root.history = parsed.history
    if (parsed.map) root.map = parsed.map
    if (parsed.ok) {
      root.ok = true
      root.error = ""
    } else {
      root.ok = false
      root.error = parsed.error || "Dish unreachable"
    }
  }

  function notifyStatus() {
    var body = root.barTooltip.split("\n").slice(0, 6).join(" · ")
    Quickshell.execDetached(["omarchy-notification-send", "--app-name", "Starlink", "Starlink", body])
  }

  function copyText(value) {
    if (!value) return
    Quickshell.execDetached(["wl-copy", String(value)])
  }

  function checkPluginUpdate() {
    if (pluginUpdateProcess.running || root.pluginUpdating) return
    pluginUpdateProcess.command = Model.pluginUpdateCheckCommand(root.moduleName, 6)
    pluginUpdateProcess.running = true
  }

  function updatePlugin() {
    if (pluginUpdateRunProcess.running || root.pluginUpdating) return
    root.pluginUpdateError = ""
    root.pluginUpdating = true
    pluginUpdateRunProcess.command = Model.pluginUpdateCommand(root.moduleName)
    pluginUpdateRunProcess.running = true
  }

  function cssColor(c, alpha) {
    if (!c) return "transparent"
    var a = alpha === undefined ? 1 : alpha
    return "rgba(" + Math.round(c.r * 255) + ", " + Math.round(c.g * 255) + ", " + Math.round(c.b * 255) + ", " + a + ")"
  }

  onOpenedChanged: {
    if (opened) {
      root.refreshDetails()
      root.checkPluginUpdate()
      root.paintSky()
      Qt.callLater(root.paintSky)
    }
  }

  FileView {
    id: mapCacheFile
    path: Quickshell.env("HOME") + "/.cache/omarchy/starlink/obstruction-map.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      var cached = Model.parseMapCache(text())
      if (cached) root.map = cached
    }
    onFileChanged: reload()
    onLoadFailed: {
      if (!root.map) Qt.callLater(root.refreshDetails)
    }
  }
  onDishHostChanged: {
    root.refresh()
    if (root.opened) root.refreshDetails()
  }

  Process {
    id: statusProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyReport(text)
    }
  }

  Process {
    id: detailProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyReport(text)
    }
  }

  Process {
    id: pluginUpdateProcess
    onExited: function(exitCode) {
      root.pluginUpdateAvailable = exitCode === 10
    }
  }

  Process {
    id: pluginUpdateRunProcess
    stdout: StdioCollector { id: pluginUpdateOutput; waitForEnd: true }
    onExited: function(exitCode) {
      root.pluginUpdating = false
      if (exitCode !== 0) {
        root.pluginUpdateError = "Update did not finish. Run `omarchy plugin update " + root.moduleName + "` to see why."
        return
      }
      root.pluginUpdateAvailable = false
      if (Model.pluginUpdated(pluginUpdateOutput.text)) {
        shellRestartProcess.command = Model.shellRestartCommand()
        shellRestartProcess.startDetached()
      }
    }
  }

  Process {
    id: shellRestartProcess
  }

  Timer {
    interval: root.refreshSec * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Timer {
    interval: 20000
    running: root.opened
    repeat: true
    onTriggered: root.refreshDetails()
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.openFromHotkey() }
    function close(): void { root.close() }
    function show(): void { root.openFromHotkey() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh(); root.refreshDetails() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: false
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r" || t === "R") {
          root.refresh()
          root.refreshDetails()
        }
      }

      Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height

        Column {
          id: column
          width: scroll.width
          spacing: Style.space(8)
          leftPadding: Style.space(14)
          rightPadding: Style.space(14)
          topPadding: Style.space(10)
          bottomPadding: Style.space(12)

          PanelHero {
            width: parent.width - parent.leftPadding - parent.rightPadding
            title: "Starlink"
            meta: {
              if (!root.ok && root.error) return root.error
              if (!root.status) return "Talking to the dish"
              return root.status.stateReason || Model.stateLabel(root.status, root.ok)
            }
            detail: Model.stateLabel(root.status, root.ok)
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconOpacity: root.tone === "off" ? 0.45 : 1
            iconComponent: Component {
              StarlinkLogo {
                pixelSize: Style.font.title
                color: root.barColor
              }
            }
          }

          Grid {
            id: statGrid
            width: parent.width - parent.leftPadding - parent.rightPadding
            columns: 2
            columnSpacing: Style.space(6)
            rowSpacing: Style.space(6)

            StatTile {
              width: (statGrid.width - statGrid.columnSpacing) / 2
              label: "PING"
              value: Model.formatMs(root.status ? root.status.pingMs : null)
              detail: Model.formatTodayPingRange(root.day, root.status ? root.status.pingMs : null)
            }
            StatTile {
              width: (statGrid.width - statGrid.columnSpacing) / 2
              label: "PING SUCCESS"
              value: Model.barSuccessText(root.minute)
            }
            StatTile {
              width: (statGrid.width - statGrid.columnSpacing) / 2
              label: "DOWNLOAD"
              value: Model.formatMbpsUnitDirect(root.minute ? root.minute.downMbps : null)
              valueColor: root.minute && root.minute.held ? root.dim : root.foreground
              detail: Model.formatTodayPeak(root.day, root.minute)
            }
            StatTile {
              width: (statGrid.width - statGrid.columnSpacing) / 2
              label: "TODAY"
              value: Model.formatTransfer(root.day)
            }
          }

          Column {
            width: parent.width - parent.leftPadding - parent.rightPadding
            spacing: Style.space(4)

            DayChart {
              width: parent.width
              height: Style.space(80)
              buckets: root.dayBuckets
              field: "down"
              title: "Download"
              stroke: root.barColor
              fill: root.barColor
              unit: "Mbps"
            }

            DayChart {
              width: parent.width
              height: Style.space(48)
              buckets: root.dayBuckets
              field: "ping"
              title: "Ping"
              stroke: root.warnColor
              fill: root.warnColor
              unit: "ms"
              connectGaps: true
            }
          }

          Column {
            width: parent.width - parent.leftPadding - parent.rightPadding
            spacing: Style.space(4)
            visible: root.mapRows > 0 && root.mapCols > 0

            PanelSectionHeader {
              text: root.status ? ("OBSTRUCTIONS  ·  " + Model.formatPct(root.status.obstructionPct)) : "OBSTRUCTIONS"
              foreground: root.status && root.status.currentlyObstructed ? root.urgent : root.foreground
              fontFamily: root.fontFamily
            }

            SkyMap {
              id: skyMap
              width: parent.width
              height: Style.space(168)
              rows: root.mapRows
              cols: root.mapCols
              snr: root.mapSnr
            }
          }

          Item {
            width: 1
            height: Style.space(36)
          }

          Column {
            width: parent.width - parent.leftPadding - parent.rightPadding
            spacing: Style.space(6)

            PanelSectionHeader {
              text: "Dish"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            InfoRow { label: "Alignment"; value: Model.alignmentLabel(root.status) }
            InfoRow { label: "Drops today"; value: Model.formatDuration(root.day ? root.day.dropSeconds : 0) }
            InfoRow { label: "Hardware"; value: root.status ? (root.status.hardware || "—") : "—" }
            InfoRow { label: "Firmware"; value: root.status ? (root.status.software || "—") : "—" }
            InfoRow { label: "Uptime"; value: root.status ? Model.formatUptime(root.status.uptimeS) : "—" }
            InfoRow { label: "GPS"; value: root.status ? ((root.status.gpsValid ? "Lock" : "No lock") + " · " + (root.status.gpsSats || 0) + " sats") : "—" }
            InfoRow { label: "Ethernet"; value: root.status && root.status.ethMbps ? (root.status.ethMbps + " Mbps") : "—" }
            InfoRow { label: "SNR"; value: root.status && root.status.snrAboveNoiseFloor === false ? "Below noise floor" : "Above noise floor" }
            InfoRow { label: "Host"; value: root.host || root.dishHost }

            Text {
              visible: !!(root.status && root.status.alerts && root.status.alerts.length)
              width: parent.width
              textFormat: Text.PlainText
              text: root.status && root.status.alerts ? root.status.alerts.join(" · ") : ""
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            Button {
              visible: root.pluginUpdateAvailable || root.pluginUpdating || root.pluginUpdateError !== ""
              width: parent.width
              text: root.pluginUpdating ? "Updating this panel…" : (root.pluginUpdateError !== "" ? "Retry update" : "Update this panel")
              tooltipText: root.pluginUpdating
                ? "Pulling the new version"
                : (root.pluginUpdateError !== "" ? root.pluginUpdateError : "A newer version is available")
              foreground: root.foreground
              fontFamily: root.fontFamily
              bordered: true
              enabled: !root.pluginUpdating
              onClicked: root.updatePlugin()
            }

            Text {
              visible: root.pluginUpdateError !== ""
              width: parent.width
              textFormat: Text.PlainText
              text: root.pluginUpdateError
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }
          }
        }
      }

      Item {
        id: moreHint
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Style.space(28)
        z: 2
        visible: scroll.contentHeight > scroll.height + 8 && !scroll.atYEnd
        enabled: false

        Rectangle {
          anchors.fill: parent
          gradient: Gradient {
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 0.45; color: Qt.rgba(Color.popups.background.r, Color.popups.background.g, Color.popups.background.b, 0.72) }
            GradientStop { position: 1.0; color: Color.popups.background }
          }
        }

        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          anchors.bottom: parent.bottom
          anchors.bottomMargin: Style.space(4)
          textFormat: Text.PlainText
          text: "More stats  ↓"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
      }
    }
  }

  component StatTile: Rectangle {
    id: tile
    property string label: ""
    property string value: ""
    property string detail: ""
    property color valueColor: root.foreground
    height: Style.space(62)
    radius: Style.cornerRadius
    color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.07)

    Column {
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(2)

      Text {
        textFormat: Text.PlainText
        text: tile.label
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        font.letterSpacing: 1.1
      }

      Text {
        width: parent.width
        textFormat: Text.PlainText
        text: tile.value
        color: tile.valueColor
        font.family: root.fontFamily
        font.pixelSize: Style.font.title
        font.bold: true
        elide: Text.ElideRight
      }

      Text {
        width: parent.width
        textFormat: Text.PlainText
        text: tile.detail !== "" ? tile.detail : " "
        color: root.dim
        opacity: tile.detail !== "" ? 1 : 0
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        elide: Text.ElideRight
      }
    }
  }

  component InfoRow: Item {
    id: row
    property string label: ""
    property string value: ""
    width: parent ? parent.width : implicitWidth
    implicitHeight: Style.space(22)

    Text {
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: row.label
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      font.bold: true
    }

    Text {
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      width: Math.min(implicitWidth, parent.width * 0.68)
      textFormat: Text.PlainText
      text: row.value
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      elide: Text.ElideMiddle
      horizontalAlignment: Text.AlignRight
    }

    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      onClicked: root.copyText(row.value)
    }
  }

  component DayChart: Item {
    id: chart
    property var buckets: []
    property string field: "down"
    property string title: ""
    property color stroke: Color.accent
    property color fill: Color.accent
    property string unit: ""
    property bool connectGaps: false

    readonly property var domain: Model.dayDomain(chart.buckets)
    readonly property var values: {
      var rows = chart.buckets || []
      var out = []
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i]
        if (!row) continue
        out.push(chart.field === "ping" ? row.ping : row.down)
      }
      return out
    }

    Text {
      id: chartTitle
      anchors.left: parent.left
      anchors.top: parent.top
      textFormat: Text.PlainText
      text: chart.title + (chart.unit ? "  ·  " + chart.unit : "")
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      font.bold: true
    }

    Canvas {
      id: plot
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: chartTitle.bottom
      anchors.topMargin: Style.space(2)
      anchors.bottom: axis.top
      anchors.bottomMargin: Style.space(2)
      onWidthChanged: requestPaint()
      onHeightChanged: requestPaint()

      Connections {
        target: chart
        function onBucketsChanged() { plot.requestPaint() }
        function onFieldChanged() { plot.requestPaint() }
      }

      onPaint: {
        var ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)
        var rows = chart.buckets || []
        var span = chart.domain.end - chart.domain.start
        if (!rows.length || span <= 0) return
        var yDomain = Model.seriesExtent(chart.values, 0.12)
        function xAt(minute) {
          return ((minute - chart.domain.start) / span) * width
        }
        function yAt(value) {
          var ys = yDomain.max - yDomain.min
          if (!ys) return height / 2
          return height - 1 - ((value - yDomain.min) / ys) * (height - 2)
        }

        ctx.strokeStyle = root.cssColor(root.dim, 0.25)
        ctx.lineWidth = 1
        var ticks = Model.hourTicks(chart.domain.start, chart.domain.end)
        for (var t = 0; t < ticks.length; t++) {
          var gx = xAt(ticks[t])
          ctx.beginPath()
          ctx.moveTo(gx, 0)
          ctx.lineTo(gx, height)
          ctx.stroke()
        }

        ctx.beginPath()
        var started = false
        var firstX = 0
        var lastX = 0
        for (var i = 0; i < rows.length; i++) {
          var row = rows[i]
          if (!row) continue
          var v = Number(chart.field === "ping" ? row.ping : row.down)
          if (!isFinite(v)) {
            if (!chart.connectGaps) started = false
            continue
          }
          var x = xAt(Number(row.t))
          var y = yAt(v)
          if (!started) {
            ctx.moveTo(x, y)
            firstX = x
            started = true
          } else {
            ctx.lineTo(x, y)
          }
          lastX = x
        }
        if (!started) return
        ctx.strokeStyle = root.cssColor(chart.stroke, 1)
        ctx.lineWidth = 1.6
        ctx.stroke()
        if (chart.field === "down") {
          ctx.lineTo(lastX, height)
          ctx.lineTo(firstX, height)
          ctx.closePath()
          ctx.fillStyle = root.cssColor(chart.fill, 0.16)
          ctx.fill()
        }
      }
    }

    Item {
      id: axis
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      height: Style.space(12)

      Repeater {
        model: Model.hourTicks(chart.domain.start, chart.domain.end)

        Text {
          required property int modelData
          x: {
            var span = chart.domain.end - chart.domain.start
            if (span <= 0) return 0
            return ((modelData - chart.domain.start) / span) * axis.width - implicitWidth / 2
          }
          textFormat: Text.PlainText
          text: Model.formatHour(modelData)
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }

  component SkyMap: Canvas {
    id: sky
    renderStrategy: Canvas.Immediate
    renderTarget: Canvas.Image
    antialiasing: false
    property int rows: 0
    property int cols: 0
    property var snr: []
    property color clearColor: Color.accent
    property color blockColor: Color.urgent

    onAvailableChanged: if (available) requestPaint()
    onVisibleChanged: if (visible) requestPaint()
    onRowsChanged: requestPaint()
    onColsChanged: requestPaint()
    onSnrChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    Connections {
      target: root
      function onOpenedChanged() {
        if (root.opened) sky.requestPaint()
      }
    }

    onPaint: {
      var ctx = getContext("2d")
      ctx.clearRect(0, 0, width, height)
      var r = sky.rows
      var c = sky.cols
      var data = sky.snr || []
      if (r <= 0 || c <= 0 || !data.length) return
      var cw = width / c
      var ch = height / r
      var good = sky.clearColor
      var bad = sky.blockColor
      for (var y = 0; y < r; y++) {
        for (var x = 0; x < c; x++) {
          var v = Number(data[y * c + x])
          if (!isFinite(v) || v < 0) continue
          var t = Math.max(0, Math.min(1, v))
          ctx.fillStyle = root.cssColor(Qt.rgba(
            bad.r + (good.r - bad.r) * t,
            bad.g + (good.g - bad.g) * t,
            bad.b + (good.b - bad.b) * t,
            1
          ), 0.35 + 0.65 * t)
          ctx.fillRect(x * cw, y * ch, cw + 0.6, ch + 0.6)
        }
      }
    }
  }
}
