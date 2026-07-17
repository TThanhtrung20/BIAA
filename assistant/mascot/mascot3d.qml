import QtQuick
import QtQuick3D
import QtQuick3D.AssetUtils

Item {
    id: root
    width: 260
    height: 260

    View3D {
        anchors.fill: parent

        environment: SceneEnvironment {
            clearColor: "transparent"
            backgroundMode: SceneEnvironment.Transparent
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }

        PerspectiveCamera {
            id: cam
            position: Qt.vector3d(0, 0, modelSize * 1.6)
            clipNear: Math.max(0.01, modelSize * 0.01)
            clipFar: modelSize * 100
        }

        // Ánh sáng có màu -> mô hình xám sẽ nhuốm màu này cho đẹp
        DirectionalLight { eulerRotation: Qt.vector3d(-30, -20, 0); color: mascotColor; brightness: 1.35 }
        DirectionalLight { eulerRotation: Qt.vector3d(15, 150, 0); color: mascotColor; brightness: 0.6 }
        // Một ít ánh sáng trắng giữ lại chi tiết, tránh bệt màu
        DirectionalLight { eulerRotation: Qt.vector3d(80, 10, 0); color: "#ffffff"; brightness: 0.35 }

        Node {
            id: pivot

            RuntimeLoader {
                id: importNode
                source: modelSource
                // dời mô hình để tâm nằm ở gốc (xoay/nhún quanh tâm)
                position: Qt.vector3d(-modelCenter.x, -modelCenter.y, -modelCenter.z)
            }

            // Xoay chậm cho sinh động
            NumberAnimation on eulerRotation.y {
                from: 0; to: 360; duration: 12000
                loops: Animation.Infinite; running: true
            }

            // Nhún nhảy nhẹ lên xuống
            SequentialAnimation on y {
                loops: Animation.Infinite
                NumberAnimation { from: 0; to: modelSize * 0.05; duration: 520; easing.type: Easing.InOutSine }
                NumberAnimation { from: modelSize * 0.05; to: 0; duration: 520; easing.type: Easing.InOutSine }
            }
        }
    }

    // Kéo để di chuyển; chuột phải để thoát
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        property real lx: 0
        property real ly: 0
        onPressed: (m) => {
            lx = m.x; ly = m.y;
            if (m.button === Qt.RightButton)
                bridge.quit();
            else
                bridge.set_dragging(true);
        }
        onReleased: bridge.set_dragging(false)
        onPositionChanged: (m) => {
            if (pressed)
                bridge.move_by(Math.round(m.x - lx), Math.round(m.y - ly));
        }
    }
}
