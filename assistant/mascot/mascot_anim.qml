import QtQuick
import QtQuick3D

Item {
    id: root
    width: 280
    height: 380

    // Python đặt nội dung bong bóng thoại (rỗng = ẩn)
    property string bubbleText: ""

    View3D {
        anchors.fill: parent

        environment: SceneEnvironment {
            clearColor: "transparent"
            backgroundMode: SceneEnvironment.Transparent
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }

        PerspectiveCamera {
            position: Qt.vector3d(0, camY, camZ)
            clipNear: 0.1
            clipFar: 100000
        }

        DirectionalLight { eulerRotation: Qt.vector3d(-30, -20, 0); brightness: 1.0 }
        DirectionalLight { eulerRotation: Qt.vector3d(20, 150, 0); brightness: 0.7 }
        DirectionalLight { eulerRotation: Qt.vector3d(80, 10, 0); brightness: 0.4 }

        Node {
            id: modelPivot
            objectName: "modelPivot"
            property real yaw: 0
            eulerRotation.y: yaw
            Behavior on yaw { NumberAnimation { duration: 300; easing.type: Easing.InOutQuad } }

            Loader3D {
                id: modelLoader
                source: modelQmlUrl
            }
        }
    }

    // Bong bóng thoại (hiện ở trên đầu nhân vật)
    Rectangle {
        id: bubble
        visible: root.bubbleText.length > 0
        color: "#f2ffffff"
        border.color: "#88888888"
        border.width: 1
        radius: 12
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 4
        width: Math.min(parent.width - 12, bubbleTxt.implicitWidth + 22)
        height: bubbleTxt.implicitHeight + 16

        Text {
            id: bubbleTxt
            anchors.centerIn: parent
            width: root.width - 34
            text: root.bubbleText
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            color: "#222222"
            font.pixelSize: 13
        }
    }

    // Kéo = di chuyển | chuột phải = menu | double-click = nói chuyện (mic)
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        property real lx: 0
        property real ly: 0
        onPressed: (m) => {
            lx = m.x; ly = m.y;
            if (m.button === Qt.RightButton)
                bridge.menu();
            else
                bridge.set_dragging(true);
        }
        onReleased: bridge.set_dragging(false)
        onPositionChanged: (m) => {
            if (pressed)
                bridge.move_by(Math.round(m.x - lx), Math.round(m.y - ly));
        }
        onDoubleClicked: bridge.listen()
    }
}
