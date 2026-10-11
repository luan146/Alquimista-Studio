from typing import TYPE_CHECKING

# Mixins are only ever combined into MainWindow (a QMainWindow). Telling the
# type checker so lets `self` be passed as a parent widget; at runtime the
# mixins stay plain classes and the MRO is unchanged.
if TYPE_CHECKING:
    from PySide6.QtWidgets import QMainWindow as WindowBase
else:
    WindowBase = object
