def classFactory(iface):
    from .rectangle_draw_plugin import RectangleDrawPlugin
    return RectangleDrawPlugin(iface)