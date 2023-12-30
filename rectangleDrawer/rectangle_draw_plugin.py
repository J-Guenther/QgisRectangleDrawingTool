from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction
from qgis.gui import QgsMapTool, QgsRubberBand, QgsAttributeEditorContext
from qgis.core import QgsWkbTypes, QgsProject, QgsGeometry, QgsPoint, QgsPointXY, QgsVectorLayer, QgsFeature, edit, QgsMapLayer, QgsCoordinateTransform, QgsExpression, QgsFeatureRequest
from qgis.utils import iface
from sys import version_info

_polygon = QgsWkbTypes.PolygonGeometry


class RectangleDrawingTool(QgsMapTool):

    def __init__(self, canvas):
        super(RectangleDrawingTool, self).__init__(canvas)
        self.canvas = canvas
        self.rb = None
        self.points_set_by_user = []
        self.isRectangle = False
        self.capturing = False

    def canvasPressEvent(self, e):
        if len(self.points_set_by_user) < 2:
            self.points_set_by_user.append(self.toMapCoordinates(e.pos()))
            
        if len(self.points_set_by_user) == 1:
            self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
            self.rb.setColor(Qt.red)
            self.rb.setWidth(1)
            self.rb.setToGeometry(QgsGeometry.fromPolygonXY([]))
            self.rb.addPoint(self.points_set_by_user[0], True)  # Add the first point
            self.capturing = True

    def canvasMoveEvent(self, e):
        if 1 <= len(self.points_set_by_user) < 2:
            mouse_position = self.toMapCoordinates(e.pos())
            self.rb.setToGeometry(QgsGeometry.fromPolygonXY([self.points_set_by_user + [mouse_position]]))
            self.rb.show()
        elif len(self.points_set_by_user) == 2 and self.capturing:
            point1 = QgsPoint(self.points_set_by_user[0])
            point2 = QgsPoint(self.points_set_by_user[1])

            # Calculate the vector representing the line
            line_vector = point2 - point1

            # Calculate the unit vector along the line
            line_unit_vector = line_vector / line_vector.length()

            # Find a perpendicular vector (normal to the line)
            perpendicular_vector = QgsPointXY(-line_unit_vector.y(), line_unit_vector.x())

            mouse_position = self.toMapCoordinates(e.pos())
            # Calculate dot product to get the width between the mouse position and the line_vector
            width = perpendicular_vector.x() * (mouse_position.x() - point1.x()) + perpendicular_vector.y() * (mouse_position.y() - point1.y())
            
            # Calculate points for the extruded parallel line
            extruded_points = [
                QgsPointXY(point1),
                QgsPointXY(point2),
                QgsPointXY(point2.x() + width * perpendicular_vector.x(), point2.y() + width * perpendicular_vector.y()),
                QgsPointXY(point1.x() + width * perpendicular_vector.x(), point1.y() + width * perpendicular_vector.y())
            ]
            
            # Create a QgsGeometry object for the extruded line (a closed polygon)
            extruded_geometry = QgsGeometry.fromPolygonXY([extruded_points])
            self.rb.setToGeometry(extruded_geometry)
            self.rb.show()
            self.isRectangle = True

    def canvasReleaseEvent(self, e):
        if len(self.points_set_by_user) < 2:
            self.points_set_by_user[-1] = self.toMapCoordinates(e.pos())
            self.rb.setToGeometry(QgsGeometry.fromPolygonXY([self.points_set_by_user]))
            self.rb.show()
        elif self.isRectangle:
        
            if e.button() == Qt.LeftButton:
                layer = self.canvas.currentLayer()
                if not layer or layer.type() != QgsMapLayer.VectorLayer or layer.geometryType() != _polygon:
                    iface.messageBar().pushInfo("Add feature", "No active polygon layer")
                    return
                else:
                    self.capturing = False
                    self.add_feature_to_layer()
                    
            elif e.button() == Qt.RightButton:
                self.reset()

    def add_feature_to_layer(self):
        layer = self.canvas.currentLayer()
        feature = QgsFeature()
        feature.setFields(layer.fields())
        geometry = self.transformed_geometry(layer)
        feature.setGeometry(self.multi_to_single_polygon(geometry))

        #if layer.fields().count():
        #    ff = iface.getFeatureForm(layer, feature)
        #    if version_info[0] >= 3:
        #        print("VERSION 3")
        #        ff.setMode(QgsAttributeEditorContext.AddFeatureMode)
        #    ff.accepted.connect(self.reset)
        #    ff.rejected.connect(self.reset)
        #    ff.show()
        #else:
        #    layer.addFeature(feature)
        #    self.reset()

        layer.addFeature(feature)
        self.reset()

    def multi_to_single_polygon(self, geometry):
        if geometry.wkbType() == QgsWkbTypes.MultiPolygon:
            geom = geometry.asMultiPolygon()
            return QgsGeometry.fromPolygonXY(geom[0])
        return geometry

    def transformed_geometry(self, layer):
        geometry = self.rb.asGeometry()

        if version_info[0] >= 3:
            source_crs = QgsProject.instance().crs()
            tr = QgsCoordinateTransform(source_crs, layer.crs(), QgsProject.instance())
        else:
            if hasattr(self.canvas, "mapSettings"):
                source_crs = self.canvas.mapSettings().destinationCrs()
            else:
                source_crs = self.canvas.mapRenderer().destinationCrs()
            tr = QgsCoordinateTransform(source_crs, layer.crs())

        if source_crs != layer.crs():
            geometry.transform(tr)

        return geometry

    def getNewId(self, layer):
        max_id = 1
        field_name = 'fid'
        expr = QgsExpression(f"maximum(\"{field_name}\")")

        # Create a request using the expression
        request = QgsFeatureRequest(expr)

        features = layer.getFeatures(request)

        # Iterate over features (there should be only one with maximum value)
        for feature in features:
            max_id = feature['maximum']
        
        return max_id

    def keyPressEvent(self, e): 
        if e.key() == Qt.Key_Escape:
            self.reset()

    def reset(self):
        if self.rb:
            self.rb.reset(QgsWkbTypes.PolygonGeometry)
            self.rb = None
        self.points_set_by_user = []
        self.isRectangle = False
        self.canvas.refresh()

    def deactivate(self):
        self.reset()
        

class RectangleDrawPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.tool = None

    def initGui(self):
        self.action = QAction("Draw Rectangle", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle_tool)
        self.iface.addPluginToMenu("&Rectangle Drawing Tool", self.action)

    def unload(self):
        self.iface.removePluginMenu("&Rectangle Drawing Tool", self.action)
        del self.action

    def toggle_tool(self, checked):
        if checked:
            self.tool = RectangleDrawingTool(self.canvas)
            self.canvas.setMapTool(self.tool)
        else:
            if self.tool:
                self.canvas.unsetMapTool(self.tool)
                self.tool.deactivate()
                self.tool = None


def classFactory(iface):
    return RectangleDrawPlugin(iface)
