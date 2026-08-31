import QtQuick
import QtQuick.Effects

// Pixel-art "\ ))" — angled dish, signal ticks up-right.
Item {
  id: root
  property color color: "#ffffff"
  property int pixelSize: 16

  width: pixelSize
  height: pixelSize
  implicitWidth: pixelSize
  implicitHeight: pixelSize

  Item {
    id: plate
    anchors.fill: parent
    layer.enabled: true
    layer.smooth: true
    layer.effect: MultiEffect {
      colorization: 1.0
      colorizationColor: root.color
    }

    Image {
      anchors.fill: parent
      source: Qt.resolvedUrl("assets/dish-mark.png")
      sourceSize.width: Math.round(root.pixelSize * 2)
      sourceSize.height: Math.round(root.pixelSize * 2)
      fillMode: Image.PreserveAspectFit
      smooth: false
      asynchronous: false
    }
  }
}
