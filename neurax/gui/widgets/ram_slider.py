from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel
from PyQt6.QtCore import pyqtSignal, Qt

class RamSlider(QWidget):
    """Custom Memory Allocation Slider displaying real-time GB metrics dynamically bounded by host system RAM."""
    valueChanged = pyqtSignal(int)

    def __init__(self, title: str, min_mb: int = 1024, max_mb: int = 16384, current_mb: int = 4096, parent=None):
        super().__init__(parent)
        current_mb = max(min_mb, min(current_mb, max_mb))
        self._value = current_mb
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-weight: 600;")
        self.val_lbl = QLabel(f"{current_mb / 1024:.1f} GB ({current_mb} MB)")
        self.val_lbl.setStyleSheet("font-weight: bold;")
        
        top_row.addWidget(self.title_lbl)
        top_row.addStretch()
        top_row.addWidget(self.val_lbl)
        layout.addLayout(top_row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(min_mb)
        self.slider.setMaximum(max_mb)
        self.slider.setSingleStep(256)
        self.slider.setPageStep(1024)
        self.slider.setValue(current_mb)
        self.slider.valueChanged.connect(self._on_change)
        
        layout.addWidget(self.slider)

    def _on_change(self, val: int):
        snapped = round(val / 256) * 256
        snapped = max(self.slider.minimum(), min(snapped, self.slider.maximum()))
        self._value = snapped
        self.val_lbl.setText(f"{snapped / 1024:.1f} GB ({snapped} MB)")
        self.valueChanged.emit(snapped)

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        val = max(self.slider.minimum(), min(val, self.slider.maximum()))
        self._value = val
        self.slider.setValue(val)
        self.val_lbl.setText(f"{val / 1024:.1f} GB ({val} MB)")
