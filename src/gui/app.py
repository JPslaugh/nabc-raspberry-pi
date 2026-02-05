import json
import os
import sys
from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets


TELEMETRY_PATH = os.environ.get("ROV_TELEMETRY_PATH", "./telemetry.json")
POLL_INTERVAL_MS = 200


class TelemetryReader(QtCore.QObject):
    telemetryUpdated = QtCore.Signal(dict)
    telemetryMissing = QtCore.Signal()

    def __init__(self, path: str, poll_interval_ms: int = POLL_INTERVAL_MS):
        super().__init__()
        self._path = path
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self._poll)
        self._last_mtime = 0.0

    def start(self) -> None:
        self._timer.start()
        self._poll()

    def _poll(self) -> None:
        if not os.path.exists(self._path):
            self.telemetryMissing.emit()
            return

        try:
            mtime = os.path.getmtime(self._path)
            if mtime == self._last_mtime:
                return
            self._last_mtime = mtime

            with open(self._path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.telemetryUpdated.emit(payload)
        except Exception:
            self.telemetryMissing.emit()


class StatusCard(QtWidgets.QFrame):
    def __init__(self, title: str, value: str = "--") -> None:
        super().__init__()
        self.setObjectName("statusCard")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        self._title = QtWidgets.QLabel(title)
        self._title.setObjectName("cardTitle")
        self._value = QtWidgets.QLabel(value)
        self._value.setObjectName("cardValue")

        layout.addWidget(self._title)
        layout.addWidget(self._value)
        layout.addStretch(1)

    def setValue(self, value: str) -> None:
        self._value.setText(value)


class DashboardWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NABC ROV Telemetry")
        self.resize(1200, 720)

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(16)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(16)

        self.status_label = QtWidgets.QLabel("No telemetry")
        self.status_label.setObjectName("headerStatus")
        self.timestamp_label = QtWidgets.QLabel("--")
        self.timestamp_label.setObjectName("headerTimestamp")

        header_layout.addWidget(self.status_label)
        header_layout.addStretch(1)
        header_layout.addWidget(QtWidgets.QLabel("Last update:"))
        header_layout.addWidget(self.timestamp_label)

        root_layout.addLayout(header_layout)

        card_layout = QtWidgets.QHBoxLayout()
        self.depth_card = StatusCard("Depth", "-- PSI")
        self.temp_card = StatusCard("Water Temp", "-- °C")
        self.heading_card = StatusCard("Heading", "--°")
        self.safety_card = StatusCard("Safety", "--")
        card_layout.addWidget(self.depth_card)
        card_layout.addWidget(self.temp_card)
        card_layout.addWidget(self.heading_card)
        card_layout.addWidget(self.safety_card)
        root_layout.addLayout(card_layout)

        main_layout = QtWidgets.QHBoxLayout()
        main_layout.setSpacing(16)

        self.sensor_table = self._build_table([
            "Sensor", "Value", "Units", "Healthy"
        ])
        self.actuator_table = self._build_table([
            "Actuator", "Command", "Feedback", "Interlock"
        ])

        left_layout = QtWidgets.QVBoxLayout()
        left_layout.addWidget(self._section_title("Sensors"))
        left_layout.addWidget(self.sensor_table)

        right_layout = QtWidgets.QVBoxLayout()
        right_layout.addWidget(self._section_title("Actuators"))
        right_layout.addWidget(self.actuator_table)

        main_layout.addLayout(left_layout, 3)
        main_layout.addLayout(right_layout, 2)

        root_layout.addLayout(main_layout, 1)

        imu_layout = QtWidgets.QHBoxLayout()
        imu_layout.addWidget(self._section_title("IMU"))
        self.imu_label = QtWidgets.QLabel("Roll: --   Pitch: --   Yaw: --")
        self.imu_label.setObjectName("imuLabel")
        imu_layout.addWidget(self.imu_label)
        imu_layout.addStretch(1)
        root_layout.addLayout(imu_layout)

    def _section_title(self, text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _build_table(self, headers: list[str]) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setObjectName("dataTable")
        return table

    def _update_table(self, table: QtWidgets.QTableWidget, rows: list[list[str]]) -> None:
        table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                item = QtWidgets.QTableWidgetItem(value)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                table.setItem(row_idx, col_idx, item)

    def setTelemetry(self, payload: dict) -> None:
        timestamp = payload.get("timestamp", "--")
        self.timestamp_label.setText(timestamp)
        self.status_label.setText("Telemetry online")

        system = payload.get("system", {})
        is_safe = system.get("safe", True)
        violation = system.get("violation", "")
        if is_safe:
            self.safety_card.setValue("SAFE")
        else:
            self.safety_card.setValue(f"FAULT: {violation}")

        sensors = payload.get("sensors", [])
        sensor_rows = []
        depth_value = None
        temp_value = None
        heading_value = None
        imu_payload = None

        for sensor in sensors:
            name = sensor.get("name", "--")
            value = sensor.get("value", "--")
            units = sensor.get("units", "")
            healthy = "OK" if sensor.get("healthy", False) else "FAULT"
            sensor_rows.append([
                str(name),
                f"{value:.2f}" if isinstance(value, (int, float)) else str(value),
                str(units),
                healthy,
            ])

            if "depth" in str(name).lower():
                depth_value = value
            if "temp" in str(name).lower():
                temp_value = value
            if "imu" in str(name).lower():
                imu_payload = sensor.get("imu")

        if depth_value is not None:
            self.depth_card.setValue(f"{depth_value:.2f} PSI")
        if temp_value is not None:
            self.temp_card.setValue(f"{temp_value:.2f} °C")

        if imu_payload:
            heading_value = imu_payload.get("yaw")
            roll = imu_payload.get("roll", 0.0)
            pitch = imu_payload.get("pitch", 0.0)
            yaw = imu_payload.get("yaw", 0.0)
            self.imu_label.setText(
                f"Roll: {roll:.1f}°   Pitch: {pitch:.1f}°   Yaw: {yaw:.1f}°"
            )

        if heading_value is not None:
            self.heading_card.setValue(f"{heading_value:.1f}°")

        self._update_table(self.sensor_table, sensor_rows)

        actuators = payload.get("actuators", [])
        actuator_rows = []
        for actuator in actuators:
            name = actuator.get("name", "--")
            command = actuator.get("command", "--")
            feedback = actuator.get("feedback", "--")
            interlock = "ON" if actuator.get("interlock", False) else "OFF"
            actuator_rows.append([
                str(name),
                f"{command:.2f}" if isinstance(command, (int, float)) else str(command),
                f"{feedback:.2f}" if isinstance(feedback, (int, float)) else str(feedback),
                interlock,
            ])
        self._update_table(self.actuator_table, actuator_rows)

    def setTelemetryMissing(self) -> None:
        self.status_label.setText("Waiting for telemetry")
        self.timestamp_label.setText("--")


def apply_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#101827"))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#E2E8F0"))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#0F172A"))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#111B2E"))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor("#E2E8F0"))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor("#111827"))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#E2E8F0"))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor("#1F2937"))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#E2E8F0"))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#38BDF8"))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#0F172A"))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QLabel#headerStatus { font-size: 20px; font-weight: 600; }
        QLabel#headerTimestamp { font-size: 13px; color: #94A3B8; }
        QLabel#sectionTitle { font-size: 16px; font-weight: 600; }
        QLabel#imuLabel { font-size: 14px; color: #E2E8F0; }
        QFrame#statusCard {
            background: #111827;
            border: 1px solid #1E293B;
            border-radius: 12px;
        }
        QLabel#cardTitle { font-size: 12px; color: #94A3B8; }
        QLabel#cardValue { font-size: 18px; font-weight: 600; }
        QTableWidget#dataTable {
            border: 1px solid #1E293B;
            background: #0F172A;
        }
        QHeaderView::section {
            background: #1E293B;
            color: #E2E8F0;
            padding: 6px;
            border: none;
        }
        """
    )


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    apply_theme(app)

    window = DashboardWindow()
    window.show()

    reader = TelemetryReader(TELEMETRY_PATH)
    reader.telemetryUpdated.connect(window.setTelemetry)
    reader.telemetryMissing.connect(window.setTelemetryMissing)
    reader.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
