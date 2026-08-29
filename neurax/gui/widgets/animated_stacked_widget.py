from PyQt6.QtWidgets import QStackedWidget
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup, Qt

class AnimatedStackedWidget(QStackedWidget):
    """StackedWidget with GPU-accelerated ultra-smooth page sliding transitions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim_group = None
        self._is_animating = False
        self._target_index = 0

    def _reset_widgets(self, active_index: int):
        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()
        self._is_animating = False
        self._target_index = active_index
        self.setCurrentIndex(active_index)
        for i in range(self.count()):
            w = self.widget(i)
            if w:
                w.move(0, 0)
                if i == active_index:
                    w.show()
                else:
                    w.hide()

    def slide_to_index(self, index: int, duration: int = 250):
        if index < 0 or index >= self.count():
            return
        if index == self.currentIndex() and not self._is_animating:
            return

        if self._is_animating:
            self._reset_widgets(self._target_index)

        if index == self.currentIndex():
            return

        self._is_animating = True
        current_idx = self.currentIndex()
        self._target_index = index
        current_widget = self.widget(current_idx)
        next_widget = self.widget(index)

        w = self.width()
        h = self.height()
        offset_x = w if index > current_idx else -w

        for i in range(self.count()):
            w_item = self.widget(i)
            if w_item and i != current_idx and i != index:
                w_item.hide()
                w_item.move(0, 0)

        next_widget.setGeometry(0, 0, w, h)
        next_widget.move(offset_x, 0)
        next_widget.show()
        next_widget.raise_()

        self._anim_group = QParallelAnimationGroup(self)

        anim_current_pos = QPropertyAnimation(current_widget, b"pos", self)
        anim_current_pos.setDuration(duration)
        anim_current_pos.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_current_pos.setStartValue(QPoint(0, 0))
        anim_current_pos.setEndValue(QPoint(-offset_x, 0))

        anim_next_pos = QPropertyAnimation(next_widget, b"pos", self)
        anim_next_pos.setDuration(duration)
        anim_next_pos.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_next_pos.setStartValue(QPoint(offset_x, 0))
        anim_next_pos.setEndValue(QPoint(0, 0))

        self._anim_group.addAnimation(anim_current_pos)
        self._anim_group.addAnimation(anim_next_pos)

        target_idx = index
        def on_anim_finished():
            self._reset_widgets(target_idx)

        self._anim_group.finished.connect(on_anim_finished)
        self._anim_group.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._is_animating:
            self._reset_widgets(self.currentIndex())
