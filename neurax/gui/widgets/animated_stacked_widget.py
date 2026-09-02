from PyQt6.QtWidgets import QStackedWidget
<<<<<<< HEAD
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup, Qt, QTimer
=======
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup, Qt
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

class AnimatedStackedWidget(QStackedWidget):
    """StackedWidget with GPU-accelerated ultra-smooth page sliding transitions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim_group = None
        self._is_animating = False
        self._target_index = 0
<<<<<<< HEAD
        # Pending swap request: when the caller asks us to reveal a tab
        # whose slot is still a placeholder, we keep the current view
        # visible and wait for ``set_lazy_widget`` to fill the slot. The
        # slide animation runs *after* the real view exists, so we never
        # animate a widget that gets destroyed mid-tween. See
        # ``MainWindow._on_tab_changed``.
        self._pending_slide_index = None
        self._pending_slide_duration = 250
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

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

<<<<<<< HEAD
    def _is_placeholder(self, index: int) -> bool:
        if index < 0 or index >= self.count():
            return False
        w = self.widget(index)
        return bool(w is not None and getattr(w, "_lazy_attr", None))

    def slide_to_index(self, index: int, duration: int = 250):
        if index < 0 or index >= self.count():
            return
        # If the slot is still a placeholder, don't run the slide yet —
        # the placeholder will be replaced by the real view via
        # ``set_lazy_widget`` shortly. We just remember what was
        # requested and wait. The current view stays on screen so the
        # GUI never goes blank, and the slide runs after the heavy
        # ``__init__`` finishes.
        if self._is_placeholder(index):
            self._pending_slide_index = index
            self._pending_slide_duration = duration
            return

        self._pending_slide_index = None

=======
    def slide_to_index(self, index: int, duration: int = 250):
        if index < 0 or index >= self.count():
            return
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
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

<<<<<<< HEAD
    def set_lazy_widget(self, index: int, real_widget) -> None:
        """Atomically replace a placeholder at ``index`` with the real
        widget and run the pending slide animation. Called from
        ``MainWindow._ensure_view`` after the heavy ``__init__`` is
        done. The atomic ``removeWidget`` + ``insertWidget`` keeps the
        animation happy because both the old placeholder and the new
        view exist for the briefest possible moment.

        If no slide was pending (the user navigated back to a tab they
        had already built), we just swap the widget in place and let
        ``setCurrentIndex`` show it.
        """
        pending = self._pending_slide_index
        pending_duration = self._pending_slide_duration
        self._pending_slide_index = None

        if pending is not None and pending == index:
            # Replace in place and animate immediately so the user
            # sees a single smooth reveal.
            old = self.widget(index)
            was_current = self.currentIndex() == index
            self.removeWidget(old)
            self.insertWidget(index, real_widget)
            old.deleteLater()
            real_widget.show()
            # Defer the slide one idle tick so Qt finishes the
            # insertWidget bookkeeping before we start moving pixels.
            QTimer.singleShot(0, lambda: self.slide_to_index(index, pending_duration))
            return

        # No pending slide. Replace and show.
        old = self.widget(index)
        if old is real_widget:
            return
        was_current = self.currentIndex() == index
        self.removeWidget(old)
        self.insertWidget(index, real_widget)
        old.deleteLater()
        if was_current:
            self.setCurrentIndex(index)

=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._is_animating:
            self._reset_widgets(self.currentIndex())
