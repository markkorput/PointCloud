bl_info = {
    "name": "Point Cloud Loader",
    "author": "Short Notion (Mark van de Korput)",
    "version": (0, 1),
    "blender": (2, 75, 0),
    "location": "View3D > T-panel > Object Tools",
    "description": "Generate point cloud from data files",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Add Mesh"}

# system stuff
import logging
# blender stuff
import bpy
from bpy.app.handlers import persistent
import bmesh

class PointCloudLoader:
  def __init__(self, scene=None, logger=None):
    self.scene=scene
    self.logger = logger
    if self.logger == None:
      self.logger = logging # default logging object from the imported logging module

  def getScene(self):
    if self.scene:
      return self.scene
    return bpy.context.scene

  # gives all objects in the scene for who the pointCloudLoaderConfig is enabled (through the panel)
  def enabledObjects(self):
    return [obj for obj in self.getScene().objects if obj.pointCloudLoaderConfig.enabled == True]

  # loads the current frame for all point-cloud-enabled objects in the scene
  def loadFrame(self):
    objs = self.enabledObjects()
    print("Number of point cloud objects: {0}".format(len(objs)))

    # load point clouds for the current frame for all point-cloud-enabled objects in the scene
    for obj in objs:
      self.loadObjectFrame(obj)

  # load point cloud for the current frame for the specified object
  def loadObjectFrame(self, obj):
    print("Loading point cloud for object: " + obj.name)

    # get the path to the data file for the point cloud of this object for this frame
    path = self.objectFrameFilePath(obj)
    file = PointCloudFrameFile(path=path, skip=obj.pointCloudLoaderConfig.skipPoints)

    # determine current data file, check if this data file isn't currently loaded already for this object
    # then find or create the point cloud child-object
    # create the points
    # self.createPoints(obj, file.get_points())
    pcofl = PointCloudObjectFrameLoader(obj, file.get_points(), scene=self.getScene())
    pcofl.createPoints()

  # returns the file path of the file that contains
  # the point-cloud data for the current frame
  def objectFrameFilePath(self, obj):
      currentFrame = self.getScene().frame_current
      mod = int(currentFrame*obj.pointCloudLoaderConfig.frameRatio) % obj.pointCloudLoaderConfig.numFiles
      path = obj.pointCloudLoaderConfig.fileName % mod
      if path.startswith("/"):
        return path
      return bpy.path.abspath("//"+path)

# end of class PointCloudLoader


class PointCloudObjectFrameLoader:
  def __init__(self, obj, points, scene=None):
    self.obj = obj
    self.points = points
    self.scene = scene

    if self.scene == None:
      self.scene = bpy.context.scene

  def _existingMesh(self):
    obj = self._existingContainerObject()
    if obj == None:
      print("Couldn't find existing container object")
      return None
    print("Found existing pointcloud mesh")
    return obj.data

  def _createMesh(self):
    print("Creating new pointcloud mesh")
    return bpy.data.meshes.new("pointscloudmesh")

  def getMesh(self):
    # this find existing container object,
    # or creates one. In both cases, it returns a container object with mesh data
    return self.getContainerObject().data

  def _existingContainerObject(self):
    # find first child whose name start with "pointcloud" and has mesh data
    for child in self.obj.children:
      if child.name.startswith("pointcloud") and child.data != None:
        print("Found existing pointcloud container object")
        return child

    return None

  def _createContainerObject(self): # uncached
    print("creating pointcloud container object")
    cobj = bpy.data.objects.new("pointcloud", self._createMesh())
    cobj.parent = self.obj
    # cobj.show_x_ray = True
    self.scene.objects.link(cobj)
    return cobj

  # ty to get existing object, otherwise create one
  def getContainerObject(self):
    return self._existingContainerObject() or self._createContainerObject()

  def _removeVertices(self, containerObj, count):
    print("Removing {0} vertices from pointcloud mesh".format(count))
    mesh = containerObj.data

    # fkin blender, man
    originalActive = self.scene.objects.active # remember currently active object, so we can restore at the end of this function
    self.scene.objects.active = containerObj # make specified object the active object
    bpy.ops.object.mode_set(mode="EDIT")  # endter edit mode
    bm = bmesh.from_edit_mesh(mesh) # start editing the mesh

    # just remove the first <count> vertices
    for i in range(count):
      bm.verts.remove(bm.verts[0])

    bmesh.update_edit_mesh(mesh)
    bpy.ops.object.mode_set(mode="OBJECT")
    self.scene.objects.active = originalActive

  def createPoints(self):
    print("Creating point cloud for object: "+self.obj.name)
    # find existing mesh or creates a new one (inside a "pointcloud" container object)
    mesh = self.getMesh()

    # first make sure the mesh has exactly the right amount of vertices
    existingVertexCount = len(mesh.vertices.values())

    if existingVertexCount < len(self.points):
      print("Adding {0} vertices to pointcloud mesh".format(len(self.points) - existingVertexCount))
      # add missing vertices
      mesh.vertices.add(len(self.points) - existingVertexCount)
    else:
      # remove any surplus vertices
      self._removeVertices(self.getContainerObject(), len(self.points) - existingVertexCount)

    # initialize all vertices of the mesh
    idx = 0
    for point in self.points:
      mesh.vertices[idx].co = (point[0], point[1], point[2])
      idx+=1

    self.scene.update()
# end of class PointCloudObjectFrameLoader

# A class that represents one file (frame) of piont cloud data,
# this class takes care of parsing the file's data into python data (arrays)
class PointCloudFrameFile:
  def __init__(self, path, skip=0, logger=None):
    self.path = path
    self.skip = skip # after every read point, skip this number of points
    self.points = [] # for the points defined in the file
    self.all_points = [] # for all points; also the non-active ones
    self.logger = logger
    if self.logger == None:
      self.logger = logging # default logging object from the imported logging module

  def get_all_points():
    if len(self.all_points) == 0:
      self._loadFrameData()
    return self.all_points

  def get_points(self):
    if len(self.points) == 0:
      self._loadFrameData()
    return self.points

  def _loadFrameData(self):
    print("Loading point cloud frame file: " + self.path)
    f = open(self.path)

    while f:
      line = f.readline()
      try: 
        idx,x,y,z = [100*float(v) for v in line.split(",")]
        # idx = int(idx)

        v = (x,y,z) #Vector(x,y,z) #c4d.Vector(x,y,z) # turn coordinates into c4d Vector object
        self.all_points.append(v) # add the vector to our list

        # create selection of relevant (non-zero) points
        if (x*y*z != 0):
          self.points.append(v)

      except ValueError:
        break

      # skip some points (if skip > 0)
      for i in range(self.skip):
        f.readline()

    f.close()
    print('PointCloudFrameFile#_loadFrameData - points read (total/active): {0}/{1}'.format(str(len(self.all_points)), str(len(self.points))))
# end of class PointCloudFrameFile


class PointCloudLoaderPanel(bpy.types.Panel):
    """Creates a Point Cloud Loader Panel in the Object properties window"""
    bl_label = "Point Cloud Loader"
    bl_idname = "OBJECT_PT_point_cloud_loader"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"


    def draw(self, context):
        layout = self.layout

        obj = context.object
        config = obj.pointCloudLoaderConfig

        row = layout.row()
        row.label(text="Active object is: " + obj.name)
        row = layout.row()
        row.prop(config, "enabled")
        row = layout.row()
        row.prop(config, "fileName")
        row = layout.row()
        row.prop(config, "skipPoints")
        row = layout.row()
        row.prop(config, "numFiles")
        row = layout.row()
        row.prop(config, "frameRatio")
# end of class PointCloudLoaderPanel


class PointCloudLoaderConfig(bpy.types.PropertyGroup):
    @classmethod
    def register(cls):
        bpy.types.Object.pointCloudLoaderConfig = bpy.props.PointerProperty(
            name="Point Cloud Loader Config",
            description="Object-specific Point Cloud Loader properties",
            type=cls)
     
        # Add in the properties
        cls.enabled = bpy.props.BoolProperty(name="enabled", default=False, description="Enable point cloud for this object")
        cls.fileName = bpy.props.StringProperty(name="Data Files", default="pointCloudData/frame%d.txt")
        cls.skipPoints = bpy.props.IntProperty(name="Skip Points", default=0, soft_min=0)
        cls.numFiles = bpy.props.IntProperty(name="Number of files", default=100, soft_min=0)
        cls.frameRatio = bpy.props.FloatProperty(name="Frame ratio", default=1.0, soft_min=0.0, description="Point cloud frame / blender frame ratio")

    @classmethod
    def unregister(cls):
        del bpy.types.Object.pointCloudLoaderConfig
# end of class PointCloudLoaderConfig


# Blender addon stuff, (un-)registerers and events handlers
@persistent
def frameHandler(scene):
    PointCloudLoader(scene=scene).loadFrame()

def register():
    bpy.utils.register_module(__name__)
    bpy.app.handlers.frame_change_pre.append(frameHandler)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.app.handlers.frame_change_pre.remove(frameHandler)

if __name__ == "__main__":
    register()
